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

function fmtInt(v) {
  if (v == null || isNaN(v)) return "";
  const n = Math.round(v);
  return n.toLocaleString("en-US");
}

function fmtCost(v) {
  if (v == null || isNaN(v)) return "";
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

// Excel CF rule: 口數 < 0 → 淡綠 (#E1EEDB), 口數 > 0 → 淡紅 (#FBC9C6).
// The lots cell drives the bg color of BOTH (lots, cost) cells in the pair.
function cfBg(lots) {
  if (lots == null || lots === 0) return "";
  return lots < 0 ? "background:#E1EEDB" : "background:#FBC9C6";
}

function tdNum(v, classes = "", inlineStyle = "") {
  if (v == null) return `<td class="${classes}" style="${inlineStyle}"></td>`;
  if (v === 0) return `<td class="${classes}" style="${inlineStyle}">0</td>`;
  const cls = classes + (v < 0 ? " neg" : "");
  return `<td class="${cls.trim()}" style="${inlineStyle}">${fmtInt(v)}</td>`;
}

function tdCost(v, classes = "", inlineStyle = "") {
  if (v == null) return `<td class="${classes}" style="${inlineStyle}"></td>`;
  const cls = classes + (v < 0 ? " neg" : "");
  return `<td class="${cls.trim()}" style="${inlineStyle}">${fmtCost(v)}</td>`;
}

function render(payload) {
  const { date, view_date, rows } = payload;

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
    const isOption = i === callIdx || i === putIdx;
    const rowCls = isPut ? "put-row" : "";

    // close_price column shown only for 台指期
    const closeCell = r.close_price != null
      ? `<td class="${rowCls}">${fmtInt(r.close_price)}</td>`
      : `<td class="${rowCls} empty"></td>`;

    let preOpenCpCell;
    if (i === callIdx) {
      preOpenCpCell = r.pre_open_cp != null
        ? `<td class="preopen-col ${r.pre_open_cp < 0 ? 'neg' : ''}" rowspan="2">${fmtInt(r.pre_open_cp)}</td>`
        : `<td class="preopen-col" rowspan="2"></td>`;
    } else if (i === putIdx) {
      preOpenCpCell = "";  // covered by CALL's rowspan
    } else {
      preOpenCpCell = `<td class="preopen-col"></td>`;
    }

    // Per Excel CF: 每對 (口數, 成本) 用「口數」正負決定 bg color.
    // PUT row 整列另有 row-level pink bg; CF 顏色不上 PUT row (Excel 也不上).
    const cfDay = isPut ? "" : cfBg(r.day_lots);
    const cfOI = isPut ? "" : cfBg(r.oi_lots);
    const cfNight = isPut ? "" : cfBg(r.night_lots);

    const closeCellHTML = r.close_price != null
      ? `<td class="col-divider">${fmtInt(r.close_price)}</td>`
      : `<td class="col-divider empty"></td>`;

    const nightLotsCell = r.night_lots == null
      ? `<td class="empty"></td>` : tdNum(r.night_lots, "", cfNight);
    const nightCostCell = r.night_cost == null
      ? `<td class="col-divider empty"></td>` : tdCost(r.night_cost, "col-divider", cfNight);
    const preOpenLotsCell = r.pre_open_lots == null
      ? `<td class="preopen-col empty"></td>`
      : `<td class="preopen-col ${r.pre_open_lots < 0 ? 'neg' : ''}">${fmtInt(r.pre_open_lots)}</td>`;

    html.push(`
      <tr class="${rowCls}">
        <td class="product">${r.product}</td>
        ${tdNum(r.day_lots, "", cfDay)}
        ${tdCost(r.day_cost, "", cfDay)}
        ${i === 0 ? closeCellHTML : `<td class="col-divider empty"></td>`}
        ${tdNum(r.oi_lots, "", cfOI)}
        ${tdCost(r.oi_cost, "col-divider", cfOI)}
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
