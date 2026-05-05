"""SQLite schema and connection helpers."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS op_legal (
    date TEXT NOT NULL,
    daynight TEXT NOT NULL,           -- 'day' or 'night'
    product TEXT NOT NULL,            -- 臺指選擇權 / 電子選擇權 / ...
    callput TEXT NOT NULL,            -- 買權 / 賣權
    role TEXT NOT NULL,               -- 自營商 / 投信 / 外資
    buy_lots INTEGER, buy_amt INTEGER,
    sell_lots INTEGER, sell_amt INTEGER,
    net_lots INTEGER, net_amt INTEGER,
    oi_buy_lots INTEGER, oi_buy_amt INTEGER,
    oi_sell_lots INTEGER, oi_sell_amt INTEGER,
    oi_net_lots INTEGER, oi_net_amt INTEGER,
    PRIMARY KEY (date, daynight, product, callput, role)
);

CREATE TABLE IF NOT EXISTS fut_legal (
    date TEXT NOT NULL,
    daynight TEXT NOT NULL,
    product TEXT NOT NULL,            -- 臺股期貨 / 小型臺指 / 微型臺指 / 股票期貨 / ...
    role TEXT NOT NULL,
    buy_lots INTEGER, buy_amt INTEGER,
    sell_lots INTEGER, sell_amt INTEGER,
    net_lots INTEGER, net_amt INTEGER,
    oi_buy_lots INTEGER, oi_buy_amt INTEGER,
    oi_sell_lots INTEGER, oi_sell_amt INTEGER,
    oi_net_lots INTEGER, oi_net_amt INTEGER,
    PRIMARY KEY (date, daynight, product, role)
);

CREATE TABLE IF NOT EXISTS fut_price (
    date TEXT NOT NULL,
    contract TEXT NOT NULL,           -- TX / MTX / ...
    expiry TEXT NOT NULL,             -- 202605 / 202605W1 ...
    open_ INTEGER, high INTEGER, low INTEGER, close INTEGER,
    change_str TEXT, change_pct_str TEXT,
    ah_vol INTEGER, day_vol INTEGER, total_vol INTEGER,
    settle INTEGER, oi INTEGER,
    best_bid INTEGER, best_ask INTEGER,
    PRIMARY KEY (date, contract, expiry)
);

CREATE TABLE IF NOT EXISTS credit_twse (
    date TEXT NOT NULL,
    item TEXT NOT NULL,               -- 融資(交易單位) / 融券(交易單位) / 融資金額(仟元) / ...
    buy REAL, sell REAL, repay REAL,
    prev_balance REAL, today_balance REAL,
    PRIMARY KEY (date, item)
);

CREATE TABLE IF NOT EXISTS credit_summary (
    date TEXT PRIMARY KEY,
    twse_margin_balance REAL,         -- 仟元
    twse_turnover REAL,               -- 元
    twse_mkt_cap REAL,                -- 億元
    tpex_margin_balance REAL,         -- 仟元
    tpex_turnover REAL,               -- 元
    tpex_mkt_cap REAL                 -- 佰萬元
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date TEXT PRIMARY KEY,
    tx_close REAL,
    op_legal_net REAL,                -- 法人選擇權淨部位 (custom: net of CALL+PUT)
    op_call_net REAL,
    op_put_net REAL,
    op_cp_net REAL,                   -- CP 合計多空 (= call - put)
    fut_pre_open_net REAL,            -- 開盤前多空
    stock_fut_legal_net REAL,         -- 股期法人淨部位
    twse_margin_pct REAL,
    tpex_margin_pct REAL,
    twse_margin_amt_oku REAL,         -- 億元
    tpex_margin_amt_oku REAL,         -- 億元
    twse_mkt_cap_chao REAL,           -- 兆元
    tpex_mkt_cap_chao REAL            -- 兆元
);

CREATE TABLE IF NOT EXISTS refresh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    target_date TEXT,
    ok INTEGER NOT NULL,              -- 1 / 0
    errors_json TEXT
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript(SCHEMA)


@contextmanager
def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()
