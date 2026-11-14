import sys, time
sys.path.insert(0, ".")
from engine.rt import RawTree
rt = RawTree(timeout=600)
sql = """
SELECT p, q, w FROM (
  SELECT a.pid AS p, b.pid AS q, sum(1 / (1 + abs(dateDiff('second', a.t, b.t)) / 600)) AS w
  FROM (SELECT session_id::String AS s, product_id::String AS pid, min(ts::DateTime64(3)) AS t FROM shop.history_events WHERE event_type = 'view' GROUP BY s, pid) AS a
  INNER JOIN (SELECT session_id::String AS s, product_id::String AS pid, min(ts::DateTime64(3)) AS t FROM shop.history_events WHERE event_type = 'view' GROUP BY s, pid) AS b ON a.s = b.s
  WHERE a.pid != b.pid
  GROUP BY p, q
) ORDER BY p, w DESC LIMIT 40 BY p
SETTINGS max_execution_time = 300
"""
t = time.time()
try:
    rows = rt.query(sql)
    print("rows", len(rows), "secs", round(time.time() - t, 1), rows[:3])
except Exception as e:
    print("ERR", round(time.time() - t, 1), str(e)[:600])
