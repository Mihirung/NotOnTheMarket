"""Energy certificates for every home in England and Wales, without the address fields.

The government's energy certificate data (get-energy-performance-data.communities.gov.uk)
is one zip of yearly CSV files, about 8 GB. It is read here as a stream, straight from
the download, and only the columns below are kept, so it never has to fit on disk.

Licence. Everything in the data is under the Open Government Licence except the address
and postcode fields, which Ordnance Survey and Royal Mail restrict to energy-efficiency
purposes. Those fields are never read into the output here. A certificate is placed by its
UPRN (the property reference number, which is open), and the UPRN is placed in a postcode
with the ONS UPRN Directory (also open).

The bearer token comes from the EPC_TOKEN_FILE environment variable (a file outside the
repository) and is never printed or written anywhere else.

    EPC_TOKEN_FILE=<file> python epc_fetch.py columns        the files in the zip and their columns
    EPC_TOKEN_FILE=<file> python epc_fetch.py fetch [years]  writes research/data/epc/certificates_<year>.parquet
    EPC_TOKEN_FILE=<file> python epc_fetch.py refresh        this year's file again (and last year's early in the year),
                                                             unless it was read in the last 20 days: the service adds a
                                                             month of certificates at a time
"""
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

API = "https://api.get-energy-performance-data.communities.gov.uk/api/files/domestic/csv"
OUT = Path("research/data/epc")
CHUNK = 32 * 1024 * 1024
# wanted columns, by the names the files might use for them (matched without case, spaces or underscores)
WANT = {"uprn": ["uprn"], "lodged": ["lodgementdate", "registrationdate", "lodgementdatetime"],
        "inspected": ["inspectiondate", "assessmentdate"], "transaction": ["transactiontype"], "tenure": ["tenure"],
        "ptype": ["propertytype"], "form": ["builtform"], "area": ["totalfloorarea"], "rooms": ["numberhabitablerooms"],
        "age": ["constructionageband"], "score": ["currentenergyefficiency"], "rating": ["currentenergyrating"]}
BANNED = ("address", "postcode", "town", "posttown")          # never read: restricted address data


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def file_url():
    """A fresh, short-lived link to the zip (the API answers with a redirect to it)."""
    token = Path(os.environ["EPC_TOKEN_FILE"]).read_text().strip()
    req = urllib.request.Request(API, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    try:
        urllib.request.build_opener(NoRedirect).open(req, timeout=60)
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307) and e.headers.get("Location"):
            return e.headers["Location"]
        raise
    raise SystemExit("the API did not answer with a link to the file")


class RangeFile(io.RawIOBase):
    """The remote zip as a seekable file: bytes are fetched in large ranges as they are asked for."""

    def __init__(self):
        self.url = file_url(); self.pos = 0; self.buf = b""; self.buf_at = 0; self.fetched = 0
        self.size = int(self._open(0, 0).headers["Content-Range"].rsplit("/", 1)[-1])

    def _open(self, a, b):
        for attempt in range(6):
            try:
                req = urllib.request.Request(self.url, headers={"Range": f"bytes={a}-{b}"})
                return urllib.request.urlopen(req, timeout=120)
            except urllib.error.HTTPError as e:
                if e.code in (400, 401, 403):                 # the link has expired: ask for a new one
                    self.url = file_url()
                else:
                    time.sleep(5 * 2 ** attempt)
            except Exception:                                 # noqa: BLE001  (network trouble)
                time.sleep(5 * 2 ** attempt)
        raise SystemExit("could not read the file")

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self.size + off
        return self.pos

    def readinto(self, b):
        n = len(b)
        if not (self.buf_at <= self.pos < self.buf_at + len(self.buf)):
            a = self.pos; e = min(self.size, a + max(CHUNK, n)) - 1
            if a > e:
                return 0
            for attempt in range(6):
                try:
                    self.buf = self._open(a, e).read(); break
                except Exception:                             # noqa: BLE001
                    time.sleep(5 * 2 ** attempt)
            self.buf_at = a; self.fetched += len(self.buf)
        o = self.pos - self.buf_at
        chunk = self.buf[o:o + n]
        b[:len(chunk)] = chunk
        self.pos += len(chunk)
        return len(chunk)


def norm(c):
    return c.lower().replace("_", "").replace(" ", "").replace("-", "")


def pick(header):
    """Map our names to the file's columns; address columns are never among them."""
    by = {norm(c): c for c in header}
    use = {}
    for k, names in WANT.items():
        for nm in names:
            if nm in by:
                use[k] = by[nm]; break
    assert not any(b in norm(c) for c in use.values() for b in BANNED)
    return use


def columns():
    z = zipfile.ZipFile(io.BufferedReader(RangeFile(), buffer_size=1024 * 1024))
    for i in z.infolist():
        print(f"{i.filename}  {i.file_size / 1e6:,.0f} MB")
    first = [i for i in z.infolist() if i.filename.lower().endswith(".csv")][0]
    with z.open(first) as f:
        header = f.readline().decode("utf-8", "replace").strip().split(",")
    print(len(header), "columns:", [c for c in header if not any(b in norm(c) for b in BANNED)])
    print("kept:", pick([c.strip('"') for c in header]))


def refresh():
    today = time.localtime()
    years = [str(today.tm_year)] + ([str(today.tm_year - 1)] if today.tm_mon <= 2 else [])
    stale = [y for y in years if not (OUT / f"certificates_{y}.parquet").exists()
             or time.time() - (OUT / f"certificates_{y}.parquet").stat().st_mtime > 20 * 86400]
    if not stale:
        print("nothing new: this year's certificates were read in the last 20 days", flush=True); return
    fetch(*stale, again=True)


def fetch(*years, again=False):
    """One parquet file per year of certificates, so a stopped run resumes at the next year. `again` reads a
    year that is already on disk afresh and replaces it."""
    OUT.mkdir(parents=True, exist_ok=True)
    rf = RangeFile()
    z = zipfile.ZipFile(io.BufferedReader(rf, buffer_size=1024 * 1024))
    members = sorted((i for i in z.infolist() if i.filename.lower().startswith("certificates-")), key=lambda i: i.filename)
    for i in members:
        year = i.filename.split("-")[1][:4]
        dest = OUT / f"certificates_{year}.parquet"
        if (years and year not in years) or (dest.exists() and not again):
            continue
        with z.open(i) as f:
            head = pd.read_csv(io.BytesIO(f.readline()), nrows=0).columns.tolist()
        use = pick(head)
        writer, total, tmp = None, 0, OUT / f"certificates_{year}.parquet.part"
        with z.open(i) as f:
            for t in pd.read_csv(f, usecols=list(use.values()), dtype=str, chunksize=500_000, on_bad_lines="skip"):
                t = t.rename(columns={v: k for k, v in use.items()})
                o = pd.DataFrame({"uprn": pd.to_numeric(t.uprn, errors="coerce")})
                o["lodged"] = pd.to_datetime(t.lodged.str.slice(0, 10), errors="coerce")
                o["inspected"] = pd.to_datetime(t.inspected.str.slice(0, 10), errors="coerce")
                for c in ("transaction", "tenure", "ptype", "form", "age", "rating"):
                    o[c] = t[c].astype("string")
                for c in ("area", "rooms", "score"):
                    o[c] = pd.to_numeric(t[c], errors="coerce").astype("float32")
                n_all = len(o)
                o = o.dropna(subset=["uprn", "lodged"])
                o["uprn"] = o.uprn.astype("int64")
                tb = pa.Table.from_pandas(o, preserve_index=False)
                if writer is None:
                    writer = pq.ParquetWriter(tmp, tb.schema, compression="zstd")
                writer.write_table(tb.cast(writer.schema))
                total += len(o)
        writer.close()
        tmp.rename(dest)
        print(f"{time.strftime('%T')} {year}: {total:,} certificates with a UPRN; {rf.fetched / 1e9:.1f} GB read", flush=True)
    print("finished", flush=True)


if __name__ == "__main__":
    {"columns": columns, "fetch": fetch, "refresh": refresh}[sys.argv[1]](*sys.argv[2:])
