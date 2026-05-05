"""TAIFEX scrapers — 5 endpoints."""
from __future__ import annotations
import re
import time
import logging
from io import StringIO
from typing import Any
import pandas as pd
import requests

log = logging.getLogger(__name__)

BASE = "https://www.taifex.com.tw/cht/3"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT = 30


def _post_html(path: str, query_date: str) -> str:
    """POST to a TAIFEX endpoint that supports queryDate."""
    url = f"{BASE}/{path}"
    payload = {
        "queryDate": query_date,
        "commodityId": "",
        "MarketCode": "0",
        "queryType": "1",
    }
    headers = {
        "User-Agent": UA,
        "Referer": url,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            r = requests.post(url, data=payload, headers=headers, timeout=TIMEOUT)
            r.raise_for_status()
            r.encoding = "utf-8"
            return r.text
        except Exception as e:  # network hiccup
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"POST {url} failed after retries: {last_err}")


def _get_html(path: str) -> str:
    url = f"{BASE}/{path}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def _extract_response_date(html: str) -> str | None:
    """Find the actual data date in the response (e.g., '日期2026/04/30')."""
    m = re.search(r"日期[：:\s]*(\d{4}/\d{1,2}/\d{1,2})", html)
    if not m:
        return None
    y, mo, d = m.group(1).split("/")
    return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"


def _to_int(v: Any) -> int | None:
    if v is None or pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _parse_legal_table(html: str, expect_oi: bool) -> list[dict]:
    """
    Parse the 三大法人 table for both OP and FUT pages.
    expect_oi = True for day session (has 未平倉餘額 columns).
    Returns flat rows; OP: row per (product, callput, role); FUT: row per (product, role).
    """
    try:
        dfs = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        return []  # no table — future date / holiday / empty session
    if not dfs:
        return []
    df = dfs[0]
    if len(df) == 0 or len(df.columns) < 4:
        return []
    # multiindex cols → positional access
    # OP columns layout:
    #   day:   [0]序號 [1]商品名稱 [2]權別 [3]身份別  [4-9] 交易口數買方/賣方/差額 ×{口數,金額}  [10-15] 未平倉×6
    #   night: [0]序號 [1]商品名稱 [2]權別 [3]身份別  [4-9] 交易口數×6   (no 未平倉)
    # FUT columns layout:
    #   day:   [0]序號 [1]商品名稱       [2]身份別  [3-8] 交易口數×6     [9-14] 未平倉×6
    #   night: [0]序號 [1]商品名稱       [2]身份別  [3-8] 交易口數×6     (no 未平倉)
    rows: list[dict] = []
    cols = df.columns.tolist()
    is_op = "權" in str(cols[2])
    role_col = 3 if is_op else 2
    trade_start = 4 if is_op else 3
    oi_start = trade_start + 6  # 6 trade cols, then OI

    for _, row in df.iterrows():
        product = str(row.iloc[1]).strip()
        if not product or product == "nan":
            continue
        role = str(row.iloc[role_col]).strip()
        if role in ("nan", "小計", ""):
            continue

        rec: dict[str, Any] = {
            "product": product,
            "role": role,
            "buy_lots": _to_int(row.iloc[trade_start]),
            "buy_amt": _to_int(row.iloc[trade_start + 1]),
            "sell_lots": _to_int(row.iloc[trade_start + 2]),
            "sell_amt": _to_int(row.iloc[trade_start + 3]),
            "net_lots": _to_int(row.iloc[trade_start + 4]),
            "net_amt": _to_int(row.iloc[trade_start + 5]),
        }
        if is_op:
            rec["callput"] = str(row.iloc[2]).strip()
        if expect_oi and len(cols) >= oi_start + 6:
            rec.update({
                "oi_buy_lots": _to_int(row.iloc[oi_start]),
                "oi_buy_amt": _to_int(row.iloc[oi_start + 1]),
                "oi_sell_lots": _to_int(row.iloc[oi_start + 2]),
                "oi_sell_amt": _to_int(row.iloc[oi_start + 3]),
                "oi_net_lots": _to_int(row.iloc[oi_start + 4]),
                "oi_net_amt": _to_int(row.iloc[oi_start + 5]),
            })
        rows.append(rec)
    return rows


def _next_business_day(query_date_slash: str) -> str:
    """'2026/04/14' -> next trading day, **holiday-aware** via DB lookup.

    Falls back to next weekday if DB lookup fails (e.g. before DB is built).
    Holiday-aware needed because TAIFEX night endpoint uses session-end date
    as queryDate; cross-holiday sessions must point at the next trading day,
    not just the next weekday.
    """
    import datetime as dt
    y, m, d = (int(x) for x in query_date_slash.split("/"))
    base = dt.date(y, m, d)
    # Try DB lookup first (only available when called from app context)
    try:
        from ..db import connect
        with connect() as con:
            row = con.execute(
                "SELECT MIN(date) FROM op_legal WHERE date > ? AND daynight='day'",
                (base.isoformat(),)
            ).fetchone()
        if row and row[0]:
            y2, m2, d2 = row[0].split("-")
            return f"{y2}/{m2}/{d2}"
    except Exception:
        pass
    # Fallback: next weekday (holiday will be re-handled later via sweep)
    nxt = base + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return f"{nxt.year:04d}/{nxt.month:02d}/{nxt.day:02d}"


def fetch_op(query_date: str, daynight: str) -> dict[str, Any]:
    """daynight: 'day' or 'night'.

    NB: TAIFEX night endpoint uses *session-end date* as the label. So when the
    caller wants the "T 日夜盤" (T 15:00 ~ T+1 05:00) — which matches the local
    convention (柴柴 / 輝哥 Excel labels it 「T 日夜盤」) — we POST queryDate=T+1
    but record the session against T.
    """
    path = "callsAndPutsDate" if daynight == "day" else "callsAndPutsDateAh"
    api_date = query_date if daynight == "day" else _next_business_day(query_date)
    html = _post_html(path, api_date)
    actual = _extract_response_date(html)
    rows = _parse_legal_table(html, expect_oi=(daynight == "day"))
    return {
        "actual_date": actual,           # what TAIFEX labels (= T+1 for night)
        "session_date": query_date.replace("/", "-"),  # local convention (= T)
        "rows": rows,
        "endpoint": path,
        "daynight": daynight,
    }


def fetch_fut(query_date: str, daynight: str) -> dict[str, Any]:
    path = "futContractsDate" if daynight == "day" else "futContractsDateAh"
    api_date = query_date if daynight == "day" else _next_business_day(query_date)
    html = _post_html(path, api_date)
    actual = _extract_response_date(html)
    rows = _parse_legal_table(html, expect_oi=(daynight == "day"))
    return {
        "actual_date": actual,
        "session_date": query_date.replace("/", "-"),
        "rows": rows,
        "endpoint": path,
        "daynight": daynight,
    }


def fetch_fut_price(query_date: str | None = None) -> dict[str, Any]:
    """台指期 TX 各到期月收盤。

    If query_date (YYYY/MM/DD) is given → POST /cht/3/futDailyMarketReport
        (honors date, supports backfill).
    Else → GET /cht/3/futDailyMarketExcel (only today, kept as fast path).
    """
    if query_date:
        url = f"{BASE}/futDailyMarketReport"
        payload = {
            "queryDate": query_date,
            "MarketCode": "0",
            "commodity_id": "TX",
            "queryType": "1",
        }
        headers = {
            "User-Agent": UA,
            "Referer": url,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        last_err: Exception | None = None
        html = ""
        for attempt in range(3):
            try:
                r = requests.post(url, data=payload, headers=headers, timeout=TIMEOUT)
                r.raise_for_status()
                r.encoding = "utf-8"
                html = r.text
                break
            except Exception as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        if not html:
            raise RuntimeError(f"POST {url} failed: {last_err}")
    else:
        html = _get_html("futDailyMarketExcel")
    actual = _extract_response_date(html)
    try:
        dfs = pd.read_html(StringIO(html), flavor="lxml")
    except ValueError:
        return {"actual_date": actual, "rows": []}
    if not dfs:
        return {"actual_date": actual, "rows": []}
    df = dfs[0]
    # cols: 契約 / 到期月份(週別) / 開盤 / 最高 / 最低 / 最後成交 / 漲跌價 / 漲跌% /
    #       盤後成交量 / 一般成交量 / 合計成交量 / 結算價 / 未沖銷契約量 / 最後最佳買 / 最後最佳賣 /
    #       歷史最高 / 歷史最低
    rows: list[dict] = []
    for _, r in df.iterrows():
        contract = str(r.iloc[0]).strip()
        if not contract or contract.lower() == "nan" or "小計" in contract:
            continue
        expiry_raw = r.iloc[1]
        if isinstance(expiry_raw, float) and not pd.isna(expiry_raw):
            expiry = str(int(expiry_raw))
        else:
            expiry = str(expiry_raw).strip()
        rows.append({
            "contract": contract,
            "expiry": expiry,
            "open_": _to_int(r.iloc[2]),
            "high": _to_int(r.iloc[3]),
            "low": _to_int(r.iloc[4]),
            "close": _to_int(r.iloc[5]),
            "change_str": str(r.iloc[6]).strip() if not pd.isna(r.iloc[6]) else None,
            "change_pct_str": str(r.iloc[7]).strip() if not pd.isna(r.iloc[7]) else None,
            "ah_vol": _to_int(r.iloc[8]),
            "day_vol": _to_int(r.iloc[9]),
            "total_vol": _to_int(r.iloc[10]),
            "settle": _to_int(r.iloc[11]),
            "oi": _to_int(r.iloc[12]),
            "best_bid": _to_int(r.iloc[13]),
            "best_ask": _to_int(r.iloc[14]),
        })
    return {"actual_date": actual, "rows": rows}
