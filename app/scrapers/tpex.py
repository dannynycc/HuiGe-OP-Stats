"""TPEX scrapers — 3 endpoints (融資 CSV, 市場成交 JSON, 重點 JSON)."""
from __future__ import annotations
import csv
import logging
import re
from io import StringIO
from typing import Any
import requests
import urllib3

log = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT = 30
VERIFY = False  # tpex.org.tw uses Chunghwa Telecom CA, not in certifi
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _to_float(s: Any) -> float | None:
    if s is None:
        return None
    txt = str(s).replace(",", "").replace('"', "").strip()
    if txt in ("", "-", "--"):
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def _roc_str(date_dash: str) -> str:
    """'2026-04-30' -> '115/04/30'"""
    y, m, d = date_dash.split("-")
    return f"{int(y) - 1911}/{m}/{d}"


def _date_url_param(date_dash: str) -> str:
    """'2026-04-30' -> '2026%2F04%2F30'"""
    y, m, d = date_dash.split("-")
    return f"{y}%2F{m}%2F{d}"


def fetch_credit_summary(date_dash: str) -> dict[str, Any]:
    """
    Returns 上櫃融資餘額（仟元）— from the last summary line of margin_bal_result CSV.
    Line we want: 融資金(仟元),,prev_bal,buy,sell,repay,today_bal,...
    """
    roc = _roc_str(date_dash)
    url = (
        "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"
        f"?l=zh-tw&o=csv&d={roc}&s=0,asc,0"
    )
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, verify=VERIFY)
    r.raise_for_status()
    text = r.content.decode("big5", errors="replace")
    actual_date = None
    m = re.search(r"資料日期[：:]\s*(\d+)/(\d+)/(\d+)", text)
    if m:
        roc_y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        actual_date = f"{roc_y + 1911:04d}-{mo:02d}-{d:02d}"
    margin_balance: float | None = None
    for line in StringIO(text):
        if "融資金(仟元)" in line:
            cols = next(csv.reader([line]))
            # cols index: 0=融資金(仟元), 1=空, 2=前資餘額, 3=資買, 4=資賣, 5=現償, 6=資餘額(today_balance)
            if len(cols) > 6:
                margin_balance = _to_float(cols[6])
            break
    return {"actual_date": actual_date, "tpex_margin_balance_thousand": margin_balance}


def fetch_market_stats(date_dash: str) -> dict[str, Any]:
    """
    上櫃證券成交統計 — total turnover at summary 總計(1~10).
    Modern API: { tables:[ { fields, data, summary } ] }
    """
    url = (
        f"https://www.tpex.org.tw/www/zh-tw/afterTrading/marketStats"
        f"?type=Daily&date={_date_url_param(date_dash)}&id=&response=json"
    )
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, verify=VERIFY)
    r.raise_for_status()
    j = r.json()
    if j.get("stat") != "ok" or not j.get("tables"):
        return {"actual_date": None, "tpex_turnover": None, "rows": []}
    tab = j["tables"][0]
    actual_date = None
    raw_date = tab.get("date")
    if raw_date:
        m = re.match(r"(\d+)/(\d+)/(\d+)", raw_date)
        if m:
            roc_y = int(m.group(1))
            actual_date = f"{roc_y + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    total_turnover: float | None = None
    for srow in (tab.get("summary") or []):
        if "總計(1~10)" in srow[0]:
            total_turnover = _to_float(srow[1])
            break
    return {
        "actual_date": actual_date,
        "tpex_turnover": total_turnover,
        "rows": tab.get("data", []),
        "summary": tab.get("summary", []),
    }


def fetch_highlight(date_dash: str) -> dict[str, Any]:
    """上櫃當日彙總 — 總市值(佰萬元) at fields/data."""
    url = (
        f"https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight"
        f"?date={_date_url_param(date_dash)}&id=&response=json"
    )
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, verify=VERIFY)
    r.raise_for_status()
    j = r.json()
    if j.get("stat") != "ok" or not j.get("tables"):
        return {"actual_date": None, "tpex_mkt_cap_million": None}
    tab = j["tables"][0]
    actual_date = None
    raw_date = tab.get("date")
    if raw_date:
        m = re.match(r"(\d+)/(\d+)/(\d+)", raw_date)
        if m:
            roc_y = int(m.group(1))
            actual_date = f"{roc_y + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    fields: list[str] = tab.get("fields", [])
    rows = tab.get("data", [])
    mkt_cap_million: float | None = None
    if rows:
        try:
            idx = fields.index("總市值(佰萬元)")
            mkt_cap_million = _to_float(rows[0][idx])
        except (ValueError, IndexError):
            pass
    return {"actual_date": actual_date, "tpex_mkt_cap_million": mkt_cap_million}
