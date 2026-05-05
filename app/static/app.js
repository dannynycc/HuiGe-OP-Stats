"use strict";

const $ = sel => document.querySelector(sel);
const status_ = $("#status");

function setStatus(text, kind = "") {
  status_.textContent = text;
  status_.className = kind;
}

function fmtNum(v) {
  if (v == null || v === "") return "";
  if (typeof v === "number") {
    return v.toLocaleString("en-US", { maximumFractionDigits: 4 });
  }
  return String(v);
}

function tdNumber(v) {
  if (v == null) return `<td></td>`;
  const n = Number(v);
  const cls = !isFinite(n) || n === 0 ? "" : (n > 0 ? "pos" : "neg");
  return `<td class="${cls}">${fmtNum(v)}</td>`;
}

function tdText(v) {
  return `<td data-text>${v == null ? "" : v}</td>`;
}

// -------- ① KPI grid --------
function renderKPI(daily, credit) {
  const grid = $("#kpiGrid");
  if (!daily) { grid.innerHTML = "<div class='kpi'>(尚無資料)</div>"; return; }
  const items = [
    ["台指期收盤", daily.tx_close],
    ["法人 CALL OI 淨", daily.op_call_net],
    ["法人 PUT OI 淨", daily.op_put_net],
    ["CP 合計多空", daily.op_cp_net],
    ["股票期貨法人淨", daily.stock_fut_legal_net],
    ["上市融資餘額(億)", daily.twse_margin_amt_oku],
    ["上櫃融資餘額(億)", daily.tpex_margin_amt_oku],
    ["上市總市值(兆)", daily.twse_mkt_cap_chao],
    ["上櫃總市值(兆)", daily.tpex_mkt_cap_chao],
    ["上市融資佔比", daily.twse_margin_pct],
    ["上櫃融資佔比", daily.tpex_margin_pct],
  ];
  grid.innerHTML = items.map(([k, v]) => `
    <div class="kpi"><div class="label">${k}</div>
      <div class="value">${v == null ? "—" : fmtNum(typeof v === "number" && Math.abs(v) < 1 ? v.toFixed(4) : v)}</div></div>
  `).join("");
}

// -------- ② Time-series chart --------
async function renderChart() {
  const r = await fetch("/api/timeseries").then(r => r.json());
  const rows = r.rows || [];
  if (!rows.length) { Plotly.purge("chart"); return; }
  const x = rows.map(r => r.date);
  const traces = [
    { x, y: rows.map(r => r.tx_close), name: "台指期收盤", yaxis: "y2",
      mode: "lines", line: { color: "#e2b341", width: 2 } },
    { x, y: rows.map(r => r.op_call_net), name: "法人 CALL OI",
      mode: "lines", line: { color: "#4ade80" } },
    { x, y: rows.map(r => r.op_put_net), name: "法人 PUT OI",
      mode: "lines", line: { color: "#f87171" } },
    { x, y: rows.map(r => r.op_cp_net), name: "CP 合計多空",
      mode: "lines", line: { color: "#5fb3ff", width: 1.5 } },
    { x, y: rows.map(r => r.stock_fut_legal_net), name: "股期法人淨",
      mode: "lines", line: { color: "#a855f7" } },
    { x, y: rows.map(r => r.fut_pre_open_net), name: "開盤前多空",
      mode: "lines", line: { color: "#ec4899", dash: "dot" } },
  ];
  const layout = {
    paper_bgcolor: "#1a1d27", plot_bgcolor: "#1a1d27",
    font: { color: "#e6e9ef", size: 11 },
    margin: { l: 60, r: 60, t: 30, b: 50 },
    xaxis: { gridcolor: "#2c3142" },
    yaxis: { title: "口數淨額", gridcolor: "#2c3142", zeroline: true, zerolinecolor: "#414659" },
    yaxis2: { title: "台指期收盤", overlaying: "y", side: "right", gridcolor: "transparent" },
    legend: { bgcolor: "rgba(0,0,0,0)", orientation: "h", y: -0.18 },
    hovermode: "x unified",
  };
  Plotly.newPlot("chart", traces, layout, { displayModeBar: false, responsive: true });
}

// -------- ③ ④ Legal tables --------
function renderOPTable(target, rows, hasOI) {
  if (!rows || !rows.length) {
    document.querySelector(target).innerHTML = "<div style='color:var(--muted)'>(無資料)</div>";
    return;
  }
  // group by product (only show 臺指選擇權 prominently; rest collapsed)
  const wantedProducts = new Set(["臺指選擇權"]);
  const filtered = rows.filter(r => wantedProducts.has(r.product));
  const head = `
    <thead>
      <tr>
        <th data-text>商品</th><th data-text>權別</th><th data-text>身份</th>
        <th>買口</th><th>買金</th><th>賣口</th><th>賣金</th>
        <th>淨口</th><th>淨金</th>
        ${hasOI ? "<th>OI買口</th><th>OI買金</th><th>OI賣口</th><th>OI賣金</th><th>OI淨口</th><th>OI淨金</th>" : ""}
      </tr>
    </thead>`;
  const body = filtered.map((r, i) => {
    const divider = (i > 0 && (filtered[i - 1].callput !== r.callput || filtered[i - 1].product !== r.product)) ? " row-group-divider" : "";
    return `<tr class="${divider}">
      ${tdText(r.product)}${tdText(r.callput || "")}${tdText(r.role)}
      ${tdNumber(r.buy_lots)}${tdNumber(r.buy_amt)}
      ${tdNumber(r.sell_lots)}${tdNumber(r.sell_amt)}
      ${tdNumber(r.net_lots)}${tdNumber(r.net_amt)}
      ${hasOI ? tdNumber(r.oi_buy_lots) + tdNumber(r.oi_buy_amt)
                + tdNumber(r.oi_sell_lots) + tdNumber(r.oi_sell_amt)
                + tdNumber(r.oi_net_lots) + tdNumber(r.oi_net_amt) : ""}
    </tr>`;
  }).join("");
  document.querySelector(target).innerHTML = `<table>${head}<tbody>${body}</tbody></table>`;
}

function renderFUTTable(target, rows, hasOI) {
  if (!rows || !rows.length) {
    document.querySelector(target).innerHTML = "<div style='color:var(--muted)'>(無資料)</div>";
    return;
  }
  const wantedProducts = new Set(["臺股期貨", "電子期貨", "金融期貨", "小型臺指期貨", "微型臺指期貨", "股票期貨"]);
  const filtered = rows.filter(r => wantedProducts.has(r.product));
  const head = `
    <thead>
      <tr>
        <th data-text>商品</th><th data-text>身份</th>
        <th>多口</th><th>多金</th><th>空口</th><th>空金</th>
        <th>淨口</th><th>淨金</th>
        ${hasOI ? "<th>OI多口</th><th>OI多金</th><th>OI空口</th><th>OI空金</th><th>OI淨口</th><th>OI淨金</th>" : ""}
      </tr>
    </thead>`;
  const body = filtered.map((r, i) => {
    const divider = (i > 0 && filtered[i - 1].product !== r.product) ? " row-group-divider" : "";
    return `<tr class="${divider}">
      ${tdText(r.product)}${tdText(r.role)}
      ${tdNumber(r.buy_lots)}${tdNumber(r.buy_amt)}
      ${tdNumber(r.sell_lots)}${tdNumber(r.sell_amt)}
      ${tdNumber(r.net_lots)}${tdNumber(r.net_amt)}
      ${hasOI ? tdNumber(r.oi_buy_lots) + tdNumber(r.oi_buy_amt)
                + tdNumber(r.oi_sell_lots) + tdNumber(r.oi_sell_amt)
                + tdNumber(r.oi_net_lots) + tdNumber(r.oi_net_amt) : ""}
    </tr>`;
  }).join("");
  document.querySelector(target).innerHTML = `<table>${head}<tbody>${body}</tbody></table>`;
}

// -------- ⑤ Fut price --------
function renderFutPrice(rows) {
  if (!rows || !rows.length) {
    $("#futPriceBody").innerHTML = "<div style='color:var(--muted)'>(無資料)</div>";
    return;
  }
  const head = `<thead><tr>
    <th data-text>契約</th><th data-text>到期月</th>
    <th>開盤</th><th>最高</th><th>最低</th><th>收盤</th>
    <th data-text>漲跌</th><th data-text>%</th>
    <th>夜盤量</th><th>日盤量</th><th>合計量</th><th>結算</th><th>未沖銷</th>
  </tr></thead>`;
  const body = rows.map(r => `<tr>
    ${tdText(r.contract)}${tdText(r.expiry)}
    ${tdNumber(r.open_)}${tdNumber(r.high)}${tdNumber(r.low)}${tdNumber(r.close)}
    ${tdText(r.change_str || "")}${tdText(r.change_pct_str || "")}
    ${tdNumber(r.ah_vol)}${tdNumber(r.day_vol)}${tdNumber(r.total_vol)}
    ${tdNumber(r.settle)}${tdNumber(r.oi)}
  </tr>`).join("");
  $("#futPriceBody").innerHTML = `<table>${head}<tbody>${body}</tbody></table>`;
}

// -------- ⑥ Credit --------
function renderCredit(twse, summary) {
  const lines = [];
  if (twse && twse.length) {
    const head = `<thead><tr>
      <th data-text>項目</th><th>買進</th><th>賣出</th><th>償還</th><th>前日餘額</th><th>今日餘額</th>
    </tr></thead>`;
    const body = twse.map(r => `<tr>
      ${tdText(r.item)}${tdNumber(r.buy)}${tdNumber(r.sell)}${tdNumber(r.repay)}
      ${tdNumber(r.prev_balance)}${tdNumber(r.today_balance)}
    </tr>`).join("");
    lines.push(`<h3 style="margin:8px 0 4px;font-size:13px">上市</h3><table>${head}<tbody>${body}</tbody></table>`);
  }
  if (summary) {
    lines.push(`<h3 style="margin:14px 0 4px;font-size:13px">市場彙總</h3>
      <div class="kpi-grid">
        <div class="kpi"><div class="label">上市融資餘額 (仟元)</div><div class="value">${fmtNum(summary.twse_margin_balance)}</div></div>
        <div class="kpi"><div class="label">上市成交金額 (元)</div><div class="value">${fmtNum(summary.twse_turnover)}</div></div>
        <div class="kpi"><div class="label">上市總市值 (億元)</div><div class="value">${fmtNum(summary.twse_mkt_cap)}</div></div>
        <div class="kpi"><div class="label">上櫃融資餘額 (仟元)</div><div class="value">${fmtNum(summary.tpex_margin_balance)}</div></div>
        <div class="kpi"><div class="label">上櫃成交金額 (元)</div><div class="value">${fmtNum(summary.tpex_turnover)}</div></div>
        <div class="kpi"><div class="label">上櫃總市值 (佰萬元)</div><div class="value">${fmtNum(summary.tpex_mkt_cap)}</div></div>
      </div>`);
  }
  $("#creditBody").innerHTML = lines.length ? lines.join("") : "<div style='color:var(--muted)'>(無資料)</div>";
}

// -------- main flow --------
async function loadDate(date) {
  setStatus("載入中…");
  try {
    const url = date ? `/api/today?date=${date}` : "/api/today";
    const r = await fetch(url).then(r => r.json());
    if (r.error) { setStatus(r.error, "err"); return; }
    $("#dateInput").value = r.date;
    $("#refreshDate").value = r.date;
    renderKPI(r.daily_summary, r.credit_summary);
    renderOPTable("#opDayBody", r.op_day, true);
    renderOPTable("#opNightBody", r.op_night, false);
    renderFUTTable("#futDayBody", r.fut_day, true);
    renderFUTTable("#futNightBody", r.fut_night, false);
    renderFutPrice(r.fut_price);
    renderCredit(r.credit_twse, r.credit_summary);
    const last = r.last_refresh;
    setStatus(`資料日期 ${r.date}`
              + (last ? `  ·  上次 refresh ${last.ts} ${last.ok ? "✓" : "✗"}` : "")
              + (last && !last.ok ? `  ·  errors: ${last.errors_json}` : ""),
              "ok");
  } catch (e) {
    console.error(e);
    setStatus(`載入失敗: ${e.message}`, "err");
  }
  await renderChart();
}

async function doRefresh() {
  const btn = $("#btnRefresh"); btn.disabled = true;
  setStatus("Refreshing...");
  try {
    const targetDate = $("#refreshDate").value;
    const url = targetDate ? `/api/refresh?date=${targetDate}` : "/api/refresh";
    const r = await fetch(url, { method: "POST" }).then(r => r.json());
    if (r.ok) {
      setStatus(`Refresh OK (${r.target_date}, ${r.elapsed_sec}s)`, "ok");
    } else {
      setStatus(`Refresh 失敗: ${(r.errors || []).join("; ")}`, "err");
    }
    await loadDate(r.target_date);
  } catch (e) {
    setStatus(`Refresh 失敗: ${e.message}`, "err");
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("btnLoad").addEventListener("click", () => loadDate($("#dateInput").value));
document.getElementById("btnRefresh").addEventListener("click", doRefresh);

// initial load: most recent date in DB
loadDate();
