"""Bulk backfill: refresh a date range, day-by-day, with throttle + skip-weekends.

Usage:
    python scripts/backfill.py --from 2024-01-01 --to 2024-12-31
    python scripts/backfill.py --from 2025-01-01 --to today --sleep 0.8
    python scripts/backfill.py --dates 2026-04-15,2026-04-30   # discrete list

Limitations (per README):
  - 台指期收盤價 (futDailyMarketExcel) is "today only" — historical tx_close
    must come from a different source (Excel migration, or another API).
  - 上市總市值 (homeApi/mkt_cap) only ships ~5 most-recent days; older dates
    will leave twse_mkt_cap = NULL.

Both holidays and weekends are skipped *based on the response*: if a day
returns empty data, it still gets logged but won't pollute summaries.
"""
import sys, pathlib, argparse, time, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.refresh import refresh


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--from", dest="start", help="YYYY-MM-DD start")
    g.add_argument("--dates", help="Comma-separated explicit YYYY-MM-DD list")
    p.add_argument("--to", default="today", help="YYYY-MM-DD end (default: today)")
    p.add_argument("--sleep", type=float, default=0.6,
                   help="Seconds to sleep between dates (rate-limit safety)")
    p.add_argument("--skip-weekends", action="store_true", default=True)
    args = p.parse_args()

    if args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    else:
        start = dt.date.fromisoformat(args.start)
        end = dt.date.today() if args.to == "today" else dt.date.fromisoformat(args.to)
        dates = []
        for d in daterange(start, end):
            if args.skip_weekends and d.weekday() >= 5:
                continue
            dates.append(d.isoformat())

    print(f"Backfilling {len(dates)} dates from {dates[0]} to {dates[-1]}")
    ok_n, fail_n = 0, 0
    for i, d in enumerate(dates, 1):
        t0 = time.time()
        try:
            r = refresh(d)
            if r["ok"]:
                ok_n += 1
                tag = "OK "
            else:
                fail_n += 1
                tag = "ERR"
            print(f"  [{i:>3}/{len(dates)}] {tag} {d}  {time.time()-t0:.1f}s"
                  + (f"  errors={r['errors']}" if not r["ok"] else ""))
        except Exception as e:
            fail_n += 1
            print(f"  [{i:>3}/{len(dates)}] EXC {d}: {e!r}")
        time.sleep(args.sleep)
    print(f"\nDone. ok={ok_n} fail={fail_n}")


if __name__ == "__main__":
    main()
