"""Inline the prototype's data into the page.

Usage: python web/build.py [data_json] [template] [out_html]
"""
import re
import sys
from pathlib import Path

here = Path(__file__).parent
data = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "demo_v4.json"
template = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "template.html"
out = Path(sys.argv[3]) if len(sys.argv) > 3 else here / "index.html"

html = template.read_text()
payload = data.read_text().replace("</", "<\\/")
html, n = re.subn(r"const DATA = .*?;\n", lambda m: "const DATA = " + payload + ";\n", html, count=1, flags=re.S)
assert n == 1, "data marker not found in template"
out.write_text(html)
print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
