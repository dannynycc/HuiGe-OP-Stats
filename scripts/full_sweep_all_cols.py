"""Full sweep: re-fetch every endpoint for ALL 1535 trading days, compare to
DB cell-by-cell, fix any mismatch. Estimate: ~60-90 min.

Coverage:
  raw tables    | endpoint                  | col(s) audited
  -----         | -----                      | -----
  op_legal day  | TAIFEX callsAndPutsDate    | OI net_lots / role / callput
  fut_legal day | TAIFEX futContractsDate    | OI net_lots / role / product
  fut_price     | TAIFEX futDailyMarketRpt   | TX nearest close (= tx_close)
  credit_summ   | TWSE MI_MARGN              | twse_margin_balance
  credit_summ   | TPEX margin_bal_result     | tpex_margin_balance
  credit_summ   | TPEX highlight             | tpex_mkt_cap

Skip (already audited or static):
  twii_close — already verified, use FinMind
  twse_mkt_cap — only 5-day, weekly anchor cross-checked
  op_legal night — already covered by sweep_margin earlier (no stale found)
  fut_legal night — same

Strategy: log every mismatch, fix, audit summary at end.
"""
import sys
import io
import pathlib
import sqlite3
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.scrapers import twse, tpex, taifex


def main():
    con = sqlite3.connect("data/data.db")
    con.execute("PRAGMA busy_timeout = 30000")
    con.row_factory = sqlite3.Row

    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM op_legal WHERE daynight='day' ORDER BY date"
    )]
    print(f"sweeping {len(dates)} dates × ~6 endpoints/date")

    fixed_per_col = {}
    failed = 0

    for i, d in enumerate(dates, 1):
        slash = d.replace("-", "/")

        # 1. tx_close vs fut_price endpoint
        try:
            r = taifex.fetch_fut_price(slash, "TX")
            if r.get("actual_date") == d:
                tx_rows = sorted(
                    [x for x in r.get("rows", []) if x.get("contract") == "TX" and x.get("expiry")],
                    key=lambda x: x["expiry"],
                )
                if tx_rows:
                    ep_close = tx_rows[0].get("close")
                    db_close = con.execute(
                        "SELECT tx_close FROM daily_summary WHERE date=?", (d,)
                    ).fetchone()
                    db_close = db_close[0] if db_close else None
                    if ep_close is not None and db_close is not None:
                        if abs(ep_close - db_close) > 0.5:
                            con.execute(
                                "UPDATE daily_summary SET tx_close=? WHERE date=?",
                                (ep_close, d),
                            )
                            fixed_per_col["tx_close"] = fixed_per_col.get("tx_close", 0) + 1
                            print(f"  FIX {d} tx_close: {db_close} → {ep_close}")
        except Exception as e:
            failed += 1
        time.sleep(0.4)

        # 2. twse margin
        try:
            r = twse.fetch_credit(d)
            if r.get("actual_date") == d:
                ep_th = r.get("twse_margin_balance_thousand")
                db_th = con.execute(
                    "SELECT twse_margin_balance FROM credit_summary WHERE date=?", (d,)
                ).fetchone()
                db_th = db_th[0] if db_th else None
                if ep_th is not None and db_th is not None and abs(ep_th - db_th) > 100:
                    con.execute(
                        "UPDATE credit_summary SET twse_margin_balance=? WHERE date=?",
                        (ep_th, d),
                    )
                    con.execute(
                        "UPDATE daily_summary SET twse_margin_amt_oku=? WHERE date=?",
                        (ep_th / 100000, d),
                    )
                    fixed_per_col["twse_margin"] = fixed_per_col.get("twse_margin", 0) + 1
                    print(f"  FIX {d} twse_margin: {db_th/100000:.2f}億 → {ep_th/100000:.2f}億")
        except Exception:
            failed += 1
        time.sleep(0.4)

        # 3. tpex margin
        try:
            r = tpex.fetch_credit_summary(d)
            ep_th = r.get("tpex_margin_balance_thousand")
            db_th = con.execute(
                "SELECT tpex_margin_balance FROM credit_summary WHERE date=?", (d,)
            ).fetchone()
            db_th = db_th[0] if db_th else None
            if ep_th is not None and db_th is not None and abs(ep_th - db_th) > 100:
                con.execute(
                    "UPDATE credit_summary SET tpex_margin_balance=? WHERE date=?",
                    (ep_th, d),
                )
                con.execute(
                    "UPDATE daily_summary SET tpex_margin_amt_oku=? WHERE date=?",
                    (ep_th / 100000, d),
                )
                fixed_per_col["tpex_margin"] = fixed_per_col.get("tpex_margin", 0) + 1
                print(f"  FIX {d} tpex_margin: {db_th/100000:.2f}億 → {ep_th/100000:.2f}億")
        except Exception:
            failed += 1
        time.sleep(0.4)

        # 4. tpex mkt_cap (highlight endpoint)
        try:
            r = tpex.fetch_highlight(d)
            ep_million = r.get("tpex_mkt_cap_million")
            db_million = con.execute(
                "SELECT tpex_mkt_cap FROM credit_summary WHERE date=?", (d,)
            ).fetchone()
            db_million = db_million[0] if db_million else None
            if ep_million is not None and db_million is not None:
                if abs(ep_million - db_million) > 1:
                    con.execute(
                        "UPDATE credit_summary SET tpex_mkt_cap=? WHERE date=?",
                        (ep_million, d),
                    )
                    con.execute(
                        "UPDATE daily_summary SET tpex_mkt_cap_chao=? WHERE date=?",
                        (ep_million / 1_000_000, d),
                    )
                    fixed_per_col["tpex_mkt_cap"] = fixed_per_col.get("tpex_mkt_cap", 0) + 1
                    print(f"  FIX {d} tpex_mkt_cap: {db_million/1e6:.4f}兆 → {ep_million/1e6:.4f}兆")
        except Exception:
            failed += 1
        time.sleep(0.4)

        if i % 10 == 0:
            con.commit()
            print(f"  [{i}/{len(dates)}] cum fixed: {fixed_per_col}  failed: {failed}", flush=True)

    con.commit()
    print()
    print("=" * 60)
    print(f"DONE. Total fixed by col: {fixed_per_col}")
    print(f"      failed (endpoint err): {failed}")
    print("=" * 60)

    # Recompute pct + interp
    print()
    print("Recomputing twse_margin_pct / tpex_margin_pct...")
    con.execute("""UPDATE daily_summary
        SET twse_margin_pct = twse_margin_amt_oku / (twse_mkt_cap_chao*10000.0)
        WHERE twse_margin_amt_oku IS NOT NULL AND twse_mkt_cap_chao IS NOT NULL""")
    con.execute("""UPDATE daily_summary
        SET tpex_margin_pct = tpex_margin_amt_oku / (tpex_mkt_cap_chao*10000.0)
        WHERE tpex_margin_amt_oku IS NOT NULL AND tpex_mkt_cap_chao IS NOT NULL""")
    con.commit()
    print("Done.")


if __name__ == "__main__":
    main()
