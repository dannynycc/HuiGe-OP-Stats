# Changelog

## [v0.3.1] - 2026-05-05 18:30

### Fixed
- 前端首次載入沒讀 URL 的 `?view_date=` query param，造成深連結直接打到
  `?view_date=2026-04-15` 卻顯示最新一天的 dashboard（用戶反饋）。
  - 初始 `loadView(_initialView)` 帶上 URL 解析結果
  - 「載入」按鈕也同步 URL（history.replaceState）

## [v0.3] - 2026-05-05 18:22

### Fixed (用戶抓到 cost 全錯)
- **期貨類 cost 公式**：amt 不該除以等效因子（lots 才要除）。Excel R240 C3
  原公式 `(I54+I56+I63+I65+I66+I68)/B240*5` 把 6 個 amt **直接相加**只除以
  等效大台 lots。我之前把 amt 也按 4 / 20 除掉了，導致台指期/電子期日夜盤
  cost 全部偏低。修正後 4/30 台指期日盤 cost = 39,565（合理價位）。
- **`daily_summary` refresh 不再覆寫舊欄位** — 改成 column-by-column merge：
  COALESCE(new, old)。原本 refresh 4/15 時 fut_price 沒拿到，把 Excel
  migration 的 tx_close=36,643 蓋成 NULL。現在 refresh 撞到 NULL 不寫。

### Changed (用戶反饋 UI 還是太複雜)
- 上方 controls 從「資料日期 / 抓資料」兩個 date 欄合併為**單一**
  「For [date] 開盤前看」+ 載入 + Refresh 抓最新。data_date 自動 = view_date
  前一個交易日。
- `/api/dashboard` 多接 `view_date=` 參數（preferred），原本的 `date=` 保留 compat。

## [v0.2] - 2026-05-05 18:11

### Changed (依用戶反饋)
- 前端 **只保留**「柴柴 法人部位彙整」橫向 6 列總表（截圖那個 view）。砍掉
  原本的 KPI grid / 時序圖 / 4 個原始法人表 / 信用交易表 — 資訊量太大、用戶不需要。

### Added
- `app/dashboard.py` — 6 列總表聚合，公式從工作表2 R240-R245 反組譯：
  - 台指期 = 大台 + 小台/4 + 微台/20，成本 ×5（點數）
  - 電子期 = 大電 + 小電/8，成本 ÷4（點數）
  - 金融期 = 大金 + 小金/4，成本 ×1（點數）
  - 買權 / 賣權 = 臺指選擇權外資+自營商，成本 ×20（權利金點數）
  - 股票期貨 = 全部股期商品（已是 native 1 口），成本 ÷2（股價）
  - 開盤前部位 = 日盤 OI 淨 + 夜盤交易淨
  - 開盤前多空 = CALL 開盤前 − PUT 開盤前（CALL/PUT 兩列共用）
- `/api/dashboard?date=YYYY-MM-DD` — 回傳上面結構

### Notes
- `tx_close` 對 backfill 日期仍依賴 daily_summary fallback（fut_price endpoint
  「only today」限制不變）

## [v0.1] - 2026-05-05 17:45

### Added
- FastAPI + SQLite + 單頁 HTML 架構，取代輝哥 Excel
- 12 endpoint scrapers (5 TAIFEX + 3 TWSE + 3 TPEX)
- SQLite schema：`op_legal` / `fut_legal` / `fut_price` / `credit_twse` /
  `credit_summary` / `daily_summary` / `refresh_log`
- `scripts/migrate_excel.py` — 一次性 import 5 個月歷史「綜合整理」進 daily_summary
  (103 列, 2025-11-06 ~ 2026-04-16)
- `scripts/backfill.py` — 多年 backfill CLI (skip-weekends, throttle)
- `scripts/refresh_now.py` — 單次 refresh CLI
- 前端：5 區塊 (KPI / 時序圖 / OP 日夜盤 / 期貨日夜盤 / 台指期 / 信用) + 手動 refresh 按鈕
- `start.bat` / `stop.bat`（hidden window，port 8765）

### Verified
- Cross-check 2026-04-15：API backfill 出來的 daily_summary 13 個欄位跟原 Excel
  「綜合整理」**完全一致**（含發現「外資+自營商，排除投信」的隱藏聚合規則）

### Known limitations (per README)
- `futDailyMarketExcel` 只回今天，**台指期歷史收盤無法 backfill**
- `homeApi/mkt_cap` 只回最近 5 天，**上市總市值老資料無法 backfill**
- `op_legal_net` / `fut_pre_open_net` 兩欄 Excel 公式未解，refresh 暫不寫
- 損益圖 (Excel 9 checkbox 邏輯) — 用戶決定不 port

### Excluded by .gitignore
- `data/*.db` (SQLite)
- `_analysis/`, `api_probe/`, `logs/` (本地工具/暫存)
