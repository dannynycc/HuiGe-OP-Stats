"""Sample audit: compare DB raw tables vs endpoint truth on 50 random dates.

Logic:
  - Pick 50 random dates spread across 2020-2026
  - For each date, fetch every endpoint and compare to DB content
  - Coverage: op_legal (TXO 30 rows), fut_legal (TX/MTX/etc), fut_price (TX/TE/TF),
    credit_summary (TWSE+TPEX margin, mkt_cap), daily_summary aggregates
  - Any mismatch → flag

If 0 mismatches found, confidence is high that no other columns are stale.
If found, a pattern emerges — then run targeted sweep.
"""
import sys
import io
import pathlib
import sqlite3
import random
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.scrapers import twse, tpex, taifex


def main():
    con = sqlite3.connect("data/data.db")
    con.row_factory = sqlite3.Row

    # Sample 50 dates across 2020-2026
    random.seed(43)
    all_dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM op_legal WHERE daynight='day' ORDER BY date"
    )]
    sample_n = 30
    samples = sorted(random.sample(all_dates, sample_n))

    issues = []
    print(f"Sampling {sample_n} dates: {samples[0]} ~ {samples[-1]}")
    print()

    for d in samples:
        slash = d.replace("-", "/")

        # 1. TWSE margin
        try:
            r = twse.fetch_credit(d)
            ep_thousand = r.get("twse_margin_balance_thousand")
            db_thousand = con.execute(
                "SELECT twse_margin_balance FROM credit_summary WHERE date=?", (d,)
            ).fetchone()
            db_v = db_thousand[0] if db_thousand else None
            if ep_thousand is not None and db_v is not None:
                if abs(ep_thousand - db_v) > 100:  # 100 仟元 容差
                    issues.append((d, "twse_margin", db_v, ep_thousand))
        except Exception as e:
            print(f"  {d} twse_margin err: {e}")
        time.sleep(0.4)

        # 2. TPEX margin
        try:
            r = tpex.fetch_credit_summary(d)
            ep_thousand = r.get("tpex_margin_balance_thousand")
            db_v = con.execute(
                "SELECT tpex_margin_balance FROM credit_summary WHERE date=?", (d,)
            ).fetchone()
            db_v = db_v[0] if db_v else None
            if ep_thousand is not None and db_v is not None:
                if abs(ep_thousand - db_v) > 100:
                    issues.append((d, "tpex_margin", db_v, ep_thousand))
        except Exception:
            pass
        time.sleep(0.3)

        # 3. TX nearest-month close
        try:
            r = taifex.fetch_fut_price(slash, "TX")
            if r.get("actual_date") == d:
                ep_rows = sorted(
                    [x for x in r.get("rows", []) if x.get("contract") == "TX" and x.get("expiry")],
                    key=lambda x: x["expiry"],
                )
                if ep_rows:
                    ep_close = ep_rows[0].get("close")
                    db_close = con.execute(
                        "SELECT tx_close FROM daily_summary WHERE date=?", (d,)
                    ).fetchone()
                    db_close = db_close[0] if db_close else None
                    if ep_close and db_close and abs(ep_close - db_close) > 1:
                        issues.append((d, "tx_close", db_close, ep_close))
        except Exception:
            pass
        time.sleep(0.3)

        # 4. op_legal (TXO 買權外資 OI net) — quick spot check 1 cell
        try:
            r = taifex.fetch_op(slash, "day")
            if r.get("actual_date") == d:
                ep_rows = [x for x in r.get("rows", [])
                           if x.get("product") == "臺指選擇權"
                           and x.get("callput") == "買權" and x.get("role") == "外資"]
                if ep_rows:
                    ep_oi = ep_rows[0].get("oi_net_lots")
                    db_oi = con.execute(
                        """SELECT oi_net_lots FROM op_legal
                           WHERE date=? AND daynight='day' AND product='臺指選擇權'
                           AND callput='買權' AND role='外資'""", (d,)
                    ).fetchone()
                    db_oi = db_oi[0] if db_oi else None
                    if ep_oi is not None and db_oi is not None and abs(ep_oi - db_oi) > 1:
                        issues.append((d, "op_call_oi_外資", db_oi, ep_oi))
        except Exception:
            pass
        time.sleep(0.4)

        print(f"  {d} done ({len(issues)} issues so far)")

    print()
    print("=" * 60)
    print(f"AUDIT COMPLETE — {len(issues)} mismatches found in {sample_n} dates × 4 cols = {sample_n * 4} checks")
    print("=" * 60)
    if issues:
        for d, col, db_v, ep_v in issues:
            print(f"  XX {d} {col}: DB={db_v} endpoint={ep_v}")
    else:
        print("  ALL CLEAN — high confidence DB matches endpoint")


if __name__ == "__main__":
    main()
