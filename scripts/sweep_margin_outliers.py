"""Sweep ALL historical dates: re-fetch TWSE MI_MARGN, fix stale margin entries.

Cause: some refresh / backfill in past wrote today's margin value to historical
date (cause unknown — possibly WAF transient + retry returning latest). Sweep
fixes all of them.

Time: ~1535 dates × 0.6s = ~15 min. Run as background.
"""
import sys
import io
import pathlib
import time
import sqlite3

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.scrapers import twse


def main():
    con = sqlite3.connect("data/data.db")
    con.row_factory = sqlite3.Row
    today = time.strftime("%Y-%m-%d")

    dates = [r[0] for r in con.execute(
        """SELECT date FROM daily_summary
           WHERE date < ? AND twse_margin_amt_oku IS NOT NULL
           ORDER BY date""", (today,)
    )]
    print(f"sweeping {len(dates)} historical dates")

    fixed = 0
    failed = 0
    for i, d in enumerate(dates, 1):
        db_oku = con.execute(
            "SELECT twse_margin_amt_oku FROM daily_summary WHERE date=?", (d,)
        ).fetchone()[0]
        try:
            r = twse.fetch_credit(d)
            actual_thousand = r.get("twse_margin_balance_thousand")
            actual_date = r.get("actual_date")
            if actual_thousand is None or actual_date != d:
                # Endpoint didn't honor this date — skip (don't break correct DB)
                failed += 1
                continue
            actual_oku = actual_thousand / 100000
            if abs(db_oku - actual_oku) / max(actual_oku, 1) > 0.01:
                # Mismatch — fix
                print(f"  FIX {d}: DB={db_oku:.2f} 億 → endpoint={actual_oku:.2f} 億")
                con.execute(
                    "UPDATE daily_summary SET twse_margin_amt_oku=? WHERE date=?",
                    (actual_oku, d),
                )
                con.execute(
                    "UPDATE credit_summary SET twse_margin_balance=? WHERE date=?",
                    (actual_thousand, d),
                )
                # Recompute pct
                con.execute(
                    """UPDATE daily_summary
                       SET twse_margin_pct = twse_margin_amt_oku / (twse_mkt_cap_chao*10000.0)
                       WHERE date=? AND twse_mkt_cap_chao IS NOT NULL""",
                    (d,),
                )
                fixed += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"  ERR {d}: {e!r}")

        if i % 50 == 0:
            con.commit()
            print(f"  [{i}/{len(dates)}] fixed={fixed} failed={failed}")
        time.sleep(0.5)

    con.commit()
    print(f"\nDone. fixed={fixed} failed={failed}")


if __name__ == "__main__":
    main()
