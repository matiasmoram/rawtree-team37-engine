"""Read-only query runner. Usage: python q.py <name> <sqlfile_or_->  ; logs every query to qlog.jsonl"""
import json, sys, time, pathlib
sys.path.insert(0, ".")
from engine.rt import RawTree
HERE = pathlib.Path(__file__).parent
FORBID = ("insert", "alter", "drop", "delete", "update", "create", "truncate", "optimize", "rename", "kill", "system", "grant")
def run(name, sql, rt=None, maxrows=50):
    low = sql.strip().lower()
    first = low.split()[0]
    assert first in ("select", "show", "describe", "desc", "with", "exists"), first
    rt = rt or RawTree(timeout=30)
    t = time.time()
    try:
        rows = rt.query(sql, timeout=30, retries=0)
        err = None
    except Exception as e:
        rows, err = [], str(e)[:600]
    dt = time.time() - t
    with open(HERE / "qlog.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"name": name, "sql": sql, "secs": round(dt, 2), "n": len(rows), "err": err}) + "\n")
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / f"{name}.json").write_text(json.dumps({"sql": sql, "err": err, "rows": rows}, indent=1, default=str), encoding="utf-8")
    print(f"## {name} ({dt:.1f}s, {len(rows)} rows){' ERR '+err if err else ''}")
    for r in rows[:maxrows]:
        print(json.dumps(r, default=str)[:700])
    return rows
if __name__ == "__main__":
    name = sys.argv[1]
    src = sys.argv[2]
    sql = sys.stdin.read() if src == "-" else pathlib.Path(src).read_text(encoding="utf-8")
    mx = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    run(name, sql, maxrows=mx)
