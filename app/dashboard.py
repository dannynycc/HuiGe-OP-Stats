"""Dashboard aggregator — produces the 6-row "柴柴 法人部位彙整" view.

Formulas reverse-engineered from the source xlsm sheet 「工作表2」 R240-R245:
  - Each row aggregates 外資 + 自營商 only (excludes 投信), summing day-session
    legal positions, then adding night-session deltas to derive 開盤前部位.
  - 「成本」 converts net_amt (千元) per lot into the contract's display unit
    (台指 點數 / 電子 點數 / 金融 點數 / OP 權利金點數 / 股期 股價) using each
    product's contract-multiplier coefficient.

Lot-equivalence for 期貨類：
  台指期 = 大台 + 小台/4 + 微台/20
  電子期 = 大電 + 小電/8
  金融期 = 大金 + 小金/4
  股票期貨 = 全部股期商品（已是該商品 native 1 口）
"""
from __future__ import annotations
from typing import Any
from .db import connect


LEGAL_ROLES = ("外資", "自營商")


def _sum_fut(con, date: str, daynight: str, products_factors: list[tuple[str, float]],
             field: str) -> tuple[float, float]:
    """Return (sum_lots_eq, sum_amt_raw).

    Per Excel formula (工作表2 R240 etc.):
      lots: each product divided by lot-equivalence factor (大台/4 = 小台 等)
      amt:  raw sum across all products (NOT divided), because contract金額
            already scales naturally with the smaller multiplier.
    Cost is then computed by caller as (sum_amt_raw / sum_lots_eq) * cost_mul.
    """
    total_lots = 0.0
    total_amt = 0.0
    for product, factor in products_factors:
        rows = con.execute(f"""
            SELECT COALESCE(SUM({field}_lots), 0), COALESCE(SUM({field}_amt), 0)
            FROM fut_legal
            WHERE date = ? AND daynight = ? AND product = ? AND role IN (?, ?)
        """, (date, daynight, product, *LEGAL_ROLES)).fetchone()
        if rows:
            total_lots += (rows[0] or 0) / factor
            total_amt += (rows[1] or 0)  # raw sum, no factor
    return total_lots, total_amt


def _sum_op(con, date: str, daynight: str, callput: str, field: str) -> tuple[float, float]:
    row = con.execute(f"""
        SELECT COALESCE(SUM({field}_lots), 0), COALESCE(SUM({field}_amt), 0)
        FROM op_legal
        WHERE date = ? AND daynight = ? AND product = '臺指選擇權'
              AND callput = ? AND role IN (?, ?)
    """, (date, daynight, callput, *LEGAL_ROLES)).fetchone()
    return (row[0] or 0), (row[1] or 0)


def _safe_div(numer: float, denom: float, mul: float = 1.0) -> float | None:
    if not denom:
        return None
    return numer / denom * mul


def build_dashboard(date: str) -> dict[str, Any]:
    """Build the 6-row dashboard for a given trading date (data date, not view date).

    Returns:
      {
        "date": "2026-04-16",          # data date
        "view_date": "2026-04-17",     # next trading day (display "For X 開盤前看")
        "rows": [
          {
            "product": "台指期",
            "day_lots": -1749, "day_cost": 37031.0, "close_price": 37645,
            "oi_lots": -46947, "oi_cost": 37652.0,
            "night_lots": -1464, "night_cost": 37126.0,
            "pre_open_lots": -48411,
            "pre_open_cp": null,        # only for CALL/PUT rows
          },
          ...
        ],
        "tx_close": 37645,
      }
    """
    # 微台上市日 = 2022/03/28；之前的日期不計入「微型臺指期貨」(per user)
    MICRO_TX_LAUNCH = "2022-03-28"
    has_micro = date >= MICRO_TX_LAUNCH

    # (label, [(product, factor), ...], cost_mul, show_night, show_pre_open)
    # show_* flags mirror Excel 工作表2 R240-R245 layout
    台指期_components: list[tuple[str, float]] = [("臺股期貨", 1.0), ("小型臺指期貨", 4.0)]
    if has_micro:
        台指期_components.append(("微型臺指期貨", 20.0))

    fut_specs: list[tuple[str, list[tuple[str, float]], float, bool, bool]] = [
        ("台指期", 台指期_components, 5.0,                                                True,  True),
        ("電子期", [("電子期貨", 1), ("小型電子期貨", 8)], 1.0 / 4.0,                    True,  False),
        ("金融期", [("金融期貨", 1), ("小型金融期貨", 4)], 1.0,                          False, False),
        ("股票期貨", [("股票期貨", 1)], 1.0 / 2.0,                                       False, False),
    ]

    out_rows: list[dict[str, Any]] = []
    with connect() as con:
        # -- futures rows --
        for label, products_factors, cost_mul, show_night, show_pre_open in fut_specs:
            day_lots, day_amt = _sum_fut(con, date, "day", products_factors, "net")
            oi_lots, oi_amt = _sum_fut(con, date, "day", products_factors, "oi_net")
            night_lots, night_amt = _sum_fut(con, date, "night", products_factors, "net")
            row = {
                "product": label,
                "day_lots": int(round(day_lots)) if day_lots else 0,
                "day_cost": _safe_div(day_amt, day_lots, cost_mul),
                "close_price": None,
                "oi_lots": int(round(oi_lots)) if oi_lots else 0,
                "oi_cost": _safe_div(oi_amt, oi_lots, cost_mul),
                "night_lots": (int(round(night_lots)) if night_lots else 0) if show_night else None,
                "night_cost": _safe_div(night_amt, night_lots, cost_mul) if show_night else None,
                "pre_open_lots": (int(round(oi_lots + night_lots))
                                  if show_pre_open and (oi_lots + night_lots)
                                  else (0 if show_pre_open else None)),
                "pre_open_cp": None,
            }
            if label == "台指期":
                tx = con.execute("""
                    SELECT close FROM fut_price
                    WHERE date = ? AND contract = 'TX' AND expiry IS NOT NULL
                    ORDER BY expiry LIMIT 1
                """, (date,)).fetchone()
                close = tx[0] if tx else None
                if close is None:
                    # fallback to daily_summary (Excel-imported history)
                    ds = con.execute(
                        "SELECT tx_close FROM daily_summary WHERE date = ?", (date,)
                    ).fetchone()
                    close = ds[0] if ds else None
                row["close_price"] = close
            out_rows.append(row)

        # -- options rows (insert AFTER 金融期, BEFORE 股票期貨 to match Excel order) --
        op_rows = []
        for label, callput in (("買權CALL", "買權"), ("賣權PUT", "賣權")):
            day_lots, day_amt = _sum_op(con, date, "day", callput, "net")
            oi_lots, oi_amt = _sum_op(con, date, "day", callput, "oi_net")
            night_lots, night_amt = _sum_op(con, date, "night", callput, "net")
            op_rows.append({
                "product": label,
                "day_lots": day_lots,
                "day_cost": _safe_div(day_amt, day_lots, 20.0),
                "close_price": None,
                "oi_lots": oi_lots,
                "oi_cost": _safe_div(oi_amt, oi_lots, 20.0),
                "night_lots": night_lots,
                "night_cost": _safe_div(night_amt, night_lots, 20.0),
                "pre_open_lots": oi_lots + night_lots,
                "pre_open_cp": None,
            })
        # 開盤前多空 = CALL 開盤前 - PUT 開盤前 (shared between the two rows)
        cp = op_rows[0]["pre_open_lots"] - op_rows[1]["pre_open_lots"]
        op_rows[0]["pre_open_cp"] = cp
        op_rows[1]["pre_open_cp"] = cp  # display once via colspan in UI

        # Excel row order: 台指期/電子期/金融期/買權CALL/賣權PUT/股票期貨
        out_rows = out_rows[:3] + op_rows + [out_rows[3]]

    # view_date defaults to "next trading day with day-session data in DB
    # (= skip both weekends AND holidays)". Falls back to next weekday if
    # nothing in DB.
    import datetime as dt
    with connect() as con:
        nxt_row = con.execute(
            "SELECT MIN(date) FROM op_legal WHERE date > ? AND daynight='day'",
            (date,)
        ).fetchone()
    if nxt_row and nxt_row[0]:
        view_date = nxt_row[0]
    else:
        d = dt.date.fromisoformat(date)
        nxt = d + dt.timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += dt.timedelta(days=1)
        view_date = nxt.isoformat()

    tx_close = next((r["close_price"] for r in out_rows if r["product"] == "台指期"), None)

    # 信用交易 — 上市/上櫃融資餘額 (億元), 從 daily_summary 取
    with connect() as con:
        ds = con.execute("""
            SELECT twse_margin_amt_oku, tpex_margin_amt_oku,
                   twse_mkt_cap_chao, tpex_mkt_cap_chao,
                   twse_margin_pct, tpex_margin_pct
            FROM daily_summary WHERE date = ?
        """, (date,)).fetchone()
    margin = {
        "twse_margin_amt_oku": ds["twse_margin_amt_oku"] if ds else None,
        "tpex_margin_amt_oku": ds["tpex_margin_amt_oku"] if ds else None,
        "twse_mkt_cap_chao": ds["twse_mkt_cap_chao"] if ds else None,
        "tpex_mkt_cap_chao": ds["tpex_mkt_cap_chao"] if ds else None,
        "twse_margin_pct": ds["twse_margin_pct"] if ds else None,
        "tpex_margin_pct": ds["tpex_margin_pct"] if ds else None,
    }

    return {
        "date": date,
        "view_date": view_date,
        "rows": out_rows,
        "tx_close": tx_close,
        "margin": margin,
    }
