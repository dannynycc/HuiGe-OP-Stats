"""Backfill TX fut_price + daily_summary.tx_close for all trading days in DB.

Uses POST /cht/3/futDailyMarketReport which honors queryDate (unlike the
GET futDailyMarketExcel that only returns today). Fast — only 1 endpoint
per date, ~1.5s each.
"""
import sys, pathlib, time, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect
from app.scrapers import taifex


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", help="YYYY-MM-DD start (default: earliest in DB)")
    p.add_argument("--to", dest="end", help="YYYY-MM-DD end (default: latest in DB)")
    p.add_argument("--sleep", type=float, default=0.4)
    p.add_argument("--only-missing", action="store_true",
                   help="skip dates that already have fut_price rows")
    args = p.parse_args()

    with connect() as con:
        rng = con.execute(
            "SELECT MIN(date), MAX(date) FROM op_legal WHERE daynight='day'"
        ).fetchone()
        start = args.start or rng[0]
        end = args.end or rng[1]
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM op_legal WHERE daynight='day' AND date BETWEEN ? AND ? ORDER BY date",
            (start, end)
        )]
        if args.only_missing:
            have = set(r[0] for r in con.execute("SELECT DISTINCT date FROM fut_price"))
            dates = [d for d in dates if d not in have]

    print(f"Backfilling fut_price for {len(dates)} trading days ({start} ~ {end})")
    ok_n, fail_n, no_data = 0, 0, 0
    for i, d in enumerate(dates, 1):
        qd = d.replace("-", "/")
        t0 = time.time()
        try:
            r = taifex.fetch_fut_price(qd)
            rows = r.get("rows") or []
            actual = r.get("actual_date")
            if not rows or actual != d:
                no_data += 1
                tag = "·"
            else:
                with connect() as con:
                    for row in rows:
                        con.execute("""
                            INSERT OR REPLACE INTO fut_price
                            (date, contract, expiry, open_, high, low, close,
                             change_str, change_pct_str, ah_vol, day_vol, total_vol,
                             settle, oi, best_bid, best_ask)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            d, row.get("contract"), row.get("expiry"),
                            row.get("open_"), row.get("high"), row.get("low"), row.get("close"),
                            row.get("change_str"), row.get("change_pct_str"),
                            row.get("ah_vol"), row.get("day_vol"), row.get("total_vol"),
                            row.get("settle"), row.get("oi"),
                            row.get("best_bid"), row.get("best_ask"),
                        ))
                    # update daily_summary.tx_close (nearest-month TX close)
                    tx_rows = sorted(
                        (rr for rr in rows if rr.get("contract") == "TX" and rr.get("expiry")),
                        key=lambda rr: rr["expiry"],
                    )
                    if tx_rows:
                        close = tx_rows[0].get("close")
                        # Merge — only set if currently NULL or matches
                        con.execute("""
                            UPDATE daily_summary SET tx_close = ?
                            WHERE date = ? AND (tx_close IS NULL OR tx_close = 0)
                        """, (close, d))
                        # Insert daily_summary row if missing (unlikely)
                        con.execute("""
                            INSERT OR IGNORE INTO daily_summary (date, tx_close) VALUES (?, ?)
                        """, (d, close))
                ok_n += 1
                tag = "OK"
            print(f"  [{i:>3}/{len(dates)}] {tag} {d}  {time.time()-t0:.1f}s")
        except Exception as e:
            fail_n += 1
            print(f"  [{i:>3}/{len(dates)}] EXC {d}: {e!r}")
        time.sleep(args.sleep)
    print(f"\nDone. ok={ok_n} no_data={no_data} fail={fail_n}")


if __name__ == "__main__":
    main()
