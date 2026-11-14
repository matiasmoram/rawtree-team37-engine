#!/bin/bash
# Keeps the recommender alive unattended: restarts serve.py / learn.py if they exit, and keeps the Mac awake.
cd "$(dirname "$0")"
caffeinate -dimsu -w $$ &
while true; do
  pgrep -f "Python serve\.py$" >/dev/null || { echo "$(date +%T) starting serve" >> watchdog.log; touch serve.log; nohup .venv/bin/python serve.py >> serve.log 2>&1 & }
  # learn.py (retraining) is NOT kept running: it needs ~1.5 GB and this laptop has 8 GB. Run it by hand when wanted.
  # a hung server (no status line for 3 minutes) is killed so the next pass restarts it
  if [ -f serve.log ] && [ $(( $(date +%s) - $(stat -f %m serve.log) )) -gt 180 ]; then echo "$(date +%T) serve hung, killing" >> watchdog.log; pkill -f "Python serve\.py$"; fi
  sleep 10
done
