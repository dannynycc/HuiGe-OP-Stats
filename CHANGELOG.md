# Changelog

## [v0.7] - 2026-05-05 20:00

### Fixed (Holiday-aware logic — 用戶 hint「4/6 有開盤嗎? 4/3 有開盤嗎?」抓到 3 個串連 bug)
- **Night session date label 對 holiday 錯位** — TAIFEX night endpoint 用「session
  結束日」當 queryDate；holiday 前一個 trading day 的夜盤跨假到下一個 trading day，
  被錯標到 holiday 當日。例：4/2 夜盤跨 4/3-4/6 long weekend 到 4/7 開市，被標
  date=4/6（清明）。修：寫 SQL fix 把所有「該日無 day-session 但有 night-session」
  的 orphan night row 重 label 到「前一個有 day session 的日期」。
  - 5 個 holiday 已修：12/25→12/24、1/1→12/31、2/20→2/11、2/27→2/26、4/6→4/2
- **Dashboard `data_date` 沒 skip holiday** — view_date=4/7 算 data_date=4/6（weekday-1）
  但 4/6 是清明補假。修：`data_date = MAX(date) WHERE date < view_date AND has day-session`，
  動態 DB lookup 不需 hardcode holiday list。
- **Dashboard `view_date` 同樣只 skip weekend** — data_date=4/2 推 view_date=4/3，但 4/3
  也是 holiday。修：`view_date = MIN(date) WHERE date > data_date AND has day-session`。

### Verified
- Dashboard `For 4/7(二) 開盤前看` 跟 Excel `4_7` sheet R237-R245 freeze ground truth
  全部對齊：台指期 -4,197 / 33,571 / (37,940) / 3,725 / 32,510 / (34,216)，
  CALL 開盤前多空 (4,329) — 1:1 match。

### Added
- `2025-11-06` ~ `2026-03-31` 完整 backfill（背景跑中，~104 個交易日，~9.5 分鐘）。

## [v0.6.x] - 2026-05-05 19:00~19:25 (中間版本未打 tag)
- font enlargement (16px → 19px / 21px → 24px) 但 table 寬度不變（padding 收）
- `<colgroup>` 設 col widths 收左右兩端、淨部位/開盤前部位較寬
- 負數紅色 `#d92929`（暗紅）→ `#FF0000`（純紅，Excel `[Red]` token）
- thead row 1 colspan 修正（之前 11 cols vs row 3 的 10 cols 不一致）

## [v0.6] - 2026-05-05 19:05

### Fixed (用戶連環抓到的格式錯誤)
- **負數沒顯示紅色** — `table.summary td { color }` (specificity 0,1,2) 把
  `td.neg { color }` (0,1,1) 蓋掉了。改成 `table.summary td.neg` 提高
  specificity (0,1,3)。
- **「For 開盤前看」cell 底色錯** — 同 specificity 問題，被
  `table.summary thead th { background }` 蓋掉。改成 `table.summary thead th.for-corner`。
- **數字格式不分**：所有負數都用 `-N`。實際 Excel numFmt 兩種：
  - `177` (`#,##0_ ;[Red]\-#,##0\ `) → 口數/成本/收盤價/夜盤 → `-1,749`
  - `178` (`#,##0_);[Red]\(#,##0\)`) → 淨部位/開盤前部位/開盤前多空 → `(46,947)`
  分別寫了 `tdMinus` 跟 `tdParen`。
- **括號破壞數字對齊** — Excel `_)` 表示「正數後面留 `)` 寬度的空白」。
  在 fmtParen 對 positive 加上 `<span style="visibility:hidden">)</span>`
  做隱形占位，個位數對齊 negative 的 `)` 前一位數字。
- **粗體擅自加** — Excel 全部 cells `<b/>` 都不存在 (non-bold)。css 全部
  `font-weight: normal`。
- **商品名稱顏色亂改** — Excel font color 全部 theme=1 (= 黑)，我改成棕色。改回。
- **PUT row 整列粉色 hardcode** — 實際 R244 整列 fillId=0 (透明白)，看起來
  粉色是 CF 規則 (PUT row dxfId 順序反轉，負→紅 / 正→綠)。移除 hardcode。
- **「柴柴」標題底色橘黃** — 實際 B237 fill=none (白)，我搞錯。改白。
- 字體 14px → 16px (Excel sz=12 等效)。標題 21px (sz=16)。

### Added
- **自動截圖驗證流程**：用 PowerShell + `msedge --headless --screenshot` 在改
  CSS / JS 後立刻 render 出 PNG 檢查，不再「自己看 CSS 字面以為對」。

## [v0.5] - 2026-05-05 18:54

### Changed (依用戶連續反饋全部一次到位)
- **Layout 對齊 Excel 慣例**：金融期 / 股票期貨 的「夜盤」欄、電子期 / 金融期 /
  股票期貨 的「開盤前部位」欄改為**留空**（per 工作表2 R240-R245 公式：這些 cell
  在 Excel 沒公式所以原本就空白）。
- **UX 改進**：移除「載入」按鈕。Date picker 改變即立刻載入新日期，URL 同步更新。
- **CF 上色規則 (mirror Excel)**：每對 (口數, 成本) cell 依「口數」正負上色：
  - 口數 < 0 → 淡綠 #E1EEDB（空方占優）
  - 口數 > 0 → 淡紅 #FBC9C6（多方占優）
  - 口數 = 0 / 空 → 預設白
  - 規則 dxfId/cfRule 從 sheet109.xml 直接拆出來
- **框線粗細**：D 欄(收盤價)右、F 欄(成本)右、H 欄(夜盤成本)右、開盤前部位左用
  2px 粗線（mirror Excel `thick` border）；其他細線。Header rows 底端加粗。
- **字體**：標楷體（DFKai-SB / 標楷體 / Kaiti TC fallback chain）跟 Excel 一致。
- **賣權 PUT 整列粉色 row background** (Excel row-level fill)。

### Added — DB 資料
- Backfill 整個 2026/04 (22 個交易日) 進 DB raw 表，dashboard 任一 4 月日期
  立即可看完整 6 列。

## [v0.4] - 2026-05-05 18:39

### Fixed (重大: 夜盤資料 shift 1 天)
- **TAIFEX night endpoint 是用「session 結束日」(T+1) 當 queryDate，不是開始日 (T)**。
  之前抓「T 日夜盤」用 `queryDate=T` 實際拿到的是「T-1 日夜盤」(T-1 15:00 ~ T 05:00)，
  整個夜盤資料 **shift 一天**。用戶從 `4_15` sheet (freeze 純數字) 對照才看出來。
  - 修法：`fetch_op` / `fetch_fut` 對 night session 內部把 queryDate 換成 T+1
    (skip weekends)，但 `session_date` 仍是 T，DB 寫入按 T 命名，符合柴柴/輝哥 label。
  - 驗證：4/14 night 臺股期貨 自營商 net_lots=31, 外資=-296 — 1:1 match Excel `4_15` R133/R135。
  - 教訓：之前比對 1201 .xlsm 的 live mirror sheet `2夜盤OP` 抓對到 queryDate=4/16
    (因為那 mirror 本身是 default queryDate=今天 抓出來的 cached) — 同一條 path 不算驗證。
- 清掉 DB 所有 daynight='night' 舊資料 (date 都標錯) 重新 backfill。
- `_parse_legal_table` 對空 response (future date / holiday / no session) graceful 回 []，
  不再 IndexError 把整個 refresh 拖垮。5/5 night 因為 5/6 是未來日無資料，
  4/30 night 因為 5/1 是勞動節 holiday，現在都會 silent skip。

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
