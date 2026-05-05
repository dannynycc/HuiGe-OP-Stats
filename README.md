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
| `/cht/3/futDailyMarketReport` | POST | ✅ | 期貨各月收盤；v0.9.4 起同時抓 TX (台指) + TE (電子) + TF (金融)，commodity_id 切換 |

POST body: `queryDate=YYYY/MM/DD&commodityId=&MarketCode=0&queryType=1`
（fut_price 的 commodity_id：`TX` / `TE` / `TF`，三個 contract 都進同一張表，`contract` 欄區分）

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

### Reference: TWSE 官方休市日曆（驗證用，不入庫）
- 網頁版：<https://www.twse.com.tw/zh/trading/holiday.html>
- JSON API：<https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date=YYYYMMDD&response=json>
- HTML API：<https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date=YYYYMMDD&response=html>
- `?date=` 帶該年內任何一天即回該年（例 `date=20250101` 回民國 114 年清單）。
- ⚠️ **注意「說明」欄**：list 內含 3 種 entry，不能整片視為 holiday：
  1. **真 holiday**（依規定放假 / 補假）→ 不交易
  2. **「市場無交易，僅辦理結算交割作業」**（如 2025/1/23、1/24）→ 不交易
  3. **「開始/最後交易日」標記**（如 2025/1/2、1/22、2/3）→ **是 trading day**
  4. 政府補班日（如 2025/2/8 Sat）TWSE「補行上班，**但不交易亦不交割**」→ 不交易
- 本專案 holiday 判定不查這個 API，而是 **endpoint 真實 response 為 ground truth**
  （endpoint 給 30 rows = trading；給 0 rows = holiday）。已驗證跟 TWSE 公告
  18/18 一致（見「已驗證資料正確性」段）。

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

瀏覽器：
- `http://localhost:8765/` — 主表「For X 開盤前看」(柴柴 6 列彙整)
- `http://localhost:8765/comprehensive` — **綜合整理 view**：完整 timeseries
  table，復刻 Excel「綜合整理」 sheet（v0.9 起）

## Backfill (歷史資料抓取)

```
python scripts/backfill.py --from 2024-01-01 --to today --sleep 0.6
python scripts/backfill.py --from 2024-01-01 --to 2024-12-31
python scripts/backfill.py --dates 2024-03-15,2024-03-18
```

**Limitations**:
- `twse_mkt_cap` (上市總市值) — `homeApi/mkt_cap` 只給最近 5 天；老資料從
  Excel migration「綜合整理」覆蓋 5 個月歷史，更早需另尋資料源。
- 其他 11 個 endpoint（含 v0.8 起新加的 `futDailyMarketReport`）都 honor date
  param，可以無上限 backfill。

**Backfill 專用 fast path**：
- `python scripts/backfill_fut_price.py [--from] [--to] [--only-missing]` —
  只跑 fut_price endpoint，比 full refresh 快約 3 倍。適合補齊 `tx_close` 欄。

## 已驗證資料正確性

### Backfill 涵蓋範圍
- DB 涵蓋 **2025-01-02 ~ 2026-05-05**，共 **319 個 trading days** (v0.7)
- 持續進行中: 2023/05/05 ~ 2024/12/31 (TAIFEX 直抓, v0.9.2)
- 持續進行中: 2020/02 ~ 2023/05/04 (FinMind, v0.9.2)
- 全部從官方 endpoints 真實抓取（非 Excel migration）
- TAIFEX endpoint cutoff = **2023/05/05**，更早只能用 FinMind (有 sub-product 限制)

### Sanity check 結果
- **Row count 一致性**：319 days 全部 op_legal day=30、fut_legal day=73，0 anomaly
- **連續性**：5 個 gap > 4 天 全部對應預期 holiday cluster（春節 ×2、清明 ×2、勞動 ×1）
- **隨機 sample 重 fetch**：5 個隨機 2025 dates 重打 endpoint 跟 DB **100% match**（net_lots、net_amt、oi_net_lots 三欄）
- **Holiday 對齊 TWSE 公告**：2025 18 個 weekday holiday，DB 跟 TWSE 公告
  ([holidaySchedule API](https://www.twse.com.tw/rwd/zh/holidaySchedule/holidaySchedule?date=20250101&response=json))
  18/18 完全一致，0 mismatch 兩邊

### Cross-holiday night session 處理
TAIFEX night endpoint 用「session 結束日」當 queryDate。當 holiday/long-weekend
中間夾 trading days 時，cross-holiday night session 會被 endpoint label 在
re-open 日。我們 **sweep 後重 label 到「假期前最後 trading day」** 才符合柴柴/輝哥
Excel 慣例。已驗證 14 個 cross-holiday absorbing dates 全部 day=30 night=6。

### Cross-check 對 Excel `4_7` / `2_23` ground truth
- **For 4/7 開盤前看（跨清明 4-day 連假）**：data_date 自動跳到 4/2，6 列
  總表跟 Excel R237-R245 freeze 1:1 match。
- **For 2/23 開盤前看（跨春節 12-day 連假）**：data_date 自動跳到 2/11，6 列
  總表跟 Excel R237-R245 freeze 1:1 match。

### Holiday-aware 邏輯（不需 hardcode 假期表）
- `data_date` = `MAX(date) FROM op_legal WHERE date < view_date AND daynight='day'`
- `view_date` (response) = `MIN(date) FROM op_legal WHERE date > data_date AND daynight='day'`
- Orphan night sweep = 把「該日無 day-session 但有 night-session」的 row 重 label
  到「之前最近有 day-session 的日期」。

## 已知尚未實作 / 缺資料

- 損益圖（Excel「損益圖」sheet 的 9 checkbox S1-S3/U1-U6 互斥邏輯）— 用戶決定不做
- 自動排程 / 定時 refresh — 用戶決定不做
- 2020-2023/05 段 daily_summary 缺 `twse_margin_amt_oku` / `tpex_margin_amt_oku`
  / `twse_mkt_cap_chao` / `stock_fut_legal_net` — 進行中（FinMind backfill）。
- `twse_mkt_cap_chao` 對 5 天前 → 找 FinMind 替代資料源中

## 公式（v0.9.3 全 reverse-engineered）

- `op_call_net` / `op_put_net` / `stock_fut_legal_net` =
  外資 + 自營商 OI 淨口（**排除投信**，隱藏 Excel 慣例）
- `op_cp_net` = `op_call_net` - `op_put_net`
- `op_legal_net`（台指期 等效大台 OI 淨）=
  外資+自營商 OI 淨 of (大台 + 小台/4 + 微台/20)
  *微台 2022-03-28 launch，之前忽略*
- `fut_pre_open_net`（開盤前部位）= `op_legal_net` + 同樣 components 的夜盤交易淨
- `tx_close` = TX 近月收盤（`futDailyMarketReport` `commodity_id=TX` 第一筆）
- `twse_margin_amt_oku` = 仟元 / 100000（仟元 → 億元）
- `twse_mkt_cap_chao` = 億元 / 10000（億元 → 兆元）
- `tpex_mkt_cap_chao` = 佰萬元 / 1,000,000（佰萬元 → 兆元）
