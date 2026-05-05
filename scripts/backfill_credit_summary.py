"""Backfill credit_summary + daily_summary margin/mkt_cap_pct for historical dates.

TWSE: FinMind TaiwanStockTotalMarginPurchaseShortSale (1 call per date, full history).
  Sub 'MarginPurchaseMoney' row.TodayBalance = 元 -> /1e8 = 億 -> matches twse_margin_balance/100000 thousands.

TPEX: existing tpex.fetch_credit_summary endpoint (TPEX honors arbitrary date).

After backfill, also recompute twse_margin_pct = margin_balance / mkt_cap if mkt_cap exists.
"""
import sys
import pathlib
import time
import argparse
import requests
import urllib3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect
from app.scrapers import tpex

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
FINMIND = "https://api.finmindtrade.com/api/v4/data"


def fetch_twse_margin_thousand(date_dash: str) -> float | None:
    """Returns TWSE margin balance in 仟元 (matches twse_margin_balance schema)."""
    p = {"dataset": "TaiwanStockTotalMarginPurchaseShortSale", "data_id": "",
         "start_date": date_dash, "end_date": date_dash}
    try:
        r = requests.get(FINMIND, params=p, timeout=20, verify=False)
        rows = r.json().get("data", [])
        for d in rows:
            if d.get("name") == "MarginPurchaseMoney" and d.get("date") == date_dash:
                yuan = d.get("TodayBalance")
                if yuan is not None:
                    return float(yuan) / 1000.0  # 元 -> 仟元
    except Exception:
        pass
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default="2020-01-01")
    p.add_argument("--to", dest="end", default="2023-05-04")
    p.add_argument("--sleep", type=float, default=0.4)
    p.add_argument("--only-missing", action="store_true", default=True,
                   help="skip dates that already have BOTH twse and tpex margin (default)")
    args = p.parse_args()

    with connect() as con:
        dates = [r[0] for r in con.execute(
            """SELECT DISTINCT date FROM op_legal
               WHERE daynight='day' AND date BETWEEN ? AND ?
               ORDER BY date""", (args.start, args.end)
        )]
        if args.only_missing:
            have = {r[0] for r in con.execute(
                """SELECT date FROM credit_summary
                   WHERE twse_margin_balance IS NOT NULL
                   AND tpex_margin_balance IS NOT NULL"""
            )}
            dates = [d for d in dates if d not in have]

    print(f"Backfilling credit_summary for {len(dates)} dates ({args.start} ~ {args.end})")
    twse_ok, tpex_ok, fail = 0, 0, 0
    for i, d in enumerate(dates, 1):
        twse_thousand = fetch_twse_margin_thousand(d)
        try:
            tp = tpex.fetch_credit_summary(d)
            tpex_thousand = tp.get("tpex_margin_balance_thousand")
        except Exception:
            tpex_thousand = None

        if twse_thousand is None and tpex_thousand is None:
            fail += 1
            tag = "·"
        else:
            with connect() as con:
                # UPSERT credit_summary, preserving fields we don't backfill here
                existing = con.execute("SELECT * FROM credit_summary WHERE date=?", (d,)).fetchone()
                values = {
                    "twse_margin_balance": twse_thousand if twse_thousand is not None else (existing["twse_margin_balance"] if existing else None),
                    "twse_turnover": existing["twse_turnover"] if existing else None,
                    "twse_mkt_cap": existing["twse_mkt_cap"] if existing else None,
                    "tpex_margin_balance": tpex_thousand if tpex_thousand is not None else (existing["tpex_margin_balance"] if existing else None),
                    "tpex_turnover": existing["tpex_turnover"] if existing else None,
                    "tpex_mkt_cap": existing["tpex_mkt_cap"] if existing else None,
                }
                con.execute(
                    """INSERT OR REPLACE INTO credit_summary
                       (date, twse_margin_balance, twse_turnover, twse_mkt_cap,
                        tpex_margin_balance, tpex_turnover, tpex_mkt_cap)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (d, values["twse_margin_balance"], values["twse_turnover"], values["twse_mkt_cap"],
                     values["tpex_margin_balance"], values["tpex_turnover"], values["tpex_mkt_cap"]),
                )
                # Also propagate to daily_summary.margin_amt_oku
                if twse_thousand is not None:
                    con.execute(
                        "UPDATE daily_summary SET twse_margin_amt_oku = ? WHERE date = ?",
                        (twse_thousand / 100000, d),
                    )
                if tpex_thousand is not None:
                    con.execute(
                        "UPDATE daily_summary SET tpex_margin_amt_oku = ? WHERE date = ?",
                        (tpex_thousand / 100000, d),
                    )
            if twse_thousand is not None:
                twse_ok += 1
            if tpex_thousand is not None:
                tpex_ok += 1
            tag = f"OK twse={'.' if twse_thousand is None else 'Y'} tpex={'.' if tpex_thousand is None else 'Y'}"

        if i % 25 == 0 or i == len(dates):
            print(f"  [{i:>4}/{len(dates)}] {d}: {tag}  (running: twse_ok={twse_ok} tpex_ok={tpex_ok} fail={fail})")
        time.sleep(args.sleep)

    print(f"\nDone. twse_ok={twse_ok} tpex_ok={tpex_ok} fail={fail}")


if __name__ == "__main__":
    main()
