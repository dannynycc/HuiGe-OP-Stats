"""Find and refill trading days whose night session was never written.

Root cause: original `_next_business_day` skipped weekends only. For trading
days right before a holiday/typhoon-day, the night session = T 15:00 ~ next-
trading-day 05:00 spans the holiday. Old code POSTed queryDate=T+1 (= holiday
weekday) → endpoint returned 0 rows → never written.

Fix: for each (date with day session but no night session AND not the latest),
re-fetch night via fetch_op/fut with queryDate = next trading day from DB.
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect
from app.scrapers import taifex


def main():
    with connect() as con:
        # day-session dates without a night-session row
        missing = [r[0] for r in con.execute("""
            SELECT DISTINCT day.date FROM op_legal day
            WHERE day.daynight='day'
              AND NOT EXISTS (
                SELECT 1 FROM op_legal n WHERE n.date = day.date AND n.daynight='night'
              )
            ORDER BY day.date
        """)]
        # exclude very latest date (today's night may not yet exist)
        latest = con.execute(
            "SELECT MAX(date) FROM op_legal WHERE daynight='day'"
        ).fetchone()[0]
        if latest in missing:
            missing.remove(latest)

    print(f"Trading days with no night session: {len(missing)}")
    for d in missing:
        print(f"  {d}")
    print()

    total_op, total_fut = 0, 0
    for i, d in enumerate(missing, 1):
        qd = d.replace("-", "/")
        try:
            r_op = taifex.fetch_op(qd, "night")
            r_fut = taifex.fetch_fut(qd, "night")
            with connect() as con:
                for row in r_op.get("rows", []):
                    con.execute("""
                        INSERT OR REPLACE INTO op_legal
                        (date, daynight, product, callput, role,
                         buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt,
                         oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt,
                         oi_net_lots, oi_net_amt)
                        VALUES (?, 'night', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        d, row.get("product"), row.get("callput"), row.get("role"),
                        row.get("buy_lots"), row.get("buy_amt"),
                        row.get("sell_lots"), row.get("sell_amt"),
                        row.get("net_lots"), row.get("net_amt"),
                        row.get("oi_buy_lots"), row.get("oi_buy_amt"),
                        row.get("oi_sell_lots"), row.get("oi_sell_amt"),
                        row.get("oi_net_lots"), row.get("oi_net_amt"),
                    ))
                    total_op += 1
                for row in r_fut.get("rows", []):
                    con.execute("""
                        INSERT OR REPLACE INTO fut_legal
                        (date, daynight, product, role,
                         buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt,
                         oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt,
                         oi_net_lots, oi_net_amt)
                        VALUES (?, 'night', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        d, row.get("product"), row.get("role"),
                        row.get("buy_lots"), row.get("buy_amt"),
                        row.get("sell_lots"), row.get("sell_amt"),
                        row.get("net_lots"), row.get("net_amt"),
                        row.get("oi_buy_lots"), row.get("oi_buy_amt"),
                        row.get("oi_sell_lots"), row.get("oi_sell_amt"),
                        row.get("oi_net_lots"), row.get("oi_net_amt"),
                    ))
                    total_fut += 1
            print(f"  [{i}/{len(missing)}] {d}: op_night={len(r_op.get('rows', []))}, fut_night={len(r_fut.get('rows', []))}")
        except Exception as e:
            print(f"  [{i}/{len(missing)}] {d}: ERR {e!r}")
        time.sleep(0.3)
    print(f"\nWrote {total_op} op_legal + {total_fut} fut_legal night rows.")


if __name__ == "__main__":
    main()
