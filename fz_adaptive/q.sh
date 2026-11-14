#!/bin/bash
# usage: ./q.sh "SQL"
set -a; source "$(dirname "$0")/.env"; set +a
curl -s https://api.rawtree.com/v1/query -H "Authorization: Bearer $RAWTREE_API_KEY" -H 'Content-Type: application/json' -d "$(python3 -c 'import json,sys; print(json.dumps({"sql":sys.argv[1]}))' "$1")"
