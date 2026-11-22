"""Planning applications for a sample of council areas, from UK PlanIt.

PlanIt (planit.org.uk) gathers the planning registers of UK councils. It is
free and run by one person, and asks bulk users to:
  * run overnight, 18:00 to 06:00 UK time,
  * leave at least 60 seconds between requests and honour Retry-After,
  * make no more than about 300 requests a day,
  * put an identifier with a contact email in the User-Agent.
This script keeps to all four. The contact address is read from the
PLANIT_CONTACT environment variable and is never written to disk or the
repository. It runs until every unit of work is done, sleeping through the
day, and resumes where it stopped.

Each unit of work is one council area and one span of years. Only small
applications are fetched (householder and similar; PlanIt's 'Small' size)
of the types that touch a home: full, outline, heritage (listed building
and conservation consents), amendments and other. Discharges of
conditions, adverts, telecoms and tree works are left out.

    PLANIT_CONTACT=<email> python planit_fetch.py <out_dir> [areas...]
    python planit_fetch.py <out_dir> --status
"""
import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://www.planit.org.uk/api"
GAP_S = 65                                   # seconds between requests (PlanIt asks for at least 60)
DAILY_CAP = 290                              # requests per night (PlanIt asks for about 300 at most)
WINDOW = (18, 6)                             # UK hours in which bulk use is welcome
PG_SZ = 2500                                 # records per page; a page must stay under PlanIt's 1,000 kB
YEARS = [(2003, 2006), (2007, 2009), (2010, 2012), (2013, 2015), (2016, 2017), (2018, 2019)]
SELECT = ("name,area_name,uid,address,postcode,description,app_type,app_size,app_state,start_date,"
          "decided_date,location_x,location_y,atype:other_fields->application_type")
# Council areas in the order they are fetched: the four cities with house-level views first, then a spread
# across regions, sizes and kinds of place. Names are PlanIt's short area names.
AREAS = ["Exeter", "Bath", "Bristol", "Plymouth", "Cheltenham", "Brighton", "York", "Cambridge", "Norwich",
         "Canterbury", "Guildford", "Reading", "Trafford", "Stockport", "Nottingham", "Cardiff", "Newcastle",
         "Harrogate", "Richmond", "Wandsworth", "Barnet", "Leeds", "Cornwall", "Wiltshire"]


def uk_hour():
    """The hour on a UK clock (GMT in winter, BST in summer)."""
    now = dt.datetime.now(dt.timezone.utc)
    y = now.year                                                     # BST: last Sunday of March to last Sunday of October, 01:00 UTC
    last_sun = lambda m: max(dt.datetime(y, m, d, 1, tzinfo=dt.timezone.utc) for d in range(25, 32)
                             if dt.date(y, m, d).weekday() == 6)
    return (now + dt.timedelta(hours=1 if last_sun(3) <= now < last_sun(10) else 0)).hour


def in_window():
    h = uk_hour()
    return h >= WINDOW[0] or h < WINDOW[1]


class State:
    def __init__(self, out):
        self.path = Path(out) / "state.json"
        self.s = json.load(open(self.path)) if self.path.exists() else {"done": {}, "requests": {}, "areas": {}}

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        json.dump(self.s, open(tmp, "w"), indent=1)
        tmp.replace(self.path)

    def night(self):
        """Requests are counted per night: a night runs from 12:00 to 12:00."""
        n = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)
        return n.strftime("%Y-%m-%d")

    def used(self):
        return self.s["requests"].get(self.night(), 0)

    def count(self):
        self.s["requests"][self.night()] = self.used() + 1
        self.save()


class Client:
    def __init__(self, contact, state):
        self.ua = f"QuietMarketResearch/0.1 (housing research, overnight bulk per PlanIt FAQ; contact {contact})"
        self.state, self.last = state, 0.0

    def wait_turn(self):
        while True:
            if not in_window():
                time.sleep(300); continue
            if self.state.used() >= DAILY_CAP:
                time.sleep(600); continue
            gap = self.last + GAP_S - time.time()
            if gap > 0:
                time.sleep(gap); continue
            return

    def get(self, path, params):
        url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
        backoff = 120
        while True:
            self.wait_turn()
            self.last = time.time(); self.state.count()
            req = urllib.request.Request(url, headers={"User-Agent": self.ua, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    body = r.read()
                return json.loads(body), len(body)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    ra = e.headers.get("Retry-After")
                    wait = int(ra) if ra and ra.isdigit() else backoff
                    log(f"429 rate limited; waiting {wait}s"); time.sleep(wait); backoff = min(backoff * 2, 3600)
                    continue
                if e.code == 403:
                    log("403 forbidden: PlanIt has blocked this client. Stopping."); sys.exit(2)
                msg = e.read()[:300]
                log(f"HTTP {e.code} for {url}: {msg!r}")
                return {"error": e.code, "message": msg.decode("utf-8", "replace")}, 0
            except Exception as e:                 # network trouble: wait and try again
                log(f"request failed: {e!r}; retrying in {backoff}s"); time.sleep(backoff); backoff = min(backoff * 2, 3600)


def log(msg):
    print(f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def resolve_areas(cl, st, wanted):
    """PlanIt's own short names for the wanted areas (one request, kept)."""
    if not st.s["areas"]:
        d, _ = cl.get("areas/json", {"pg_sz": 1000, "select": "area_name,area_id,long_name,area_type,planning",
                                     "compress": "on"})
        st.s["areas"] = {r["area_name"]: r for r in d.get("records", [])}
        st.save()
        log(f"{len(st.s['areas'])} PlanIt areas listed")
    names = {n.lower(): n for n in st.s["areas"]}
    out = []
    for w in wanted:
        hit = names.get(w.lower()) or next((n for k, n in names.items() if k.startswith(w.lower())), None)
        if hit:
            out.append(hit)
        else:
            log(f"no PlanIt area called {w!r}; skipped")
    return out


def fetch(out, areas):
    out = Path(out); (out / "raw").mkdir(parents=True, exist_ok=True)
    contact = os.environ.get("PLANIT_CONTACT", "").strip()
    if "@" not in contact:
        sys.exit("set PLANIT_CONTACT to the contact email PlanIt asks for")
    st = State(out); cl = Client(contact, st)
    for area in resolve_areas(cl, st, areas):
        for y0, y1 in YEARS:
            unit = f"{area}|{y0}-{y1}"
            if unit in st.s["done"]:
                continue
            page, got, sz = 1, 0, PG_SZ
            while True:
                f = out / "raw" / f"{area}_{y0}_{y1}_{page:03d}.json.gz"
                if f.exists():
                    d = json.load(gzip.open(f))
                else:
                    d, nbytes = cl.get("applics/json", {
                        "auth": area, "start_date": f"{y0}-01-01", "end_date": f"{y1}-12-31", "app_size": "Small",
                        "app_type": "Full,Outline,Heritage,Amendment,Other", "select": SELECT, "sort": "name",
                        "pg_sz": sz, "page": page, "compress": "on"})
                    if "error" in d:
                        if sz > 500:                    # too big or too slow: smaller pages from the start of this unit
                            sz //= 2; page = 1; got = 0
                            for g in (out / "raw").glob(f"{area}_{y0}_{y1}_*.json.gz"):
                                g.unlink()
                            log(f"{unit}: error, retrying with pages of {sz}"); continue
                        log(f"{unit}: giving up on this unit"); break
                    json.dump(d, gzip.open(f, "wt"))
                    log(f"{unit} page {page}: {len(d.get('records', []))} of {d.get('total')} "
                        f"({nbytes / 1000:.0f} kB); {st.used()} requests tonight")
                got += len(d.get("records", []))
                total = d.get("total") or 0
                if not d.get("records") or got >= total:
                    break
                page += 1
            st.s["done"][unit] = got; st.save()
    log("every unit done")


def status(out):
    st = State(out)
    done = st.s["done"]
    print(f"{len(done)} units done, {sum(done.values()):,} applications; requests by night: {st.s['requests']}")
    by = {}
    for u, n in done.items():
        a = u.split("|")[0]; by[a] = by.get(a, 0) + n
    for a, n in by.items():
        print(f"  {a}: {n:,}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--status":
        status(sys.argv[1])
    else:
        fetch(sys.argv[1], sys.argv[2:] or AREAS)
