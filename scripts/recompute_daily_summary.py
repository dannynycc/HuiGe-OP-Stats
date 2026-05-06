"""Re-compute daily_summary from raw tables (op_legal/fut_legal/fut_price/etc).

Used after bulk-loading raw data via FinMind backfill (which doesn't go through
refresh()), or any time daily_summary is missing rows that op_legal has.

Aggregation rules — same as refresh.compute_daily_summary:
  op_call_net / op_put_net / stock_fut_legal_net = sum(oi_net_lots)
    where role IN ('外資','自營商') (excludes 投信, per Excel convention)
  op_cp_net = op_call_net - op_put_net
  tx_close = TX nearest-month close from fut_price
  twse_margin_amt_oku = twse_margin_balance / 100000  (仟元 → 億元)
  ...
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.db import connect

LEGAL_ROLES = ("外資", "自營商")


def main():
    with connect() as con:
        # All trading dates (= dates with day-session op_legal data)
        dates = [r[0] for r in con.execute(
            "SELECT DISTINCT date FROM op_legal WHERE daynight='day' ORDER BY date"
        )]
    print(f"Recomputing daily_summary for {len(dates)} trading days...")
    MICRO_TX_LAUNCH = "2022-03-28"

    written, skipped = 0, 0
    for d in dates:
        has_micro = d >= MICRO_TX_LAUNCH
        with connect() as con:
            # op_call_net / op_put_net (臺指選擇權, 外資+自營商, OI net_lots)
            op_call = con.execute("""
                SELECT COALESCE(SUM(oi_net_lots), 0) FROM op_legal
                WHERE date = ? AND daynight='day' AND product='臺指選擇權'
                  AND callput='買權' AND role IN (?, ?)
            """, (d, *LEGAL_ROLES)).fetchone()[0]
            op_put = con.execute("""
                SELECT COALESCE(SUM(oi_net_lots), 0) FROM op_legal
                WHERE date = ? AND daynight='day' AND product='臺指選擇權'
                  AND callput='賣權' AND role IN (?, ?)
            """, (d, *LEGAL_ROLES)).fetchone()[0]
            # op_pre_open_cp_net = (CALL OI day + CALL net night) - (PUT OI day + PUT net night)
            # NULL for dates without night data (TAIFEX endpoint cutoff = 2023/05/05)
            night_call = con.execute("""
                SELECT COALESCE(SUM(net_lots), 0) FROM op_legal
                WHERE date = ? AND daynight='night' AND product='臺指選擇權'
                  AND callput='買權' AND role IN (?, ?)
            """, (d, *LEGAL_ROLES)).fetchone()[0]
            night_put = con.execute("""
                SELECT COALESCE(SUM(net_lots), 0) FROM op_legal
                WHERE date = ? AND daynight='night' AND product='臺指選擇權'
                  AND callput='賣權' AND role IN (?, ?)
            """, (d, *LEGAL_ROLES)).fetchone()[0]
            has_night_op = con.execute(
                "SELECT 1 FROM op_legal WHERE date = ? AND daynight='night' "
                "AND product='臺指選擇權' LIMIT 1", (d,)
            ).fetchone() is not None
            op_pre_open_cp_net = (
                int((op_call + night_call) - (op_put + night_put))
                if has_night_op else None
            )
            stock_fut = con.execute("""
                SELECT COALESCE(SUM(oi_net_lots), 0) FROM fut_legal
                WHERE date = ? AND daynight='day' AND product='股票期貨'
                  AND role IN (?, ?)
            """, (d, *LEGAL_ROLES)).fetchone()[0]

            # 台指期 OI 等效大台 = 大台 + 小台/4 + 微台/20 (微台 only after launch)
            tx_components = [("臺股期貨", 1.0), ("小型臺指期貨", 4.0)]
            if has_micro:
                tx_components.append(("微型臺指期貨", 20.0))

            tx_oi_lots = 0.0
            tx_night_lots = 0.0
            for product, factor in tx_components:
                tx_oi = con.execute("""
                    SELECT COALESCE(SUM(oi_net_lots), 0) FROM fut_legal
                    WHERE date = ? AND daynight='day' AND product = ? AND role IN (?, ?)
                """, (d, product, *LEGAL_ROLES)).fetchone()[0]
                tx_n = con.execute("""
                    SELECT COALESCE(SUM(net_lots), 0) FROM fut_legal
                    WHERE date = ? AND daynight='night' AND product = ? AND role IN (?, ?)
                """, (d, product, *LEGAL_ROLES)).fetchone()[0]
                tx_oi_lots += tx_oi / factor
                tx_night_lots += tx_n / factor

            op_legal_net = round(tx_oi_lots, 2) if tx_oi_lots else None
            fut_pre_open_net = round(tx_oi_lots + tx_night_lots) if (tx_oi_lots or tx_night_lots) else None

            # tx_close (TX nearest-month)
            tx = con.execute("""
                SELECT close FROM fut_price WHERE date = ? AND contract='TX'
                ORDER BY expiry LIMIT 1
            """, (d,)).fetchone()
            tx_close = tx[0] if tx else None

            # margin / mkt cap from credit_summary
            cs = con.execute(
                "SELECT * FROM credit_summary WHERE date = ?", (d,)
            ).fetchone()
            twse_thousand = cs["twse_margin_balance"] if cs else None
            tpex_thousand = cs["tpex_margin_balance"] if cs else None
            twse_oku = cs["twse_mkt_cap"] if cs else None
            tpex_million = cs["tpex_mkt_cap"] if cs else None

            twse_margin_oku = twse_thousand / 100000 if twse_thousand else None
            tpex_margin_oku = tpex_thousand / 100000 if tpex_thousand else None
            twse_mkt_chao = twse_oku / 10000 if twse_oku else None
            tpex_mkt_chao = tpex_million / 1_000_000 if tpex_million else None
            twse_pct = (twse_thousand / 100000) / twse_oku if twse_thousand and twse_oku else None
            tpex_pct = (tpex_thousand / 100000) / (tpex_million / 100) if tpex_thousand and tpex_million else None

            values = {
                "tx_close": tx_close,
                "op_legal_net": op_legal_net,    # 台指期 等效大台 OI 淨
                "op_call_net": int(op_call) if op_call else None,
                "op_put_net": int(op_put) if op_put else None,
                "op_cp_net": int(op_call - op_put) if (op_call or op_put) else None,
                "op_pre_open_cp_net": op_pre_open_cp_net,  # 選擇權開盤前多空 (NULL 對 2023-05-04 之前)
                "fut_pre_open_net": fut_pre_open_net,  # 開盤前部位 = OI + night
                "stock_fut_legal_net": int(stock_fut) if stock_fut else None,
                "twse_margin_pct": twse_pct,
                "tpex_margin_pct": tpex_pct,
                "twse_margin_amt_oku": twse_margin_oku,
                "tpex_margin_amt_oku": tpex_margin_oku,
                "twse_mkt_cap_chao": twse_mkt_chao,
                "tpex_mkt_cap_chao": tpex_mkt_chao,
            }
            if all(v is None for v in values.values()):
                skipped += 1
                continue

            # Merge with existing row (preserve any non-NULL fields already there
            # that we couldn't recompute, e.g. tx_close from Excel migration)
            existing = con.execute(
                "SELECT * FROM daily_summary WHERE date = ?", (d,)
            ).fetchone()
            for k in list(values.keys()):
                if values[k] is None and existing and existing[k] is not None:
                    values[k] = existing[k]

            cols = list(values.keys())
            con.execute(f"""
                INSERT OR REPLACE INTO daily_summary
                (date, {", ".join(cols)})
                VALUES (?, {", ".join("?" * len(cols))})
            """, (d, *[values[c] for c in cols]))
            written += 1

    print(f"\nDone. Wrote {written} rows, skipped {skipped} all-NULL.")


if __name__ == "__main__":
    main()
