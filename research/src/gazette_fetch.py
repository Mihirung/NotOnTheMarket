"""Deceased-estate and bankruptcy notices from The Gazette, for a test of whether they predict a sale.

When someone dies, their executors usually publish a notice in The Gazette
(Trustee Act 1925, section 27) giving the address of the deceased and the
date of death. A home whose owner has died is very often sold within a year
or two. The notices are public and published under the Open Government
Licence.

Bankruptcy orders are published there too, with the address of the person
made bankrupt. A trustee in bankruptcy can sell the home to pay creditors.
These notices are about living people, so they are fetched only for a test
the owner of this project asked for, and using them beyond a test needs
legal review first.

What is kept: the notice number, the day it was published, the date of
death or of the order, and the address and postcode. Names, dates of birth
and occupations are never stored. The files stay in research/data, outside
the repository, like every other address-level file.

The Gazette's robots.txt asks for 10 seconds between requests; this script
waits 11, runs one request at a time, honours Retry-After and resumes where
it stopped. Only the search pages and the notice pages are read (the
linked-data views that robots.txt excludes are not).

    python gazette_fetch.py <out_dir> <kind> days <n_days> <year> [<year> ...]   sample whole publication days
    python gazette_fetch.py <out_dir> <kind> range <from> <to>                    every notice between two dates
    python gazette_fetch.py <out_dir> <kind> --status

<kind> is deceased or bankruptcy; give each its own <out_dir>.

Writes <out_dir>/notices.jsonl (one notice per line) and state.json.
"""
import datetime as dt
import html
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SITE = "https://www.thegazette.co.uk"
GAP_S = 11
UA = "research-client/1.0"
DD = re.compile(r'<dd about="this:([A-Za-z-]*[Dd]eceased[A-Za-z-]*?)(?:-(\d+))?"([^>]*)property="([^"]+)"([^>]*)>(.*?)</dd>', re.S)
KEEP = {"vcard:street-address": "a1", "vcard:extended-address": "a2", "vcard:locality": "town",
        "vcard:region": "county", "vcard:postal-code": "postcode", "vcard:adr": "address",
        "personal-legal:dateOfDeath": "died"}
POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b")
KINDS = {"deceased": ("wills-and-probate", "2903"), "bankruptcy": ("insolvency", "2503")}
ADDR = re.compile(r'data-gazettes="PersonAddress"[^>]*>\s*<span content="([^"]*)"[^>]*property="vcard:label"', re.S)
ORDER = re.compile(r'content="(\d{4}-\d{2}-\d{2})[^"]*"[^>]*property="insolvency:dateOfBankruptcyOrder"'
                   r'|property="insolvency:dateOfBankruptcyOrder"[^>]*content="(\d{4}-\d{2}-\d{2})', re.S)
PETITION = re.compile(r'content="([^"]*)"[^>]*property="insolvency:typeOfPetition"', re.S)
_last = [0.0]


def get(url):
    for attempt in range(8):
        wait = _last[0] + GAP_S - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                _last[0] = time.time()
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            _last[0] = time.time()
            if e.code == 404:
                return None
            ra = e.headers.get("Retry-After") if e.headers else None
            pause = int(ra) if ra and ra.isdigit() else 60 * 2 ** attempt
            print(f"{dt.datetime.now():%F %T} HTTP {e.code}; waiting {pause}s", flush=True)
            time.sleep(pause)
        except Exception as e:                       # noqa: BLE001  (network trouble: wait and try again)
            _last[0] = time.time()
            print(f"{dt.datetime.now():%F %T} request failed: {e!r}; waiting {60 * 2 ** attempt}s", flush=True)
            time.sleep(60 * 2 ** attempt)
    raise SystemExit("giving up after repeated failures")


def list_ids(d0, d1, kind="deceased"):
    """Notice numbers and publication days between two dates (inclusive). Names in the list are not kept."""
    section, code = KINDS[kind]
    out, page = [], 1
    while True:
        j = json.loads(get(f"{SITE}/{section}/notice/data.json?results-page-size=100&noticetypes={code}"
                           f"&start-publish-date={d0}&end-publish-date={d1}&results-page={page}"))
        ent = j.get("entry") or []
        ent = ent if isinstance(ent, list) else [ent]
        for e in ent:
            if e.get("f:notice-code") == code:
                out.append((e["id"].rsplit("/", 1)[-1], e.get("published", "")[:10]))
        if page * 100 >= int(j.get("f:total", 0)) or not ent:
            return out
        page += 1


def parse(page):
    """The edition, date of death and address of the deceased. The Gazette has used two layouts:
    the address in parts (street, town, postcode) or as one line."""
    r = {}
    m = re.search(r"Edition:</dt>\s*<dd[^>]*>(.*?)</dd>", page, re.S)
    r["edition"] = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""
    clean = lambda v: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", v))).strip()   # noqa: E731
    for _, n, pre, prop, post, val in DD.findall(page):
        k = KEEP.get(prop)
        if not k:
            continue
        if k == "died":
            d = re.search(r'(?:content|datetime)="(\d{4}-\d{2}-\d{2})"', pre + post + val)
            r[k] = d.group(1) if d else clean(val)
            continue
        if n and n != "1":                                    # a second address of the deceased: kept apart
            k = f"{k}_{n}"
        r[k] = clean(val)
    if "address" not in r and "a1" not in r:                  # the summary under the notice, as a last resort
        m = re.search(r"<dt>Address of Deceased</dt>\s*<dd>(.*?)</dd>", page, re.S)
        if m:
            r["address"] = clean(m.group(1))
    if "postcode" not in r and r.get("address"):
        m = POSTCODE.search(r["address"].upper())
        if m:
            r["postcode"] = f"{m.group(1)} {m.group(2)}"
    return r


def parse_bankruptcy(page):
    """The edition, the date of the order, who petitioned, and the first address given for the person."""
    r = {"edition": parse(page)["edition"]}
    m = ORDER.search(page)
    if m:
        r["ordered"] = m.group(1) or m.group(2)
    m = PETITION.search(page)
    if m:
        r["petition"] = html.unescape(m.group(1)).strip()[:12]
    a = ADDR.findall(page)
    if a:
        r["address"] = html.unescape(a[0]).strip()
        m = POSTCODE.search(r["address"].upper())
        if m:
            r["postcode"] = f"{m.group(1)} {m.group(2)}"
        r["n_addresses"] = len(a)
    return r


def run(out, todo, kind="deceased"):
    out.mkdir(parents=True, exist_ok=True)
    f = out / "notices.jsonl"
    done = {json.loads(l)["id"] for l in open(f)} if f.exists() else set()
    todo = [(i, d) for i, d in todo if i not in done]
    print(f"{dt.datetime.now():%F %T} {len(todo):,} notices to read, {len(done):,} already held; "
          f"about {len(todo) * GAP_S / 3600:.1f} hours", flush=True)
    with open(f, "a") as fh:
        for n, (i, d) in enumerate(todo, 1):
            page = get(f"{SITE}/notice/{i}")
            rec = {"id": i, "published": d, **((parse if kind == "deceased" else parse_bankruptcy)(page) if page else {"missing": True})}
            fh.write(json.dumps(rec) + "\n"); fh.flush()
            if n % 100 == 0:
                print(f"{dt.datetime.now():%F %T} {n:,} of {len(todo):,}", flush=True)
    print(f"{dt.datetime.now():%F %T} finished", flush=True)


def main():
    out, kind = Path(sys.argv[1]), sys.argv[2]
    assert kind in KINDS, f"kind must be one of {list(KINDS)}"
    sys.argv.pop(2)
    st_f = out / "state.json"
    st = json.load(open(st_f)) if st_f.exists() else {"lists": {}}
    if sys.argv[2] == "--status":
        f = out / "notices.jsonl"
        n = sum(1 for _ in open(f)) if f.exists() else 0
        print(f"{n:,} notices held; {sum(len(v) for v in st['lists'].values()):,} listed over {len(st['lists'])} spans")
        return
    out.mkdir(parents=True, exist_ok=True)
    if sys.argv[2] == "days":
        n_days, years = int(sys.argv[3]), [int(y) for y in sys.argv[4:]]
        rng = random.Random(7)
        spans = []
        for y in years:
            days = [dt.date(y, 1, 1) + dt.timedelta(k) for k in range(366) if (dt.date(y, 1, 1) + dt.timedelta(k)).year == y]
            days = [d for d in days if d.weekday() < 5]
            spans += [(str(d), str(d)) for d in sorted(rng.sample(days, n_days))]
    else:
        spans = [(sys.argv[3], sys.argv[4])]
    todo = []
    for d0, d1 in spans:
        k = f"{d0}..{d1}"
        if k not in st["lists"]:
            st["lists"][k] = list_ids(d0, d1, kind)
            json.dump(st, open(st_f, "w"))
            print(f"{dt.datetime.now():%F %T} {k}: {len(st['lists'][k])} notices", flush=True)
        todo += [tuple(x) for x in st["lists"][k]]
    run(out, todo, kind)


if __name__ == "__main__":
    main()
