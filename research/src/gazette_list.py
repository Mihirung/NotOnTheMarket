"""Deceased-estate and bankruptcy notices from The Gazette, read from its search listings.

The search listing gives a short extract of every notice, 100 to a page. For a
deceased-estate notice the extract is the address of the deceased (the date of
death is only on the notice itself). For a bankruptcy order it opens with the
person's name and then their address. The address and the day of publication
are all this project uses, so a whole year can be read in a few hundred
requests instead of one request per notice (gazette_fetch.py).

What is kept: the notice number, the day it was published, the address and the
postcode. Names are never stored:
the name that opens a bankruptcy extract is cut off in memory, and an extract
whose name cannot be cut off cleanly is dropped. The files stay in
research/data, outside the repository, like every other address-level file.

The Gazette's robots.txt asks for 10 seconds between requests; this script
waits 11, runs one request at a time, honours Retry-After and resumes where it
stopped. Only the search listing is read.

    python gazette_list.py <out_dir> <kind> <year> [<year> ...]     every notice published in those years
    python gazette_list.py <out_dir> <kind> --status

<kind> is deceased or bankruptcy; give each its own <out_dir>.

Writes <out_dir>/listing.jsonl (one notice per line) and listing_state.json.
"""
import calendar
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from gazette_fetch import KINDS, POSTCODE, SITE, get  # noqa: E402

PAGE = 100
TAGS = re.compile(r"<[^>]+>")
ADDRESS = re.compile(r"Address of Deceased\s*</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)


def clean(v):
    return re.sub(r"\s+", " ", html.unescape(TAGS.sub(" ", v or ""))).strip()


def tidy(addr):
    return re.sub(r"\s+,", ",", addr).strip(" ,.")


def parse_deceased(e):
    c = e.get("content") or ""
    r = {}
    m = ADDRESS.search(c)
    if m:
        r["address"] = tidy(clean(m.group(1)))
        p = POSTCODE.search(r["address"].upper())
        if p:
            r["postcode"] = f"{p.group(1)} {p.group(2)}"
    return r


def parse_bankruptcy(e):
    """The extract reads 'Family , Forenames address , town , postcode ...' and the entry's title is
    'Forenames Family'. The name is cut off by matching it against the title; what is left, up to the
    first postcode, is the address."""
    t, title = clean(e.get("content")), clean(e.get("title"))
    low, toks = t.lower(), title.split()
    for k in range(1, len(toks)):
        pre = (" ".join(toks[k:]) + " , " + " ".join(toks[:k]) + " ").lower()
        if low.startswith(pre):
            body = t[len(pre):]
            p = POSTCODE.search(body.upper())
            if not p:
                return {}
            return {"address": tidy(body[:p.end()]), "postcode": f"{p.group(1)} {p.group(2)}"}
    return {}


PARSE = {"deceased": parse_deceased, "bankruptcy": parse_bankruptcy}


def months(years):
    for y in years:
        for m in range(12, 0, -1):
            yield f"{y}-{m:02d}", f"{y}-{m:02d}-01", f"{y}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"


def main():
    out, kind = Path(sys.argv[1]), sys.argv[2]
    assert kind in KINDS, f"kind must be one of {list(KINDS)}"
    section, code = KINDS[kind]
    f, st_f = out / "listing.jsonl", out / "listing_state.json"
    st = json.load(open(st_f)) if st_f.exists() else {"done": {}, "page": {}}
    if sys.argv[3] == "--status":
        n = sum(1 for _ in open(f)) if f.exists() else 0
        print(f"{n:,} notices held over {len(st['done'])} months; listed {sum(v['listed'] for v in st['done'].values()):,}, "
              f"with an address {sum(v['kept'] for v in st['done'].values()):,}")
        return
    out.mkdir(parents=True, exist_ok=True)
    seen = {json.loads(l)["id"] for l in open(f)} if f.exists() else set()
    with open(f, "a") as fh:
        for tag, d0, d1 in months([int(y) for y in sys.argv[3:]]):
            if tag in st["done"]:
                continue
            page = st["page"].get(tag, {"next": 1, "listed": 0, "kept": 0})
            while True:
                j = json.loads(get(f"{SITE}/{section}/notice/data.json?results-page-size={PAGE}&noticetypes={code}"
                                   f"&start-publish-date={d0}&end-publish-date={d1}&results-page={page['next']}"))
                ent = j.get("entry") or []
                ent = ent if isinstance(ent, list) else [ent]
                for e in ent:
                    i = e["id"].rsplit("/", 1)[-1]
                    if e.get("f:notice-code") != code or i in seen:
                        continue
                    seen.add(i); page["listed"] += 1
                    r = PARSE[kind](e)
                    if r.get("postcode"):
                        page["kept"] += 1
                        fh.write(json.dumps({"id": i, "published": (e.get("published") or "")[:10], **r}) + "\n")
                fh.flush()
                total = int(j.get("f:total", 0))
                last = page["next"] * PAGE >= total or not ent
                page["next"] += 1
                if last:
                    st["done"][tag] = {"listed": page["listed"], "kept": page["kept"], "total": total}
                    st["page"].pop(tag, None)
                else:
                    st["page"][tag] = page
                json.dump(st, open(st_f, "w"))
                if last:
                    print(f"{dt.datetime.now():%F %T} {kind} {tag}: {total:,} listed, {page['kept']:,} with an address", flush=True)
                    break
    print(f"{dt.datetime.now():%F %T} finished {kind} {' '.join(sys.argv[3:])}", flush=True)


if __name__ == "__main__":
    main()
