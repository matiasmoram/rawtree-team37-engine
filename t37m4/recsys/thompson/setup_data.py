"""One-time download of the history caches the live state needs (read-only SQL, ~5-10 min).

    python -m recsys.thompson.setup_data
"""
from .. import data as D

if __name__ == "__main__":
    for name in ("purchases", "user_cat", "item_stats", "coview"):
        D.pull(name)
    print("caches ready in", D.DATA)
