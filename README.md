# 法人OP日夜盤數據 (HuiGe-OP-Stats)

期交所三大法人選擇權/期貨日夜盤數據 + 上市/上櫃信用交易彙整 — 網頁版（取代輝哥 Excel）。

版本紀錄見 [CHANGELOG.md](CHANGELOG.md)。

## 目的

每天開盤前快速看「柴柴 法人部位彙整」**橫向 6 列總表**（v0.2 砍到只剩這個 view）：

| 列 | 日盤口數 | 日盤成本 | 收盤價 | 淨部位 | 淨部位成本 | 夜盤口數 | 夜盤成本 | 開盤前部位 | 開盤前多空 |
|---|---|---|---|---|---|---|---|---|---|
| 台指期 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | |
| 電子期 | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ | | |
| 金融期 | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ | | |
| 買權 CALL | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓(共用) |
| 賣權 PUT | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ | ✓ | ✓(共用) |
| 股票期貨 | ✓ | ✓ | | ✓ | ✓ | ✓ | ✓ | | |

## 架構

```
[手動 Refresh / Backfill]
    │
    ▼
scrapers (12 endpoints)
    │
    ▼
SQLite raw 表 (op_legal / fut_legal / fut_price / credit_*)
    │
    ▼
build_dashboard() 套 Excel 公式 (排除投信，等效大台/電/金、selecciónes ×20、股期 ÷2)
    │
    ▼
/api/dashboard?view_date=YYYY-MM-DD ──→ 單頁 HTML + vanilla JS
```

- **後端**：Python 3 + FastAPI + requests + pandas + BeautifulSoup
- **DB**：SQLite (`data/data.db`)，7 張表
- **前端**：單頁 HTML + vanilla JS（無 framework，無 chart lib）
- **無自動排程** — 手動按 refresh 抓當日；`scripts/backfill.py` 抓歷史
- **Holiday-aware**：`data_date` / `view_date` 都用 DB lookup 自動 skip 假日，
  不需 hardcode holiday list（兒童節、清明、過年、228、元旦、勞動節等都 OK）

## 資料來源（12 個 endpoint）

### TAIFEX（5）
| Endpoint | Method | Date 支援 | 對應 |
|---|---|---|---|
| `/cht/3/callsAndPutsDate` | POST | ✅ | 三大法人 OP 日盤 |
| `/cht/3/callsAndPutsDateAh` | POST | ✅ | 三大法人 OP 夜盤 |
| `/cht/3/futContractsDate` | POST | ✅ | 三大法人期貨日盤 |
| `/cht/3/futContractsDateAh` | POST | ✅ | 三大法人期貨夜盤 |
| `/cht/3/futDailyMarketExcel` | GET | ❌（只當天）| 台指期 TX 各月 |

POST body: `queryDate=YYYY/MM/DD&commodityId=&MarketCode=0&queryType=1`

### TWSE（3）
| URL | 編碼 | 用途 |
|---|---|---|
| `twse.com.tw/exchangeReport/MI_MARGN?response=csv&date=YYYYMMDD&selectType=ALL` | Big5 | 上市信用交易 |
| `twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=YYYYMMDD&response=json` | UTF-8 JSON | 上市成交金額 |
| `twse.com.tw/rwd/zh/homeApi/mkt_cap` | UTF-8 JSON | 上市總市值 |

### TPEX（3）
| URL | 編碼 |
|---|---|
| `tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&o=csv&d=NNN/MM/DD&s=0,asc,0` | Big5 CSV |
| `tpex.org.tw/www/zh-tw/afterTrading/marketStats?type=Daily&date=YYYY%2FMM%2FDD&id=&response=json` | UTF-8 JSON |
| `tpex.org.tw/www/zh-tw/afterTrading/highlight?date=YYYY%2FMM%2FDD&id=&response=json` | UTF-8 JSON |

## 目錄結構

```
app/
  main.py              # FastAPI app
  db.py                # SQLite schema + init
  scrapers/
    taifex.py          # 5 TAIFEX endpoints
    twse.py            # 3 TWSE endpoints
    tpex.py            # 3 TPEX endpoints
    summarize.py       # 把 raw 資料聚合成 daily_summary 一列
  static/
    index.html         # 單頁 UI
data/
  data.db              # SQLite (gitignore)
scripts/
  init_db.py           # 建表
  migrate_excel.py     # 一次性把 Excel「綜合整理」import 進 daily_summary
  refresh_now.py       # CLI 觸發 refresh（測試用）
logs/                  # 執行紀錄 (gitignore)
start.bat / stop.bat
```

## SQLite Schema

- `op_legal(date, daynight, product, callput, role, buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt, oi_buy_lots, oi_buy_amt, oi_sell_lots, oi_sell_amt, oi_net_lots, oi_net_amt, PK(date,daynight,product,callput,role))`
- `fut_legal(date, daynight, product, role, buy_lots, buy_amt, sell_lots, sell_amt, net_lots, net_amt, [oi 6 cols], PK(date,daynight,product,role))`
- `fut_price(date, contract, expiry, open, high, low, close, settle, change, ah_vol, day_vol, total_vol, oi, best_bid, best_ask, PK(date,contract,expiry))`
- `credit_twse(date, item, buy, sell, repay, prev_balance, today_balance, PK(date,item))`
- `credit_summary(date, twse_margin_balance, twse_turnover, twse_mkt_cap, tpex_margin_balance, tpex_turnover, tpex_mkt_cap, PK(date))`
- `daily_summary(date PK, tx_close, op_legal_net, op_call_net, op_put_net, op_cp_net, fut_pre_open_net, stock_fut_legal_net, twse_margin_pct, tpex_margin_pct, twse_margin_amt_oku, tpex_margin_amt_oku, twse_mkt_cap_chao, tpex_mkt_cap_chao)`
- `refresh_log(id, ts, ok, errors_json)`

## 啟動

```
start.bat   # 背景啟動 uvicorn :8765
stop.bat    # 停掉
```

瀏覽器開 `http://localhost:8765`。

## Backfill (歷史資料抓取)

```
python scripts/backfill.py --from 2024-01-01 --to today --sleep 0.6
python scripts/backfill.py --from 2024-01-01 --to 2024-12-31
python scripts/backfill.py --dates 2024-03-15,2024-03-18
```

**Limitations**:
- `tx_close` (台指期收盤) — `futDailyMarketExcel` endpoint 只回當日，無法 backfill；
  歷史值要從別處（Excel migration 已覆蓋 5 個月，更早需另尋資料源）。
- `twse_mkt_cap` (上市總市值) — `homeApi/mkt_cap` 只給最近 5 天；老資料同上，
  Excel 「綜合整理」已 import 5 個月歷史。
- 其他 9 個 endpoint 都 honor date param，可以無上限 backfill。

## 已驗證資料正確性

對 2026-04-15 cross-check：API backfill 出來的 `daily_summary` 跟原 Excel
「綜合整理」13 個欄位**完全一致**。聚合公式：
- `op_call_net` / `op_put_net` / `stock_fut_legal_net` =
  外資 + 自營商 OI 淨口（**排除投信**，這是隱藏在 Excel 公式裡的潛規則）
- `tx_close` = TX 近月收盤（`futDailyMarketExcel` 第一筆）
- `op_cp_net` = `op_call_net` - `op_put_net`
- `twse_margin_amt_oku` = 仟元 / 100000（仟元 → 億元）
- `twse_mkt_cap_chao` = 億元 / 10000（億元 → 兆元）
- `tpex_mkt_cap_chao` = 佰萬元 / 1,000,000（佰萬元 → 兆元）

## 已知尚未實作（用戶決定不做）

- 損益圖（Excel「損益圖」sheet 的 9 checkbox S1-S3/U1-U6 互斥邏輯）
- 自動排程 / 定時 refresh
- `op_legal_net` / `fut_pre_open_net` 兩欄位 Excel 公式不明（不是簡單 OI sum），
  歷史值由 Excel migration 提供，refresh 暫不寫這兩欄。
