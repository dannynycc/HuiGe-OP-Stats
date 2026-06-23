"""Refresh orchestrator — runs all 12 scrapers for a target date and writes DB."""
from __future__ import annotations
import json
import logging
import sqlite3
import time
import requests
import urllib3
from datetime import datetime, date, timedelta
from typing import Any
from .db import connect, init_db
from .scrapers import taifex, twse, tpex

log = logging.getLogger(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _third_wednesday(year: int, month: int):
    """Compute 3rd Wed of a month — TAIFEX 月選結算日 rule (97% accurate,
    holiday-順延 in 春節 1-2月 偶 mismatch e.g. 2023/01 = 1/30 not 1/18)."""
    import datetime as _dt
    first = _dt.date(year, month, 1)
    days_to_wed = (2 - first.weekday()) % 7
    return first + _dt.timedelta(days=days_to_wed + 14)


def _maybe_fetch_settlement_dates(target_date: str) -> dict[str, Any]:
    """Ensure TEO 月選 settlement dates for target_date's month are in DB.

    Strategy:
    1. If month entry already in DB AND has settlement_price → cached (true 真值), skip
    2. If entry in DB but price NULL (predicted by 第三 Wed rule) AND target_date >=
       predicted settlement date → endpoint should now have actual data, fetch & verify
    3. If month not in DB → insert predicted (3rd Wed), don't fetch endpoint
       (= future month, no point asking endpoint that hasn't released)

    Result: endpoint only hit on settlement-day refresh (~1 day per month).
    Other refreshes are 0ms DB lookups.
    """
    import datetime as _dt
    try:
        target = _dt.date.fromisoformat(target_date)
    except ValueError:
        return {"skipped": True, "reason": "bad target_date"}

    yyyymm = f"{target.year:04d}{target.month:02d}"
    with connect() as con:
        cached = con.execute(
            """SELECT date, settlement_price FROM option_settlement_dates
               WHERE contract_month = ? AND product = 'TEO' LIMIT 1""",
            (yyyymm,)
        ).fetchone()

    # Case 1: cached with real price → skip
    if cached and cached[1] is not None:
        return {"cached": True, "month": yyyymm}

    # Case 2: predicted entry exists, check if settlement should have happened
    # by now (target_date >= predicted date) → fetch endpoint to upgrade
    predicted_date = _third_wednesday(target.year, target.month)
    if cached and cached[0]:
        # Predicted entry exists. If target hasn't reached settlement, skip.
        try:
            stored_date = _dt.date.fromisoformat(cached[0])
        except ValueError:
            stored_date = predicted_date
        if target < stored_date:
            return {"predicted": True, "month": yyyymm,
                    "predicted_date": stored_date.isoformat()}
        # else: fall through to fetch & verify
    else:
        # Case 3: no entry → insert predicted
        with connect() as con:
            con.execute(
                """INSERT OR IGNORE INTO option_settlement_dates
                   (date, product, contract_month, settlement_price)
                   VALUES (?, 'TEO', ?, NULL)""",
                (predicted_date.isoformat(), yyyymm),
            )
        # If target hasn't reached predicted date, don't fetch
        if target < predicted_date:
            return {"predicted_inserted": True, "month": yyyymm,
                    "predicted_date": predicted_date.isoformat()}

    # Settlement should have happened — fetch endpoint to confirm/upgrade
    from io import StringIO
    import pandas as pd
    url = "https://www.taifex.com.tw/cht/5/optIndxFSP"
    # Query 9 months back so endpoint includes our target month (its quirk)
    sy, sm = target.year, target.month - 9
    while sm < 1:
        sy -= 1
        sm += 12
    payload = {
        "start_year": str(sy), "start_month": str(sm),
        "end_year": str(target.year), "end_month": str(target.month),
        "commodityIds": "8",
    }
    r = requests.post(url, data=payload, headers={"User-Agent": UA, "Referer": url},
                      timeout=30, verify=False)
    try:
        df = pd.read_html(StringIO(r.content.decode("utf-8", errors="replace")), flavor="lxml")[0]
    except (ValueError, IndexError):
        return {"fetched": True, "month": yyyymm, "note": "no_table"}
    if df.shape[1] < 2:
        return {"fetched": True, "month": yyyymm, "note": "empty_table"}
    df.columns = ["date", "contract"] + (["price"] if df.shape[1] >= 3 else [])
    month_only = df[df["contract"].astype(str).str.match(r"^\d{6}$")]
    n_upgraded = 0
    with connect() as con:
        for _, row in month_only.iterrows():
            iso = str(row["date"]).replace("/", "-")
            contract = str(row["contract"])
            price = None
            if "price" in row:
                p = row["price"]
                if isinstance(p, str):
                    price = float(p.replace(",", "")) if p not in ("-", "") else None
                elif isinstance(p, (int, float)) and not (isinstance(p, float) and p != p):
                    price = float(p)
            # If predicted entry exists for this month with different date,
            # delete it (calendar 預測 vs actual settlement may differ for 春節)
            con.execute(
                "DELETE FROM option_settlement_dates WHERE contract_month = ? AND product = 'TEO' AND date != ?",
                (contract, iso),
            )
            con.execute(
                """INSERT OR REPLACE INTO option_settlement_dates
                   (date, product, contract_month, settlement_price)
                   VALUES (?, 'TEO', ?, ?)""",
                (iso, contract, price),
            )
            n_upgraded += 1
    return {"fetched": True, "month": yyyymm, "rows_written": n_upgraded}


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _fetch_twii(target_date: str) -> dict[str, Any]:
    """加權指數 (TAIEX) close from FinMind TaiwanStockPrice."""
    r = requests.get(
        "https://api.finmindtrade.com/api/v4/data",
        params={"dataset": "TaiwanStockPrice", "data_id": "TAIEX",
                "start_date": target_date, "end_date": target_date},
        timeout=20, verify=False,
    )
    j = r.json()
    rows = j.get("data") or []
    for row in rows:
        if row.get("date") == target_date and row.get("close") is not None:
            return {"actual_date": target_date, "twii_close": float(row["close"])}
    return {"actual_date": None, "twii_close": None}


# 上櫃指數 (OTC index close) 由 tpex.fetch_highlight 一起回傳 ("收市指數" field).
# v0.10.42 起改用 TPEX 官方 highlight (避免 FinMind rate limit) — actual_date guard
# 在 write_to_db 內處理.


def _slash(date_dash: str) -> str:
    return date_dash.replace("-", "/")


def latest_likely_trading_date(today: date | None = None) -> str:
    """Pick most-recent weekday that is likely to have data (skip weekends).
    Holidays not handled — caller can override."""
    d = today or date.today()
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d.isoformat()


def catch_up_refresh(today: date | None = None) -> dict[str, Any]:
    """Catch-up mode: refresh all weekdays from (last_db_date + 1) to today.

    For users who haven't refreshed for several days. Auto-detects gaps
    and fills each one. Holidays naturally skip (endpoint returns no rows
    → daily_summary not written via the all-NULL guard).

    Per-day sanity check: row counts must match expected after refresh.
    Reports any day where data looks incomplete.
    """
    init_db()
    today = today or date.today()
    if today.weekday() >= 5:
        # Today is weekend — use last weekday
        while today.weekday() >= 5:
            today -= timedelta(days=1)

    # Find last date in DB
    with connect() as con:
        row = con.execute(
            "SELECT MAX(date) FROM op_legal WHERE daynight='day'"
        ).fetchone()
    last_db = row[0] if row and row[0] else None
    if not last_db:
        # Empty DB — just refresh today
        return {"mode": "single", "results": [refresh()]}

    last_d = date.fromisoformat(last_db)
    target_dates: list[str] = []
    cursor = last_d + timedelta(days=1)
    while cursor <= today:
        if cursor.weekday() < 5:  # weekday only (Mon-Fri)
            target_dates.append(cursor.isoformat())
        cursor += timedelta(days=1)

    # Always re-fetch today (today's data may still be evolving — partial release
    # in trading hours, late-night sessions, late-arriving credit/mkt_cap, etc).
    today_iso = today.isoformat()
    if today.weekday() < 5 and today_iso not in target_dates:
        target_dates.append(today_iso)
    # Also re-refresh last_db — its **night session** (T 日夜盤 = T 15:00 ~ T+1
    # 05:00) only releases ~05:30 next morning, which falls AFTER last_db was
    # first ingested. Without re-refresh, "T 日夜盤" rows are permanently
    # missing from op_legal/fut_legal. Same applies to late-arriving credit /
    # mkt_cap on T (sometimes hours after close).
    if last_db not in target_dates and last_db != today_iso:
        target_dates.insert(0, last_db)

    if not target_dates:
        return {"mode": "no_op", "last_db": last_db, "today": today.isoformat(),
                "message": "DB already up-to-date (today is weekend)"}

    log.info("catch-up: %d weekdays from %s to %s",
             len(target_dates), target_dates[0], target_dates[-1])

    SNAPSHOT_COLS = ("tx_close", "twii_close", "twse_margin_amt_oku",
                     "tpex_margin_amt_oku", "twse_mkt_cap_chao",
                     "tpex_mkt_cap_chao", "op_call_net", "op_put_net",
                     "stock_fut_legal_net")

    results = []
    for d in target_dates:
        # Snapshot before — so we can detect endpoint vs DB conflict
        with connect() as con:
            con.row_factory = sqlite3.Row
            before_row = con.execute(
                f"SELECT {', '.join(SNAPSHOT_COLS)} FROM daily_summary WHERE date=?",
                (d,)
            ).fetchone()
            con.row_factory = None
        before = dict(before_row) if before_row else {}

        out = refresh(d)

        # Sanity: row counts
        with connect() as con:
            con.row_factory = sqlite3.Row
            op_n = con.execute(
                "SELECT COUNT(*) FROM op_legal WHERE date=? AND daynight='day'", (d,)
            ).fetchone()[0]
            fut_n = con.execute(
                "SELECT COUNT(*) FROM fut_legal WHERE date=? AND daynight='day'", (d,)
            ).fetchone()[0]
            after_row = con.execute(
                f"SELECT {', '.join(SNAPSHOT_COLS)} FROM daily_summary WHERE date=?",
                (d,)
            ).fetchone()
            con.row_factory = None
        after = dict(after_row) if after_row else {}

        # Conflict detection: compare before vs after for each col
        conflicts = []
        for col in SNAPSHOT_COLS:
            v_before = before.get(col)
            v_after = after.get(col)
            if v_before is None or v_after is None:
                continue
            if isinstance(v_before, (int, float)) and isinstance(v_after, (int, float)):
                # Tolerance: 0.5% relative diff
                if v_before == 0:
                    if abs(v_after) > 0.5:
                        conflicts.append({"col": col, "old": v_before, "new": v_after})
                elif abs(v_after - v_before) / abs(v_before) > 0.005:
                    conflicts.append({"col": col, "old": v_before, "new": v_after})

        if op_n == 0 and fut_n == 0:
            out["status"] = "skipped (holiday or pre-release)"
        elif not after:
            out["status"] = f"INCOMPLETE (op={op_n}, fut={fut_n}) - daily_summary not generated"
        else:
            out["status"] = f"ok (op={op_n} fut={fut_n})"
        out["target_date"] = d
        out["conflicts"] = conflicts  # always populated
        results.append(out)

    # Run outlier detection on the freshly-touched dates
    suspicious = []
    if target_dates:
        suspicious = _audit_recent_dates(target_dates)

    return {
        "mode": "catch_up",
        "last_db": last_db,
        "today": today.isoformat(),
        "weekdays_checked": len(target_dates),
        "results": results,
        "outlier_audit": suspicious,
    }


def _audit_recent_dates(dates: list[str]) -> list[dict]:
    """Run outlier detection on a list of dates. Returns list of suspicious cells.

    Checks:
    - mkt_cap day-over-day (vs TWII)
    - margin day-over-day (vs TWII)
    """
    if not dates:
        return []
    issues = []
    with connect() as con:
        for d in dates:
            r = con.execute(
                """SELECT date, twii_close, twse_mkt_cap_chao, twse_margin_amt_oku,
                       (SELECT twii_close FROM daily_summary WHERE date < ? ORDER BY date DESC LIMIT 1) AS prev_twii,
                       (SELECT twse_mkt_cap_chao FROM daily_summary WHERE date < ? ORDER BY date DESC LIMIT 1) AS prev_mc,
                       (SELECT twse_margin_amt_oku FROM daily_summary WHERE date < ? ORDER BY date DESC LIMIT 1) AS prev_margin
                   FROM daily_summary WHERE date=?""",
                (d, d, d, d)
            ).fetchone()
            if not r:
                continue
            cur_twii, cur_mc, cur_margin = r[1], r[2], r[3]
            prev_twii, prev_mc, prev_margin = r[4], r[5], r[6]
            # mkt_cap > 3% jump but TWII < 3% = suspicious
            if cur_mc and prev_mc and prev_twii and cur_twii:
                mc_pct = abs(cur_mc - prev_mc) / prev_mc
                tw_pct = abs(cur_twii - prev_twii) / prev_twii
                if mc_pct > 0.03 and abs(mc_pct - tw_pct) > 0.03:
                    issues.append({"date": d, "type": "mkt_cap_jump",
                                   "prev": prev_mc, "cur": cur_mc,
                                   "twii_change_pct": tw_pct * 100})
            # margin > 5% jump but TWII < 3% = suspicious
            if cur_margin and prev_margin and prev_twii and cur_twii:
                mg_pct = abs(cur_margin - prev_margin) / prev_margin
                tw_pct = abs(cur_twii - prev_twii) / prev_twii
                if mg_pct > 0.05 and tw_pct < 0.03:
                    issues.append({"date": d, "type": "margin_jump",
                                   "prev": prev_margin, "cur": cur_margin,
                                   "twii_change_pct": tw_pct * 100})
    return issues


def refresh(target_date: str | None = None) -> dict[str, Any]:
    """Fetch everything for target_date (YYYY-MM-DD). If None, use latest weekday."""
    init_db()
    target_date = target_date or latest_likely_trading_date()
    target_slash = _slash(target_date)
    started = time.time()
    errors: list[str] = []
    results: dict[str, Any] = {"target_date": target_date}

    def safe(name: str, fn, *args, **kwargs):
        try:
            results[name] = fn(*args, **kwargs)
            log.info("[ok] %s", name)
        except Exception as e:
            log.exception("[err] %s", name)
            errors.append(f"{name}: {e!r}")
            results[name] = {"error": str(e)}

    safe("op_day", taifex.fetch_op, target_slash, "day")
    safe("op_night", taifex.fetch_op, target_slash, "night")
    safe("fut_day", taifex.fetch_fut, target_slash, "day")
    safe("fut_night", taifex.fetch_fut, target_slash, "night")
    safe("fut_price", taifex.fetch_fut_price, target_slash, "TX")
    safe("fut_price_te", taifex.fetch_fut_price, target_slash, "TE")
    safe("fut_price_tf", taifex.fetch_fut_price, target_slash, "TF")
    safe("twse_credit", twse.fetch_credit, target_date)
    safe("twse_turnover", twse.fetch_turnover, target_date)
    safe("twse_mkt_cap", twse.fetch_mkt_cap, target_date)
    safe("tpex_credit", tpex.fetch_credit_summary, target_date)
    safe("tpex_market_stats", tpex.fetch_market_stats, target_date)
    safe("tpex_highlight", tpex.fetch_highlight, target_date)
    safe("twii_close", _fetch_twii, target_date)
    safe("settlement_dates", _maybe_fetch_settlement_dates, target_date)

    write_to_db(target_date, results)

    # Auto post-process: if mkt_cap was NOT obtained from official source for
    # this date (homeApi only gives 5-day window), interpolate it from the
    # nearest mkt_cap_weekly anchor + TWII ratio. Idempotent — won't touch
    # 'official' rows. Also recompute pct if we just got a new mkt_cap.
    try:
        _post_refresh_aggregate(target_date)
    except Exception as e:
        log.warning("post-refresh aggregate failed for %s: %r", target_date, e)
        errors.append(f"post_refresh: {e!r}")

    # 連假時 TAIFEX 把「假期前最後交易日的夜盤」label 在假日當天（該日只有 night、
    # 無 day）。自動把這些夜盤重貼回前一個交易日，符合柴柴/輝哥 Excel 慣例。
    try:
        _reattribute_cross_holiday_night()
    except Exception as e:
        log.warning("cross-holiday night reattribute failed: %r", e)
        errors.append(f"reattribute_night: {e!r}")

    elapsed = time.time() - started
    with connect() as con:
        con.execute(
            "INSERT INTO refresh_log (ts, target_date, ok, errors_json) VALUES (?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"),
             target_date, 1 if not errors else 0, json.dumps(errors, ensure_ascii=False)),
        )
    return {
        "target_date": target_date,
        "elapsed_sec": round(elapsed, 2),
        "errors": errors,
        "ok": not errors,
    }


def _post_refresh_aggregate(date_dash: str) -> None:
    """For target_date: if twse_mkt_cap_chao still NULL, interpolate via
    weekly anchor × (TWII_d / TWII_anchor). Then recompute margin_pct
    (margin_balance / mkt_cap) so the view doesn't show 0% when raw data
    just flowed in.
    """
    with connect() as con:
        row = con.execute(
            """SELECT twii_close, twse_mkt_cap_chao, mkt_cap_source,
                      twse_margin_amt_oku, tpex_margin_amt_oku
               FROM daily_summary WHERE date = ?""", (date_dash,)
        ).fetchone()
        if not row:
            return
        twii_d = row["twii_close"]
        mkt_cap = row["twse_mkt_cap_chao"]
        src = row["mkt_cap_source"]

        # 1. Interpolate mkt_cap if NULL & TWII available
        if mkt_cap is None and twii_d is not None:
            anchor = con.execute(
                """SELECT date, twse_mkt_cap_oku FROM mkt_cap_weekly
                   WHERE date >= ? AND date < date(?, '+8 days')
                   ORDER BY date LIMIT 1""", (date_dash, date_dash)
            ).fetchone() or con.execute(
                """SELECT date, twse_mkt_cap_oku FROM mkt_cap_weekly
                   WHERE date < ? ORDER BY date DESC LIMIT 1""", (date_dash,)
            ).fetchone()
            if anchor:
                anchor_twii = con.execute(
                    "SELECT twii_close FROM daily_summary WHERE date = ?", (anchor[0],)
                ).fetchone()
                if anchor_twii and anchor_twii[0] is not None:
                    new_chao = anchor[1] * (twii_d / anchor_twii[0]) / 10000.0
                    con.execute(
                        """UPDATE daily_summary
                           SET twse_mkt_cap_chao = ?, mkt_cap_source = 'interp'
                           WHERE date = ?""", (new_chao, date_dash)
                    )
                    mkt_cap = new_chao
                    src = "interp"

        # 2. Recompute pct from margin / mkt_cap
        if mkt_cap and mkt_cap > 0:
            if row["twse_margin_amt_oku"]:
                pct = row["twse_margin_amt_oku"] / (mkt_cap * 10000)  # both in 億
                con.execute(
                    "UPDATE daily_summary SET twse_margin_pct = ? WHERE date = ?",
                    (pct, date_dash),
                )
        log.info("post-refresh aggregate done: %s mkt_cap=%s src=%s",
                 date_dash, mkt_cap, src)


def _reattribute_cross_holiday_night() -> None:
    """連假時 TAIFEX 把「假期前最後交易日的夜盤」label 在假日當天（該日只有 night、
    無 day）。把這些夜盤 rows 搬回前一個有 day 的交易日，並重算該日 daily_summary
    的開盤前欄位。冪等：已正確的日子不動（沒有 night-without-day 就是 no-op）。
    """
    moved_to: set[str] = set()
    with connect() as con:
        # 「有 night 但完全沒有 day」= 假日吸收了夜盤
        holidays = [r[0] for r in con.execute("""
            SELECT DISTINCT n.date FROM (
                SELECT date FROM op_legal  WHERE daynight='night'
                UNION
                SELECT date FROM fut_legal WHERE daynight='night'
            ) n
            WHERE NOT EXISTS (SELECT 1 FROM op_legal  d WHERE d.date=n.date AND d.daynight='day')
              AND NOT EXISTS (SELECT 1 FROM fut_legal d WHERE d.date=n.date AND d.daynight='day')
            ORDER BY n.date
        """)]
        for h in holidays:
            prev = con.execute(
                "SELECT MAX(date) FROM op_legal WHERE date<? AND daynight='day'", (h,)
            ).fetchone()[0]
            if not prev:
                continue
            for tbl in ("op_legal", "fut_legal"):
                prev_has_night = con.execute(
                    f"SELECT 1 FROM {tbl} WHERE date=? AND daynight='night' LIMIT 1", (prev,)
                ).fetchone()
                if prev_has_night:
                    # prev 已有夜盤 → h 的是重複，刪掉避免 PK 衝突
                    con.execute(f"DELETE FROM {tbl} WHERE date=? AND daynight='night'", (h,))
                else:
                    con.execute(
                        f"UPDATE {tbl} SET date=? WHERE date=? AND daynight='night'", (prev, h)
                    )
            moved_to.add(prev)
        con.commit()

    # 夜盤搬動後，重算受影響交易日的 daily_summary 開盤前欄位（comprehensive 用到）。
    # 用 build_dashboard 的結果回寫，避免公式分叉。
    for prev in moved_to:
        try:
            _recompute_pre_open_fields(prev)
            log.info("reattributed cross-holiday night → %s", prev)
        except Exception as e:
            log.warning("recompute pre_open for %s failed: %r", prev, e)


def _recompute_pre_open_fields(date_dash: str) -> None:
    """夜盤搬動後，用 build_dashboard 重算 daily_summary 的 fut_pre_open_net /
    op_pre_open_cp_net（兩者皆含夜盤），保持與主表一致。"""
    from .dashboard import build_dashboard
    bd = build_dashboard(date_dash)
    tx = next((r for r in bd.get("rows", []) if r.get("product") == "台指期"), None)
    call = next((r for r in bd.get("rows", []) if r.get("product") == "買權CALL"), None)
    fut_pre = tx.get("pre_open_lots") if tx else None
    op_cp = call.get("pre_open_cp") if call else None
    with connect() as con:
        con.execute(
            "UPDATE daily_summary SET fut_pre_open_net=?, op_pre_open_cp_net=? WHERE date=?",
            (fut_pre, op_cp, date_dash),
        )
        con.commit()


def _safe_rows(payload: Any) -> list[dict]:
    if not isinstance(payload, dict) or "rows" not in payload:
        return []
    return payload["rows"]


def write_to_db(date_dash: str, results: dict[str, Any]) -> None:
    with connect() as con:
        # OP legal — day + night
        for tag, daynight in (("op_day", "day"), ("op_night", "night")):
            for row in _safe_rows(results.get(tag)):
                con.execute("""
                    INSERT OR REPLACE INTO op_legal
                    (date, daynight, product, callput, role,
                     buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt,
                     oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt,
                     oi_net_lots, oi_net_amt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date_dash, daynight,
                    row.get("product"), row.get("callput"), row.get("role"),
                    row.get("buy_lots"), row.get("buy_amt"),
                    row.get("sell_lots"), row.get("sell_amt"),
                    row.get("net_lots"), row.get("net_amt"),
                    row.get("oi_buy_lots"), row.get("oi_buy_amt"),
                    row.get("oi_sell_lots"), row.get("oi_sell_amt"),
                    row.get("oi_net_lots"), row.get("oi_net_amt"),
                ))

        # FUT legal — day + night
        for tag, daynight in (("fut_day", "day"), ("fut_night", "night")):
            for row in _safe_rows(results.get(tag)):
                con.execute("""
                    INSERT OR REPLACE INTO fut_legal
                    (date, daynight, product, role,
                     buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt,
                     oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt,
                     oi_net_lots, oi_net_amt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date_dash, daynight,
                    row.get("product"), row.get("role"),
                    row.get("buy_lots"), row.get("buy_amt"),
                    row.get("sell_lots"), row.get("sell_amt"),
                    row.get("net_lots"), row.get("net_amt"),
                    row.get("oi_buy_lots"), row.get("oi_buy_amt"),
                    row.get("oi_sell_lots"), row.get("oi_sell_amt"),
                    row.get("oi_net_lots"), row.get("oi_net_amt"),
                ))

        # FUT price — TX (台指) + TE (電子) + TF (金融) all flow into fut_price
        # table; row.contract column distinguishes (TX/MTX/TE/TF/etc).
        for tag in ("fut_price", "fut_price_te", "fut_price_tf"):
            fp = results.get(tag) or {}
            fp_actual = fp.get("actual_date") or date_dash
            for row in _safe_rows(fp):
                con.execute("""
                    INSERT OR REPLACE INTO fut_price
                    (date, contract, expiry, open_, high, low, close,
                     change_str, change_pct_str, ah_vol, day_vol, total_vol,
                     settle, oi, best_bid, best_ask)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fp_actual, row.get("contract"), row.get("expiry"),
                    row.get("open_"), row.get("high"), row.get("low"), row.get("close"),
                    row.get("change_str"), row.get("change_pct_str"),
                    row.get("ah_vol"), row.get("day_vol"), row.get("total_vol"),
                    row.get("settle"), row.get("oi"),
                    row.get("best_bid"), row.get("best_ask"),
                ))

        # TWSE credit
        cr = results.get("twse_credit") or {}
        for row in _safe_rows(cr):
            con.execute("""
                INSERT OR REPLACE INTO credit_twse
                (date, item, buy, sell, repay, prev_balance, today_balance)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                date_dash, row.get("item"),
                row.get("buy"), row.get("sell"), row.get("repay"),
                row.get("prev_balance"), row.get("today_balance"),
            ))

        # credit_summary — guard mkt_cap because that endpoint is "today only"
        twse_margin_thousand = (results.get("twse_credit") or {}).get("twse_margin_balance_thousand")
        twse_turnover = (results.get("twse_turnover") or {}).get("turnover")
        twse_mkt_meta = results.get("twse_mkt_cap") or {}
        target_md = "/".join(date_dash.split("-")[1:]) if date_dash else None
        twse_mkt_cap_oku = (twse_mkt_meta.get("mkt_cap_oku")
                            if twse_mkt_meta.get("actual_md") == target_md else None)
        tpex_margin_thousand = (results.get("tpex_credit") or {}).get("tpex_margin_balance_thousand")
        tpex_turnover = (results.get("tpex_market_stats") or {}).get("tpex_turnover")
        tpex_mkt_cap_million = (results.get("tpex_highlight") or {}).get("tpex_mkt_cap_million")
        con.execute("""
            INSERT OR REPLACE INTO credit_summary
            (date, twse_margin_balance, twse_turnover, twse_mkt_cap,
             tpex_margin_balance, tpex_turnover, tpex_mkt_cap)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            date_dash,
            twse_margin_thousand, twse_turnover, twse_mkt_cap_oku,
            tpex_margin_thousand, tpex_turnover, tpex_mkt_cap_million,
        ))

        # daily_summary aggregate row — merge instead of overwrite. Critical:
        # SQLite INSERT OR REPLACE wipes ALL columns not in the cols list, so
        # twii_close / mkt_cap_source must be IN the cols list with carry-over,
        # otherwise refresh() destroys those fields each time.
        summary = compute_daily_summary(date_dash, results)
        # Codex 2026-05-07 16:40:44 +08:00: added TWII plausibility guard.
        # TWII: prefer TWSE FMTQIK (in fetch_turnover payload), fall back to
        # FinMind. Guard against stale/misaligned endpoint values by comparing
        # with TX close; the cash index and TX close should not be wildly apart.
        twii_from_turnover = (results.get("twse_turnover") or {}).get("twii_close")
        twii_from_finmind = (results.get("twii_close") or {}).get("twii_close")
        tx_close = summary.get("tx_close")

        def _plausible_twii(v: Any) -> bool:
            if v is None:
                return False
            if tx_close is None:
                return True
            return abs(float(v) - float(tx_close)) / float(tx_close) <= 0.2

        twii_v = twii_from_turnover if _plausible_twii(twii_from_turnover) else None
        if twii_v is None and _plausible_twii(twii_from_finmind):
            twii_v = twii_from_finmind
        if (
            twii_v is None
            and (twii_from_turnover is not None or twii_from_finmind is not None)
        ):
            log.warning(
                "drop implausible twii_close for %s: twse=%s finmind=%s tx=%s",
                date_dash, twii_from_turnover, twii_from_finmind, tx_close,
            )
        summary["twii_close"] = twii_v
        # mkt_cap_source: 'official' if we just got it from homeApi, else None
        # (post-aggregate may set 'interp' after this write)
        if summary.get("twse_mkt_cap_chao") is not None:
            summary["mkt_cap_source"] = "official"
        # 上櫃指數收盤 — 從 tpex.fetch_highlight 取「收市指數」, 但只有 highlight
        # actual_date 跟 target_date 一致才寫 (防 endpoint 回 stale day, v2.08 教訓)
        tp_h = results.get("tpex_highlight") or {}
        if tp_h.get("actual_date") == date_dash:
            summary["tpex_index_close"] = tp_h.get("tpex_index_close")

        # Codex 2026-05-07 16:40:44 +08:00: summary completeness follows
        # comprehensive-view fields, not the total TAIFEX fut product count.
        # Day-session completeness check.
        # The comprehensive table only needs the core summary fields below.
        # Do not depend on total fut_legal product count because TAIFEX can add,
        # remove, or omit unrelated products without affecting this view.
        op_day_count = con.execute(
            "SELECT COUNT(*) FROM op_legal WHERE date=? AND daynight='day'",
            (date_dash,)
        ).fetchone()[0]
        required_summary_fields = (
            "op_legal_net",
            "op_call_net",
            "op_put_net",
            "op_cp_net",
            "stock_fut_legal_net",
        )
        day_complete = (
            op_day_count >= 30
            and all(summary.get(c) is not None for c in required_summary_fields)
        )

        existing = con.execute(
            "SELECT * FROM daily_summary WHERE date = ?", (date_dash,)
        ).fetchone()
        cols = ["tx_close", "op_legal_net", "op_call_net", "op_put_net", "op_cp_net",
                "op_pre_open_cp_net", "fut_pre_open_net", "stock_fut_legal_net",
                "twse_margin_pct", "tpex_margin_pct",
                "twse_margin_amt_oku", "tpex_margin_amt_oku",
                "twse_mkt_cap_chao", "tpex_mkt_cap_chao",
                "twii_close", "mkt_cap_source", "tpex_index_close"]
        if not day_complete:
            # 日盤未收盤 → 不寫 daily_summary (= 不在綜合整理出現). 若已有 row,
            # 一併清掉 (e.g. 早上 refresh 不小心寫進去過).
            if existing:
                con.execute("DELETE FROM daily_summary WHERE date = ?", (date_dash,))
        else:
            merged = {}
            for c in cols:
                new_val = summary.get(c)
                old_val = existing[c] if existing else None
                merged[c] = new_val if new_val is not None else old_val
            # Skip writing the row if it would be all-NULL (e.g. backfilling a
            # holiday — no point creating an empty placeholder).
            if any(v is not None for v in merged.values()):
                con.execute(f"""
                    INSERT OR REPLACE INTO daily_summary
                    (date, {", ".join(cols)})
                    VALUES (?, {", ".join("?" * len(cols))})
                """, (date_dash, *[merged[c] for c in cols]))
            elif existing:
                con.execute("DELETE FROM daily_summary WHERE date = ?", (date_dash,))


def compute_daily_summary(target_date: str, results: dict[str, Any]) -> dict[str, Any]:
    """Aggregate today's raw fetch into the 14-column daily_summary row.

    Definitions (cross-checked against Excel 「綜合整理」 sheet):
      op_call_net = sum(oi_net_lots) where product=臺指選擇權, callput=買權, all 3 roles
      op_put_net  = sum(oi_net_lots) where product=臺指選擇權, callput=賣權, all 3 roles
      op_cp_net   = op_call_net - op_put_net
      stock_fut_legal_net = sum(oi_net_lots) where product=股票期貨, all 3 roles
      tx_close   = TX nearest-month close (smallest expiry like '202605')
      twse_margin_amt_oku = twse_margin_thousand / 100000  (仟元 → 億元)
      tpex_margin_amt_oku = tpex_margin_thousand / 100000
      twse_margin_pct     = twse_margin_amt_oku / (twse_mkt_cap_oku)
      tpex_margin_pct     = tpex_margin_thousand_in_oku / (tpex_mkt_cap_oku from million)
      twse_mkt_cap_chao   = twse_mkt_cap_oku / 10000   (億元 → 兆元)
      tpex_mkt_cap_chao   = tpex_mkt_cap_million / 1_000_000  (佰萬元 → 兆元)
    """
    out: dict[str, Any] = {}

    # op_call_net / op_put_net  — Excel uses 外資 + 自營商 only (excludes 投信),
    # verified by cross-check on 2026-04-15 (1412 = 外資 824 + 自營商 588).
    op_rows = _safe_rows(results.get("op_day"))
    LEGAL_ROLES = {"外資", "自營商"}
    call_net, put_net = 0, 0
    has_call, has_put = False, False
    for r in op_rows:
        if r.get("product") != "臺指選擇權" or r.get("role") not in LEGAL_ROLES:
            continue
        v = r.get("oi_net_lots")
        if v is None:
            continue
        if r.get("callput") == "買權":
            call_net += v
            has_call = True
        elif r.get("callput") == "賣權":
            put_net += v
            has_put = True
    out["op_call_net"] = call_net if has_call else None
    out["op_put_net"] = put_net if has_put else None
    if has_call and has_put:
        out["op_cp_net"] = call_net - put_net

    # stock_fut_legal_net — same convention: 外資 + 自營商 only
    fut_rows = _safe_rows(results.get("fut_day"))
    sf = 0
    has_sf = False
    for r in fut_rows:
        if r.get("product") == "股票期貨" and r.get("role") in LEGAL_ROLES:
            v = r.get("oi_net_lots")
            if v is not None:
                sf += v
                has_sf = True
    out["stock_fut_legal_net"] = sf if has_sf else None

    # op_legal_net (台指期等效大台 OI 淨) = 大台 OI + 小台 OI/4 + 微台 OI/20
    # fut_pre_open_net = op_legal_net + 同樣 components 的夜盤 net_lots
    MICRO_TX_LAUNCH = "2022-03-28"
    has_micro = target_date >= MICRO_TX_LAUNCH
    tx_components = [("臺股期貨", 1.0), ("小型臺指期貨", 4.0)]
    if has_micro:
        tx_components.append(("微型臺指期貨", 20.0))

    fut_night_rows = _safe_rows(results.get("fut_night"))
    tx_oi = 0.0
    tx_night = 0.0
    has_tx_oi = False
    has_tx_night = False
    for product, factor in tx_components:
        for r in fut_rows:
            if r.get("product") == product and r.get("role") in LEGAL_ROLES:
                v = r.get("oi_net_lots")
                if v is not None:
                    tx_oi += v / factor
                    has_tx_oi = True
        for r in fut_night_rows:
            if r.get("product") == product and r.get("role") in LEGAL_ROLES:
                v = r.get("net_lots")
                if v is not None:
                    tx_night += v / factor
                    has_tx_night = True
    out["op_legal_net"] = round(tx_oi, 2) if has_tx_oi else None
    out["fut_pre_open_net"] = (
        round(tx_oi + tx_night) if (has_tx_oi or has_tx_night) else None
    )

    # op_pre_open_cp_net = (CALL OI day + CALL night net) - (PUT OI day + PUT night net)
    # NULL if no night data (TAIFEX endpoint cutoff = 2023/05/05)
    op_night_rows = _safe_rows(results.get("op_night"))
    night_call, night_put = 0, 0
    has_night_call, has_night_put = False, False
    for r in op_night_rows:
        if r.get("product") != "臺指選擇權" or r.get("role") not in LEGAL_ROLES:
            continue
        v = r.get("net_lots")
        if v is None:
            continue
        if r.get("callput") == "買權":
            night_call += v
            has_night_call = True
        elif r.get("callput") == "賣權":
            night_put += v
            has_night_put = True
    has_op_night = has_night_call or has_night_put
    if has_call and has_put and has_op_night:
        out["op_pre_open_cp_net"] = (call_net + night_call) - (put_net + night_put)

    # tx_close — only write if fut_price actual date matches the target;
    # the GET-only futDailyMarketExcel always returns TODAY, so a backfill
    # call with target=2026-04-30 must NOT inherit today's close.
    fp = results.get("fut_price") or {}
    if fp.get("actual_date") == target_date:
        fp_rows = _safe_rows(fp)
        tx_rows = sorted(
            (r for r in fp_rows if r.get("contract") == "TX" and r.get("expiry")),
            key=lambda r: r["expiry"],
        )
        if tx_rows:
            out["tx_close"] = tx_rows[0].get("close")

    # margin / mkt cap
    twse_thousand = (results.get("twse_credit") or {}).get("twse_margin_balance_thousand")
    tpex_thousand = (results.get("tpex_credit") or {}).get("tpex_margin_balance_thousand")
    tpex_mkt_million = (results.get("tpex_highlight") or {}).get("tpex_mkt_cap_million")
    # twse_mkt_cap from homeApi is "today only" — only honor if actual_md
    # matches MM/DD of target_date.
    twse_mkt_meta = results.get("twse_mkt_cap") or {}
    target_md = "/".join(target_date.split("-")[1:]) if target_date else None
    twse_mkt_oku = twse_mkt_meta.get("mkt_cap_oku") if twse_mkt_meta.get("actual_md") == target_md else None

    if twse_thousand is not None:
        out["twse_margin_amt_oku"] = twse_thousand / 100000  # 仟元→億元
    if tpex_thousand is not None:
        out["tpex_margin_amt_oku"] = tpex_thousand / 100000
    if twse_mkt_oku is not None:
        out["twse_mkt_cap_chao"] = twse_mkt_oku / 10000  # 億元→兆元
    if tpex_mkt_million is not None:
        out["tpex_mkt_cap_chao"] = tpex_mkt_million / 1_000_000  # 佰萬元→兆元
    if twse_thousand and twse_mkt_oku:
        out["twse_margin_pct"] = (twse_thousand / 100000) / twse_mkt_oku
    if tpex_thousand and tpex_mkt_million:
        out["tpex_margin_pct"] = (tpex_thousand / 100000) / (tpex_mkt_million / 100)

    return out
