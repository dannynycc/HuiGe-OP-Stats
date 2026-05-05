"""Refresh orchestrator — runs all 12 scrapers for a target date and writes DB."""
from __future__ import annotations
import json
import logging
import time
from datetime import datetime, date, timedelta
from typing import Any
from .db import connect, init_db
from .scrapers import taifex, twse, tpex

log = logging.getLogger(__name__)


def _slash(date_dash: str) -> str:
    return date_dash.replace("-", "/")


def latest_likely_trading_date(today: date | None = None) -> str:
    """Pick most-recent weekday that is likely to have data (skip weekends).
    Holidays not handled — caller can override."""
    d = today or date.today()
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d -= timedelta(days=1)
    return d.isoformat()


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
    safe("fut_price", taifex.fetch_fut_price, target_slash)
    safe("twse_credit", twse.fetch_credit, target_date)
    safe("twse_turnover", twse.fetch_turnover, target_date)
    safe("twse_mkt_cap", twse.fetch_mkt_cap, target_date)
    safe("tpex_credit", tpex.fetch_credit_summary, target_date)
    safe("tpex_market_stats", tpex.fetch_market_stats, target_date)
    safe("tpex_highlight", tpex.fetch_highlight, target_date)

    write_to_db(target_date, results)

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

        # FUT price
        fp = results.get("fut_price") or {}
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

        # daily_summary aggregate row — merge instead of overwrite, so a fresh
        # refresh that can't get tx_close (fut_price endpoint = today only) will
        # not blank out a value previously imported from Excel.
        summary = compute_daily_summary(date_dash, results)
        existing = con.execute(
            "SELECT * FROM daily_summary WHERE date = ?", (date_dash,)
        ).fetchone()
        cols = ["tx_close", "op_legal_net", "op_call_net", "op_put_net", "op_cp_net",
                "fut_pre_open_net", "stock_fut_legal_net",
                "twse_margin_pct", "tpex_margin_pct",
                "twse_margin_amt_oku", "tpex_margin_amt_oku",
                "twse_mkt_cap_chao", "tpex_mkt_cap_chao"]
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
            # All inputs NULL but DB had an existing row — also clean it up
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
