"""Unified historical backfill — single process, all 4 missing sources.

Sources per date:
1. TWSE 信用餘額: FinMind TaiwanStockTotalMarginPurchaseShortSale (MarginPurchaseMoney)
2. TPEX 信用餘額: TPEX margin_bal_result endpoint (existing scraper)
3. 個股期合計法人: FinMind TaiwanFuturesInstitutionalInvestors data_id='SF'
4. TPEX 上櫃總市值: TPEX highlight endpoint (existing scraper)

Run per date — 4 calls × ~0.5s = ~2s/date. 809 dates → ~30 min.
Idempotent — UPDATE only NULL fields, won't overwrite existing values.
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


def fetch_finmind_twse_margin(d: str) -> float | None:
    """TWSE total margin balance, in 仟元 (matches credit_summary schema)."""
    p = {"dataset": "TaiwanStockTotalMarginPurchaseShortSale", "data_id": "",
         "start_date": d, "end_date": d}
    try:
        r = requests.get(FINMIND, params=p, timeout=20, verify=False).json()
        for row in r.get("data", []):
            if row.get("name") == "MarginPurchaseMoney" and row.get("date") == d:
                yuan = row.get("TodayBalance")
                if yuan:
                    return float(yuan) / 1000.0
    except Exception:
        pass
    return None


def fetch_finmind_stock_fut(d_start: str, d_end: str) -> dict[str, dict]:
    """Per-date dict of {role: oi_net_lots} for SF (個股期合計).

    SF aggregates all stock futures into one row per (date, role).
    Returns: {date: {'外資': lots, '自營商': lots, '投信': lots}}
    """
    p = {"dataset": "TaiwanFuturesInstitutionalInvestors", "data_id": "SF",
         "start_date": d_start, "end_date": d_end}
    try:
        r = requests.get(FINMIND, params=p, timeout=30, verify=False).json()
    except Exception:
        return {}
    out: dict[str, dict[str, int]] = {}
    for row in r.get("data", []):
        d = row["date"]
        role = row["institutional_investors"]
        oibl = row.get("long_open_interest_balance_volume") or 0
        oisl = row.get("short_open_interest_balance_volume") or 0
        oi_net = oibl - oisl
        out.setdefault(d, {})[role] = oi_net
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="start", default="2020-01-01")
    p.add_argument("--to", dest="end", default="2023-05-04")
    p.add_argument("--sleep", type=float, default=0.4)
    args = p.parse_args()

    with connect() as con:
        dates = [r[0] for r in con.execute(
            """SELECT DISTINCT date FROM op_legal
               WHERE daynight='day' AND date BETWEEN ? AND ?
               ORDER BY date""", (args.start, args.end)
        )]

    print(f"Unified backfill: {len(dates)} dates ({args.start} ~ {args.end})")
    print(f"Sources: TWSE margin (FinMind) | TPEX margin | SF stock_fut | TPEX mkt_cap\n")

    # 1. Pre-fetch all SF (single FinMind call covers full range, much faster)
    print("Pre-fetching SF (個股期合計法人) for full range...")
    sf_map = fetch_finmind_stock_fut(args.start, args.end)
    print(f"  got {len(sf_map)} dates of SF data\n")

    cnt = {"twse_m": 0, "tpex_m": 0, "sf": 0, "tpex_cap": 0, "fail": 0}
    for i, d in enumerate(dates, 1):
        # 1) TWSE margin (FinMind)
        twse_thousand = fetch_finmind_twse_margin(d)
        time.sleep(args.sleep)

        # 2) TPEX margin balance + 3) TPEX mkt_cap (concurrent fields, separate endpoints)
        tpex_thousand = None
        tpex_million = None
        try:
            tp = tpex.fetch_credit_summary(d)
            tpex_thousand = tp.get("tpex_margin_balance_thousand")
        except Exception:
            pass
        time.sleep(args.sleep / 2)
        try:
            hl = tpex.fetch_highlight(d)
            tpex_million = hl.get("tpex_mkt_cap_million")
        except Exception:
            pass
        time.sleep(args.sleep / 2)

        # 4) SF (already pre-fetched)
        sf_data = sf_map.get(d, {})
        # Apply Excel rule: 外資 + 自營商 (排除投信)
        sf_oi_net = (sf_data.get("外資", 0) or 0) + (sf_data.get("自營商", 0) or 0) if sf_data else None

        # Write to credit_summary + daily_summary
        with connect() as con:
            existing = con.execute("SELECT * FROM credit_summary WHERE date=?", (d,)).fetchone()
            con.execute(
                """INSERT OR REPLACE INTO credit_summary
                   (date, twse_margin_balance, twse_turnover, twse_mkt_cap,
                    tpex_margin_balance, tpex_turnover, tpex_mkt_cap)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (d,
                 twse_thousand if twse_thousand is not None else (existing["twse_margin_balance"] if existing else None),
                 existing["twse_turnover"] if existing else None,
                 existing["twse_mkt_cap"] if existing else None,
                 tpex_thousand if tpex_thousand is not None else (existing["tpex_margin_balance"] if existing else None),
                 existing["tpex_turnover"] if existing else None,
                 tpex_million if tpex_million is not None else (existing["tpex_mkt_cap"] if existing else None)),
            )
            # Propagate to daily_summary
            if twse_thousand is not None:
                con.execute("UPDATE daily_summary SET twse_margin_amt_oku=? WHERE date=?",
                            (twse_thousand / 100000, d))
                cnt["twse_m"] += 1
            if tpex_thousand is not None:
                con.execute("UPDATE daily_summary SET tpex_margin_amt_oku=? WHERE date=?",
                            (tpex_thousand / 100000, d))
                cnt["tpex_m"] += 1
            if tpex_million is not None:
                # 佰萬元 → 兆元 = / 1,000,000
                con.execute("UPDATE daily_summary SET tpex_mkt_cap_chao=? WHERE date=?",
                            (tpex_million / 1_000_000, d))
                cnt["tpex_cap"] += 1
            if sf_oi_net is not None:
                con.execute("UPDATE daily_summary SET stock_fut_legal_net=? WHERE date=?",
                            (sf_oi_net, d))
                cnt["sf"] += 1

            # Recompute pct from daily_summary cols (margin / mkt_cap)
            con.execute("""UPDATE daily_summary
                SET twse_margin_pct = twse_margin_amt_oku / (twse_mkt_cap_chao * 10000.0)
                WHERE date=? AND twse_margin_amt_oku IS NOT NULL
                  AND twse_mkt_cap_chao IS NOT NULL AND twse_mkt_cap_chao > 0""", (d,))
            con.execute("""UPDATE daily_summary
                SET tpex_margin_pct = tpex_margin_amt_oku / (tpex_mkt_cap_chao * 10000.0)
                WHERE date=? AND tpex_margin_amt_oku IS NOT NULL
                  AND tpex_mkt_cap_chao IS NOT NULL AND tpex_mkt_cap_chao > 0""", (d,))

        if i % 25 == 0 or i == len(dates):
            print(f"  [{i:>4}/{len(dates)}] {d}  cum: twse_m={cnt['twse_m']} tpex_m={cnt['tpex_m']} sf={cnt['sf']} tpex_cap={cnt['tpex_cap']}")

    print(f"\nDone. {cnt}")


if __name__ == "__main__":
    main()
