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

function tdNum(v, classes = "") {
  if (v == null || v === 0) return `<td class="${classes}">${v === 0 ? "0" : ""}</td>`;
  const cls = classes + (v < 0 ? " neg" : "");
  return `<td class="${cls.trim()}">${fmtInt(v)}</td>`;
}

function tdCost(v, classes = "") {
  if (v == null) return `<td class="${classes}"></td>`;
  const cls = classes + (v < 0 ? " neg" : "");
  return `<td class="${cls.trim()}">${fmtCost(v)}</td>`;
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

    html.push(`
      <tr>
        <td class="product ${rowCls}">${r.product}</td>
        ${tdNum(r.day_lots, `${rowCls} day-section`)}
        ${tdCost(r.day_cost, `${rowCls} day-section`)}
        ${closeCell}
        ${tdNum(r.oi_lots, rowCls)}
        ${tdCost(r.oi_cost, rowCls)}
        ${tdNum(r.night_lots, rowCls)}
        ${tdCost(r.night_cost, rowCls)}
        <td class="preopen-col ${r.pre_open_lots < 0 ? 'neg' : ''}">${fmtInt(r.pre_open_lots)}</td>
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
    const last = r.last_refresh;
    setStatus(
      `資料日期 ${r.date}`
      + (last ? `  ·  上次 refresh ${last.ts.replace("T", " ")} ${last.ok ? "✓" : "✗"}` : ""),
      "ok"
    );
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

$("#btnLoad").addEventListener("click", () => loadView($("#viewDate").value));
$("#btnRefresh").addEventListener("click", doRefresh);

loadView();
