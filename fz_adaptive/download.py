"""Download history from RawTree into local parquet files.
Sessions: raw rows per day (newest first). Events: aggregated inside RawTree (SQL) to keep transfers small."""
import sys, time, pandas as pd
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from q import q
D = Path(__file__).parent / "data"
days = list(pd.date_range("2026-09-15", "2026-11-14").strftime("%Y-%m-%d"))[::-1]

def retry(f):
    def g(*a):
        for i in range(6):
            try: return f(*a)
            except Exception as e: print("retry", a, str(e)[:200], flush=True); time.sleep(3)
    return g

@retry
def sessions(day):
    f = D / f"se_{day}.parquet"
    if f.exists(): return
    rows = q(f"""SELECT request_id::String rid, toUnixTimestamp64Milli(ts::DateTime64(3)) t, user_id::String u,
        context.device::String d, context.region::String r, context.page::String pg,
        arrayMap(x->x.product_id::String, recent_views::Array(Dynamic)) rv, shown, propensity,
        ifNull(clicked::String,'') clicked, ifNull(purchased::String,'') purchased
        FROM shop.history_sessions WHERE ts::DateTime64(3) >= '{day} 00:00:00' AND ts::DateTime64(3) < '{day} 00:00:00'::DateTime + INTERVAL 1 DAY""")
    pd.DataFrame(rows).to_parquet(f); print("se", day, len(rows), flush=True)

@retry
def agg(name, sql):
    f = D / f"{name}.parquet"
    if f.exists(): return
    t = time.time(); rows = q(sql); pd.DataFrame(rows).to_parquet(f); print(name, len(rows), round(time.time() - t), flush=True)

EV = "(SELECT event_type::String e, user_id::String u, product_id::String p, price_eur::Float64 price, device::String d, region::String r, ts FROM shop.history_events)"
AGGS = {
 # product popularity: views / carts / purchases, overall and in the last 7 days
 "prod_stats": f"""SELECT p, countIf(e='view') v, countIf(e='add_to_cart') c, countIf(e='purchase') b,
     countIf(e='view' AND ts>='2026-11-07 00:00:00') v7, countIf(e='purchase' AND ts>='2026-11-07 00:00:00') b7, avg(price) price FROM {EV} GROUP BY p""",
 # product x device and product x region purchase/view counts are too wide; use category-level context instead
 "ctx_stats": f"""SELECT d, r, c.subcategory::String sub, countIf(e='view') v, countIf(e='purchase') b
     FROM {EV} x INNER JOIN shop.catalog c ON c.product_id::String = x.p GROUP BY d, r, sub""",
 # user taste profile: counts per subcategory and per brand, plus mean price paid/viewed
 "user_sub": f"""SELECT u, c.subcategory::String sub, countIf(e='view') v, countIf(e='add_to_cart') c, countIf(e='purchase') b
     FROM {EV} x INNER JOIN shop.catalog c ON c.product_id::String = x.p GROUP BY u, sub""",
 "user_stats": f"""SELECT u, count() n, countIf(e='purchase') b, avg(log(price)) lp, stddevPop(log(price)) sp,
     avgIf(log(price), e='purchase') lpb, any(d) dev, any(r) reg, uniq(d) nd, uniq(r) nr FROM {EV} GROUP BY u""",
 "user_bought": f"""SELECT u, groupUniqArray(p) ps FROM {EV} WHERE e='purchase' GROUP BY u""",
}

ATTRS = ["a sporty style","a family-size format","a luxury feel","organic ingredients","a minimalist design","built for professionals",
 "wireless connectivity","bold colours","designed for kids","premium materials","smart app control","whisper-quiet operation","a vintage look",
 "made from recycled materials","great value for money","a travel-ready build","extra durability","a waterproof shell","a handmade finish","lightweight"]
for part in range(4):
    # user x brand counts, in 4 hash slices to stay under the 100 MiB result limit
    AGGS[f"user_brand_{part}"] = f"""SELECT u, c.brand::String br, countIf(e='view') v, countIf(e='purchase') b
     FROM {EV} x INNER JOIN shop.catalog c ON c.product_id::String = x.p WHERE cityHash64(u) % 4 = {part} GROUP BY u, br"""
# user x description-attribute counts: the attribute phrases are matched in SQL on the product description
AGGS["user_attr"] = "SELECT u, " + ", ".join(
    f"countIf(e='view' AND position(c.description::String, '{a}')>0) v{i}, countIf(e='purchase' AND position(c.description::String, '{a}')>0) b{i}"
    for i, a in enumerate(ATTRS)) + f" FROM {EV} x INNER JOIN shop.catalog c ON c.product_id::String = x.p GROUP BY u"
for part in range(4):
    # user x product pairs the shopper added to cart: first cart time, first purchase time (0 = never bought)
    AGGS[f"user_cart_{part}"] = f"""SELECT u, p, toUnixTimestamp(minIf(ts::DateTime64(3), e='add_to_cart')) tc,
     toUnixTimestamp(minIf(ts::DateTime64(3), e='purchase')) tb, countIf(e='add_to_cart') nc
     FROM {EV} WHERE e != 'view' AND cityHash64(u) % 4 = {part} GROUP BY u, p HAVING nc > 0"""
if __name__ == "__main__":
    what = sys.argv[1]
    if what == "se":
        with ThreadPoolExecutor(3) as ex: list(ex.map(sessions, days[:int(sys.argv[2])]))
    else:
        for k, s in AGGS.items(): agg(k, s)
    print("done", what)
