"""Tiny synthetic frames for the thompson tests (no network)."""
import pandas as pd

CATS = ["A", "B", "C"]


def frames(n_per_cat: int = 10):
    rows = []
    for c in CATS:
        for k in range(n_per_cat):
            sub = f"{c}{k % 2}"  # two subcategories per category
            rows.append(dict(product_id=f"p_{c}{k}", category=c, subcategory=sub, brand="x",
                             price=float(5 + 10 * k), is_active=True, created_at="2026-01-01"))
    catalog = pd.DataFrame(rows)
    updates = pd.DataFrame(columns=["ts", "change", "product_id", "category", "subcategory", "brand", "price"])
    purchases = pd.DataFrame([dict(user_id="u1", product_id="p_A0", ts="2026-11-01 10:00:00")])
    user_cat = pd.DataFrame([dict(user_id="u1", category="A", pre=1, v=10, c=1, p=1, spend=10.0),
                             dict(user_id="u1", category="B", pre=1, v=5, c=0, p=0, spend=0.0)])
    item_stats = pd.DataFrame([dict(product_id=p, pre=1, v=100, c=10, p=k % 10, buyers=1)
                               for k, p in enumerate(catalog.product_id)])
    coview = pd.DataFrame([dict(p="p_A0", q="p_B1", n=5), dict(p="p_A0", q="p_C2", n=3)])
    return catalog, updates, purchases, user_cat, item_stats, coview


def state():
    from recsys.thompson.state import LiveState
    return LiveState.from_frames(*frames())
