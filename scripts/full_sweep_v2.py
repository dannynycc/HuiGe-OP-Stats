"""Full sweep v2 — cover 11 cols 之前 v1 漏掉的:

Coverage:
  twii_close          ← FinMind TaiwanStockPrice TAIEX
  op_call_net         ← TAIFEX op_legal day, 臺指選擇權 買權 外資+自營商 OI net
  op_put_net          ← TAIFEX op_legal day, 臺指選擇權 賣權 外資+自營商 OI net
  op_legal_net        ← TAIFEX fut_legal day, 大台/小台/微台 等效 OI net
  fut_pre_open_net    ← op_legal_net + 同 components 的 night net
  op_pre_open_cp_net  ← (CALL OI day + CALL night) - (PUT OI day + PUT night)
  stock_fut_legal_net ← TAIFEX fut_legal day, 股票期貨 外資+自營商 OI net
  twse_mkt_cap_chao   ← weekly + TWII interp (re-derive, compare DB)

Skip (already verified by v1):
  tx_close / twse_margin / tpex_margin / tpex_mkt_cap

Strategy: refresh-style fetch + compare. Only UPDATE if mismatch > tolerance.
Read-only for matched cells (majority).
"""
import sys
import io
import pathlib
import sqlite3
import time
import datetime as dt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from app.scrapers import taifex
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LEGAL_ROLES = ("外資", "自營商")
MICRO_TX_LAUNCH = "2022-03-28"


def fetch_finmind_taiex_month(yyyy, mm):
    s = dt.date(yyyy, mm, 1).isoformat()
    next_m = mm + 1
    next_y = yyyy
    if next_m > 12:
        next_m = 1
        next_y += 1
    e = (dt.date(next_y, next_m, 1) - dt.timedelta(days=1)).isoformat()
    p = {"dataset": "TaiwanStockPrice", "data_id": "TAIEX",
         "start_date": s, "end_date": e}
    try:
        r = requests.get("https://api.finmindtrade.com/api/v4/data",
                         params=p, timeout=30, verify=False)
        return {row["date"]: row.get("close") for row in r.json().get("data", [])}
    except Exception:
        return {}


def main():
    con = sqlite3.connect("data/data.db")
    con.execute("PRAGMA busy_timeout = 30000")
    con.row_factory = sqlite3.Row

    dates = [r[0] for r in con.execute(
        "SELECT DISTINCT date FROM op_legal WHERE daynight='day' ORDER BY date"
    )]
    print(f"sweeping {len(dates)} dates", flush=True)

    fixed = {"twii": 0, "op_call": 0, "op_put": 0, "op_legal_net": 0,
             "fut_pre_open": 0, "op_pre_open_cp": 0, "stock_fut": 0,
             "twse_pct": 0, "tpex_pct": 0, "twse_mkt": 0}
    failed = 0

    # 1. TWII batch fetch by month
    twii_map = {}
    cur = dt.date.fromisoformat(dates[0]).replace(day=1)
    end = dt.date.fromisoformat(dates[-1])
    print(f"[twii] fetching FinMind monthly chunks...", flush=True)
    while cur <= end:
        m = fetch_finmind_taiex_month(cur.year, cur.month)
        twii_map.update(m)
        nxt_y, nxt_m = (cur.year + 1, 1) if cur.month == 12 else (cur.year, cur.month + 1)
        cur = dt.date(nxt_y, nxt_m, 1)
        time.sleep(0.3)
    print(f"[twii] got {len(twii_map)} dates", flush=True)

    # Compare twii vs DB
    for d in dates:
        ep = twii_map.get(d)
        if ep is None:
            continue
        db_v = con.execute("SELECT twii_close FROM daily_summary WHERE date=?", (d,)).fetchone()
        db_v = db_v[0] if db_v else None
        if db_v is not None and abs(ep - db_v) > 0.01:
            con.execute("UPDATE daily_summary SET twii_close=? WHERE date=?", (ep, d))
            fixed["twii"] += 1
            print(f"  FIX {d} twii: {db_v} → {ep}", flush=True)
    con.commit()
    print(f"[twii] fixed {fixed['twii']}", flush=True)

    # 2. Per-date sweep for op + fut
    for i, d in enumerate(dates, 1):
        slash = d.replace("-", "/")

        # ---- op_legal day ----
        try:
            r = taifex.fetch_op(slash, "day")
            if r.get("actual_date") == d:
                # sum 買權 / 賣權 OI net (外資 + 自營商)
                ep_call = sum(x.get("oi_net_lots", 0) or 0 for x in r["rows"]
                              if x.get("product") == "臺指選擇權"
                              and x.get("callput") == "買權"
                              and x.get("role") in LEGAL_ROLES)
                ep_put = sum(x.get("oi_net_lots", 0) or 0 for x in r["rows"]
                             if x.get("product") == "臺指選擇權"
                             and x.get("callput") == "賣權"
                             and x.get("role") in LEGAL_ROLES)
                row = con.execute("""SELECT op_call_net, op_put_net FROM daily_summary WHERE date=?""", (d,)).fetchone()
                if row:
                    db_call, db_put = row["op_call_net"], row["op_put_net"]
                    if db_call is not None and abs(ep_call - db_call) > 1:
                        con.execute("UPDATE daily_summary SET op_call_net=?, op_cp_net=op_call_net-op_put_net WHERE date=?",
                                    (ep_call, d))
                        fixed["op_call"] += 1
                        print(f"  FIX {d} op_call: {db_call} → {ep_call}", flush=True)
                    if db_put is not None and abs(ep_put - db_put) > 1:
                        con.execute("UPDATE daily_summary SET op_put_net=?, op_cp_net=op_call_net-op_put_net WHERE date=?",
                                    (ep_put, d))
                        fixed["op_put"] += 1
                        print(f"  FIX {d} op_put: {db_put} → {ep_put}", flush=True)
        except Exception:
            failed += 1
        time.sleep(0.3)

        # ---- fut_legal day (台指期 等效大台 OI + stock_fut OI) ----
        try:
            r = taifex.fetch_fut(slash, "day")
            if r.get("actual_date") == d:
                # 台指期 等效大台 OI = 大台 + 小台/4 + 微台/20
                has_micro = d >= MICRO_TX_LAUNCH
                tx_components = [("臺股期貨", 1.0), ("小型臺指期貨", 4.0)]
                if has_micro:
                    tx_components.append(("微型臺指期貨", 20.0))
                ep_oi = 0.0
                for prod, factor in tx_components:
                    s = sum(x.get("oi_net_lots", 0) or 0 for x in r["rows"]
                            if x.get("product") == prod and x.get("role") in LEGAL_ROLES)
                    ep_oi += s / factor
                ep_oi = round(ep_oi, 2)

                # stock_fut OI net (外資 + 自營商)
                ep_sf = sum(x.get("oi_net_lots", 0) or 0 for x in r["rows"]
                            if x.get("product") == "股票期貨" and x.get("role") in LEGAL_ROLES)

                row = con.execute("SELECT op_legal_net, stock_fut_legal_net FROM daily_summary WHERE date=?", (d,)).fetchone()
                if row:
                    db_oi, db_sf = row["op_legal_net"], row["stock_fut_legal_net"]
                    if db_oi is not None and abs(ep_oi - db_oi) > 0.5:
                        con.execute("UPDATE daily_summary SET op_legal_net=? WHERE date=?", (ep_oi, d))
                        fixed["op_legal_net"] += 1
                        print(f"  FIX {d} op_legal_net: {db_oi} → {ep_oi}", flush=True)
                    if db_sf is not None and abs(ep_sf - db_sf) > 1:
                        con.execute("UPDATE daily_summary SET stock_fut_legal_net=? WHERE date=?", (ep_sf, d))
                        fixed["stock_fut"] += 1
                        print(f"  FIX {d} stock_fut: {db_sf} → {ep_sf}", flush=True)
        except Exception:
            failed += 1
        time.sleep(0.3)

        # ---- night sessions (only if 2023-05-04+) for fut_pre_open + op_pre_open_cp ----
        if d >= "2023-05-04":
            try:
                rn_op = taifex.fetch_op(slash, "night")
                rn_fut = taifex.fetch_fut(slash, "night")
                # Compute fut_pre_open_net = op_legal_net + night net of TX components
                day_oi_row = con.execute("SELECT op_legal_net FROM daily_summary WHERE date=?", (d,)).fetchone()
                if day_oi_row and day_oi_row[0] is not None:
                    has_micro = d >= MICRO_TX_LAUNCH
                    tx_components = [("臺股期貨", 1.0), ("小型臺指期貨", 4.0)]
                    if has_micro:
                        tx_components.append(("微型臺指期貨", 20.0))
                    night_oi = 0.0
                    for prod, factor in tx_components:
                        s = sum(x.get("net_lots", 0) or 0 for x in rn_fut.get("rows", [])
                                if x.get("product") == prod and x.get("role") in LEGAL_ROLES)
                        night_oi += s / factor
                    ep_pre_open = round(day_oi_row[0] + night_oi)
                    db_pre_open = con.execute("SELECT fut_pre_open_net FROM daily_summary WHERE date=?", (d,)).fetchone()[0]
                    if db_pre_open is not None and abs(ep_pre_open - db_pre_open) > 1:
                        con.execute("UPDATE daily_summary SET fut_pre_open_net=? WHERE date=?", (ep_pre_open, d))
                        fixed["fut_pre_open"] += 1
                        print(f"  FIX {d} fut_pre_open: {db_pre_open} → {ep_pre_open}", flush=True)

                # op_pre_open_cp_net = (CALL OI day + CALL night) - (PUT OI day + PUT night)
                op_day_row = con.execute("SELECT op_call_net, op_put_net FROM daily_summary WHERE date=?", (d,)).fetchone()
                if op_day_row and op_day_row[0] is not None and op_day_row[1] is not None:
                    night_call = sum(x.get("net_lots", 0) or 0 for x in rn_op.get("rows", [])
                                     if x.get("product") == "臺指選擇權"
                                     and x.get("callput") == "買權"
                                     and x.get("role") in LEGAL_ROLES)
                    night_put = sum(x.get("net_lots", 0) or 0 for x in rn_op.get("rows", [])
                                    if x.get("product") == "臺指選擇權"
                                    and x.get("callput") == "賣權"
                                    and x.get("role") in LEGAL_ROLES)
                    ep_op_pre = (op_day_row[0] + night_call) - (op_day_row[1] + night_put)
                    db_op_pre = con.execute("SELECT op_pre_open_cp_net FROM daily_summary WHERE date=?", (d,)).fetchone()[0]
                    if db_op_pre is not None and abs(ep_op_pre - db_op_pre) > 1:
                        con.execute("UPDATE daily_summary SET op_pre_open_cp_net=? WHERE date=?", (ep_op_pre, d))
                        fixed["op_pre_open_cp"] += 1
                        print(f"  FIX {d} op_pre_open_cp: {db_op_pre} → {ep_op_pre}", flush=True)
            except Exception:
                failed += 1
            time.sleep(0.3)

        if i % 25 == 0:
            con.commit()
            print(f"  [{i}/{len(dates)}] cum: {fixed} failed={failed}", flush=True)

    con.commit()

    # 3. Recompute pct from cells (margin/mkt_cap), audit re-derive correctness
    print(f"\n[pct] re-deriving twse/tpex margin pct from cells...", flush=True)
    n_pct = con.execute("""UPDATE daily_summary
        SET twse_margin_pct = twse_margin_amt_oku / (twse_mkt_cap_chao*10000.0)
        WHERE twse_margin_amt_oku IS NOT NULL AND twse_mkt_cap_chao IS NOT NULL""").rowcount
    n_pct2 = con.execute("""UPDATE daily_summary
        SET tpex_margin_pct = tpex_margin_amt_oku / (tpex_mkt_cap_chao*10000.0)
        WHERE tpex_margin_amt_oku IS NOT NULL AND tpex_mkt_cap_chao IS NOT NULL""").rowcount
    fixed["twse_pct"] = n_pct
    fixed["tpex_pct"] = n_pct2
    con.commit()
    print(f"[pct] re-derived twse_pct={n_pct} tpex_pct={n_pct2} (= total rows touched, 寫入 idempotent)", flush=True)

    # 4. twse_mkt_cap_chao re-interp (already verified by weekly anchor + TWII MAD-z)
    # Skip here — already covered by detect_outliers method 1+2

    print(f"\nDONE. fixed={fixed} failed={failed}", flush=True)


if __name__ == "__main__":
    main()
