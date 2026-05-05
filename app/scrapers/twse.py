"""TWSE scrapers — 3 endpoints (信用交易 CSV, 成交金額 JSON, 總市值 JSON)."""
from __future__ import annotations
import csv
import logging
from io import StringIO
from typing import Any
import requests
import urllib3

log = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
TIMEOUT = 30
# twse.com.tw uses a Chunghwa Telecom CA that certifi does not bundle, so
# requests fails verification while curl (system store) succeeds. Public data
# endpoints — fine to skip verification.
VERIFY = False
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


def _yyyymmdd(date_dash: str) -> str:
    """'2026-04-30' -> '20260430'"""
    return date_dash.replace("-", "")


def fetch_credit(date_dash: str) -> dict[str, Any]:
    """
    MI_MARGN — 上市信用交易. Returns first 5 summary rows:
       融資(交易單位) / 融券(交易單位) / 融資金額(仟元) / 融券金額(仟元) ...
    Big5 CSV.
    """
    yyyymmdd = _yyyymmdd(date_dash)
    url = (
        f"https://www.twse.com.tw/exchangeReport/MI_MARGN"
        f"?response=csv&date={yyyymmdd}&selectType=ALL"
    )
    headers = {
        "User-Agent": UA,
        "Referer": "https://www.twse.com.tw/zh/page/trading/exchange/MI_MARGN.html",
    }
    r = requests.get(url, headers=headers, timeout=TIMEOUT, verify=VERIFY)
    r.raise_for_status()
    text = r.content.decode("big5", errors="replace")
    if "融資" not in text:
        return {"actual_date": None, "rows": [], "twse_margin_balance_thousand": None}

    # First few lines = summary table; first line is title with date.
    reader = csv.reader(StringIO(text))
    lines = list(reader)
    rows: list[dict] = []
    margin_balance_thousand: float | None = None
    # Header row at index 1: 項目, 買進, 賣出, 現金(券)償還, 前日餘額, 今日餘額
    # Data rows 2..4 (3 rows): 融資(交易單位)/融券(交易單位)/融資金額(仟元)
    for line in lines[2:5]:
        if not line or not line[0].strip():
            continue
        item = line[0].strip()
        try:
            row = {
                "item": item,
                "buy": _to_float(line[1]),
                "sell": _to_float(line[2]),
                "repay": _to_float(line[3]),
                "prev_balance": _to_float(line[4]),
                "today_balance": _to_float(line[5]),
            }
        except IndexError:
            continue
        rows.append(row)
        if item == "融資金額(仟元)":
            margin_balance_thousand = row["today_balance"]

    # Date pattern in title: "115年04月30日 信用交易統計"
    actual_date = None
    if lines and lines[0]:
        import re
        m = re.search(r"(\d+)年(\d+)月(\d+)日", lines[0][0])
        if m:
            roc, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            actual_date = f"{roc + 1911:04d}-{mo:02d}-{d:02d}"

    return {
        "actual_date": actual_date,
        "rows": rows,
        "twse_margin_balance_thousand": margin_balance_thousand,
    }


def fetch_turnover(date_dash: str) -> dict[str, Any]:
    """FMTQIK — 上市成交金額 (whole-month, returns the last row matching date)."""
    yyyymmdd = _yyyymmdd(date_dash)
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={yyyymmdd}&response=json"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, verify=VERIFY)
    r.raise_for_status()
    j = r.json()
    if j.get("stat") != "OK":
        return {"actual_date": None, "turnover": None}
    # data: list of [日期, 成交股數, 成交金額, 成交筆數, 加權指數, 漲跌點數]
    # 日期 is ROC like "115/04/30"
    data = j.get("data", []) or []
    target_roc = f"{int(yyyymmdd[:4]) - 1911}/{yyyymmdd[4:6]}/{yyyymmdd[6:8]}"
    last_row = None
    for row in data:
        if row[0] == target_roc:
            last_row = row
            break
    if last_row is None and data:
        last_row = data[-1]
    if last_row is None:
        return {"actual_date": None, "turnover": None}
    actual_date = None
    parts = last_row[0].split("/")
    if len(parts) == 3:
        actual_date = f"{int(parts[0]) + 1911:04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    return {
        "actual_date": actual_date,
        "turnover": _to_float(last_row[2]),  # 成交金額 (元)
        "twii_close": _to_float(last_row[4]),  # 加權指數
    }


def fetch_mkt_cap(target_date_dash: str | None = None) -> dict[str, Any]:
    """homeApi/mkt_cap — 上市總市值. NB: this endpoint only ships the most recent
    ~5 trading days; older dates are unrecoverable from this URL.
    If target_date_dash given (YYYY-MM-DD) and matches an entry's MM/DD, return that one;
    otherwise return the last (latest) entry. The full array is included so a caller
    can verify whether the requested date was actually present.
    """
    url = "https://www.twse.com.tw/rwd/zh/homeApi/mkt_cap"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, verify=VERIFY)
    r.raise_for_status()
    arr = r.json() or []
    if not arr:
        return {"actual_md": None, "mkt_cap_oku": None, "available": []}
    target_md = None
    if target_date_dash:
        parts = target_date_dash.split("-")
        if len(parts) == 3:
            target_md = f"{parts[1]}/{parts[2]}"
    chosen = None
    if target_md:
        for entry in arr:
            if entry[0] == target_md:
                chosen = entry
                break
    chosen = chosen or arr[-1]
    return {
        "actual_md": chosen[0],
        "mkt_cap_oku": _to_float(chosen[1]),
        "available": [a[0] for a in arr],
    }
