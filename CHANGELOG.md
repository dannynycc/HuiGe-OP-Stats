# Changelog

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
