# Changelog

## [v0.9.4] - 2026-05-05 23:59

### Fixed
- **綜合整理 sticky thead 完全失效** — 用戶截圖顯示 R1+R2 跟 row 一起被滾走。
  Root cause: `border-collapse: collapse` 跟 `position: sticky` 在 `<th>` 上不
  相容（Chromium/Edge 已知 bug）。改 `border-collapse: separate; border-spacing: 0`，
  border 只畫 right+bottom + table 外 left+top 補齊。Playwright 驗證 scroll 800px
  後 R1+R2 仍 stick wrap top，R1→R2 gap=0px。

### Added
- **TAIFEX 電子期 (TE) / 金融期 (TF) 日收盤抓取**
  - `taifex.fetch_fut_price(query_date, commodity_id)` 加 `commodity_id` 參數
    (default "TX" 維持向後相容)
  - `app/refresh.py`：每次 refresh 同時 POST TX + TE + TF 寫入 `fut_price`
    （`contract` 欄位區分）
  - `scripts/backfill_fut_price.py`：每個 date 內 loop 三個 commodity，
    同步 backfill 整段 history
  - 驗證 2026-04-30：TX 39360 / TE 2527 / TF 2491 三 contract 都拿得到
- `scripts/verify_sticky.py` — Playwright sticky/scroll 視覺與量測驗證

## [v0.9.3] - 2026-05-05 23:35

### Fixed (用戶連續抓到 3 個問題)

#### 1. 16 個 holiday-前一交易日 漏抓 night session
- 例：2026-04-30 (勞動節前)、2024-04-30、2024-10-09 (國慶前) 等
- Root cause：`_next_business_day` 只 skip weekend，holiday 前一交易日的 night
  session = T 15:00 ~ next-trading-day 05:00 跨假，但 fetch 時 queryDate=T+1
  正好打到 holiday → endpoint 0 rows → 永遠沒寫
- Fix：`_next_business_day` 改用 DB lookup（next trading day with day-session），
  holiday-aware；對 16 個漏抓 dates 個別 re-fetch 補進 op_legal/fut_legal night
- Verify: 16/16 都成功補回

#### 2. daily_summary 對歷史段缺 row + op_legal_net / fut_pre_open_net 永遠空
- Root cause #1：FinMind backfill 直接寫 raw 表，不經過 refresh()，daily_summary
  對 2020-2023/05 段沒 row。
- Root cause #2：我之前說 op_legal_net / fut_pre_open_net 「公式不明」是錯的。
  Excel 的 daily_summary 用 `=INDIRECT('sheet'!E$240)` / `J$243` 從每日 sheet 的
  R240/R243 (= 主表的「台指期淨部位」+「開盤前部位」) 抓的。**那就是主表已經算
  的公式**：台指期等效大台 OI 淨 (= 大台 + 小台/4 + 微台/20) + 夜盤交易淨。
- Fix：寫 `scripts/recompute_daily_summary.py` 從 raw tables 重算所有 1,536 天的
  daily_summary，含 op_legal_net + fut_pre_open_net 兩欄。
- Verify: 2026-04-14 重算 = -44,447.15 / 8,777，跟 Excel 4_15 sheet R104 ground
  truth 完全 1:1 對齊。

#### 3. 綜合整理 view UI
- 加淺灰框（`#d0d0d0`，per user "顏色不用太深"）
- font 16px → 14px、padding 收緊，1920×1080 viewport 100% 縮放可 fit 完整 15 cols
- table-wrap right padding 加大避免最右 border 被切

#### 4. margin panel 不顯示小數點
- `fmtOku()` 改 `Math.round(v).toLocaleString()` (DB 還是 raw decimal)

#### 5. 綜合整理 group header 真 merge + sticky 置頂
- R1 group header 用 colspan: 「台指期」 colspan=2、「選擇權未平倉」 colspan=4、
  「融資餘額佔市值比」/「融資餘額」/「總市值」各 colspan=2
- 「For 開盤前看」/「前一日日盤Data」/「股票期貨」用 rowspan=2 跨頂兩 row
- `<colgroup>` 設 explicit %widths: 上市/上櫃 sub-col 等寬 (6%/6%)
- `table-layout: fixed` 確保 colgroup widths 生效
- thead 兩 row sticky 到 viewport top (移除 page header sticky 避免衝突)

### Added
- `scripts/recompute_daily_summary.py` — 從 raw tables 重算 daily_summary，
  歷史 backfill 後可一鍵 reconstruct
- `scripts/fix_missing_night.py` — 找出 missing night sessions 並 holiday-aware 補抓

## [v0.9.2] - 2026-05-05 23:14

### Fixed (用戶抓到 refresh button 沒生效)
- **JavaScript timezone bug**：`Date.toISOString().slice(0,10)` 在 UTC+8 (台北) 會
  把本地午夜倒回前一天。前端 `doRefresh` 算 dataDate 時受害 — view_date=5/6 算成
  data_date=5/4 而不是 5/5，server 收到的 target_date 永遠少一天。
  - 修法：改用 `getFullYear()` / `getMonth()` / `getDate()` 從本地分量組字串。
  - User 23:09 按 refresh 跑去 backfill 5/4 而 5/5 的 daily_summary 永遠沒被
    update — 5/5 信用統計欄一直顯示「—」的根因。
- **誣賴用戶事件**：我之前看 refresh_log 只看 `target_date='2026-05-05'` 的 entry
  (3 個)，沒看到 23:00+ 的，就歸因「endpoint 還沒釋出」。實際上 user 真的有按，
  只是 timezone bug 讓 entry 寫到 target_date='2026-05-04'。應該先驗證 client
  side 行為再下結論。

### Changed
- 微台條件邏輯（per user "在還沒有微台的時代就拿掉不計入"）
  - `app/dashboard.py` 加 `has_micro = date >= '2022-03-28'`，view 早於微台上市日
    時，「台指期」公式不含「微型臺指期貨」項。

### Added (進行中, 此 commit 含 scaffold)
- `app/scrapers/finmind.py` — FinMind 第三方 source scraper（2020+ 三大法人 OP /
  期貨 / 台指期 OHLC 含日夜盤）。
- `scripts/backfill_finmind.py` — bulk-fetch FinMind 整段歷史寫進 DB.
- `scripts/backfill.py` 加 `--dates-file` 支援。

### Notes — 第三方 source 限制 (FinMind free tier)
- OP/FUT 法人**沒夜盤分離** — historical 夜盤欄位空白
- 期貨主商品 (TX/MTX/TE/TF) 有，**子商品 (微台/小電/小金) 跟個股期沒**
- TX 各到期月 OHLC ✓ 含日夜盤分離 (`trading_session=position/after_market`)

### 仍跑中 (不在本次 commit, 結果 v0.9.x 後續)
- 2023/05/05 ~ 2024/12/31 TAIFEX 直抓 backfill (PID 68132)
- 2020/02 ~ 2023/05/04 FinMind backfill (PID 15076)

## [v0.9.1] - 2026-05-05 22:08

### Fixed (用戶抓到「落單 row」)
- 綜合整理 view 顯示 4/6 / 4/3 等 holiday 自己占一行（其他欄位空白）。
- 根因：refresh.py 對任一日期都寫 `daily_summary` row，即使該日所有欄位都是
  NULL（holiday backfill 的副作用）。導致 daily_summary 多了 29 個「全空殼」row。
- 修法：
  1. 一次性掃 daily_summary 找「除 date 外所有欄位都 NULL」的 row → DELETE 29 個
  2. refresh.py 加防呆：若 merged 後所有欄位都 NULL 不寫；若 DB 已有同 date 的
     全空 row 順便 DELETE 清乾淨
- 順便整個 DB 掃了一遍：credit_summary 0 zombie、fut_price 0 orphan、
  credit_twse 0 orphan，僅 daily_summary 有此問題。
- daily_summary rows 348 → 319（= op_legal day-session date 數量，完全對齊）

### 加上日期 + 顏色 fix
- 兩個 page 的日期顯示 `M/D(週)` → `YYYY/M/D(週)` 帶年份（per 用戶反饋）。
- 綜合整理 td.neg specificity 修：`table.zonghe td { color: var(--fg) }`
  (0,1,2) 原本蓋掉 `td.neg { color: red }` (0,1,1)，所有負數都顯示黑色。
  改成 `table.zonghe td.neg` (0,1,3) 後純紅 #FF0000 正常生效。

## [v0.9.0] - 2026-05-05 21:51

### Added — 綜合整理 view
- 新 page `/comprehensive` — 復刻 Excel「綜合整理」 sheet 的 timeseries view。
- 新 endpoint `/api/comprehensive` — 回傳 `daily_summary` 全 rows + 每天對應的
  `view_date`（= 之後最近一個 trading day, 由 DB 動態算出）。
- 主表 header 加「綜合整理 →」link。

### Layout decisions (per Excel sheet110 inspect)
- 15 cols: A,B (日期 labels) + C-I (台指期/選擇權/股期 數字) + J-K (融資佔比%)
  + L-M (融資餘額億元) + N-O (總市值兆元)
- 2-row header: R1 group label (台指期/選擇權未平倉/股票期貨/融資餘額佔市值比/
  融資餘額/總市值) + R2 column header
- **無邊框、無底色、無 zebra** — pure white per Excel
- Sticky thead (mirrors Excel frozen pane ySplit=2)
- numFmt 各欄精確 mirror Excel:
  - C 欄 (日盤收盤): `#,##0` 千分位無括號
  - D-I (期權淨部位等): `#,##0_);[Red](#,##0)` 千分位 + 紅色負括號
  - J-K (融資佔市值比): `0.0000%` 4-位小數百分比
  - L-M (融資餘額億元): accounting `#,##0`
  - N-O (總市值兆元): `0.00_);[Red](0.00)` 2-位小數紅色負括號
- 字體標楷體 sz=12 (16px), 不 bold (mirror Excel font)
- 倒序排列 (newest first) 方便 daily 看
- 範圍涵蓋「每個 trading day 都一行」(115 dates from 11/2025 onward, 比 Excel
  102 entries 多覆蓋一些 Excel 跳過的日子如 4/13)

### Notes
- Excel cells 用 `=INDIRECT("'sheet_name'!cell_ref")` 跨 sheet 抓彙整 (R237-R245
  area)。我的版本不需 INDIRECT，直接從 daily_summary 表 query。
- 部分歷史 row (e.g. 2026/4/13) 有少數欄位 NULL — 因為 Excel migration 沒覆蓋
  那天 (Excel sheet 跳過)，且 mkt_cap endpoint only 5-day window 不能 backfill
  歷史 twse_mkt_cap_chao。Display 留空，不偽造數字。

## [v0.8.0] - 2026-05-05 21:31

### Added (兩個用戶要的新功能)

#### 1. 台指期收盤價歷史 backfill — 收盤價欄不再空白
- 新 endpoint `futDailyMarketReport`（POST + queryDate）支援 backfill 任意歷史
  日期。原本用的 `futDailyMarketExcel` (GET, only today) 是 v0.1 留下的限制，
  v0.6 README 還寫成「無法 backfill」。現在解了。
- `fetch_fut_price(query_date)` 新加可選 date 參數；無 date 時 fallback GET
  endpoint（保留原快路徑）。
- `refresh()` 現在會把 `target_slash` 傳給 `fetch_fut_price`，所以 backfill 跑
  任意日期都能拿到當日 TX 各到期月的收盤/結算/未沖銷。
- 新 script `scripts/backfill_fut_price.py` — 只跑 fut_price endpoint 補齊
  歷史，比 full refresh 快 ~3 倍。
- **319 / 319 trading days 全部跑完**，daily_summary.tx_close 也同步 fill。

#### 2. 主表下方加「上市/上櫃融資餘額」獨立 panel（依用戶要求）
- 從工作表2 R196 / R201（= '7信用交易' 表 B7 / B12）對齊到 daily_summary 的
  `twse_margin_amt_oku` / `tpex_margin_amt_oku`（仟元 → 億元 = ÷100,000）。
- 資料來源：VBA `GetTWSE_TPEX_Final_Correct_Value` 抓的 MI_MARGN（上市）
  + margin_bal_result（上櫃），早從 v0.1 就在 DB 裡，這次只是 UI 補上呈現。
- 獨立 div panel 在主表下方，**不混入主表**（per 用戶澄清「不要加進去表格」）。
- 跟 Excel 4_15 sheet 對齊：4/14 上市 4,149.55 億 ✓ / 上櫃 1,540.95 億 ✓

### Verified
- 截圖驗證 view_date=2026-04-15 view 跟 Excel 4_15 ground truth 1:1
- fut_price 319/319 dates ok=1 (refresh_log 全綠)
- daily_summary.tx_close 從 backfill 寫入後填滿原本因 endpoint 限制留 NULL 的 cells

### UI polish
- margin panel 改 `display: inline-flex` 寬度 fit content，不再延伸到主表右邊
  造成右側大量留白（per 用戶反饋「方框右邊太大了」）。padding 左右對稱各 14px。

## [v0.7.1] - 2026-05-05 21:14

### Added
- **Backfill 整個 2025 年**（2025-01-02 ~ 2025-11-05，221 weekday → 204 trading days，
  17 holiday graceful skip）。加上之前已有的 11/6/2025 ~ 5/5/2026，DB 現在涵蓋
  **319 個 trading days, 全部從官方 endpoints 真實抓取**。
- README 加入 TWSE 官方休市日曆 reference URL：
  - <https://www.twse.com.tw/zh/trading/holiday.html>（網頁版）
  - JSON API: `?date=YYYYMMDD&response=json`
  - HTML API: `?date=YYYYMMDD&response=html`
- README「已驗證資料正確性」段重寫，列出本次完整 sanity check 結果。

### Verified（針對「100% 確定」的多重驗證）
- 319 days row count 一致性：全部 op_day=30 / fut_day=73，0 anomaly
- 連續性檢查：5 個 gap > 4 天全為預期 holiday cluster
- 隨機 5 sample 重 fetch endpoint 對 DB 100% match
- 跟 TWSE 官方 2025 holiday list 18/18 完全一致（0 mismatch 兩邊）
- 4/7 view + 2/23 view 跟 Excel ground truth 1:1 match

### Fixed
- 1 個 1/1/2025 orphan night row 因 DB 沒 2024 資料無處 absorb，直接 delete。

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
