#!/bin/bash
# The live site's refresh. Run from anywhere; about an hour.
#
#   bash research/refresh.sh
#
# 1. Notices: every bankruptcy order and deceased-estate notice published since a week before the latest one held.
#    The Gazette's robots.txt asks for 10 seconds between requests; gazette_list.py waits 11, makes one request
#    at a time and reads only the search listing. Skipped if another download of notices is running.
# 2. Sales: the Land Registry's yearly files for this year and last, if it has reissued them since they were read
#    (it does so near the end of each month).
# 3. Every owned home scored again: on the first of the month after the sale records end, with the notices
#    published to today (export_site_v5.py live), and the site's files written.
#
# Run it weekly: the notices change every day, and read once a year they add less than half of what they add
# read as they appear (outputs/signals/NOTICE_MONTHLY.md); the sales change monthly. Building the page (web/build.py) and publishing
# it are separate steps. A step that fails stops the run, except the notices: the site is then refreshed without
# the newest ones and the log says so.
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=research/src
CACHE=research/outputs/site5_cache
LOG=${REFRESH_LOG:-$CACHE/refresh.log}
mkdir -p "$CACHE"
step() { echo "=== $1 $(date -u +%F_%T)" | tee -a "$LOG"; }
run() { "$@" >> "$LOG" 2>&1 || { echo "FAILED: $*" | tee -a "$LOG"; exit 1; }; }

step "notices"
if pgrep -f "gazette_list.py" > /dev/null; then
  echo "another download of notices is running; reading what is on disk" | tee -a "$LOG"
else
  for pair in "gazette deceased" "gazette_bankruptcy bankruptcy"; do
    set -- $pair
    python research/src/gazette_list.py research/data/$1 $2 --since auto >> "$LOG" 2>&1 \
      || echo "NOTICES NOT READ ($2): the site is refreshed without the newest ones" | tee -a "$LOG"
  done
fi
step "sales"
run python research/src/live_sales.py
step "score every owned home"
run python research/src/export_site_v5.py live research/outputs/lab/model_deploy.txt research/outputs/lab/lab_deploy.json \
    $CACHE research/outputs/lab/lab_second_notice.json
step "export the site"
run python research/src/export_site_v5.py export $CACHE research/data/geo_postcode.parquet \
    research/outputs/national research/outputs/lab research/outputs/site5
run python research/src/export_travel.py research/outputs/site5
step "refresh finished"
grep -E "^live:|scored homes have a notice|owned homes scored|NOT READ|nothing new|listed, " "$LOG" | tail -8
