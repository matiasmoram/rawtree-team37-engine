"""Tiny RawTree client: q(sql) -> list of dict rows."""
import os, json, requests
from pathlib import Path
for line in (Path(__file__).parent / ".env").read_text().splitlines():
    k, _, v = line.partition("="); os.environ.setdefault(k.strip(), v.strip())
API = "https://api.rawtree.com"; TEAM = os.environ["TEAM_ID"]
http = requests.Session(); http.headers["Authorization"] = f"Bearer {os.environ['RAWTREE_API_KEY']}"
def q(sql, timeout=600):
    r = http.post(f"{API}/v1/query", json={"sql": sql}, timeout=timeout)
    if r.status_code != 200: raise RuntimeError(r.text[:600])
    return r.json()["data"]
if __name__ == "__main__":
    import sys
    for row in q(sys.argv[1]): print(json.dumps(row, ensure_ascii=False))
