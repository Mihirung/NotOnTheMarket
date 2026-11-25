#!/bin/bash
# The live site's refresh. Run from anywhere; about an hour.
#
#   bash research/refresh.sh
#
# 1. Notices: every notice of the kinds the model reads, published since a week before the latest one held.
#    The later-sales model reads deceased-estate notices only (bankruptcy orders failed its test), so only
#    those are fetched: nothing is collected about living people that the site does not use.
#    The Gazette's robots.txt asks for 10 seconds between requests; gazette_list.py waits 11, makes one request
#    at a time and reads only the search listing. Skipped if another download of notices is running.
# 2. Sales: the Land Registry's yearly files for this year and last, if it has reissued them since they were read
#    (it does so near the end of each month).
# 3. Energy certificates: this year's file again, about once a month (epc_fetch.py refresh). Needs EPC_TOKEN_FILE,
#    a file outside the repository holding the service's token; without it the certificates on disk are used.
# 4. Every owned home scored again: on the first of the month after the sale records end, with the notices
#    published to today (export_site_v5.py live), and the site's files written. MODEL picks the model: "late"
#    (the default: homes likely to sell and not yet on the market, with certificates) or "year" (a sale in the
#    next twelve months).
#
# Run it weekly: the notices change every day, and read once a year they add less than half of what they add
# read as they appear (outputs/signals/NOTICE_MONTHLY.md); the sales change monthly. Building the page (web/build.py) and publishing
# it are separate steps. A step that fails stops the run, except the notices: the site is then refreshed without
# the newest ones and the log says so.
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=research/src
# MEMORY_CAP_GB: a job that outgrows it stops with an error instead of starving everything else on the machine
[ -n "${MEMORY_CAP_GB:-}" ] && ulimit -v $((MEMORY_CAP_GB * 1024 * 1024))
CACHE=research/outputs/site5_cache
LOG=${REFRESH_LOG:-$CACHE/refresh.log}
mkdir -p "$CACHE"
step() { echo "=== $1 $(date -u +%F_%T)" | tee -a "$LOG"; }
run() { "$@" >> "$LOG" 2>&1 || { echo "FAILED: $*" | tee -a "$LOG"; exit 1; }; }

LAB=research/outputs/lab
if [ "${MODEL:-late}" = late ]; then TAG=_late; else TAG=; fi
KINDS=$(python -c "import json; print(' '.join(json.load(open('$LAB/lab_second_notice$TAG.json'))['kinds']))")
step "notices ($KINDS)"
if pgrep -f "gazette_list.py" > /dev/null; then
  echo "another download of notices is running; reading what is on disk" | tee -a "$LOG"
else
  for k in $KINDS; do
    if [ "$k" = dec ]; then set -- gazette deceased; else set -- gazette_bankruptcy bankruptcy; fi
    python research/src/gazette_list.py research/data/$1 $2 --since auto >> "$LOG" 2>&1 \
      || echo "NOTICES NOT READ ($2): the site is refreshed without the newest ones" | tee -a "$LOG"
  done
fi
step "sales"
run python research/src/live_sales.py
step "certificates"
if [ -n "${EPC_TOKEN_FILE:-}" ] && [ -f "$EPC_TOKEN_FILE" ]; then
  python research/src/epc_fetch.py refresh >> "$LOG" 2>&1 || echo "CERTIFICATES NOT READ: those on disk are used" | tee -a "$LOG"
else
  echo "no certificate token (EPC_TOKEN_FILE): the certificates on disk are used" | tee -a "$LOG"
fi
step "score every owned home"
run python research/src/export_site_v5.py live $LAB/model_deploy$TAG.txt $LAB/lab_deploy$TAG.json $CACHE $LAB/lab_second_notice$TAG.json
step "export the site"
run python research/src/export_site_v5.py export $CACHE research/data/geo_postcode.parquet \
    research/outputs/national research/outputs/lab research/outputs/site5
run python research/src/export_travel.py research/outputs/site5
step "refresh finished"
grep -E "^live:|scored homes have a notice|owned homes scored|NOT READ|nothing new|no certificate token|listed, " "$LOG" | tail -10
