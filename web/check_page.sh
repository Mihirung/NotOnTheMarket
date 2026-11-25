#!/bin/bash
# Serve a built site folder on this machine and load it in a headless browser (check_page.js).
#   bash web/check_page.sh research/outputs/site5 [screenshot.png]
# The folder holds index.html (web/build.py) beside the site's files. Exit 0 and a last line of [] is a clean run.
DIR=${1:?the folder holding index.html}
PORT=${PORT:-8765}
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$DIR" > /dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null' EXIT
sleep 2
node "$(dirname "$0")/check_page.js" "http://127.0.0.1:$PORT/index.html" "${2:-}"
