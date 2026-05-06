# Changelog

## [v0.10.44] - 2026-05-06 18:45

### Fixed: Scatter 圖 jargon 改白話

- 用戶: 「Pearson r = -0.144... 這啥?」
- 之前直接顯示「Pearson r = -0.144」對 retail user 是 jargon
- 改顯示「同步度 -0.14 → 幾乎不相關 (指數漲跌跟融資% 沒對應)」
- 分級:
  - |r| < 0.3 → 「幾乎不相關 (隨機)」 (不加方向, 因為太弱時方向沒意義)
  - 0.3 ~ 0.6 → 「中度同步」 / 「中度反向」
  - > 0.6 → 「強同步」 / 「強反向」
- 加上一行小字 「(n=X, 範圍 -1 反向 ~ 0 無關 ~ +1 同步)」 自我說明

### Self-reflect
- v0.10.43 的 reflect 不夠徹底 — 我自審「我看得懂」但忘了 jargon 對 retail user
  仍是門檻. 「我看得懂」 != 「user 看得懂」, 兩個分開檢查

## [v0.10.43] - 2026-05-06 17:39

### 綜合整理 表寬 fit + chart 4 mode toggle

#### 表寬縮 1615 → 1567 (1600 viewport fit, no h-scroll)
- 用戶: 「整張大表又超框了 (因為加了OTC指數進去)」+ 「台指期/OTC指數/融資餘額/總市值 padding 可以縮一點」
- `nth-child(4),(5),(15),(16),(17),(18)` cell padding 3px 5px → 3px 2px
- col widths: 台指期 75→60, OTC指數 80→65, 融資餘額 88→76 ×2, 總市值 88→78 ×2
- Playwright multi-viewport (1280/1366/1600/1920) 0 overflow ✓

#### Chart `/chart` 4 mode 切換
- 用戶: 「天馬行空... 多設計一點 ABCDEFGH 讓我驚喜」+ 「前提是你自己看的懂」
- Self-review 後砍掉 2 個 (combined 4 軸混亂、normalize 跟 stacked 重複)、留:
  - **A · 上下雙圖** (default) — 上 panel 加權指數+上市%, 下 panel OTC+上櫃%
  - **B · 純融資%** — 兩條 % line dual axis (= v0.10.41 base)
  - **C · 散佈圖** — 兩 panel scatter, 點 alpha gradient (淡=2020 → 濃=2026), 全段 Pearson r
    - 結果有意思: 上市 r=-0.144 (幾乎無相關), 上櫃 r=0.681 (中度正相關)
  - **D · 月份熱力圖** — 年×月 grid, color = 該月平均融資%, 上下兩 panel
- Mode toggle button bar in header, click 切, default = A
- `setMode(mode)`: destroyPlots() → renderLegend → render via RAF

#### Race-condition fix (stacked panel 高度=0)
- 之前 `panel.clientHeight` read 在 createElement+appendChild 同 sync block, layout
  還沒 reflow → uPlot 拿到 height=0 → canvas invisible
- 改 `getPanelSize(mode)`: 直接從 chartArea 父容器 clientWidth/Height 算, 不依賴
  child element layout

#### Tech
- `app/static/chart.html` 重寫: 4 render functions + DATA cache + mode bar
  - `renderStacked` / `renderOriginal` 用 uPlot
  - `renderScatter` 用 vanilla canvas (uPlot 不擅 scatter)
  - `renderHeatmap` 用 div grid (uPlot 不支援 heatmap)
  - `colorScale` 綠→黃→紅 lerp helper (跟 comprehensive 一致)
  - `pearsonR` static r 計算 (整段, 不是 rolling — rolling 對 trending series 統計
    上 questionable)
- `app/static/comprehensive.html` CSS:
  - `:nth-child(4)/(5)/(15)/(16)/(17)/(18)` padding 3px 2px override
  - colgroup col widths 縮

#### Verified
- 表寬 1567 ≤ 1600 viewport ✓ (Playwright 4 viewport 全 pass)
- 4 chart mode 全部 render 成功 (canvases / panels count match expectation) ✓
- Scatter Pearson r 計算正確 (上市 -0.144, 上櫃 0.681) ✓
- Heatmap 月份聚合正確 (2026-04 上市 0.35%, 上櫃 1.62% 對 DB 內值) ✓

## [v0.10.42] - 2026-05-06 17:25

### Added: 上櫃指數 (OTC index) col + chart zoom-out clamp

#### 綜合整理 加 OTC指數 col
- `daily_summary` schema 加 `tpex_index_close REAL` (17 → 18 cols)
- 「指數收盤」 R1 group colspan 2→3, 第三 col = OTC指數 (千分位+2 位小數)
- Backfill 1537 rows (2020-01-02 ~ 2026-05-06) 全段成功

#### 改用 TPEX 官方 endpoint (取代 FinMind)
- 用戶: 「FinMind TPEx 全段都有, 開幹 → 你要不要去抓官方資料, 要不然 FinMind 你
  等一下如果又被 rate limit」
- TPEX 官方 highlight endpoint 第 5 個 fields 是「**收市指數**」, 直接就是上櫃指數
  收盤 — 不用多開 HTTP, 跟既有 mkt_cap 共用同一 call
- `tpex.fetch_highlight` payload 多回 `tpex_index_close`
- `refresh.write_to_db` 寫入時 enforce `actual_date == target_date` (防 stale day,
  v2.08 STOCK_DAY_ALL 災難教訓)
- 移除 `_fetch_tpex_index` (FinMind helper)
- Cross-check: 既有 1537 rows (FinMind backfill) vs TPEX 官方 highlight 對 8 個
  random + 邊界 dates **0 mismatch** — backfill data 不需重抓, exact 一致 (407.44)

#### Chart zoom-out clamp (v0.10.41 build-on)
- 用戶: 「我一直 zoom out 時, 應該極限就是起始日 & 終點日吧」
- `attachWheelZoom` 新增 `dataMin`/`dataMax` clamp:
  - newMin < dataMin → newMin = dataMin
  - newMax > dataMax → newMax = dataMax
  - Edge: clamp 後 newMin >= newMax → fallback 全 range
- 拖曳框選 zoom 自動繼承 (因為 visible 已 clamped)

### Tech
- `app/db.py` schema: +`tpex_index_close REAL`
- `app/scrapers/tpex.py` `fetch_highlight`: 多抓「收市指數」 field
- `app/refresh.py` `write_to_db`: 加 actual_date guard + cols list 加 `tpex_index_close`
- `app/static/comprehensive.html`: R1 colspan 2→3, R2 加 OTC指數, tbody render 加 cell
- `app/static/chart.html`: wheel handler 加 dataMin/dataMax clamp

### Verified
- E2E single-day refresh: DB 寫入 407.44 對 2026-05-05 ✓
- Random 8 dates × FinMind backfill vs TPEX 官方: 0 mismatch ✓
- Playwright visual: 18 cells per row, OTC指數 col fits 80px width, 字不超框 ✓
- Headers: R1 「指數收盤」 colspan=3 covering 加權指數+台指期+OTC指數 ✓

## [v0.10.41] - 2026-05-06 17:50

### Added: 融資餘額佔市值比 走勢圖 `/chart`
- 用 uPlot CDN (~50KB) — 不破壞 「無 chart lib」 spec 太多 (CDN, no build)
- X 軸: 日期 (2020-01-02 ~ today, 愈右愈近)
- Dual Y 軸:
  - 左軸 (紅): 上市 TWSE % (range 0.16~0.91%)
  - 右軸 (藍): 上櫃 TPEX % (range 1.10~1.81%)
- 互動:
  - **滑鼠滾輪 zoom** (mouse pivot, scale around cursor)
  - **拖曳 pan** (uPlot internal drag)
  - **雙擊 reset** (回 full picture)
- 綜合整理 header 加 「📈 走勢圖」 button

### Tech
- `app/main.py`: `/chart` route → `static/chart.html`
- uPlot scales: `twse` + `tpex` 各自 auto-range
- Custom wheel handler 對 X 軸 zoom (uPlot 沒內建)

## [v0.10.40] - 2026-05-06 17:30

### Fixed (用戶: 綜合整理 spinner 應取代資料日期 info)
- 之前: refresh 時 spinner 顯示在右側 status, info 維持原樣
- 現在: spinner 取代 「資料日期 X · 上次 refresh Y ✓」 info 顯示
- 跑完 load() 自動 fetch 新 timestamp 替回 info

### Verified Playwright
- BEFORE: `資料日期 2026-05-06 · 上次 refresh 2026-05-06 16:31:10 ✓`
- DURING: `🔵 抓取資料中…` (spinner 取代)
- AFTER: 新 timestamp 自動寫回

## [v0.10.39] - 2026-05-06 17:20

### Fixed (用戶: 不要鉅細靡遺說 + spinner 主表沒看到)
- Refresh status 簡化到極致:
  - 1 天: `2026/5/6 ✓`
  - 多天: `3 天 ✓`
  - failed: `失敗`
- 拿掉所有「還沒收完盤 / 期貨 70/73 / 14:30 後再按」 細節
  (用戶: 沒 data 就是還沒出, 不需講)
- spinner 主表確認 Playwright 驗證有做, browser cache 影響

## [v0.10.38] - 2026-05-06 17:00

### Fixed (用戶: Catch-up: 0 ok, 1 incomplete, 0 skipped 這啥)
- 之前 status 是 jargon: `Catch-up: N ok, N incomplete, N skipped`
- 改白話:
  - 1 dates incomplete: `2026-05-06 資料還沒收完 (期貨 70/73) — 等 14:30 收盤後再按一次`
  - 1 dates ok: `2026-05-06 抓完 ✓`
  - 1 dates skipped: `2026-05-06 endpoint 還沒釋出 (假日 / 盤前太早)`
  - 多 dates: `2 天抓完 ✓, 1 天資料還沒齊`
- 兩 view 都用 `formatRefreshStatus()` 同樣 logic

### Added (用戶: refresh 時轉圈圈圖示)
- CSS `.spinner` (CSS keyframes spin animation, 14x14 px)
- doRefresh 開始時顯示「轉圈 + 抓取資料中…」
- 跑完替換成 status text

## [v0.10.37] - 2026-05-06 16:50

### Fixed (用戶: 兩 view Refresh 行為應一致)
- 之前: 主表 doRefresh 帶 `?date=<dataDate>` 走 single-day refresh
        綜合整理 doRefresh 不帶 date 走 catch_up_refresh
- 兩 API path 不同 → 行為 + status format 不同 → user 困惑
- Fix: 主表 doRefresh **拿掉 date param**, 都走 catch_up
  - 兩 view 都 hit `POST /api/refresh` (no params)
  - 都解析 `r.mode === "catch_up"` 同樣 status 顯示
- 結果: 兩 view 點 Refresh 行為完全一致

### 結合 v0.10.36
- catch_up always include today → 點 Refresh 一定 refetch today data
- v0.10.37 unify: 兩 view 同 endpoint, 同 logic, 同 status format

## [v0.10.36] - 2026-05-06 16:30

### Fixed (用戶: 綜合整理 Refresh 完全不 refresh, 顯示 「DB already up-to-date」)

#### Root cause
- catch_up_refresh 邏輯: 列出 `last_db+1 ~ today` 缺的 weekdays
- 如 last_db == today → target_dates empty → mode=no_op → 不 fetch endpoint
- 但 today 的 data 是 evolving (盤中 partial / 14:30 後 day session / 5:00 後 night session / 信用 mkt_cap 不同 timing)
- User 期待: click refresh **always** 對 today 重抓

#### Fix
- catch_up_refresh: **always include today_iso** in target_dates (if weekday)
- 即使 last_db == today, today 仍會 refetch 一次

#### Verified
- Click refresh: 8.3 sec, status `INCOMPLETE (op=30/30, fut=70/73)` (= 14:30 前 fut 還沒全釋出)
- 對 weekend (today is Sat/Sun): 仍 no_op (跳過, 因 endpoint 沒 weekend data)

### 之前主表為什麼 work
- 主表 doRefresh 帶 `?date=<dataDate>` query, API 走 single-day refresh (不 catch_up)
- single-day 不 check last_db, 一定 fetch endpoint
- 綜合整理 doRefresh 沒帶 date → 走 catch_up 預設

## [v0.10.35] - 2026-05-06 16:20

### UI: 綜合整理 header rearrange + 「For 開盤前看」 cell clickable

#### Header 加 Refresh button + 回主表 button + 資料日期/上次 refresh info
- 之前 layout: 「綜合整理 [muted text] ... [Refresh] [Status] [回主表]」
- 改 layout: 「綜合整理 [muted text] [Refresh] [回主表] [info: 資料日期 ... 上次 refresh ...] | [Status]」
- info 從 `/api/comprehensive` payload 帶 `last_data_date` + `last_refresh` (跟主表同 API source)

#### 「For 開盤前看」 col cells clickable
- cursor: pointer + color 藍
- hover underline + 淡藍 background
- click navigate to `/?view_date=YYYY-MM-DD` (主表該日)

### Verified Playwright
- cursor='pointer' / color='rgb(44,90,160)' / vd='2026-05-07'
- click → URL `/?view_date=2026-05-07` 跳主表 ✓

### Background sweep (PID 48498) 跑中
- full_sweep_v2.py 對 11 cols 全段 endpoint cross-check
- 進度 [75/1537] 跑 0 fixed (= DB match)
- chain `byoejn7mf` 等完成 auto-report

## [v0.10.34] - 2026-05-06 15:30

### 「第 2 DB」 比對 final report

`scripts/full_sweep_all_cols.py` 跑完全段 1536 dates × 4 endpoints
(tx_close / twse_margin / tpex_margin / tpex_mkt_cap):
- **Total fixed: 0 cells**
- **Failed: 0**

= DB 全段跟 endpoint 真值 100% 一致 ✓

我之前誤判 sweep stuck — 因 sweep stdout 進 chain output file 不是
process redirect file. 一定要看 task output 而不是 自己 redirect.

### Final audit (5 method, all dates)
- Weekly anchor cross-check: 0 mismatch
- TWII × ratio MAD-z 5σ: 2 borderline (春節 ratio 微擾)
- mkt_cap day-over-day jump: 0
- margin / mkt_cap MAD-z 5σ: 0
- margin day-over-day jump: 2 (真實武漢 2020-03-13 / 台疫 2021-05-17 crash)

### 結論: DB 高 confidence, 不需 rebuild fresh DB

## [v0.10.32] - 2026-05-06 15:10

### Fixed (用戶: 日盤口數欄上下數字對不齊 + 收盤價窄 + 日期超框)
- 主表 `max-width` 1050 → 1300px (用戶允許拉寬)
- col widths redistribute 容下「For 2025/11/27(四) 開盤前看」+ 收盤價 7%→8%
- 加 `font-variant-numeric: tabular-nums` 對數字 cells
  - 每 char (digit/comma/minus) 等寬 9.5px
  - 確保 row 之間 digit position 上下對齊 (column-style)

### Auto-verify Playwright
- 3 viewports × 5 dates = 15 場景 0 overflow
- 5 row 「日盤口數」 cell text width: 57.0 / 28.5 / 9.5 / 28.5 / 47.5 / 66.5
  全 9.5 倍數 → 字寬一致

### Note v0.10.31 README freshness 已 push, 此 commit 補功能修復

## [v0.10.30] - 2026-05-06 14:55

### Fixed (用戶: 字超框 + 你明明就有工具可以檢查)
- 我 v0.10.29 改 `table-layout: fixed` 沒驗 visual, col widths 跟 cell 內容
  不 match → 「(三)」 corner 超框 / 「開盤前多空」 col header 超框
- 修: redistribute col widths
  - corner 8% → 14% (容 「For 2026/5/6(三) 開盤前看」)
  - 開盤前多空 8% → 12% (容 5 中字 header)
  - 其他 col 縮 1-2%
- **Auto-verified Playwright**: 3 viewports (1366/1600/1900) × 5 dates
  (2020-03-25 / 2023-02-21 / 2024-08-15 / 2025-04-29 / 2026-05-06) = 15 場景
  全部 0 overflow

### Lesson
改 layout 不能只看數值, 必跑 Playwright 對 cell scrollWidth > offsetWidth check.
verify_sticky.py 跟 verify_main_view.py 已有 logic, 但 col widths fixed 後
也要 audit ALL cells (corner / header / data) 不 wrap.

## [v0.10.29] - 2026-05-06 14:45

### Fixed (用戶: 切換日期時表格欄寬會抖動)
- `table.summary` 加 `table-layout: fixed`
- 之前預設 `auto`, col widths 跟隨 cell content 動態調整
  → 切日期 content 不同 (e.g. -5,865 vs -643,205) → 寬度不一 → 視覺抖動
- 改 fixed 後 col widths 完全 follow `<colgroup>` % 值, 不 dynamic
- 驗證 2 dates (2026-05-06 / 2024-08-15) widths 完全一致 [506, 192, 132, 101]

## [v0.10.28] - 2026-05-06 14:35

### Fixed (用戶: 為什麼按 refresh 還要 Ctrl+F5)
- doRefresh 對 catch_up response 沒 handle, status 顯示「失敗」誤導用戶
  → 修: 解析 catch_up mode, 顯示 「N ok / N incomplete / N skipped」
- 主表 doRefresh **已經** await loadView 自動 reload, 之前看似沒更新是因
  status 顯示錯誤讓用戶以為 refresh 失敗

### Added: 綜合整理 view 加 Refresh button
- 之前只有主表有 button, 看綜合整理時要切回主表
- 現在綜合整理 header 也有 Refresh button + status, 同 logic 自動 reload

## [v0.10.27] - 2026-05-06 14:20

### Added: Refresh catch-up mode + 多層正確性防護

**用戶問**: 幾天沒按 refresh, 補完整 DB? 怎確保 fetch 正確? DB vs endpoint 不一致怎 handle? 兩 view 同步?

#### 1. Catch-up: `refresh.catch_up_refresh()`
- 找 DB MAX(date) → 補 last_db+1 ~ today 每個 weekday
- API: `POST /api/refresh` 預設 `catch_up=true`
  - `?date=YYYY` 指定單日 / `?catch_up=false` 關閉

#### 2. 三層正確性防護 (per day)
- **Endpoint actual_date 必須 match target** (防 stale fall-back, fetch_credit /
  fetch_mkt_cap 已 implement year-bug guard)
- **Row count sanity**: op=30/30 + fut=73/73 ✓ / partial → INCOMPLETE 警告
- **Conflict detection**: snapshot DB before refresh, fetch 後比對 9 cols
  diff > 0.5% 列入 `conflicts`

#### 3. 跑完 outlier audit
- 對補的 dates 跑 day-over-day check:
  - mkt_cap > 3% but TWII < 3% → suspicious
  - margin > 5% but TWII < 3% → suspicious
- 結果 in response `outlier_audit`

#### 4. 兩 view 自動同步
- DB single source of truth: `refresh()` 寫 `daily_summary`, 兩 view query 同 table
- 兩 view 都加 `Cache-Control: no-cache, no-store, must-revalidate`
- Ctrl+F5 強制 browser fetch fresh

### Test verified
- 模擬 today=2026-05-08 (last_db=2026-05-05): 自動 check 5/6/7/8
- 5/6 today=ok (op=30 fut=70) → 報 INCOMPLETE 因今天還沒 14:30 收盤
- 5/7 / 5/8 future = skipped (endpoint 0 rows)

## [v0.10.26] - 2026-05-06 14:00

### UI: 主表 max-width 1300px → 1050px (用戶: 欄寬太寬, 留太多空白)
- 數字 col 跟內容貼合, 沒多餘 white space

## [v0.10.25] - 2026-05-06 13:52

### MD freshness (用戶提醒): README 補完 v0.10 系列改動
v0.10.5 ~ v0.10.24 只 update CHANGELOG, README 沒掃, 補上:
- SQLite Schema 加 `option_settlement_dates` (v0.10.15)
- `daily_summary` 17 cols 含 `op_pre_open_cp_net` (v0.10.6)
- 「綜合整理 view 功能」段加: 17-col layout / settlement highlight (淡黃) /
  色階 (融資佔比上市/上櫃 各自綠→紅) / 窄 viewport 橫向 scroll
- 「資料完整度」 段更新到 v0.10.21 (1536 dates × 17 cols)
- 加 「Audit / Sweep 工具表」 (6 個 scripts: audit_and_fix_all,
  full_audit, detect_outliers, sweep_margin_outliers,
  full_sweep_all_cols, audit_raw_vs_endpoint)
- 加 「Outlier-detection 5 方法」 (weekly anchor / TWII MAD-z /
  day-over-day jumps + margin variants)

## [v0.10.24] - 2026-05-06 13:50

### UI revert: 總市值(兆元) 色階拿掉
- 用戶 review 後拿掉, 只保留 融資餘額佔市值比 上市/上櫃 色階

## [v0.10.23] - 2026-05-06 13:50

### UI: revert 融資餘額(億元) 色階, 改加在總市值(兆元)
- 用戶要求 revert v0.10.22 的 融資億色階, 改套在總市值
- 新 helper `tdParen2Scale` (= tdParen2 + colorScale)
- 4 cols 套色階: 上市% / 上櫃% / 上市兆 / 上櫃兆
- 上市/上櫃 各自獨立 range

## [v0.10.22] - 2026-05-06 13:40

### UI: 融資餘額(億元) 加色階
- 用戶要求 上市/上櫃 各自獨立綠→黃→紅
- 新 helper `tdAcctScale(v, mn, mx)` 同 tdPctScale logic
- pre-compute twseAmts / tpexAmts min/max
- 4 cols 都套色階 (上市%, 上櫃%, 上市億, 上櫃億), 各自 range

## [v0.10.21] - 2026-05-06 13:30

### Confidence audit (用戶: 對 DB 內容沒信心, 想建 fresh DB 比對)

`scripts/audit_raw_vs_endpoint.py` — 抽 30 random dates 跨 2020-2025
對 4 個 critical cells 全 fetch endpoint 比對:
1. `credit_summary.twse_margin_balance`
2. `credit_summary.tpex_margin_balance`
3. `daily_summary.tx_close` (TX nearest-month)
4. `op_legal` 個別 row (買權外資 OI net) — raw table spot check

### Result: 30 dates × 4 cols = 120 checks, 0 mismatches ALL CLEAN

跨年 sample (2020-03-09 ~ 2025-11-20) 全 match endpoint 真值. 不重建 fresh DB
(30-60 min 太貴), 此 sample 已給 high confidence.

## [v0.10.20] - 2026-05-06 13:00

### Sweep 找到 9 個 stale margin (用戶 flag 8 dates 中 6 個確認 stale)

`scripts/sweep_margin_outliers.py` silent background 跑完 (log buffered 沒 flush
但 process commit 進 DB):

| date | stale DB | endpoint 真值 |
|---|---|---|
| 2024-02-16 | 1367 億 | 2477.88 億 |
| 2024-03-19 | 1729 | 2720.07 |
| 2024-05-13 | 1753 | 2895.75 |
| 2024-06-03 | 1729 | 3012.38 |
| 2024-12-03 | 2219 | 3241.54 |
| 2025-02-21 | 2089 | 3217.84 |
| (3 dates user 沒 flag) | | |

= 用戶看到的 1367 / 1729 / 1753 / 2219 / 2089 都是 stale, sweep 修對.

### v0.10.19 (前一個 push)
- API 加 Cache-Control no-cache header 強制 browser fresh fetch
- detect_outliers.py 加 method 4+5 (margin MAD-z + day-over-day)

### Final audit (1535 dates)
- Weekly anchor 0 mismatch
- mkt_cap MAD-z 2 borderline (春節 ratio 短暫變動)
- mkt_cap day-over-day 0
- margin MAD-z 0
- margin jump 2 (2020-03-13 武漢 / 2021-05-17 台疫, 真實 market crash 不修)
- **TOTAL UNEXPECTED: 0**

## [v0.10.19] - 2026-05-06 12:55

### Fixed
- API `/api/comprehensive` 加 Cache-Control no-cache headers
- 用戶 Ctrl+Shift+R 還看到 stale 因 browser cache, 加 header 強制 fresh fetch

### Improved detect_outliers.py
- Method 4: margin/mkt_cap ratio MAD-z (rolling 21-day, 5σ)
- Method 5: margin day-over-day jump > 5% **but TWII < 3%**
  (區別「真實 market crash」 vs 「真 outlier」)

## [v0.10.18] - 2026-05-06 14:15

### 5 個 changes 集中 push (前面 v0.10.17 push 的是 hover/settlement 顏色)

#### 1. Settlement strategy: calendar predict + verify
- 用戶 valid 質疑「每月第一次 refresh 多打 endpoint 沒用」
- 改用「第三 Wed」規則 (97% 準, 76 dates 中 74 對 — 春節 2 個順延例外)
- Logic: DB cached + price → skip / predicted + target<predicted → skip /
  target>=predicted → fetch verify
- 颱風/holiday 順延: endpoint 自動有真值, fetch 時 DELETE predicted INSERT actual
- Pre-insert 未來 7 個月 predicted entries (2026-05 ~ 2026-11)

#### 2. 補完 2020 結算日
- TAIFEX endpoint 怪規律: result 從 `start_month + 9` 起
- 改 query `start=2019/04` → 76 rows (2020/01 起完整) vs 之前 67

#### 3. Excel 色階 (融資餘額佔市值比)
- 上市/上櫃 各自獨立色階 (twsePcts/tpexPcts 各算 min/max)
- 綠 #63BE7B → 黃 #FFEB84 → 紅 #F87171 (低→中→高)
- 顯示效果: 上市段範圍 0.16%-0.91%, 上櫃 1.10%-1.81%

#### 4. Outlier detection — robust 法 (用戶: 5% threshold 太鬆)
新 script `scripts/detect_outliers.py` 三個 robust method:
- **Weekly anchor cross-check**: mkt_cap_weekly vs daily_summary, exact match
- **TWII ratio MAD-z (5σ)**: rolling 21-day median absolute deviation
- **Day-over-day jump**: mkt_cap > 3% but TWII < 3% = 不正常

#### 5. 修了 6 個 stale outliers
- **mkt_cap 4 outliers** (寫成 today 2026-05-05 的 2x 值):
  - 2025-04-28 / 04-29 / 04-30 / 05-05 (= 跟 today MM/DD 同月日)
  - Wipe + interp 重算
  - 後 audit: 0 mismatch
- **margin 2 outliers** (寫成 today 4751.45 億):
  - 2023-08-23 / 2024-01-04
  - 重 fetch endpoint + recompute pct
- **Background sweep (PID 43175)** 跑全 1535 dates margin 找剩餘 stale

### Final audit (after fix)
- Weekly anchor cross-check: 0 mismatch ✓
- TWII ratio outliers: 6 → 2 (剩 2023-01-05/06 borderline z=5.0 春節)
- Day-over-day jump: 4 → 0 ✓

## [v0.10.16] - 2026-05-06 12:50

### Added (用戶: refresh 時也要 trigger settlement check, 想 efficient 法)

#### `_maybe_fetch_settlement_dates(target_date)` 加進 refresh
- DB cache check first (PK index, ~0.8ms)
- Cache miss → fetch TAIFEX endpoint, query 「target month + 6 個月 ahead」
  一次 cache 多月 (settlement 一月 1 個, 規律)
- **In-memory negative cache** (1 hr TTL): 對 endpoint return 0 rows 的月份
  (= 未來月份 settlement 還沒釋出), 1 小時內不重打

### Performance verified
| 情境 | 耗時 |
|---|---|
| DB cached (歷史月份) | ~1.5ms |
| Future month, first call (endpoint hit) | ~400ms |
| Future month, re-call (neg-cached) | ~0.8ms |
| Past month, never cached | ~400ms one-time |

每天第 1 次 refresh 對 future month 多 ~400ms (settlement 未釋出),
之後 neg-cache 零成本. 該月實際結算後 endpoint 有資料, 1 hr cache 過期
重打就寫進 DB.

### Refresh idempotency 仍保持
- 已有 DB row 的月份, refresh 不會重打 endpoint
- 連續 refresh 5/6 兩次, 第 2 次 settlement check 0.8ms

## [v0.10.15] - 2026-05-06 12:30

### Added (用戶: 標記電子選擇權月選結算日)

#### 新 schema: option_settlement_dates table
```sql
CREATE TABLE option_settlement_dates (
    date TEXT NOT NULL,
    product TEXT NOT NULL,        -- 'TEO' / 'TXO' / 'TFO'
    contract_month TEXT,           -- '202604' (純 6-digit = 月選)
    settlement_price REAL,
    PRIMARY KEY (date, product)
);
```

#### Source: TAIFEX optIndxFSP endpoint
- URL: `https://www.taifex.com.tw/cht/5/optIndxFSP`
- POST form: `start_year`, `start_month`, `end_year`, `end_month`, `commodityIds=8` (TEO)
- Response: HTML table 含 (最後結算日, 契約月份, settlement price)
- Filter contract_month matching `^\d{6}$` 為**月選** (排除週選 W1-W5 / F1-F5)

#### Backfilled 67 TEO 月選結算日 (2020/10/21 ~ 2026/04/15)
- TEO 上市 2019/10, 之前 2020/01-09 沒這 contract → daily_summary 那段不會 highlight

#### UI: comprehensive view 加 row highlight
- `/api/comprehensive` payload 多 `is_settlement: bool`
- `tr.settlement` background `#FFF8DC` (cornsilk 淡黃)
- hover 變 `#FFEFA0` (深一點黃)

### Verified
- Playwright: 67 `tr.settlement` rows / 1536 total ✓ 跟 DB 一致

## [v0.10.14] - 2026-05-06 11:55

### UI (用戶: 切換按鈕要直覺清晰)
- 主表 → 綜合整理: 「綜合整理 →」 link → 「📊 綜合整理 (歷史總表)」 button
- 綜合整理 → 主表: 「← 回主表 (For 開盤前看)」 link → 「← 回主表 (For X 開盤前看)」 button
- 兩邊都加 `.nav-btn` class (outline style: 白底藍邊 / hover 反白藍底)
- 視覺上區別於 「Refresh 抓最新」 (solid blue) — 一個是「同步動作」, 一個是「換頁」

## [v0.10.13] - 2026-05-06 12:10

### 用戶要求 deeper audit (含 refresh) — 找到 2 個 bug

#### Bug #1: refresh wipe twii_close + mkt_cap_source ⚠️
- 之前 refresh 寫入 daily_summary 的 `cols` list 沒含 `twii_close` 跟 `mkt_cap_source`
- SQLite `INSERT OR REPLACE` wipe 沒列出的 columns → refresh 後變 NULL
- 用戶下次按 refresh 馬上失去 加權指數 + mkt_cap_source flag
- **驗證**: refresh(2026-05-05) before twii=40769.29, after twii=NULL
- Fix: `cols` list 加 `twii_close` + `mkt_cap_source`, summary 加 carry-over
- **Bonus discovery**: TWSE FMTQIK endpoint (`fetch_turnover` 已 return) 自帶
  `twii_close`, 改成優先用它, 不依賴 FinMind quota

#### Bug #2: mkt_cap_source 永遠 None 對 official mkt_cap
- _post_refresh_aggregate 只 set `'interp'` 對 NULL mkt_cap
- 對 5/5 / 5/4 等 official mkt_cap 從不 set source → 永 NULL
- Fix: write_to_db 對 official mkt_cap 直接 set `'official'`

### Idempotency verified
- refresh(2026-05-05) 跑 2 次, 14 cols 全 unchanged
- refresh(2026-05-04) historical date 也 idempotent (pct float rounding ~1e-15
  雜訊不算 bug)

### Endpoint year-bug audit
- TWSE MI_MARGN: honor historical date ✓
- TWSE FMTQIK: honor historical + 自帶 TWII close ✓
- TWSE homeApi/mkt_cap: 5-day window only (v0.10.12 加 7-day guard)
- TPEX 3 endpoints: 全 honor historical ✓

## [v0.10.12] - 2026-05-06 11:50

### 用戶要求 full audit 找漏的 bug — 找到 1 個

#### Bug: fetch_mkt_cap 對 historical 同月日 寫 stale today value
- TWSE `homeApi/mkt_cap` endpoint return `[['MM/DD', mkt_cap_oku], ...]`
  最近 5 trading days, **沒 year**
- `fetch_mkt_cap(target_date_dash)` 對歷史 date 比 MM/DD, 同月日 (5/5/4-29/4-30)
  match 到 today (2026) 的 entry → 寫 today's mkt_cap 到 historical row
- 這影響 3 個 dates 的 `credit_summary.twse_mkt_cap`:
  - 2023-05-05: 寫 1,329,411 億 (= 2026-05-05 值, 正確 ~493,000 億)
  - 2024-04-29: 寫 1,281,726 億 (= 2026-04-29 值)
  - 2024-04-30: 寫 1,269,524 億 (= 2026-04-30 值)
- 連帶 `recompute_daily_summary.py` 用 stale mkt_cap 算 `twse_margin_pct`,
  3 個 dates pct 算錯一半左右

#### Fix
- `app/scrapers/twse.py:fetch_mkt_cap`: 加 7-day window guard
  - target_date 在 today-7 ~ today+1 才 honor MM/DD match
  - 否則 return `actual_md=None mkt_cap_oku=None note="out-of-window"`
  - 原意: endpoint 限制 5-day window, 對歷史本來就應該 reject
- 立刻 wipe 3 個 stale `credit_summary.twse_mkt_cap` 寫 NULL
- 重算 3 dates 的 `daily_summary.twse_margin_pct` 從 cols (margin/mkt_cap)
  - 2023-05-05: 0.13% → 0.36% ✓
  - 2024-04-29: 0.22% → 0.43% ✓
  - 2024-04-30: 0.22% → 0.44% ✓

### Audit script 留下: `scripts/full_audit.py`
8 sections:
1. NULL count per col
2. Schema consistency
3. Derived field sanity (op_cp_net = call - put, pct = margin / mkt_cap)
4. Orphan detection (daily_summary <-> op_legal)
5. Trading days continuity (gap > 4 days = holiday cluster)
6. UI <-> backend column alignment (R2 cells == colgroup == JS td count)
7. Idempotency / spot-check 5 random dates
8. Final verdict (exit 1 if any issue)

ALL CLEAN after this fix.

## [v0.10.11] - 2026-05-06 11:30

### Audit (用戶: refresh 後綜合整理表所有 data 都要最新)

#### 找到 3 個 column refresh 後不會更新
- `op_legal_net` (台指期等效大台 OI)
- `fut_pre_open_net` (開盤前多空 = OI + 夜盤)
- `op_pre_open_cp_net` (選擇權開盤前多空, v0.10.6 加 column 沒寫)

Root cause: `cols` list 列了 `fut_pre_open_net` 但 `compute_daily_summary`
function 沒實作 → 永遠回傳 None → merge 時用 stale 值

#### Fix
- `compute_daily_summary` 加 3 個 column 的計算邏輯:
  - 大台 OI + 小台 OI/4 + 微台 OI/20 (微台 2022-03-28 後)
  - 加 fut_night net 同樣 components 算 fut_pre_open_net
  - 選擇權 CALL/PUT day OI + night net 算 op_pre_open_cp_net
- `cols` 加入 `op_pre_open_cp_net`

#### Bug 修副作用
- `recompute_daily_summary.py` INSERT OR REPLACE 沒列 `twii_close` /
  `mkt_cap_source` → 跑全段 wipe 1536 個 twii ⚠️
- 立刻 inline 用 FinMind backfill 1536 rows twii_close
- 重 tag 265 official mkt_cap rows + 跑 recompute_mktcap_interp 補 1271 interp

### 最終 audit (1536 dates × 16 cols)
- 全 0 NULL ✓ except `op_pre_open_cp_net` 808 NULL (= 2020-2023/04 沒夜盤
  預期 NULL, 不是 bug)

### 結論: refresh 後 16 個 column 都最新
| col | refresh 後更新? |
|---|---|
| tx_close | ✓ (TX 端點) |
| twii_close | ✓ (v0.10.10 加 FinMind) |
| op_legal_net | ✓ (這 PR 加) |
| op_call_net / op_put_net / op_cp_net | ✓ (一直有) |
| op_pre_open_cp_net | ✓ (這 PR 加) |
| fut_pre_open_net | ✓ (這 PR 加) |
| stock_fut_legal_net | ✓ (一直有) |
| twse/tpex_margin_amt_oku | ✓ (TWSE/TPEX 端點) |
| twse/tpex_mkt_cap_chao | ✓ (TWSE 5-day or interp via _post_refresh_aggregate) |
| twse/tpex_margin_pct | ✓ (派生) |
| mkt_cap_source | ✓ (post-aggregate set) |

## [v0.10.10] - 2026-05-06 11:00

### Fixed (用戶: 2026/5/6 加權指數空, 早上 refresh 過了還是空)

#### Root cause
- refresh.py 12 source 沒含 TWII
- TWII 是 v0.9.7 後 backfill 補的, 用 FinMind TaiwanStockPrice TAIEX
- 用戶 5/6 早上 refresh 5/5 → 12 source 跑完, 沒抓 TWII → 5/5 twii_close=NULL

#### Fix
- `app/refresh.py` 加 `_fetch_twii(target_date)` (FinMind TaiwanStockPrice TAIEX)
- `safe("twii_close", _fetch_twii, target_date)` 加進 refresh source list
- `write_to_db` 加 logic 把 twii_close 寫進 daily_summary
  (用 ON CONFLICT...UPDATE 避免覆蓋現有 row 的其他欄位)
- Inline 補 5/5 twii=40769.29 (= 用戶看到的那天)

驗證 _fetch_twii(2026-05-05) → 40769.29 ✓

## [v0.10.9] - 2026-05-06 10:45

### Reverted v0.10.8 (用戶: 我沒叫你改字體跟 title)
- 我擅自縮短 title + R2 字體 12px → 是錯的, 用戶要的是調整欄寬
- 字體還原 14px, R2 title 還原原始 Excel layout
  - 「開盤前看」 → 「For 開盤前看」
  - 「前一日日盤」 → 「前一日日盤Data」
  - 「日盤收盤」 → 「台指期」
  - 「淨部位」 → 「法人淨部位」
  - 「買權 CALL」 → 「法人買權CALL」
  - 「賣權 PUT」 → 「法人賣權PUT」
  - 「CP合計多空」 → 「法人CP合計多空」
  - 「上市億元」 → 「上市(億元)」 等

### Real fix: col widths in px (not %)
- 17 cols 各設 px 寬度，每欄都 fit nowrap title
- 總寬 1535px + padding ≈ 1568px
- 1700+ viewport 自然 fit；1280/1366/1500 viewport `.table-wrap`
  自動 horizontal scroll (`overflow-x: auto` 已存在)

### Verified 6 viewports
- 1280 / 1366 / 1500 / 1700 / 1900 / 2200 全 R2 height=24px (single line)
- 0 title overflow
- 數字 cell 也都 nowrap fit

## [v0.10.8] - 2026-05-06 10:30

### Fixed (用戶: title wrap 成 2 行 = 醜)

#### 我 v0.10.7 verify 邏輯錯了
- v0.10.7 量 `scrollW <= offsetW` 對 nowrap 有用，對 `white-space: normal` wrap 沒用
  (wrap 後 scrollW = offsetW = 沒 overflow, 但視覺上 2 line 還是醜)
- 用戶截圖 1900 viewport「前一日日盤Da」+「ta」確實 wrap 我沒抓到

#### Real fix
- thead 改回 `white-space: nowrap` (不允許 wrap)
- 縮短 R2 title (R1 group 已暗示 product, 砍「法人」prefix):
  - 「For 開盤前看」 → 「開盤前看」
  - 「前一日日盤Data」 → 「前一日日盤」
  - 「台指期」 → 「日盤收盤」 (clarify)
  - 「法人淨部位」 → 「淨部位」 (×2)
  - 「法人買權CALL」 → 「買權 CALL」
  - 「法人賣權PUT」 → 「賣權 PUT」
  - 「法人CP合計多空」 → 「CP合計多空」
  - 「上市(億元)」 → 「上市億元」 (砍括號)
- R2 font-size 14px → 12px (R1 group 維持 14px)

#### Improved verifier
- `verify_sticky.py` 加 line-count check (`offsetHeight > 30`)
- Tested 6 viewports (1280/1366/1500/1600/1900/2200) ALL PASS, 0 overflow

## [v0.10.7] - 2026-05-06 08:00

### Fixed (用戶: title 有些會超框)
- thead `<th>` `white-space: normal` + `line-height: 1.2` + `word-break: keep-all`
  允許長 title 折行 (數字 cell 在 `<td>` 仍 nowrap, 不影響資料 column)
- col widths 重排:
  - 5 / 6 / 5 / 5 / 6 / 6 / **7 / 7 / 7** / 6 / 6 / 5×6 (= 96%)
  - 「法人買權CALL」「法人賣權PUT」「法人CP合計多空」三長 title col 加大到 7%

### Verified across viewports (Playwright)
- 1366 / 1600 / 1920 px viewport 全部 0 overflow (scrollW <= offsetW)
- 17 cols 全 fit, 沒 title 超框

## [v0.10.6] - 2026-05-06 07:55

### Added (用戶: 選擇權未平倉的開盤前多空還是要有, historical 留空)
- 新欄位 `daily_summary.op_pre_open_cp_net` REAL
- 公式: (CALL OI day + CALL net night) - (PUT OI day + PUT net night)
  外資 + 自營商 (排除投信)
- 對 2023-05-04 之後 (有夜盤 op_legal): 計算
- 對 2020-2023/04 (沒夜盤 op_legal): NULL — 用戶要求 hardcode 留空
- Backfilled 728 dates, 808 dates 留 NULL

### UI: comprehensive.html 加回「選擇權 開盤前多空」 column
- R1 group「選擇權未平倉」 colspan=4 (CALL / PUT / CP / 開盤前多空)
- R1 group「台指期」 仍是 colspan=2 (法人淨部位 + 開盤前多空 = 大台等效)
- 兩個「開盤前多空」並存:
  - 台指期 group 的: `fut_pre_open_net` (大台等效 OI + 夜盤)
  - 選擇權 group 的: `op_pre_open_cp_net` (CALL/PUT 各別 OI + 夜盤 net 差)

### Verified samples
- 2026-04-30: op_cp_net=-6969 (day), op_pre_open_cp_net=-4334 (day+night)
- 2020-03-25: op_pre_open_cp_net=NULL (沒夜盤)
- 對應跟 op_cp_net 該不該等於 fut_pre_open_net 的問題: 兩者完全不同
  (一個是選擇權, 一個是台指期)

### Code touched
- `app/db.py`: schema 加 `op_pre_open_cp_net REAL`
- `scripts/recompute_daily_summary.py`: 算 op_pre_open_cp_net (NULL if no night)
- `app/static/comprehensive.html`: 17 cols, R1 group 重排 + 加 column

## [v0.10.5] - 2026-05-06 07:45

### Fixed (用戶: 選擇權未平倉的開盤前多空是不是亂算)

#### Layout bug — R1 group 把「開盤前多空」放錯位置
- 之前: R1「選擇權未平倉」 colspan=4 (CALL/PUT/CP/開盤前多空)
- 但「開盤前多空」 = `fut_pre_open_net` = 台指期等效大台 OI + 夜盤交易,
  跟選擇權無關！讓用戶誤以為是選擇權的開盤前多空
- Fix: R1 group 改成
  - 「台指期」 colspan=2 (法人淨部位 + 開盤前多空)
  - 「選擇權未平倉」 colspan=3 (CALL / PUT / CP)
- R2 column 順序也調整: 開盤前多空 移到「台指期 法人淨部位」旁邊

### Documented limitation (用戶問: 夜盤資料只到哪天)
- fut_legal night session 涵蓋 **2023-05-04 ~ 2026-05-05** (732 dates)
- **2020-2023/04 段 (~800 dates) 沒夜盤資料** — TAIFEX endpoint cutoff = 2023/05/05,
  FinMind 也沒給歷史夜盤
- 所以那段 `fut_pre_open_net` = `op_legal_net` (= 純日盤 OI 淨, 沒夜盤加成)
- 證據: 2020-03-25 op_legal_net=50088 == fut_pre_open_net=50088
- 2023-05-05 之後才會看到差值 (e.g. 2026-04-30: 差 1898 口 = 夜盤交易淨)

## [v0.10.4] - 2026-05-06 07:39

### 🎯 ALL CLEAN — 14 columns × 1536 trading days, 0 NULL

#### 補完用的 4 source unified backfill (PID 35537)
- `scripts/backfill_historical_unified.py` 一個 process 跑 4 source:
  - TWSE 信用 (FinMind TaiwanStockTotalMarginPurchaseShortSale)
  - TPEX 信用 (TPEX margin_bal_result endpoint)
  - 個股期合計法人 (FinMind TaiwanFuturesInstitutionalInvestors data_id='SF')
  - TPEX 上櫃總市值 (TPEX highlight endpoint)
- 結果: 809/809 dates: tpex_m / sf / tpex_cap = 全 cover, twse_m 卡 301 (FinMind quota)

#### Audit + auto-fix chain (PID 37188)
- `scripts/audit_and_fix_all.py` — 跑完 unified 自動 trigger
  - 4 個 fix strategies 串跑: derive pct / op_cp_net / mkt_cap interp / TWSE MI_MARGN
  - 對 ALL NULL twse_margin_amt_oku 用 TWSE MI_MARGN 抓 (WAF lift 後 honor historical)
  - 結果: 514 -> 6 NULL (508 fixed), 6 個 transient TWSE timeout
- Inline 補最後 6 dates (2021-09-22, 10-08, 2022-01-03, 03-11, 06-22, 2023-01-04)
  - 全成功重抓: 2635 / 2513 / 2824 / 2656 / 2141 / 1660 億
- Bug fix in audit script: SQLite connection closed at exit, retry logic for TWSE transient

#### Final coverage
| col | NULL |
|---|---|
| tx_close | 0 ✓ |
| twii_close | 0 ✓ |
| op_legal_net | 0 ✓ |
| op_call_net | 0 ✓ |
| op_put_net | 0 ✓ |
| op_cp_net | 0 ✓ |
| fut_pre_open_net | 0 ✓ |
| stock_fut_legal_net | 0 ✓ |
| twse_margin_amt_oku | 0 ✓ |
| tpex_margin_amt_oku | 0 ✓ |
| twse_mkt_cap_chao | 0 ✓ |
| tpex_mkt_cap_chao | 0 ✓ |
| twse_margin_pct | 0 ✓ |
| tpex_margin_pct | 0 ✓ |

## [v0.10.3] - 2026-05-06 01:14

### Fixed (md freshness — 用戶提醒每次 commit 必掃)
- v0.10.2 寫「yfinance 裝不起來」是**誤診** — 實際是我用 `pip install -q + timeout=60s`
  太短，pip 還沒下載完就被 timeout kill；無 -q 重跑「Successfully installed yfinance-1.3.0」
- 補：FinMind 從 HTTP 402 (quota) 升級到 HTTP 403 (`ip banned`)，24h-7d 才解
- README 的 SQLite schema 補 `twii_close` / `mkt_cap_source` / `mkt_cap_weekly` (v0.9.7 起欄位)
- README 「Backfill 涵蓋範圍」段更新到 v0.10.x 現況 (1536 dates、新 source 對應、缺欄位列表)
- README 「twse_mkt_cap_chao 資料策略」段更新成 FinMind TaiwanStockPrice (取代 v0.9.7 的
  TWSE MI_5MINS_HIST，因後者觸發 WAF ban)

## [v0.10.2] - 2026-05-06 01:48

### Fixed (用戶: 融資餘額/佔市值比 還有漏)
- twse_margin_pct: 之前 recompute_daily_summary 從 credit_summary 算 pct,
  但 credit_summary.twse_mkt_cap 對歷史段沒值 → pct=NULL 即使 daily_summary
  其他 col 有值
- Fix: SQL 直接從 daily_summary cols 算: `pct = margin_amt_oku / (mkt_cap_chao × 10000)`
- Updated 774 rows (pre 84% NULL → 後段 NULL 大幅減少)

### Audit + 老實列剩下不能補的
- 2023-05-05 之後 (727 rows) 還有 11 個 dates twse_margin_amt_oku NULL:
  2023-08-16, 2023-08-31, 2024-01-03, 2024-03-22, 2024-09-26,
  2024-11-01, 2024-12-10, 2025-01-16, 2025-06-12, 2025-08-14, 2025-10-13
- 2020-2023/05 段全 NULL: twse_margin_amt_oku / tpex_margin_amt_oku /
  tpex_mkt_cap_chao / stock_fut_legal_net (~800 dates each)

### 三個 source 卡死

| Source | 狀態 | 升級狀況 |
|---|---|---|
| TWSE WAF (MI_5MINS_HIST / MI_MARGN) | HTTP 307 ban | 等 ~1h+ lift |
| FinMind 免費版 | HTTP 402 quota 用完 | 後升級成 HTTP 403 `ip banned` (24h-7d) |
| ~~yfinance 裝不起來~~ | **誤診修正** | 實際裝得起來 (我用 -q + timeout=60s 太短假象), 但只給個股 price 沒「TWSE 融資餘額」, 不解我們的問題 |

### Added
- `scripts/backfill_historical_unified.py` — 一個 process 抓 4 source
  (留著等 quota / ban reset 後再跑)
- `scripts/backfill_credit_summary.py` — TWSE+TPEX 信用 backfill (FinMind+TPEX)

## [v0.10.1] - 2026-05-06 01:30

### Fixed (用戶: For 開盤前看 第一個是空的 / 能不能自動一點)

#### #1 最新 row 的 view_date NULL
- Root cause: `/api/comprehensive` 從 op_legal 算 `next_map`,
  最新 trading day 沒下一個 → next=None → frontend 「For (空) 開盤前看」
- Fix: latest row 用 calendar fallback (`next weekday`, skip 週末)
- 驗證: 2026-05-05 → view_date=2026-05-06 ✓

#### #2 Refresh 後沒 auto-aggregate (用戶嫌手動)
- 之前: `homeApi/mkt_cap` 只給 5 天, refresh 拿不到時 daily_summary 寫 NULL,
  user 還要手動跑 `recompute_mktcap_interp.py` 才看得到. pct 也不會自動算.
- Fix: `app/refresh.py` 加 `_post_refresh_aggregate(target_date)` hook
  - 對該 date 若 mkt_cap NULL: 用 weekly anchor + TWII 比例 internal interp
  - 寫 `mkt_cap_source = 'interp'`
  - 重算 `twse_margin_pct = margin_amt_oku / (mkt_cap × 10000)`
  - Idempotent — 'official' rows 不被覆蓋
- 結果: 用戶每次按「Refresh 抓最新」自動完成 aggregate, 不用手動跑 script

### Background TE/TF backfill 完成 (PID boy7b23dc → exit 0)
- 2025-04-15 ~ 2026-05-05 段補完
- Playwright verify 7 historical dates ALL PASS

### Background started (PID 33669)
- `backfill_credit_summary.py --from 2020-01-01 --to 2023-05-04`
- 補 TWSE / TPEX 信用餘額 2020-2023/05 段 (809 dates, ~7 min)

## [v0.10.0] - 2026-05-06 01:18

### Fixed (用戶: 加權指數怎麼也缺那麼多)
- 加權指數 / 上市總市值 對 2024-03 ~ 2026-05 段全 NULL (542 dates)
- Root cause: TWSE WAF 把連續 50+ requests 的 IP 暫時 ban,
  之前 `MI_5MINS_HIST` endpoint 抓不到後段 month
- **改用 FinMind `TaiwanStockPrice` data_id='TAIEX'** — 給 OHLC + Trading_money,
  分 26 quarterly chunks, 寫 1536 rows 全段覆蓋
- 重跑 `recompute_mktcap_interp.py` → 1421 interp rows (其中 1191 是新補的)

### Cleanup edge case
- 2024-10-31 (康芮颱風): 股票休市但期貨夜盤有開 → `op_legal` 有 6 night rows
  → `daily_summary` 被 recompute 寫入 row 但 TAIEX 那天沒值 → 永遠 NULL
- DELETE: orphan 規則 = `daily_summary` row 沒對應 day-session op_legal 就刪
- 命中 1 row (= 2024-10-31), op_legal 保留 (真資料)

### Final coverage (1536 trading days)
- `twii_close`: 0 NULL ✓
- `twse_mkt_cap_chao`: 0 NULL ✓ (115 official + 1421 interp)

## [v0.9.9] - 2026-05-06 01:08

### Fixed (用戶罵醒：「自己不會驗證嗎」「每次都憑感覺亂猜」)
- **主表 (For X 開盤前看) 電子期 / 金融期 close 永遠空** — 不管後端 emit 啥
- Root cause: `app/static/app.js:147` 寫死 `${i === 0 ? closeCellHTML : ...empty}`
  — 只有第一 row (台指期) 才用 closeCellHTML，2/3 row 永遠 empty
- 已在 v0.9.5 修 dashboard.py emit close_price for 電子期/金融期，但
  frontend 寫死的條件壓過去 → 我之前看 raw API 有值就以為 OK，沒驗 UI

### Added
- `scripts/verify_main_view.py` — Playwright 驗主表多日期 close 真的渲染
- 跑 7 個歷史日期 sample，5/7 通過；剩 2 dates (2025-08-18 / 2026-04-15)
  TE/TF 還空是 DB 沒 backfill (因 PID 16876 中途 kill 過)，inline 重跑中

## [v0.9.8] - 2026-05-06 00:54

### Fixed
- **歷史 (2020-2023/04) 任挑一天主表電子期 / 金融期 close 都空**
  - Root cause: 那段是 FinMind backfill 段 (TAIFEX cutoff 之前)，但
    `app/scrapers/finmind.py` 的 `fetch_fut_price_tx` 寫死只抓 TX
  - Inline 補了 14 個 quarterly chunks: TaiwanFuturesDaily data_id=TE/TF
  - 寫入 fut_price 5,615 (TE) + 5,749 (TF) rows
  - 含 OHLC + day_vol + ah_vol + settle + oi (跟 TX 結構一致)
  - 隨機 7 dates sample 驗證 (2020-03-25 ~ 2022-04-29) close 都合理範圍

### Coverage 進度
- TX: 1,536 dates (2020-01-02 ~ 2026-05-05)  全段
- TE: 1,303 dates (2020-01-02 ~ 2026-05-05)  缺 ~230 dates 2025-04-15+
- TF: 1,303 dates                              同 TE，等 background backfill_fut_price 跑完

### Background tasks 進度 (snapshot)
- `backfill_fut_price.py --from 2023-05-05` (PID 16876): 470/727 (65%), ETA ~13 min
- `backfill_twii.py --from 2024-03` (PID 32332): 等 TWSE WAF ban lift 中

## [v0.9.7] - 2026-05-06 00:42

### Added — historical 上市總市值 backfill (用戶提供 source)

#### TWSE 市值週報 import
- 用戶下載 `https://www.twse.com.tw/zh/trading/statistics/week.html` 的 `week1-new.xls`
  (1059 週末筆，2005-09-02 ~ 2026-04-30)，import 成新 DB 表 `mkt_cap_weekly`

#### 加權指數 (TWII) 每日 backfill
- TWSE `MI_5MINS_HIST?date=YYYYMMDD` endpoint 每月 1 call 拿整月 OHLC
- 寫進 `daily_summary.twii_close` (新加的 column)
- 結果：50/77 月份 OK (2020-01 ~ 2024-02)、27 個月份被 WAF rate-limit 阻擋
  (2024-03 ~ 2026-05) — 等 ban lift 補抓

#### Daily mkt_cap 內插
- 新 script `recompute_mktcap_interp.py`
- 公式：`daily_mkt_cap = weekly_anchor.oku × (TWII_d / TWII_anchor)`
- 寫 960 interp rows，新欄位 `mkt_cap_source` 區分 `'official'` / `'interp'` / NULL
- 已有的 115 official rows 保護不被覆蓋
- Sanity check: 2022-04-01 = weekly anchor 自己, ratio=1.0, daily mkt_cap = 54.69 兆 ✓

### Schema migration (live DB)
- `daily_summary` 加 `twii_close REAL` + `mkt_cap_source TEXT`
- 新表 `mkt_cap_weekly (date PK, twse_mkt_cap_oku REAL, source TEXT)`
- 自動 tag 既有非 NULL `twse_mkt_cap_chao` 為 `'official'` (115 rows)

### UI
- `app/static/comprehensive.html`：加「加權指數」column 在「台指期 日盤收盤」之前
  - R1 group「指數收盤」 colspan=2 涵蓋 加權指數 + 台指期
  - colgroup 重排 16 cols (was 15)，sub-col 等寬
  - JS 多 `fmtTwii` (千分位 + 2 位小數) + `tdTwii` helpers
- `app/dashboard.py`：API payload 多 `twii_close` + `margin.mkt_cap_source`

### Coverage 進度

| 年 | official | interp | NULL | total |
|---|---|---|---|---|
| 2020 | 0 | 222 | 23 | 245 |
| 2021 | 0 | 222 | 22 | 244 |
| 2022 | 0 | 246 | 0 | 246 |
| 2023 | 1 | 238 | 0 | 239 |
| 2024 | 2 | 32 | 209 | 243 |
| 2025 | 43 | 0 | 200 | 243 |
| 2026 | 69 | 0 | 8 | 77 |

2024-03+ NULL 等 WAF ban 解開後 retry TWII backfill + 重跑 interp 即可補完。

## [v0.9.6] - 2026-05-06 00:14

### Fixed
- **fut_price 價格欄位被截掉小數** — 用戶看到 TE/TF close 都沒小數
  - 例 5/5 TE 真實 = 2658.65，DB 寫 2658；TF 真實 = 2505.8，DB 寫 2505
  - Root cause: `_to_int` 對 price columns 用 `int(float(s))` 強制截斷
  - Fix: 加 `_to_float` helper，scraper 對 open/high/low/close/settle/best_bid/
    best_ask 全改用 float；vol/oi/lots 維持 int
  - SQLite INTEGER affinity 對 REAL 值會保留浮點，schema 不需 ALTER
  - 重新 fetch 5/4 + 5/5：TX 41031/41035, TE 2658.2/2658.65, TF 2493/2505.8

### Re-running
- 跑中的 v0.9.4 backfill 用舊 _to_int 已 kill；重啟 (--from 2023-05-05) 用新 _to_float
- 預估 727 trading days × 3s = ~36 min 跑完

## [v0.9.5] - 2026-05-06 00:11

### Fixed
- **主表 (For X 開盤前看) 的「電子期 / 金融期」收盤欄一直空白**
  - Root cause: `dashboard.py` 只對 label=="台指期" 才 SELECT close FROM fut_price，
    其他 contract 永遠 None
  - Fix: 用 `contract_code` map (台指期→TX / 電子期→TE / 金融期→TF) 都 lookup
  - 驗證 2026-05-04: 台指 41031 / 電子 2658 / 金融 2493 ✅

### In Progress
- Historical TE/TF backfill (`scripts/backfill_fut_price.py --from 2023-05-05`)
  跑中 — fut_price 對 2023/05/05 起每天加 TE+TF rows (~750 trading days)
- 2020-2023/05 段 daily_summary 缺 margin / mkt_cap 欄位 (FinMind backfill 待寫)

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
