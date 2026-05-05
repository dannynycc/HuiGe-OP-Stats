"""Backfill historical 2020-2023/05/04 from FinMind.

Bulk fetches OP 三大法人 (TXO) + FUT 三大法人 (per primary product) +
fut_price (TX) and writes into op_legal / fut_legal / fut_price tables.

Limitations (documented in README v0.10):
  - daynight always 'day' (FinMind has no day/night split for institutional);
  - 缺微台 (2022/03+ 部分)、小電、小金、個股期 — FinMind free tier;
  - fut_price 含日夜盤 (FinMind has trading_session for daily price).
"""
import sys, pathlib, argparse, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect
from app.scrapers import finmind


def run_op(start: str, end: str) -> int:
    rows = finmind.fetch_op_institutional(start, end)
    if not rows:
        print(f"  OP: 0 rows")
        return 0
    with connect() as con:
        for r in rows:
            con.execute("""
                INSERT OR REPLACE INTO op_legal
                (date, daynight, product, callput, role,
                 buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt,
                 oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt,
                 oi_net_lots, oi_net_amt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"], r["daynight"], r["product"], r["callput"], r["role"],
                r["buy_lots"], r["buy_amt"], r["sell_lots"], r["sell_amt"],
                r["net_lots"], r["net_amt"],
                r["oi_buy_lots"], r["oi_buy_amt"], r["oi_sell_lots"], r["oi_sell_amt"],
                r["oi_net_lots"], r["oi_net_amt"],
            ))
    print(f"  OP: {len(rows)} rows")
    return len(rows)


def run_fut(data_id: str, start: str, end: str) -> int:
    rows = finmind.fetch_fut_institutional(data_id, start, end)
    if not rows:
        print(f"  FUT {data_id}: 0 rows")
        return 0
    with connect() as con:
        for r in rows:
            con.execute("""
                INSERT OR REPLACE INTO fut_legal
                (date, daynight, product, role,
                 buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt,
                 oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt,
                 oi_net_lots, oi_net_amt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"], r["daynight"], r["product"], r["role"],
                r["buy_lots"], r["buy_amt"], r["sell_lots"], r["sell_amt"],
                r["net_lots"], r["net_amt"],
                r["oi_buy_lots"], r["oi_buy_amt"], r["oi_sell_lots"], r["oi_sell_amt"],
                r["oi_net_lots"], r["oi_net_amt"],
            ))
    print(f"  FUT {data_id}: {len(rows)} rows")
    return len(rows)


def run_fut_price(start: str, end: str) -> int:
    rows = finmind.fetch_fut_price_tx(start, end)
    if not rows:
        print(f"  FUT_PRICE: 0 rows")
        return 0
    with connect() as con:
        for r in rows:
            con.execute("""
                INSERT OR REPLACE INTO fut_price
                (date, contract, expiry, open_, high, low, close,
                 change_str, change_pct_str, ah_vol, day_vol, total_vol,
                 settle, oi, best_bid, best_ask)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["date"], r["contract"], r["expiry"],
                r["open_"], r["high"], r["low"], r["close"],
                r["change_str"], r["change_pct_str"],
                r["ah_vol"], r["day_vol"], r["total_vol"],
                r["settle"], r["oi"],
                r["best_bid"], r["best_ask"],
            ))
    print(f"  FUT_PRICE: {len(rows)} rows")
    return len(rows)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default="2020-01-02")
    p.add_argument("--to", dest="end", default="2023-05-04")
    p.add_argument("--chunk", type=int, default=180,
                   help="days per FinMind request (free tier rate-friendly)")
    p.add_argument("--products", default="TX,MTX,TE,TF",
                   help="comma-separated FinMind futures_id list")
    p.add_argument("--sleep", type=float, default=1.0,
                   help="seconds between requests (free-tier rate limit)")
    args = p.parse_args()

    import datetime as dt
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    # chunk into 180-day windows so each FinMind response stays small
    windows = []
    cur = start
    while cur <= end:
        nxt = min(cur + dt.timedelta(days=args.chunk - 1), end)
        windows.append((cur.isoformat(), nxt.isoformat()))
        cur = nxt + dt.timedelta(days=1)

    print(f"Backfilling {args.start} ~ {args.end}  ({len(windows)} windows × {args.chunk} days)")
    products = [p.strip() for p in args.products.split(",") if p.strip()]
    print(f"Futures products: {products}\n")

    total_op = 0
    total_fut = 0
    total_price = 0
    t0 = time.time()
    for i, (s, e) in enumerate(windows, 1):
        print(f"[Window {i}/{len(windows)}] {s} ~ {e}")
        total_op += run_op(s, e); time.sleep(args.sleep)
        for fid in products:
            total_fut += run_fut(fid, s, e); time.sleep(args.sleep)
        total_price += run_fut_price(s, e); time.sleep(args.sleep)
    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s. OP rows: {total_op}, FUT rows: {total_fut}, fut_price rows: {total_price}")


if __name__ == "__main__":
    main()
