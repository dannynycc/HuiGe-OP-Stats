"use strict";

const $ = sel => document.querySelector(sel);
const status_ = $("#status");

function setStatus(text, kind = "") {
  status_.textContent = text;
  status_.className = kind;
}

// ── 靜態 (GitHub Pages) 模式 ──────────────────────────────────────────
// docs/ 版本的 index.html 會注入 `window.__STATIC__ = true`。
// 本機 FastAPI 模式下 __STATIC__ undefined → 走原本的 /api/* 路徑。
const STATIC = window.__STATIC__ === true;
const DATA_BASE = "./data";
let _datesCache = null;

// 取得「日盤交易日」清單 (ascending)，用來把 view_date 換算成 data_date。
async function getDates() {
  if (_datesCache) return _datesCache;
  const r = await fetch(`${DATA_BASE}/dates.json?_=${Date.now()}`).then(r => r.json());
  _datesCache = r.dates || [];
  return _datesCache;
}

// 複製 server 端 `MAX(date) < view_date AND daynight='day'` 的邏輯：
// view_date X 對應的 data_date = 嚴格小於 X 的最近一個交易日。
function resolveDataDate(viewDate, dates) {
  let best = null;
  for (const d of dates) {
    if (d < viewDate) best = d; else break;   // dates 已 ascending
  }
  return best;
}

const MD_DAY = ["日", "一", "二", "三", "四", "五", "六"];

function fmtMD(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  const day = new Date(iso + "T00:00:00").getDay();
  return `${y}/${m}/${d}(${MD_DAY[day]})`;   // 帶年份, 避免歷史 view 不知是哪一年
}

// Number formats per Excel sheet109 numFmts:
//   numFmt 177: `#,##0_ ;[Red]\-#,##0\ `   →  negatives = [Red]-N
//   numFmt 178: `#,##0_);[Red]\(#,##0\)`   →  negatives = [Red](N)
// Both add comma thousands; round to int.
function fmtMinus(v) {
  if (v == null || isNaN(v)) return "";
  const n = Math.round(v);
  return n.toLocaleString("en-US");      // -1,234  /  1,234
}

// Excel numFmt `#,##0_);[Red]\(#,##0\)` → the `_)` after positives means
// "leave a right-side gap as wide as `)`" so digits line up with the negative
// form (which has trailing `)`). We replicate that with a hidden `)` span.
const _PAREN_PAD = '<span style="visibility:hidden">)</span>';
function fmtParen(v) {
  if (v == null || isNaN(v)) return "";
  const n = Math.round(v);
  if (n < 0) return "(" + Math.abs(n).toLocaleString("en-US") + ")";
  return n.toLocaleString("en-US") + _PAREN_PAD;
}

// Cost cells in Excel use numFmt 177 too (no decimals shown — rounded).
const fmtCost = fmtMinus;

// Excel CF rule per sheet109.xml:
//   一般 row (台指期/電子期/金融期/CALL/股票期貨): 口數 < 0 → 淡綠, > 0 → 淡紅
//   賣權 PUT row (R244): rules **reversed** — 口數 < 0 → 淡紅, > 0 → 淡綠
// (PUT 多空意義相反)
function cfBg(lots, isPut) {
  if (lots == null || lots === 0) return "";
  const negColor = "#E1EEDB", posColor = "#FBC9C6";
  if (isPut) {
    return lots < 0 ? `background:${posColor}` : `background:${negColor}`;
  }
  return lots < 0 ? `background:${negColor}` : `background:${posColor}`;
}

// Two formatters per Excel numFmt:
//   tdMinus → "-1,234" (口數/成本/收盤價/夜盤)
//   tdParen → "(1,234)" (淨部位/開盤前部位/開盤前多空)
// Both colour negatives red (Excel [Red] token).
function tdMinus(v, classes = "", inlineStyle = "") {
  if (v == null) return `<td class="${classes}" style="${inlineStyle}"></td>`;
  if (v === 0) return `<td class="${classes}" style="${inlineStyle}">0</td>`;
  const cls = classes + (v < 0 ? " neg" : "");
  return `<td class="${cls.trim()}" style="${inlineStyle}">${fmtMinus(v)}</td>`;
}

function tdParen(v, classes = "", inlineStyle = "") {
  if (v == null) return `<td class="${classes}" style="${inlineStyle}"></td>`;
  const cls = classes + (v < 0 ? " neg" : "");
  return `<td class="${cls.trim()}" style="${inlineStyle}">${fmtParen(v)}</td>`;
}

const tdNum = tdMinus;
const tdCost = tdMinus;

function fmtOku(v) {
  if (v == null || isNaN(v)) return "—";
  // Display rounded integer (DB still keeps raw decimals — display-only round).
  return Math.round(v).toLocaleString("en-US");
}

function render(payload) {
  const { date, view_date, rows, margin } = payload;
  // 融資餘額 panel — title 同主表用「M/D(週)」格式
  if (margin) {
    document.getElementById("marginTitle").textContent = `${fmtMD(date)} 信用交易統計`;
    document.getElementById("twseMarginAmt").textContent = fmtOku(margin.twse_margin_amt_oku);
    document.getElementById("tpexMarginAmt").textContent = fmtOku(margin.tpex_margin_amt_oku);
  }

  // Update headers
  $("#forCell").innerHTML = `For<br>${fmtMD(view_date)}<br>開盤前看`;
  $("#dayHeader").textContent = `${fmtMD(date)} 日盤`;
  $("#nightHeader").textContent = `${fmtMD(date)} 夜盤`;

  const tbody = $("#tbody");
  if (!rows || !rows.length) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:var(--muted);padding:30px">(${date} 無資料)</td></tr>`;
    return;
  }

  // Build rows; CALL/PUT pre_open_cp gets shared via rowspan
  const html = [];
  const callIdx = rows.findIndex(r => r.product === "買權CALL");
  const putIdx = rows.findIndex(r => r.product === "賣權PUT");

  rows.forEach((r, i) => {
    const isPut = r.product === "賣權PUT";

    // CF colors: applied to each (lots, cost) pair based on the lots sign.
    // PUT row uses inverted rules (per Excel sheet109.xml dxfId mapping).
    const cfDay = cfBg(r.day_lots, isPut);
    const cfOI = cfBg(r.oi_lots, isPut);
    const cfNight = cfBg(r.night_lots, isPut);

    // Per Excel numFmt: 淨部位 / 開盤前部位 / 開盤前多空 → paren format (E,I,J cols)
    //                   其他 → minus format (B,C,D,F,G,H cols)
    let preOpenCpCell;
    if (i === callIdx) {
      preOpenCpCell = r.pre_open_cp != null
        ? `<td class="preopen-col ${r.pre_open_cp < 0 ? 'neg' : ''}" rowspan="2">${fmtParen(r.pre_open_cp)}</td>`
        : `<td class="preopen-col" rowspan="2"></td>`;
    } else if (i === putIdx) {
      preOpenCpCell = "";
    } else {
      preOpenCpCell = `<td class="preopen-col"></td>`;
    }

    const closeCellHTML = r.close_price != null
      ? `<td class="col-divider">${fmtMinus(r.close_price)}</td>`
      : `<td class="col-divider empty"></td>`;

    const nightLotsCell = r.night_lots == null
      ? `<td class="empty"></td>` : tdMinus(r.night_lots, "", cfNight);
    const nightCostCell = r.night_cost == null
      ? `<td class="col-divider empty"></td>` : tdMinus(r.night_cost, "col-divider", cfNight);
    const preOpenLotsCell = r.pre_open_lots == null
      ? `<td class="preopen-col empty"></td>`
      : tdParen(r.pre_open_lots, "preopen-col", "");

    html.push(`
      <tr>
        <td class="product col-divider">${r.product}</td>
        ${tdMinus(r.day_lots, "", cfDay)}
        ${tdMinus(r.day_cost, "", cfDay)}
        ${closeCellHTML}
        ${tdParen(r.oi_lots, "", cfOI)}
        ${tdMinus(r.oi_cost, "col-divider", cfOI)}
        ${nightLotsCell}
        ${nightCostCell}
        ${preOpenLotsCell}
        ${preOpenCpCell}
      </tr>
    `);
  });
  tbody.innerHTML = html.join("");
}

async function loadView(viewDate) {
  setStatus("載入中…");
  try {
    let url;
    if (STATIC) {
      // 靜態模式：讀預先產好的 JSON。view_date 先換算成 data_date。
      if (viewDate) {
        const dd = resolveDataDate(viewDate, await getDates());
        if (!dd) throw new Error(`${viewDate} 之前查無資料`);
        url = `${DATA_BASE}/dashboard/${dd}.json?_=${Date.now()}`;
      } else {
        url = `${DATA_BASE}/dashboard/latest.json?_=${Date.now()}`;
      }
    } else {
      url = viewDate ? `/api/dashboard?view_date=${viewDate}` : "/api/dashboard";
    }
    const r = await fetch(url).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
    $("#viewDate").value = r.view_date;
    render(r);

    // detect "all empty" — raw fut_legal/op_legal not in DB for this data date
    const hasAnyData = (r.rows || []).some(row =>
      row.day_lots !== 0 || row.oi_lots !== 0 || row.night_lots !== 0
    );
    const last = r.last_refresh;
    const lastTxt = last ? `  ·  上次 refresh ${last.ts.replace("T", " ")} ${last.ok ? "✓" : "✗"}` : "";
    if (!hasAnyData) {
      const hint = STATIC
        ? `資料日期 ${r.date} 尚無 raw 資料（將於下次雲端定時更新時補上）`
        : `資料日期 ${r.date} 的 raw 資料還沒進 DB → 點「Refresh 抓最新」即可抓 ${r.date}`;
      setStatus(hint + lastTxt, "err");
    } else {
      setStatus(`資料日期 ${r.date}` + lastTxt, "ok");
    }
  } catch (e) {
    console.error(e);
    setStatus(`載入失敗: ${e.message}`, "err");
  }
}

// 白話 refresh status — 給用戶看, 不用任何 jargon / 數字
function formatRefreshStatus(r) {
  // 把 ISO date 改成 「YYYY/M/D」 跟主表一致
  const fmtDate = iso => {
    if (!iso) return "";
    const [y,m,d] = iso.split("-").map(Number);
    return `${y}/${m}/${d}`;
  };
  if (r.mode === "catch_up") {
    const results = r.results || [];
    if (results.length === 1) {
      return `${fmtDate(results[0].target_date)} ✓`;
    }
    return `${results.length} 天 ✓`;
  }
  if (r.mode === "no_op") return r.message || "資料已是最新";
  if (r.ok) return `${fmtDate(r.target_date)} 已抓最新 ✓`;
  return `失敗: ${(r.errors || []).join("; ") || "未知"}`;
}
function getRefreshSeverity(r) {
  if (r.mode === "catch_up") {
    const inc = (r.results || []).filter(x => x.status && x.status.startsWith("INCOMPLETE")).length;
    return inc ? "err" : "ok";
  }
  if (r.ok || r.mode === "no_op") return "ok";
  return "err";
}

async function doRefresh() {
  const btn = $("#btnRefresh"); btn.disabled = true;
  // 靜態模式：沒有後端可抓，只重新載入目前畫面（資料由雲端 cron 定時更新）。
  if (STATIC) {
    _datesCache = null;   // 清快取，確保抓到最新日期清單
    try {
      await loadView($("#viewDate").value);
      setStatus("已重新整理（資料由雲端定時更新）", "ok");
    } finally {
      btn.disabled = false;
    }
    return;
  }
  // Show spinner + "抓取中" text
  const stat = $("#status");
  stat.innerHTML = '<span class="spinner"></span>抓取資料中…';
  stat.className = "";
  try {
    const viewDate = $("#viewDate").value;
    const r = await fetch("/api/refresh", { method: "POST" }).then(r => r.json());
    // catch-up mode response: { mode: 'catch_up', results: [...], outlier_audit: [...] }
    // single-day response: { ok, target_date, elapsed_sec, errors }
    setStatus(formatRefreshStatus(r), getRefreshSeverity(r));
    await loadView(viewDate);
  } catch (e) {
    setStatus(`Refresh 失敗: ${e.message}`, "err");
  } finally {
    btn.disabled = false;
  }
}

// Date picker: load immediately on change (debounced lightly).
let _loadTimer = null;
$("#viewDate").addEventListener("change", () => {
  const v = $("#viewDate").value;
  const u = new URL(window.location);
  if (v) u.searchParams.set("view_date", v);
  else u.searchParams.delete("view_date");
  history.replaceState(null, "", u);
  clearTimeout(_loadTimer);
  _loadTimer = setTimeout(() => loadView(v), 50);
});
$("#btnRefresh").addEventListener("click", doRefresh);

// 靜態模式：按鈕語意從「抓最新」改成「重新整理」（抓取由雲端 cron 負責）。
if (STATIC) {
  const _b = $("#btnRefresh");
  if (_b) _b.textContent = "🔄 重新整理";
}

// Honor ?view_date= in the URL on first load
const _params = new URLSearchParams(window.location.search);
const _initialView = _params.get("view_date");
if (_initialView) $("#viewDate").value = _initialView;
loadView(_initialView);
