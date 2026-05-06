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

### TWSE（5）
| URL | 編碼 | 用途 |
|---|---|---|
| `twse.com.tw/exchangeReport/MI_MARGN?response=csv&date=YYYYMMDD&selectType=ALL` | Big5 | 上市信用交易 |
| `twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=YYYYMMDD&response=json` | UTF-8 JSON | 上市成交金額 |
| `twse.com.tw/rwd/zh/homeApi/mkt_cap` | UTF-8 JSON | 上市總市值 (**只回最近 5 天**) |
| `twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=YYYYMMDD&response=json` | UTF-8 JSON | 加權指數 OHLC (整月) |
| `twse.com.tw/zh/trading/statistics/week.html` (xls 下載) | xls | 市值週報 (週頻、2005-09 起) |

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
- `daily_summary(date PK, tx_close, op_legal_net, op_call_net, op_put_net, op_cp_net, fut_pre_open_net, stock_fut_legal_net, twse_margin_pct, tpex_margin_pct, twse_margin_amt_oku, tpex_margin_amt_oku, twse_mkt_cap_chao, tpex_mkt_cap_chao, twii_close, mkt_cap_source, op_pre_open_cp_net)` *(17 cols; op_pre_open_cp_net v0.10.6 起)*
- `mkt_cap_weekly(date PK, twse_mkt_cap_oku, source)` *(v0.9.7 起；TWSE 市值週報 import)*
- `option_settlement_dates(date, product, contract_month, settlement_price, PK(date,product))` *(v0.10.15 起；TEO 月選結算日)*
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

### Refresh 行為 (v0.10.27 起 catch-up mode)
- `POST /api/refresh` 預設 `catch_up=true`: 自動補 last_db_date+1 ~ today 所有 weekdays
- `?date=YYYY-MM-DD` 指定單日 (override catch_up)
- `?catch_up=false` 關掉只抓今天
- 三層正確性防護:
  1. Endpoint `actual_date == target` 防 stale (year-bug guard)
  2. Row count sanity: op=30 / fut=73 才算完整
  3. Conflict detection: snapshot DB before refresh, 比對 9 cols diff > 0.5% 列出
- 跑完 outlier audit on 補的 dates (day-over-day mkt_cap / margin vs TWII)
- 兩 view (主表 / 綜合整理) 都 query `daily_summary`, refresh 後**自動 reload** (無需 Ctrl+F5, v0.10.28)
- 兩 view header 都有 Refresh button (主表 / 綜合整理 都可 trigger refresh)
- API responses 加 `Cache-Control: no-cache` 強制 browser fresh fetch

### 主表 layout (v0.10.29-32)
- `table-layout: fixed` — col widths 鎖死, 切日期不抖動 (v0.10.29)
- `max-width: 1300px` (v0.10.32, 從 1050 拉寬容下日期/header)
- col widths 經 Playwright 多 viewport / 多 dates 驗證 0 overflow
  (corner cell 14% 容 「For YYYY/M/D(週) 開盤前看」, 開盤前多空 12% 容 header + paren)
- 數字 cells `font-variant-numeric: tabular-nums` (v0.10.32)
  - 每 char (digit/comma/minus/paren) 等寬 9.5px
  - row 之間 digit 位置上下對齊 (column-style alignment)

### 綜合整理 view 功能 (v0.10.x)
- **17 cols** layout：For 開盤前看 / 前一日 / 加權指數 / 台指期收盤 / 法人淨部位 /
  開盤前多空 / CALL / PUT / CP合計 / 選擇權開盤前多空 / 股期 / 上市%/上櫃% /
  上市億/上櫃億 / 上市兆/上櫃兆
- **電子選擇權月選結算日 highlight**：那 row 整列淡黃 (`#FEF3C7`)，hover 變 amber
- **色階 (融資餘額佔市值比)**：上市/上櫃 各自獨立綠 → 黃 → 紅 漸層
- **窄 viewport** (≤1500px) 自動橫向 scroll，每欄 nowrap fit

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

### Backfill 涵蓋範圍 (v0.10.x 現況)
- DB 涵蓋 **2020-01-02 ~ 2026-05-05**，共 **1,536 個 trading days**
- 2023/05/05 起 TAIFEX 直抓 (TX/TE/TF/op/fut)
- 2020/01 ~ 2023/05/04 用 FinMind (TaiwanFuturesDaily + Options/Futures Institutional)
- 加權指數 1536 days 全段用 FinMind `TaiwanStockPrice` data_id='TAIEX'
- 上市總市值 1536 days 全段 (115 official + 1421 interp via 週報 + TWII)
- 全部從官方 / 第三方 endpoints 真實抓取（非 Excel migration）
- TAIFEX endpoint cutoff = **2023/05/05**，更早只能用 FinMind (有 sub-product 限制)
- **仍缺**：2020-2023/05 段 信用餘額 (TWSE+TPEX) / 上櫃總市值 / 個股期合計法人
  + 2023-05-05 後 11 個 dates 也缺 信用餘額 (詳「已知尚未實作」段)

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

## 已知尚未實作

- 損益圖（Excel「損益圖」sheet 的 9 checkbox S1-S3/U1-U6 互斥邏輯）— 用戶決定不做
- 自動排程 / 定時 refresh — 用戶決定不做

## 資料完整度 (v0.10.21 ALL CLEAN, 1536 dates × 17 cols)

`daily_summary` 16/17 cols 0 NULL（`op_pre_open_cp_net` 在 2020-2023/04 為 NULL
是預期，因 TAIFEX 夜盤 endpoint 那段沒料）。

### Audit / Sweep 工具 (v0.10.x 累積)
| script | 用途 |
|---|---|
| `scripts/audit_and_fix_all.py` | NULL audit + auto-fix (derive pct / interp / TWSE MI_MARGN) |
| `scripts/full_audit.py` | 8-section comprehensive audit (NULL / schema / derived / orphan / continuity / UI alignment / spot-check) |
| `scripts/detect_outliers.py` | 5-method outlier detection (weekly anchor / TWII MAD-z / day-over-day jumps for both mkt_cap & margin) |
| `scripts/sweep_margin_outliers.py` | 全段 1535 dates 對 TWSE MI_MARGN endpoint 比對, fix stale |
| `scripts/full_sweep_all_cols.py` | 全段 endpoint sweep (tx_close / twse_margin / tpex_margin / tpex_mkt_cap) |
| `scripts/audit_raw_vs_endpoint.py` | Random sample audit, 30 dates × 4 cols sanity-check |

### Outlier-detection 方法 (robust, 不用固定 threshold)
1. **Weekly anchor exact match** — `mkt_cap_weekly` vs `daily_summary` cell 對 cell
2. **TWII × ratio MAD-z** — rolling 21-day median absolute deviation, 5σ outlier
3. **Day-over-day mkt_cap jump** w/ TWII cross-check (mkt_cap > 3% 但 TWII < 3%)
4. **Margin / mkt_cap ratio MAD-z** — same logic for margin
5. **Day-over-day margin jump** w/ TWII cross-check (排除真實 market crash)

### Caveat: fut_pre_open_net 對 2020-2023/04 段
- 公式: `fut_pre_open_net = 日盤 OI net (大台等效) + 夜盤 net_lots`
- 但 TAIFEX 夜盤 endpoint cutoff = **2023/05/05**, FinMind 也沒歷史夜盤
- → 2020-2023/04 段 (~800 dates) `fut_pre_open_net` = `op_legal_net`
  (= 純日盤 OI, 沒夜盤加成)
- 看「綜合整理」view 那段「開盤前多空」 column 跟「台指期 法人淨部位」 一樣
  是預期, 不是 bug

## 上市總市值 (twse_mkt_cap_chao) 資料策略 (v0.10.0 起)

公開 endpoint `homeApi/mkt_cap` 只回最近 5 天 → 歷史靠下面組合補：

1. **TWSE 市值週報 .xls** (`mkt_cap_weekly` 表): 週頻、2005-09 起 1059 筆
2. **加權指數 daily** (`daily_summary.twii_close`): **FinMind `TaiwanStockPrice` data_id='TAIEX'** 抓
   （v0.9.7 原本用 TWSE `MI_5MINS_HIST` 但連續抓 50+ 月份觸發 WAF ban，
   改用 FinMind 全段 26 chunks 一次 backfill 完成）
3. **內插**: `daily_mkt_cap_chao = weekly_anchor × (TWII_daily / TWII_anchor)`

`mkt_cap_source` 欄區分:
- `'official'`: TWSE homeApi 抓的真值 (refresh 那天 + Excel migration import)
- `'interp'`: 用上述內插算的近似 (誤差預估 1-3%)
- `NULL`: 應該不再有 (v0.10.0 後 1536 trading days 全 cover)

Backfill 流程:
```
python scripts/import_weekly_mktcap.py "path/to/week1-new.xls"
# (TWII 直接用 inline FinMind script, 見 v0.10.0 changelog)
python scripts/recompute_mktcap_interp.py
```

**v0.10.1 起 refresh 後自動 trigger** `_post_refresh_aggregate()`:
- 該天若 mkt_cap NULL → 自動 interp
- 重算 `twse_margin_pct = margin / (mkt_cap × 10000)`

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
