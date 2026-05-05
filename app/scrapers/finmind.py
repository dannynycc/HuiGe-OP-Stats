"""FinMind data source — historical backfill for 2020-2023/05 era.

Limitations vs. native TAIFEX:
  - No daynight separation for institutional investor data (op/fut).
    All rows recorded as daynight='day'. Historical 夜盤 columns will be blank.
  - FinMind free tier covers index futures main contracts only:
    TX, MTX, TE, TF, GTF, XIF, SHF, SOF, SXF, SPF, UDF, UNF, BTF, SF, STF.
    Sub-products (微台 MXF, 小電, 小金) and individual stock futures are NOT
    available — these will simply not be backfilled.
  - TaiwanFuturesDaily DOES have trading_session (position/after_market) so
    fut_price 含夜盤 is supported.
"""
from __future__ import annotations
import logging
import time
from typing import Any
import requests
import urllib3

log = logging.getLogger(__name__)
BASE = "https://api.finmindtrade.com/api/v4/data"
UA = "Mozilla/5.0"
TIMEOUT = 30
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Mapping FinMind futures_id → TAIFEX/Excel product 中文名
FUT_ID_TO_PRODUCT = {
    "TX":  "臺股期貨",
    "MTX": "小型臺指期貨",
    "TE":  "電子期貨",
    "TF":  "金融期貨",
    "GTF": "櫃買期貨",
    "XIF": "非金電期貨",
    "SHF": "半導體30期貨",
    "SOF": "東證期貨",
    "SXF": "美國標普500期貨",
    "SPF": "美國費城半導體期貨",
    "UDF": "美國道瓊期貨",
    "UNF": "美國那斯達克100期貨",
    "BTF": "英國富時100期貨",
}
FUT_IDS_PRIMARY = ["TX", "MTX", "TE", "TF"]  # 主表必需的核心 4 個
FUT_IDS_ALL = list(FUT_ID_TO_PRODUCT.keys())


def _fetch(dataset: str, data_id: str, start_date: str, end_date: str,
           retries: int = 3) -> list[dict]:
    """Single FinMind API call. Returns rows or [] on error/empty."""
    params = {
        "dataset": dataset,
        "data_id": data_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(BASE, params=params, headers={"User-Agent": UA},
                             timeout=TIMEOUT, verify=False)
            r.raise_for_status()
            j = r.json()
            if j.get("status") == 200 and j.get("msg") in ("success", None):
                return j.get("data", []) or []
            else:
                # Free-tier limit / dataset rejection — return [] silently
                return []
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    log.warning("FinMind %s data_id=%s failed after %d retries: %s",
                dataset, data_id, retries, last_err)
    return []


def fetch_op_institutional(start_date: str, end_date: str) -> list[dict]:
    """TaiwanOptionInstitutionalInvestors → list of normalized op_legal rows.

    Schema mapping (FinMind → DB column):
      option_id 'TXO'                                   → product '臺指選擇權'
      call_put '買權'/'賣權'                            → callput
      institutional_investors '自營商'/'投信'/'外資'    → role
      long_deal_volume                                  → buy_lots
      long_deal_amount                                  → buy_amt
      short_deal_volume                                 → sell_lots
      short_deal_amount                                 → sell_amt
      long_open_interest_balance_volume                 → oi_buy_lots
      long_open_interest_balance_amount                 → oi_buy_amt
      short_open_interest_balance_volume                → oi_sell_lots
      short_open_interest_balance_amount                → oi_sell_amt
      net_lots / net_amt / oi_net_lots / oi_net_amt: computed
      daynight: hardcoded 'day' (FinMind has no separation)
    """
    raw = _fetch("TaiwanOptionInstitutionalInvestors", "TXO", start_date, end_date)
    out = []
    for r in raw:
        bl = r.get("long_deal_volume")
        sl = r.get("short_deal_volume")
        ba = r.get("long_deal_amount")
        sa = r.get("short_deal_amount")
        oibl = r.get("long_open_interest_balance_volume")
        oisl = r.get("short_open_interest_balance_volume")
        oiba = r.get("long_open_interest_balance_amount")
        oisa = r.get("short_open_interest_balance_amount")
        out.append({
            "date": r["date"],
            "daynight": "day",
            "product": "臺指選擇權",
            "callput": r["call_put"],
            "role": r["institutional_investors"],
            "buy_lots": bl,
            "buy_amt": ba,
            "sell_lots": sl,
            "sell_amt": sa,
            "net_lots": (bl - sl) if (bl is not None and sl is not None) else None,
            "net_amt": (ba - sa) if (ba is not None and sa is not None) else None,
            "oi_buy_lots": oibl,
            "oi_buy_amt": oiba,
            "oi_sell_lots": oisl,
            "oi_sell_amt": oisa,
            "oi_net_lots": (oibl - oisl) if (oibl is not None and oisl is not None) else None,
            "oi_net_amt": (oiba - oisa) if (oiba is not None and oisa is not None) else None,
        })
    return out


def fetch_fut_institutional(data_id: str, start_date: str, end_date: str) -> list[dict]:
    """TaiwanFuturesInstitutionalInvestors → fut_legal rows for one product."""
    raw = _fetch("TaiwanFuturesInstitutionalInvestors", data_id, start_date, end_date)
    product = FUT_ID_TO_PRODUCT.get(data_id, data_id)
    out = []
    for r in raw:
        bl = r.get("long_deal_volume")
        sl = r.get("short_deal_volume")
        ba = r.get("long_deal_amount")
        sa = r.get("short_deal_amount")
        oibl = r.get("long_open_interest_balance_volume")
        oisl = r.get("short_open_interest_balance_volume")
        oiba = r.get("long_open_interest_balance_amount")
        oisa = r.get("short_open_interest_balance_amount")
        out.append({
            "date": r["date"],
            "daynight": "day",
            "product": product,
            "role": r["institutional_investors"],
            "buy_lots": bl, "buy_amt": ba,
            "sell_lots": sl, "sell_amt": sa,
            "net_lots": (bl - sl) if (bl is not None and sl is not None) else None,
            "net_amt": (ba - sa) if (ba is not None and sa is not None) else None,
            "oi_buy_lots": oibl, "oi_buy_amt": oiba,
            "oi_sell_lots": oisl, "oi_sell_amt": oisa,
            "oi_net_lots": (oibl - oisl) if (oibl is not None and oisl is not None) else None,
            "oi_net_amt": (oiba - oisa) if (oiba is not None and oisa is not None) else None,
        })
    return out


def fetch_fut_price_tx(start_date: str, end_date: str) -> list[dict]:
    """TaiwanFuturesDaily TX → fut_price rows (merged day/night per expiry).

    FinMind returns 1 row per (date, expiry, trading_session). We merge to one
    row per (date, expiry) with day_vol from 'position' rows + ah_vol from
    'after_market' rows. open/high/low/close/settle/oi taken from day session.
    """
    raw = _fetch("TaiwanFuturesDaily", "TX", start_date, end_date)
    # Group by (date, expiry)
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for r in raw:
        date = r["date"]
        expiry = r.get("contract_date")
        if not expiry:
            continue
        key = (date, expiry)
        if key not in grouped:
            grouped[key] = {
                "date": date, "contract": "TX", "expiry": str(expiry),
                "open_": None, "high": None, "low": None, "close": None,
                "change_str": None, "change_pct_str": None,
                "ah_vol": None, "day_vol": None, "total_vol": None,
                "settle": None, "oi": None,
                "best_bid": None, "best_ask": None,
            }
        rec = grouped[key]
        sess = r.get("trading_session")
        vol = r.get("volume")
        if sess == "position":
            # day session — main OHLC + settle + OI
            rec["open_"] = r.get("open")
            rec["high"] = r.get("max")
            rec["low"] = r.get("min")
            rec["close"] = r.get("close")
            rec["settle"] = r.get("settlement_price") or None
            rec["oi"] = r.get("open_interest") or None
            rec["day_vol"] = vol
            spread = r.get("spread")
            spread_pct = r.get("spread_per")
            if spread is not None:
                rec["change_str"] = str(spread)
            if spread_pct is not None:
                rec["change_pct_str"] = f"{spread_pct}%"
        elif sess == "after_market":
            rec["ah_vol"] = vol
    # Compute total_vol
    out = []
    for rec in grouped.values():
        d = rec["day_vol"] or 0
        a = rec["ah_vol"] or 0
        if d or a:
            rec["total_vol"] = d + a
        out.append(rec)
    return out
