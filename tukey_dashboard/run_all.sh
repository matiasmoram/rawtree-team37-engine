#!/usr/bin/env bash
# Refresh every input and rebuild the Tukey dashboard (macOS / Linux twin of run_all.ps1).
# Usage: ./run_all.sh        (from anywhere; needs .venv with requirements.txt and RAWTREE_API_KEY in the repo's .env)
# While the final runs the public API hides the leaderboard: the final is then read from the RawTree DB only, and the
# official numbers are added by re-running this script once the API publishes them.
set -euo pipefail
export PYTHONIOENCODING=utf-8
root="$(cd "$(dirname "$0")" && pwd)"
py="$root/.venv/bin/python"
cd "$root"

echo "1/5 public leaderboard API (hourly + 15-min windows)"
"$py" pipeline/fetch_api.py --step 3600 --by model
"$py" pipeline/fetch_api.py --step 900 --by model
"$py" pipeline/build_api_tables.py

echo "2/5 RawTree DB, practice period (read-only SELECTs)"
"$py" pipeline/extract_db.py --period practice

if [ "$(date -u +%s)" -ge 1794733800 ]; then   # Sun 15 Nov 09:10 UTC = 10:10 CET
  echo "3/5 RawTree DB, final period"
  "$py" pipeline/extract_db.py --period final
else
  echo "3/5 final period not started yet: skipped"
fi

echo "4/5 derived dataset"
"$py" pipeline/build_dataset.py

echo "5/5 render (offline single file + CDN variant)"
"$py" pipeline/render.py
"$py" pipeline/render.py --cdn
echo "Done: $root/dist/index.html  ·  Shiny: $py -m shiny run app/app.py --port 8000"
