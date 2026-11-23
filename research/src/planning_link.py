"""Planning applications, tidied, classified and joined to homes.

Three steps on the pages planit_fetch.py stored:

  1. Tidy. One row per application: council area, dates applied and
     decided, the decision (approved, refused, withdrawn, undecided), the
     address, postcode and position.
  2. Classify the job from its description. One application can be several
     jobs (a rear extension and a loft); the first in JOBS order is its main
     job.
  3. Join to homes. The sale records key a home on its postcode, house number
     or name, and flat (build_dataset.py). The same key is built from the
     application's address, so an application lands on the exact home whose
     sales we know. Applications whose address will not parse are kept with
     their postcode only.

Writes research/data/planning/applications.parquet.

Usage: python planning_link.py
"""
import gzip
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

RAW = Path("research/data/planning/raw")
OUT = Path("research/data/planning/applications.parquet")

JOBS = [
    ("new_home", r"(?:erection|construction|build\w*) of .{0,40}?(?:dwelling|house|bungalow|home)s?\b(?! extension)|"
                 r"new (?:dwelling|house|bungalow)s?|residential development|^(?:a |one |\d+ )?(?:detached |semi-detached )?"
                 r"(?:dwelling|bungalow|house)s?\b|redevelopment to provide .{0,30}(?:dwelling|house|flats)"),
    ("split", r"(?:conversion|convert|sub-?division|subdivide)\w* .{0,40}(?:into |to )(?:\w+ )?(?:self-contained )?(?:flats|apartments|"
              r"dwellings|units|maisonettes)|change of use .{0,60}(?:to|into) (?:\w+ )?(?:flats|hmo|house in multiple)"),
    ("basement", r"basement|lower ground floor extension"),
    ("two_storey", r"two[- ]stor(?:e)?y|double[- ]stor(?:e)?y|first[- ]floor (?:rear |side )?extension|"
                   r"2[- ]stor(?:e)?y"),
    ("wraparound", r"wrap[- ]?around"),
    ("loft", r"loft|dormer|hip[- ]to[- ]gable|roof extension|raise (?:the )?roof|mansard|rooflights?"),
    ("rear", r"rear extension|extension to (?:the )?rear|single[- ]stor(?:e)?y (?:rear )?extension|conservatory|orangery"),
    ("side", r"side extension|extension to (?:the )?side"),
    ("front", r"porch|front extension|extension to (?:the )?front|bay window"),
    ("garage", r"garage conversion|conver\w+ (?:of )?(?:the )?(?:existing )?(?:integral )?garage|garage into|"
               r"(?:replace|in place of) (?:the )?(?:integral )?garages?|garage to (?:provide|form)"),
    ("outbuilding", r"outbuilding|garden (?:room|studio|office|building)|summer ?house|annexe|annex\b|home office|"
                    r"detached (?:garage|gym|studio|single storey building)|cabin|log cabin|workshop|shed\b|garage\b"),
    ("extension", r"extension|extend"),
    ("listed", r"listed building consent|\blbc\b"),
    ("lawful", r"certificate of lawful|lawful development|lawfulness|prior approval|prior notification"),
    ("trees", r"\btree|\bt\d+\b|crown (?:lift|reduc|thin)|fell\b|pollard|hedge"),
    ("windows", r"window|door|cladding|render|solar|photovoltaic|heat pump|satellite|chimney|flue"),
    ("alterations", r"(?:external|internal) (?:and (?:internal|external) )?alterations|^alterations"),
    ("commercial", r"shop ?front|\bsign|advert|atm\b|class a\d|class b\d|class e\b|plant|air condition|condensing|"
                   r"telecom|mast\b|canopy|kiosk"),
    ("boundary", r"fence|wall\b|walls\b|gate|driveway|dropped kerb|hardstanding|hard standing|parking|crossover|vehicular access"),
    ("demolition", r"demoli"),
    ("change_of_use", r"change of use"),
]
JOB_RE = [(k, re.compile(p, re.I)) for k, p in JOBS]
# what the description says about the home itself: its era and its kind (factual record, no documents needed)
HINTS = [("georgian", r"georgian|regency"), ("victorian", r"victorian"), ("edwardian", r"edwardian"),
         ("interwar", r"19[23]0s|inter-?war"), ("postwar", r"19[5-7]0s|post-?war"),
         ("bungalow", r"bungalow"), ("cottage", r"cottage"), ("barn", r"\bbarn\b"), ("thatched", r"thatch"),
         ("farmhouse", r"farm ?house"), ("townhouse", r"town ?house"), ("listed_mention", r"listed building|grade (?:i|ii)")]
HINT_RE = [(k, re.compile(p, re.I)) for k, p in HINTS]
STATE = {"Permitted": "approved", "Conditions": "approved", "Rejected": "refused", "Withdrawn": "withdrawn",
         "Undecided": "undecided", "Referred": "other", "Unresolved": "other", "Other": "other"}
PC_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b")
SUB = re.compile(r"^(FLAT|APARTMENT|APT|UNIT|MAISONETTE|ROOM|STUDIO|BASEMENT FLAT|GROUND FLOOR FLAT|FIRST FLOOR FLAT|"
                 r"TOP FLOOR FLAT|GARDEN FLAT)\b\.?\s*([A-Z0-9]+)?", re.I)
NUM = re.compile(r"^(\d+[A-Z]?(?:\s*-\s*\d+[A-Z]?)?)\b", re.I)
NOT_HOME = re.compile(r"^(LAND|SITE|PLOT|GARAGES?|REAR OF|LAND AT|LAND ADJ|ADJACENT|ADJ|LAND TO|LAND REAR|PART OF|"
                      r"PROPOSED|LAND OFF|DEVELOPMENT SITE)\b", re.I)


EXT_WORDS = re.compile(r"extension|alteration|loft|dormer|porch|conservatory|garage conversion", re.I)


def jobs(desc):
    d = str(desc or "")
    hit = [k for k, r in JOB_RE if r.search(d)]
    if "new_home" in hit and EXT_WORDS.search(d) and not re.search(r"new (?:dwelling|house|bungalow)", d, re.I):
        hit.remove("new_home")                        # "erection of a rear extension to the dwelling" is an extension
    return hit


def parse_address(address, postcode):
    """(PAON, SAON) as the Price Paid Data would hold them, or None."""
    a = str(address or "").upper()
    pc = str(postcode or "").upper().strip()
    if pc:
        a = a.replace(pc, " ")
    a = PC_RE.sub(" ", a)
    parts = [p.strip(" .") for p in re.split(r",|\n", a) if p.strip(" .")]
    if not parts or NOT_HOME.match(parts[0]):
        return None
    saon = ""
    m = SUB.match(parts[0])
    if m:
        saon = re.sub(r"\s+", " ", m.group(0)).strip()
        rest = parts[0][m.end():].strip(" ,")
        parts = ([rest] if rest else []) + parts[1:]
        if not parts:
            return None
    m = NUM.match(parts[0])
    if m:
        return re.sub(r"\s+", "", m.group(1)), saon
    # a house name: the PPD holds it as the primary address, and any number on the next line goes with the street
    name = parts[0]
    if len(name) < 3 or len(parts) == 1 and re.search(r"\d", name) is None and " " not in name:
        return None
    return name, saon


STREET = re.compile(r"\b(ROAD|STREET|LANE|AVENUE|CLOSE|DRIVE|WAY|HILL|PLACE|CRESCENT|GARDENS|TERRACE|GROVE|PARK|"
                    r"COURT|SQUARE|WALK|ROW|MEWS|VIEW|RISE|GREEN|VALE|END|PARADE|BANK|MEADOWS?|FIELDS?|CROFT|ESTATE)\b")


def readings(address, postcode):
    """Every plausible (PAON, SAON) for an address, most likely first."""
    first = parse_address(address, postcode)
    out = [first] if first else []
    a = str(address or "").upper().replace(str(postcode or "").upper(), " ")
    a = PC_RE.sub(" ", a)
    parts = [p.strip(" .") for p in re.split(r",|\n", a) if p.strip(" .")]
    if parts and not NOT_HOME.match(parts[0]):
        words = parts[0].split()
        m = STREET.search(parts[0])
        stop = len(parts[0][:m.start()].split()) - 1 if m else len(words)   # the word before ROAD is the street name
        for k in range(min(stop, 6), 0, -1):          # house names written without commas: "ROSE COTTAGE MILL LANE"
            out.append((" ".join(words[:k]), ""))
        if len(parts) > 1:
            n2 = NUM.match(parts[1])
            if n2 and first and not NUM.match(first[0]):
                out.append((f"{first[0]}, {n2.group(1)}", first[1]))   # "ROSE COTTAGE, 12"
                out.append((n2.group(1), first[1]))
    seen, uniq = set(), []
    for r in out:
        if r not in seen:
            seen.add(r); uniq.append(r)
    return uniq


def key_of(pc, paon, saon):
    """The property key of build_dataset.py for (postcode, PAON, SAON)."""
    s = (pd.Series(pc, dtype="string").str.strip().str.upper() + "|" + pd.Series(paon, dtype="string").str.strip().str.upper()
         + "|" + pd.Series(saon, dtype="string").str.strip().str.upper())
    return pd.util.hash_array(s.to_numpy(dtype=object)).astype("int64")


def load_raw():
    rows = []
    for f in sorted(RAW.glob("*.json.gz")):
        d = json.load(gzip.open(f))
        rows += d.get("records", [])
    t = pd.DataFrame(rows)
    # an application can be listed under an old district, a new unitary and a joint planning service at once
    t = t.drop_duplicates("name")
    return t.drop_duplicates(["uid", "address"]) if {"uid", "address"} <= set(t.columns) else t


def main():
    t = load_raw()
    print(f"{len(t):,} applications from {t.area_name.nunique()} council areas", flush=True)
    t["state"] = t.app_state.map(STATE).fillna("other")
    t["start"] = pd.to_datetime(t.start_date, errors="coerce")
    t["decided"] = pd.to_datetime(t.decided_date, errors="coerce")
    J = [jobs(d) for d in t.description]
    t["job"] = [j[0] if j else "other" for j in J]
    for k, _ in JOBS:
        t[f"job_{k}"] = [k in j for j in J]
    for k, r in HINT_RE:
        t[f"hint_{k}"] = [bool(r.search(str(d or ""))) for d in t.description]
    pc = t.postcode.fillna("").str.upper().str.strip()
    tx = pd.read_parquet("research/data/transactions.parquet", columns=["key"])
    known = np.unique(tx.key.to_numpy())
    # every reading of every address, keyed; an application takes the first reading that is a home with sales
    R = [(i, r) for i, (a, p) in enumerate(zip(t.address, pc)) if len(p) >= 5 for r in readings(a, p)]
    ri = np.array([i for i, _ in R], dtype=np.int64)
    rk = key_of(pc.to_numpy()[ri], [r[0] for _, r in R], [r[1] for _, r in R]) if len(R) else np.array([], np.int64)
    hit = np.isin(rk, known)
    t["paon"] = None; t["saon"] = None
    t["key"] = pd.array([pd.NA] * len(t), dtype="Int64")
    t["on_sale_record"] = False
    first = pd.Series(range(len(ri))).groupby(ri).first()            # the most likely reading
    best = pd.Series(np.nonzero(hit)[0]).groupby(ri[hit]).first() if hit.any() else pd.Series(dtype=int)
    pick = first.copy(); pick.loc[best.index] = best.to_numpy()
    rows_ = pick.index.to_numpy(); sel = pick.to_numpy()
    t.loc[rows_, "paon"] = [R[j][1][0] for j in sel]
    t.loc[rows_, "saon"] = [R[j][1][1] for j in sel]
    t.loc[rows_, "key"] = rk[sel]
    t.loc[rows_, "on_sale_record"] = hit[sel]
    t["postcode"] = pc.where(pc.str.len() >= 5)
    keep = ["name", "area_name", "uid", "address", "postcode", "description", "app_type", "app_size", "state",
            "start", "decided", "location_x", "location_y", "atype", "job", "paon", "saon", "key", "on_sale_record"] \
        + [f"job_{k}" for k, _ in JOBS] + [f"hint_{k}" for k, _ in HINTS]
    t = t[[c for c in keep if c in t.columns]]
    t.to_parquet(OUT, index=False)
    by = t.groupby("area_name").agg(apps=("name", "size"), parsed=("key", lambda k: k.notna().mean()),
                                    on_record=("on_sale_record", "mean"))
    print(by.round(3).to_string())
    print("main job:", t.job.value_counts().head(15).to_dict())
    print("decisions:", t.state.value_counts().to_dict())


if __name__ == "__main__":
    main()
