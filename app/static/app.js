"use strict";

const $ = sel => document.querySelector(sel);
const status_ = $("#status");

function setStatus(text, kind = "") {
  status_.textContent = text;
  status_.className = kind;
}

const MD_DAY = ["日", "一", "二", "三", "四", "五", "六"];

function fmtMD(iso) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-").map(Number);
  const day = new Date(iso + "T00:00:00").getDay();
  return `${m}/${d}(${MD_DAY[day]})`;
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
  return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
        ${i === 0 ? closeCellHTML : `<td class="col-divider empty"></td>`}
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
    const url = viewDate ? `/api/dashboard?view_date=${viewDate}` : "/api/dashboard";
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
      setStatus(
        `資料日期 ${r.date} 的 raw 資料還沒進 DB → 點「Refresh 抓最新」即可抓 ${r.date}` + lastTxt,
        "err"
      );
    } else {
      setStatus(`資料日期 ${r.date}` + lastTxt, "ok");
    }
  } catch (e) {
    console.error(e);
    setStatus(`載入失敗: ${e.message}`, "err");
  }
}

async function doRefresh() {
  const btn = $("#btnRefresh"); btn.disabled = true;
  setStatus("Refreshing...");
  try {
    // Refresh fetches the data-date, which is the weekday before view_date.
    const viewDate = $("#viewDate").value;
    let dataDate = null;
    if (viewDate) {
      const d = new Date(viewDate + "T00:00:00");
      do { d.setDate(d.getDate() - 1); } while (d.getDay() === 0 || d.getDay() === 6);
      dataDate = d.toISOString().slice(0, 10);
    }
    const url = dataDate ? `/api/refresh?date=${dataDate}` : "/api/refresh";
    const r = await fetch(url, { method: "POST" }).then(r => r.json());
    if (r.ok) {
      setStatus(`Refresh OK (data ${r.target_date}, ${r.elapsed_sec}s)`, "ok");
    } else {
      setStatus(`Refresh 失敗: ${(r.errors || []).join("; ")}`, "err");
    }
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

// Honor ?view_date= in the URL on first load
const _params = new URLSearchParams(window.location.search);
const _initialView = _params.get("view_date");
if (_initialView) $("#viewDate").value = _initialView;
loadView(_initialView);
