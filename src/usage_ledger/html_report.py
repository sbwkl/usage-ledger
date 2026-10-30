from __future__ import annotations

import json
from datetime import datetime

from .models import FIELDS

PLACEHOLDER = "__USAGE_LEDGER_PAYLOAD__"


def build_payload(rows, dims, since, until, notices, generated_at=None) -> dict:
    payload_rows = []
    for row in rows:
        item = dict(zip(dims, row["dims"]))
        for field in FIELDS:
            item[field] = row[field]
        item["total"] = row["total"]
        item["turns"] = row["turns"]
        item["cost_equiv_usd"] = row["cost_equiv_usd"]
        item["cost_source"] = row["cost_source"]
        payload_rows.append(item)
    return {
        "generated_at": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "range": {"since": since, "until": until},
        "rows": payload_rows,
        "notices": list(notices),
    }


def render_html(payload: dict) -> str:
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # "<" 一律转义，避免数据中的 </script> 提前闭合脚本块
    blob = blob.replace("<", "\\u003c")
    return TEMPLATE.replace(PLACEHOLDER, blob)


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>Usage Ledger · 用量统计</title>
<style>
:root{
  color-scheme: light;
  --bg:#f4f5f7;
  --bg-grad: radial-gradient(1100px 480px at 8% -10%, #e8edff 0%, transparent 60%), radial-gradient(900px 420px at 100% 0%, #e6f7f1 0%, transparent 55%);
  --surface:#ffffff;
  --surface-2:#f7f8fa;
  --border:#e3e6ec;
  --text:#16181d;
  --muted:#69707d;
  --accent:#3b6cf6;
  --accent-soft:#eef3ff;
  --shadow:0 1px 2px rgba(16,24,40,.04), 0 8px 24px rgba(16,24,40,.06);
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#0d0f13;
  --bg-grad: radial-gradient(1100px 480px at 8% -10%, #15203b 0%, transparent 60%), radial-gradient(900px 420px at 100% 0%, #10231d 0%, transparent 55%);
  --surface:#15181e;
  --surface-2:#1b1f27;
  --border:#282d37;
  --text:#e9ecf1;
  --muted:#9aa3b2;
  --accent:#7aa2ff;
  --accent-soft:#1b2740;
  --shadow:0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--bg);
  background-image:var(--bg-grad);
  background-attachment:fixed;
  color:var(--text);
  font-family:-apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-size:14px;
  line-height:1.5;
  -webkit-font-smoothing:antialiased;
}
.topbar{max-width:1320px;margin:0 auto;padding:22px 24px 10px;display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}
.logo{width:38px;height:38px;border-radius:11px;background:linear-gradient(135deg,var(--accent),#22c1a4);color:#fff;font-weight:700;display:grid;place-items:center;font-size:13px;letter-spacing:.5px;box-shadow:var(--shadow)}
h1{font-size:18px;margin:0;letter-spacing:.2px}
.sub{margin:2px 0 0;color:var(--muted);font-size:12.5px}
.top-actions{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
main{max-width:1320px;margin:0 auto;padding:8px 24px 40px;display:flex;flex-direction:column;gap:16px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;box-shadow:var(--shadow);padding:16px}
.filters{display:flex;flex-direction:column;gap:12px}
.filter-line{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center}
label.field{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12.5px}
input[type="date"],input[type="search"],select{
  background:var(--surface-2);color:var(--text);border:1px solid var(--border);border-radius:9px;
  padding:7px 9px;font:inherit;font-size:13px;outline:none;max-width:230px;
}
input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.presets{display:inline-flex;gap:6px;flex-wrap:wrap}
.btn{border:1px solid var(--border);background:var(--surface-2);color:var(--text);border-radius:9px;padding:7px 12px;font:inherit;font-size:13px;cursor:pointer;transition:border-color .15s,color .15s,background .15s}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.btn.ghost{background:transparent}
.btn.small{padding:5px 9px;font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:7px;flex:1 1 340px}
.chip{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:5px 10px;font-size:12.5px;border:1px solid var(--border);background:var(--surface-2);color:var(--muted);cursor:pointer;font-family:inherit;transition:border-color .15s,background .15s,color .15s}
.chip:hover{border-color:var(--accent)}
.chip.active{background:var(--accent-soft);border-color:var(--accent);color:var(--text)}
.chip small{opacity:.62;font-variant-numeric:tabular-nums}
.chip-tip{font-size:11.5px;color:var(--muted);align-self:center;white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;flex:none;display:inline-block}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px 14px;box-shadow:var(--shadow);min-width:0}
.kpi.primary{grid-column:span 2;background:linear-gradient(135deg,var(--accent-soft),var(--surface) 72%);border-color:var(--accent)}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:clamp(20px,2.1vw,27px);font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.3px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-sub{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,.85fr);gap:16px}
.chart-card{grid-column:1/-1}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;flex-wrap:wrap}
.card-head h2{font-size:14px;margin:0;letter-spacing:.2px}
.muted{color:var(--muted);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 4px;padding-left:2px}
.legend-item{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.legend-item b{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
.legend-dot{width:9px;height:9px;border-radius:3px;display:inline-block}
.chart-wrap{position:relative;width:100%}
#chart{width:100%;min-height:300px}
#chart svg{display:block;width:100%;height:auto}
#chart text{fill:var(--muted);font-size:11px;font-family:inherit}
#chart .grid-line{stroke:var(--border);stroke-width:1;shape-rendering:crispEdges}
#chart .seg{stroke:var(--surface);stroke-width:.6}
#chart .hit{fill:transparent;cursor:crosshair}
#chart .hover-line{stroke:var(--accent);stroke-width:1;stroke-dasharray:3 3;opacity:.45;pointer-events:none}
.empty{display:grid;place-items:center;min-height:200px;color:var(--muted);font-size:13px}
.tooltip{position:absolute;z-index:5;top:8px;left:0;transform:translateX(-50%);min-width:190px;max-width:280px;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.18);padding:9px 11px;pointer-events:none;display:none}
.tt-head{font-size:12px;font-weight:650;margin-bottom:2px}
.tt-meta{font-size:11px;color:var(--muted);margin-bottom:6px}
.tt-row{display:flex;justify-content:space-between;gap:14px;font-size:12px;padding:1.5px 0}
.tt-name{display:inline-flex;align-items:center;gap:6px;color:var(--muted)}
.tt-name i{width:7px;height:7px;border-radius:2px;display:inline-block}
.tt-val{font-variant-numeric:tabular-nums;color:var(--text)}
.tt-total{border-top:1px solid var(--border);margin-top:5px;padding-top:5px;font-weight:600}
.bars{display:flex;flex-direction:column;gap:11px;min-height:120px}
.bar-row{display:block;width:100%;border:0;background:transparent;padding:0;margin:0;text-align:left;cursor:pointer;border-radius:8px;font:inherit;color:inherit}
.bar-row:hover .bar-name{color:var(--accent)}
.bar-row:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.bar-row.selected .bar-name{color:var(--accent);font-weight:700}
.bar-row.selected .bar-track{box-shadow:0 0 0 1px var(--accent)}
.bar-top{display:flex;justify-content:space-between;gap:10px;font-size:12px;margin-bottom:4px}
.bar-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70%;font-family:var(--mono);font-size:11.5px}
.bar-value{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.bar-track{height:7px;border-radius:999px;background:var(--surface-2);overflow:hidden}
.bar-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#22c1a4);min-width:2px}
.table-card{padding-bottom:10px}
.table-wrap{overflow:auto;max-height:660px;border:1px solid var(--border);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:12.5px;min-width:900px}
thead th{position:sticky;top:0;background:var(--surface-2);z-index:1;border-bottom:1px solid var(--border);padding:0;text-align:left;white-space:nowrap}
th.num{text-align:right}
.th-btn{border:0;background:transparent;color:var(--muted);font:inherit;font-weight:600;padding:9px 10px;cursor:pointer;width:100%;display:flex;gap:4px;align-items:center;text-align:inherit;justify-content:flex-start}
th.num .th-btn{justify-content:flex-end}
.th-btn:hover{color:var(--text)}
.arrow{font-size:9px;opacity:.8}
tbody td{padding:7px 10px;border-bottom:1px solid var(--border);white-space:nowrap;max-width:280px;overflow:hidden;text-overflow:ellipsis}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:var(--surface-2)}
td.num{text-align:right;font-variant-numeric:tabular-nums;font-family:var(--mono);font-size:12px}
td.zero{color:var(--muted);opacity:.55}
.pager{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding-top:10px}
.pager button{border:1px solid var(--border);background:var(--surface-2);color:var(--text);border-radius:8px;padding:5px 10px;font:inherit;font-size:12px;cursor:pointer}
.pager button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.pager button:disabled{opacity:.42;cursor:default}
#pageinfo{font-variant-numeric:tabular-nums}
footer{padding:4px 4px 0;color:var(--muted);font-size:11.5px}
footer p{margin:3px 0}
@media (max-width:940px){
  .grid{grid-template-columns:1fr}
  .chart-card{grid-column:auto}
}
@media (max-width:640px){
  main{padding:8px 14px 32px}
  .topbar{padding:16px 14px 8px}
  .kpi.primary{grid-column:span 1}
  .kpis{grid-template-columns:repeat(auto-fit,minmax(130px,1fr))}
}
</style>
<script>
try {
  var savedTheme = localStorage.getItem("usage-ledger-theme");
  document.documentElement.dataset.theme = savedTheme ||
    (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
} catch (e) {}
</script>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <div class="logo">UL</div>
    <div>
      <h1>Usage Ledger</h1>
      <p class="sub">本地 AI 编码工具 token 用量 · 离线单文件</p>
    </div>
  </div>
  <div class="top-actions">
    <span id="generated" class="muted"></span>
    <button id="theme" class="btn ghost small" type="button">深色模式</button>
  </div>
</header>

<main>
  <section class="card filters" aria-label="筛选">
    <div class="filter-line">
      <label class="field">起 <input type="date" id="start"></label>
      <label class="field">止 <input type="date" id="end"></label>
      <div class="presets" id="presets"></div>
      <button id="reset" class="btn ghost small" type="button">重置筛选</button>
    </div>
    <div class="filter-line">
      <div class="chips" id="sources" aria-label="来源"></div>
      <label class="field">模型 <select id="model"></select></label>
      <label class="field">项目 <select id="project"></select></label>
      <label class="field">搜索 <input type="search" id="q" placeholder="日期 / 模型 / 项目"></label>
    </div>
  </section>

  <section class="kpis" id="kpis" aria-label="汇总指标"></section>

  <section class="grid">
    <div class="card chart-card">
      <div class="card-head">
        <h2>每日用量</h2>
        <label class="field">指标
          <select id="metric">
            <option value="total">总量</option>
            <option value="input">输入</option>
            <option value="output">输出</option>
            <option value="cache_read">缓存读</option>
            <option value="cache_write">缓存写</option>
            <option value="reasoning">推理</option>
          </select>
        </label>
      </div>
      <div class="legend" id="legend"></div>
      <div class="chart-wrap">
        <div id="chart"></div>
        <div id="tooltip" class="tooltip"></div>
      </div>
      <p class="muted" id="hint" style="margin:8px 0 0"></p>
    </div>
    <div class="card">
      <div class="card-head"><h2>模型 Top 8</h2><span class="muted">点击筛选 / 再点取消</span></div>
      <div class="bars" id="models"></div>
    </div>
    <div class="card">
      <div class="card-head"><h2>项目 Top 8</h2><span class="muted">点击筛选 / 再点取消</span></div>
      <div class="bars" id="projects"></div>
    </div>
  </section>

  <section class="card table-card">
    <div class="card-head">
      <h2>明细</h2>
      <span class="muted" id="rowinfo"></span>
    </div>
    <div class="table-wrap">
      <table>
        <thead id="thead"></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
    <div class="pager">
      <button id="prev" type="button">上一页</button>
      <span id="pageinfo" class="muted"></span>
      <button id="next" type="button">下一页</button>
    </div>
  </section>

  <footer id="footer"></footer>
</main>

<script type="application/json" id="data">__USAGE_LEDGER_PAYLOAD__</script>
<script>
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  var FIELDS = ["input", "output", "cache_read", "cache_write", "reasoning"];
  var FIELD_LABELS = { input: "输入", output: "输出", cache_read: "缓存读", cache_write: "缓存写", reasoning: "推理" };
  var KNOWN_COLORS = { claude: "#d97706", codex: "#0ea5e9", opencode: "#7c3aed", kilo: "#10b981" };
  var PALETTE = ["#ef4444", "#f59e0b", "#14b8a6", "#6366f1"];
  var KNOWN_ORDER = ["claude", "codex", "opencode", "kilo"];
  var numberFormat = new Intl.NumberFormat("en-US");
  var $ = function (selector) { return document.querySelector(selector); };

  function number(value) {
    var parsed = Number(value);
    return isFinite(parsed) ? parsed : 0;
  }

  var ROWS = (Array.isArray(DATA.rows) ? DATA.rows : []).map(function (row) {
    var copy = {};
    Object.keys(row).forEach(function (key) { copy[key] = row[key]; });
    var total = 0;
    FIELDS.forEach(function (field) { total += number(row[field]); });
    copy.total = total;
    copy.turns = number(row.turns);
    copy.project = row.project || "-";
    return copy;
  });

  var PRESENT = [];
  ROWS.forEach(function (row) {
    if (PRESENT.indexOf(row.source) < 0) PRESENT.push(row.source);
  });
  var SOURCES = KNOWN_ORDER.filter(function (name) { return PRESENT.indexOf(name) >= 0; })
    .concat(PRESENT.filter(function (name) { return KNOWN_ORDER.indexOf(name) < 0; }).sort());
  var COLORS = {};
  SOURCES.forEach(function (name, index) {
    COLORS[name] = KNOWN_COLORS[name] || PALETTE[index % PALETTE.length];
  });

  function minMaxDay(rows) {
    var min = "", max = "";
    rows.forEach(function (row) {
      if (!min || row.day < min) min = row.day;
      if (!max || row.day > max) max = row.day;
    });
    return [min, max];
  }

  var bounds = minMaxDay(ROWS);
  var RANGE = DATA.range || {};
  var DATA_SINCE = RANGE.since || bounds[0] || "";
  var DATA_UNTIL = RANGE.until || bounds[1] || "";
  var DATA_DAYS = new Set(ROWS.map(function (row) { return row.day; }));
  var TODAY = localToday();
  var PICK_MAX = DATA_UNTIL > TODAY ? DATA_UNTIL : TODAY;

  var state = {
    start: DATA_SINCE,
    end: DATA_UNTIL,
    sources: new Set(SOURCES),
    model: "",
    project: "",
    q: "",
    metric: "total",
    sortKey: "day",
    sortDir: "desc",
    page: 0,
    pageSize: 50
  };

  var el = {
    start: $("#start"), end: $("#end"), presets: $("#presets"), reset: $("#reset"),
    sources: $("#sources"), model: $("#model"), project: $("#project"), q: $("#q"),
    kpis: $("#kpis"), metric: $("#metric"), legend: $("#legend"), chart: $("#chart"),
    tooltip: $("#tooltip"), hint: $("#hint"), models: $("#models"), projects: $("#projects"),
    thead: $("#thead"), tbody: $("#tbody"), rowinfo: $("#rowinfo"),
    pageinfo: $("#pageinfo"), prev: $("#prev"), next: $("#next"),
    generated: $("#generated"), footer: $("#footer"), theme: $("#theme")
  };

  function fmtInt(value) {
    return numberFormat.format(Math.round(number(value)));
  }

  function fmtCompact(value) {
    value = number(value);
    if (value >= 1e9) return trimZero((value / 1e9).toFixed(2)) + "B";
    if (value >= 1e6) return trimZero((value / 1e6).toFixed(2)) + "M";
    if (value >= 1e3) return trimZero((value / 1e3).toFixed(1)) + "K";
    if (value >= 10 || Math.floor(value) === value) return String(Math.round(value));
    return trimZero(value.toFixed(1));
  }

  function trimZero(text) {
    return text.replace(/\.0+$/, "").replace(/(\.\d)0$/, "$1");
  }

  function pct(value) {
    if (!isFinite(value) || value <= 0) return "0%";
    return (value * 100).toFixed(1) + "%";
  }

  function fmtCost(value) {
    if (value === null || value === undefined) return "—";
    return "$" + number(value).toFixed(4);
  }

  function fmtDateTime(iso) {
    if (!iso) return "";
    var parsed = new Date(iso);
    if (isNaN(parsed.getTime())) return String(iso);
    return parsed.toLocaleString("zh-CN", { hour12: false });
  }

  function parseDay(day) { return new Date(day + "T00:00:00Z"); }

  function dayString(date) { return date.toISOString().slice(0, 10); }

  function pad2(value) { return (value < 10 ? "0" : "") + value; }

  function localToday() {
    var now = new Date();
    return now.getFullYear() + "-" + pad2(now.getMonth() + 1) + "-" + pad2(now.getDate());
  }

  function addDays(day, offset) {
    var date = parseDay(day);
    date.setUTCDate(date.getUTCDate() + offset);
    return dayString(date);
  }

  function enumerateDays(start, end) {
    var days = [];
    if (!start || !end) return days;
    var cursor = parseDay(start);
    var last = parseDay(end);
    if (isNaN(cursor.getTime()) || isNaN(last.getTime())) return days;
    while (cursor <= last) {
      days.push(dayString(cursor));
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    return days;
  }

  function weekStart(day) {
    var date = parseDay(day);
    var offset = (date.getUTCDay() + 6) % 7;
    date.setUTCDate(date.getUTCDate() - offset);
    return dayString(date);
  }

  function groupTotals(rows, key) {
    var map = new Map();
    rows.forEach(function (row) {
      var name = row[key] || "-";
      if (!map.has(name)) map.set(name, { key: name, total: 0, turns: 0 });
      var entry = map.get(name);
      entry.total += row.total;
      entry.turns += row.turns;
    });
    return Array.from(map.values());
  }

  function byTotal(a, b) { return b.total - a.total; }

  var MODEL_OPTIONS = groupTotals(ROWS, "model").sort(byTotal);
  var PROJECT_OPTIONS = groupTotals(ROWS, "project").sort(byTotal);
  var SOURCE_TOTALS = {};
  ROWS.forEach(function (row) {
    SOURCE_TOTALS[row.source] = (SOURCE_TOTALS[row.source] || 0) + row.total;
  });

  function buildChips() {
    el.sources.textContent = "";
    SOURCES.forEach(function (source) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.dataset.source = source;
      button.title = "单击只看 " + source + "，再次单击恢复全部；⌘/Ctrl/Shift+单击多选";
      var dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = COLORS[source];
      var name = document.createElement("span");
      name.textContent = source;
      var total = document.createElement("small");
      total.textContent = fmtCompact(SOURCE_TOTALS[source] || 0);
      button.appendChild(dot);
      button.appendChild(name);
      button.appendChild(total);
      button.addEventListener("click", function (event) {
        var additive = event.metaKey || event.ctrlKey || event.shiftKey;
        if (additive) {
          if (state.sources.has(source)) {
            if (state.sources.size === 1) return;
            state.sources.delete(source);
          } else {
            state.sources.add(source);
          }
        } else if (state.sources.size === 1 && state.sources.has(source)) {
          state.sources = new Set(SOURCES);
        } else {
          state.sources = new Set([source]);
        }
        state.page = 0;
        syncChips();
        render();
      });
      el.sources.appendChild(button);
    });
    if (SOURCES.length > 1) {
      var tip = document.createElement("span");
      tip.className = "chip-tip";
      tip.textContent = navigator.platform.indexOf("Mac") >= 0
        ? "单击只看 · ⌘+单击多选" : "单击只看 · Ctrl+单击多选";
      el.sources.appendChild(tip);
    }
    syncChips();
  }

  function syncChips() {
    Array.prototype.forEach.call(el.sources.querySelectorAll(".chip"), function (button) {
      var active = state.sources.has(button.dataset.source);
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function fillSelect(select, options, allLabel, labelFn) {
    select.textContent = "";
    var all = document.createElement("option");
    all.value = "";
    all.textContent = allLabel;
    select.appendChild(all);
    options.forEach(function (option) {
      var item = document.createElement("option");
      item.value = option.key;
      item.textContent = labelFn(option.key);
      select.appendChild(item);
    });
  }

  function buildControls() {
    fillSelect(el.model, MODEL_OPTIONS, "全部模型", function (key) { return key; });
    fillSelect(el.project, PROJECT_OPTIONS, "全部项目", function (key) {
      return key === "-" ? "（未标注）" : key;
    });

    el.start.min = DATA_SINCE || "";
    el.start.max = PICK_MAX;
    el.end.min = DATA_SINCE || "";
    el.end.max = PICK_MAX;
    el.start.value = state.start;
    el.end.value = state.end;

    [{ label: "今日", kind: "today" }, { label: "全部", kind: "all" },
     { label: "近 7 天", days: 7 },
     { label: "近 30 天", days: 30 }, { label: "近 90 天", days: 90 }].forEach(function (preset) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn ghost small";
      button.textContent = preset.label;
      button.addEventListener("click", function () {
        var end = preset.kind === "all" ? DATA_UNTIL : TODAY;
        var start = preset.kind === "today" ? TODAY
                  : preset.kind === "all" ? DATA_SINCE
                  : addDays(end, -(preset.days - 1));
        state.start = start < DATA_SINCE ? DATA_SINCE : start;
        state.end = end;
        el.start.value = state.start;
        el.end.value = state.end;
        state.page = 0;
        render();
      });
      el.presets.appendChild(button);
    });

    el.start.addEventListener("change", onDateChange);
    el.end.addEventListener("change", onDateChange);
    el.model.addEventListener("change", function () {
      state.model = el.model.value;
      state.page = 0;
      render();
    });
    el.project.addEventListener("change", function () {
      state.project = el.project.value;
      state.page = 0;
      render();
    });

    var searchTimer;
    el.q.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.q = el.q.value.trim().toLowerCase();
        state.page = 0;
        render();
      }, 120);
    });

    el.metric.addEventListener("change", function () {
      state.metric = el.metric.value;
      renderChart(filteredRows());
    });

    el.reset.addEventListener("click", resetFilters);
    el.prev.addEventListener("click", function () {
      if (state.page > 0) { state.page -= 1; render(); }
    });
    el.next.addEventListener("click", function () { state.page += 1; render(); });
  }

  function onDateChange(event) {
    var start = el.start.value;
    var end = el.end.value;
    if (!start) start = DATA_SINCE;
    if (!end) end = DATA_UNTIL;
    if (start > end) {
      if (event.target === el.start) end = start;
      else start = end;
    }
    el.start.value = start;
    el.end.value = end;
    state.start = start;
    state.end = end;
    state.page = 0;
    render();
  }

  function resetFilters() {
    state.start = DATA_SINCE;
    state.end = DATA_UNTIL;
    state.sources = new Set(SOURCES);
    state.model = "";
    state.project = "";
    state.q = "";
    state.metric = "total";
    state.sortKey = "day";
    state.sortDir = "desc";
    state.page = 0;
    el.start.value = state.start;
    el.end.value = state.end;
    el.model.value = "";
    el.project.value = "";
    el.q.value = "";
    el.metric.value = "total";
    syncChips();
    render();
  }

  function matchesQuery(row) {
    if (!state.q) return true;
    var haystack = (row.day + " " + row.source + " " + row.model + " " + row.project).toLowerCase();
    return haystack.indexOf(state.q) >= 0;
  }

  function filteredRows(ignore) {
    return ROWS.filter(function (row) {
      if (state.start && row.day < state.start) return false;
      if (state.end && row.day > state.end) return false;
      if (!state.sources.has(row.source)) return false;
      if (ignore !== "model" && state.model && row.model !== state.model) return false;
      if (ignore !== "project" && state.project && row.project !== state.project) return false;
      return matchesQuery(row);
    });
  }

  function addKpi(label, value, sub, primary) {
    var card = document.createElement("div");
    card.className = "kpi" + (primary ? " primary" : "");
    var labelNode = document.createElement("div");
    labelNode.className = "kpi-label";
    labelNode.textContent = label;
    var valueNode = document.createElement("div");
    valueNode.className = "kpi-value";
    valueNode.textContent = value;
    valueNode.title = sub;
    var subNode = document.createElement("div");
    subNode.className = "kpi-sub";
    subNode.textContent = sub;
    card.appendChild(labelNode);
    card.appendChild(valueNode);
    card.appendChild(subNode);
    el.kpis.appendChild(card);
  }

  function renderKpis(rows) {
    var sums = {};
    FIELDS.forEach(function (field) { sums[field] = 0; });
    var turns = 0;
    var cost = 0;
    var costKnown = false;
    rows.forEach(function (row) {
      FIELDS.forEach(function (field) { sums[field] += number(row[field]); });
      turns += row.turns;
      if (row.cost_equiv_usd !== null && row.cost_equiv_usd !== undefined) {
        cost += number(row.cost_equiv_usd);
        costKnown = true;
      }
    });
    var total = FIELDS.reduce(function (acc, field) { return acc + sums[field]; }, 0);

    el.kpis.textContent = "";
    addKpi("总 Token", fmtCompact(total), fmtInt(total), true);
    FIELDS.forEach(function (field) {
      addKpi(FIELD_LABELS[field], fmtCompact(sums[field]), fmtInt(sums[field]));
    });
    addKpi("缓存占比", total ? pct(sums.cache_read / total) : "—", "cache_read / 总量");
    addKpi("轮次", fmtCompact(turns), fmtInt(turns));
    if (costKnown) addKpi("等价成本", "$" + cost.toFixed(2), "按 API 价折算，非实付");
  }

  function metricOf(values) {
    if (!values) return 0;
    if (state.metric === "total") {
      return FIELDS.reduce(function (acc, field) { return acc + number(values[field]); }, 0);
    }
    return number(values[state.metric]);
  }

  function rowMetric(row) {
    if (state.metric === "total") return row.total;
    return number(row[state.metric]);
  }

  function setAttrs(node, attrs) {
    Object.keys(attrs).forEach(function (key) {
      var value = attrs[key];
      if (value !== null && value !== undefined) node.setAttribute(key, String(value));
    });
    return node;
  }

  function svgEl(tag, attrs) {
    return setAttrs(document.createElementNS("http://www.w3.org/2000/svg", tag), attrs);
  }

  function niceScale(maximum, tickCount) {
    if (maximum <= 0) maximum = 1;
    var rough = maximum / tickCount;
    var power = Math.pow(10, Math.floor(Math.log10(rough)));
    var fraction = rough / power;
    var niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    var step = niceFraction * power;
    var max = Math.ceil(maximum / step) * step;
    var ticks = [];
    for (var value = 0; value <= max + step * 0.5; value += step) ticks.push(value);
    return { max: max, ticks: ticks };
  }

  function buildBuckets(rows) {
    var days = enumerateDays(state.start, state.end);
    if (!days.length) return [];
    var weekly = days.length > 200;
    var buckets = [];
    var index = new Map();
    days.forEach(function (day) {
      var key = weekly ? weekStart(day) : day;
      if (!index.has(key)) {
        var bucket = { key: key, start: day, end: day, bySource: {} };
        index.set(key, bucket);
        buckets.push(bucket);
      } else {
        index.get(key).end = day;
      }
    });
    buckets.forEach(function (bucket) {
      bucket.label = bucket.start.slice(5);
      bucket.tooltip = weekly ? bucket.start + " ~ " + bucket.end : bucket.start;
    });
    rows.forEach(function (row) {
      var key = weekly ? weekStart(row.day) : row.day;
      var bucket = index.get(key);
      if (!bucket) return;
      if (!bucket.bySource[row.source]) {
        bucket.bySource[row.source] = {};
        FIELDS.forEach(function (field) { bucket.bySource[row.source][field] = 0; });
      }
      FIELDS.forEach(function (field) {
        bucket.bySource[row.source][field] += number(row[field]);
      });
    });
    buckets.forEach(function (bucket) {
      bucket.metricTotal = 0;
      bucket.metricBySource = {};
      SOURCES.forEach(function (source) {
        var value = metricOf(bucket.bySource[source]);
        bucket.metricBySource[source] = value;
        bucket.metricTotal += value;
      });
    });
    return buckets;
  }

  function renderLegend(rows) {
    el.legend.textContent = "";
    var totals = {};
    rows.forEach(function (row) {
      totals[row.source] = (totals[row.source] || 0) + rowMetric(row);
    });
    SOURCES.forEach(function (source) {
      if (!state.sources.has(source)) return;
      var item = document.createElement("span");
      item.className = "legend-item";
      var dot = document.createElement("i");
      dot.className = "legend-dot";
      dot.style.background = COLORS[source];
      var name = document.createElement("span");
      name.textContent = source;
      var value = document.createElement("b");
      value.textContent = fmtCompact(totals[source] || 0);
      item.appendChild(dot);
      item.appendChild(name);
      item.appendChild(value);
      el.legend.appendChild(item);
    });
  }

  function tooltipRow(source, value, strong) {
    var row = document.createElement("div");
    row.className = "tt-row" + (strong ? " tt-total" : "");
    var name = document.createElement("span");
    name.className = "tt-name";
    if (!strong) {
      var dot = document.createElement("i");
      dot.style.background = COLORS[source] || "var(--accent)";
      name.appendChild(dot);
    }
    var label = document.createElement("span");
    label.textContent = strong ? "合计" : source;
    name.appendChild(label);
    var amount = document.createElement("span");
    amount.className = "tt-val";
    amount.textContent = fmtInt(value);
    row.appendChild(name);
    row.appendChild(amount);
    return row;
  }

  function renderChart(rows) {
    var buckets = buildBuckets(rows);
    el.chart.textContent = "";
    el.legend.textContent = "";
    el.tooltip.style.display = "none";
    if (!buckets.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = ROWS.length ? "所选范围内没有数据" : "暂无数据";
      el.chart.appendChild(empty);
      return;
    }

    var width = Math.max(el.chart.clientWidth || 900, 320);
    var height = 300;
    var margin = { top: 14, right: 14, bottom: 28, left: 62 };
    var plotW = Math.max(width - margin.left - margin.right, 10);
    var plotH = height - margin.top - margin.bottom;
    var maximum = buckets.reduce(function (acc, bucket) {
      return Math.max(acc, bucket.metricTotal);
    }, 0);
    var scale = niceScale(maximum, 4);
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": "按来源堆叠的每日 token 用量"
    });

    scale.ticks.forEach(function (value) {
      var y = margin.top + plotH - (value / scale.max) * plotH;
      svg.appendChild(svgEl("line", {
        x1: margin.left, x2: width - margin.right, y1: y, y2: y,
        class: "grid-line"
      }));
      var text = svgEl("text", {
        x: margin.left - 8, y: y + 3.5, "text-anchor": "end"
      });
      text.textContent = fmtCompact(value);
      svg.appendChild(text);
    });

    var band = plotW / buckets.length;
    var barW = Math.max(1.5, Math.min(26, band * 0.66));
    var hoverLine = svgEl("line", {
      x1: 0, x2: 0, y1: margin.top, y2: margin.top + plotH, class: "hover-line"
    });

    function moveHover(index) {
      if (index < 0) {
        hoverLine.setAttribute("x1", 0);
        hoverLine.setAttribute("x2", 0);
        return;
      }
      var center = margin.left + band * index + band / 2;
      hoverLine.setAttribute("x1", center);
      hoverLine.setAttribute("x2", center);
    }

    buckets.forEach(function (bucket, index) {
      var x = margin.left + band * index + (band - barW) / 2;
      var y = margin.top + plotH;
      SOURCES.forEach(function (source) {
        if (!state.sources.has(source)) return;
        var value = bucket.metricBySource[source] || 0;
        if (value <= 0) return;
        var slice = (value / scale.max) * plotH;
        y -= slice;
        svg.appendChild(svgEl("rect", {
          x: x, y: y, width: barW, height: slice,
          fill: COLORS[source], class: "seg", rx: barW > 4 ? 1.5 : 0
        }));
      });

      var hit = svgEl("rect", {
        x: margin.left + band * index, y: margin.top,
        width: Math.max(band, 1), height: plotH, class: "hit"
      });
      hit.addEventListener("mouseenter", function (event) {
        moveHover(index);
        showTooltip(bucket, event);
      });
      hit.addEventListener("mousemove", positionTooltip);
      hit.addEventListener("mouseleave", function () {
        moveHover(-1);
        el.tooltip.style.display = "none";
      });
      svg.appendChild(hit);
    });
    svg.appendChild(hoverLine);

    var labelCount = Math.min(buckets.length, Math.max(2, Math.floor(plotW / 90)));
    var step = labelCount <= 1 ? 1 : (buckets.length - 1) / (labelCount - 1);
    var used = new Set();
    for (var k = 0; k < labelCount; k += 1) {
      var index = Math.round(k * step);
      if (used.has(index)) continue;
      used.add(index);
      var label = svgEl("text", {
        x: margin.left + band * index + band / 2,
        y: height - 8,
        "text-anchor": "middle"
      });
      label.textContent = buckets[index].label;
      svg.appendChild(label);
    }

    el.chart.appendChild(svg);
    renderLegend(rows);

    function showTooltip(bucket, event) {
      el.tooltip.textContent = "";
      var head = document.createElement("div");
      head.className = "tt-head";
      head.textContent = bucket.tooltip;
      el.tooltip.appendChild(head);
      var meta = document.createElement("div");
      meta.className = "tt-meta";
      meta.textContent = "指标：" + (state.metric === "total" ? "总量" : FIELD_LABELS[state.metric]);
      el.tooltip.appendChild(meta);

      var entries = [];
      SOURCES.forEach(function (source) {
        if (!state.sources.has(source)) return;
        var value = bucket.metricBySource[source] || 0;
        if (value > 0) entries.push({ source: source, value: value });
      });
      entries.sort(function (a, b) { return b.value - a.value; });
      if (!entries.length) {
        var none = document.createElement("div");
        none.className = "tt-row";
        none.textContent = "无数据";
        el.tooltip.appendChild(none);
      } else {
        entries.forEach(function (entry) {
          el.tooltip.appendChild(tooltipRow(entry.source, entry.value, false));
        });
        el.tooltip.appendChild(tooltipRow(null, bucket.metricTotal, true));
      }
      el.tooltip.style.display = "block";
      positionTooltip(event);
    }

    function positionTooltip(event) {
      var rect = el.chart.parentElement.getBoundingClientRect();
      var x = event.clientX - rect.left;
      var half = 110;
      x = Math.max(half, Math.min(x, rect.width - half));
      el.tooltip.style.left = x + "px";
    }
  }

  function renderBarList(host, items, grandTotal, selected, onPick) {
    host.textContent = "";
    if (!items.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "无数据";
      host.appendChild(empty);
      return;
    }
    var maximum = Math.max(items[0].total, 1);
    items.forEach(function (item) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "bar-row" + (item.key === selected ? " selected" : "");
      button.setAttribute("aria-pressed", item.key === selected ? "true" : "false");
      var top = document.createElement("div");
      top.className = "bar-top";
      var name = document.createElement("span");
      name.className = "bar-name";
      name.textContent = item.key === "-" ? "（未标注）" : item.key;
      name.title = item.key;
      var value = document.createElement("span");
      value.className = "bar-value";
      value.textContent = fmtCompact(item.total) + " · " + pct(grandTotal ? item.total / grandTotal : 0);
      top.appendChild(name);
      top.appendChild(value);
      var track = document.createElement("div");
      track.className = "bar-track";
      var fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = Math.max(item.total / maximum * 100, 1.5).toFixed(1) + "%";
      track.appendChild(fill);
      button.appendChild(top);
      button.appendChild(track);
      button.title = "筛选：" + item.key;
      button.addEventListener("click", function () { onPick(item.key); });
      host.appendChild(button);
    });
  }

  function renderBars(modelRows, projectRows) {
    var modelTotal = modelRows.reduce(function (acc, row) { return acc + row.total; }, 0);
    renderBarList(el.models, groupTotals(modelRows, "model").sort(byTotal).slice(0, 8),
      modelTotal, state.model, function (key) {
        state.model = state.model === key ? "" : key;
        el.model.value = state.model;
        state.page = 0;
        render();
      });
    var projectTotal = projectRows.reduce(function (acc, row) { return acc + row.total; }, 0);
    renderBarList(el.projects, groupTotals(projectRows, "project").sort(byTotal).slice(0, 8),
      projectTotal, state.project, function (key) {
        state.project = state.project === key ? "" : key;
        el.project.value = state.project;
        state.page = 0;
        render();
      });
  }

  var NUMERIC_KEYS = new Set(FIELDS.concat(["total", "turns", "cost_equiv_usd"]));
  var COST_KNOWN = ROWS.some(function (row) {
    return row.cost_equiv_usd !== null && row.cost_equiv_usd !== undefined;
  });
  var COLUMNS = [
    { key: "day", label: "日期", type: "text" },
    { key: "source", label: "来源", type: "text" },
    { key: "model", label: "模型", type: "text" },
    { key: "project", label: "项目", type: "text" }
  ];
  FIELDS.forEach(function (field) {
    COLUMNS.push({ key: field, label: FIELD_LABELS[field], type: "num" });
  });
  COLUMNS.push({ key: "total", label: "合计", type: "num" });
  COLUMNS.push({ key: "turns", label: "轮次", type: "num" });
  if (COST_KNOWN) COLUMNS.push({ key: "cost_equiv_usd", label: "等价成本", type: "num" });

  function comparator(a, b) {
    var av = a[state.sortKey];
    var bv = b[state.sortKey];
    var cmp;
    if (NUMERIC_KEYS.has(state.sortKey)) cmp = number(av) - number(bv);
    else cmp = String(av).localeCompare(String(bv), "zh-CN");
    if (cmp === 0 && state.sortKey !== "total") cmp = a.total - b.total;
    return state.sortDir === "asc" ? cmp : -cmp;
  }

  function renderTable(rows) {
    var sorted = rows.slice().sort(comparator);
    var pages = Math.max(1, Math.ceil(sorted.length / state.pageSize));
    if (state.page >= pages) state.page = pages - 1;
    if (state.page < 0) state.page = 0;
    var start = state.page * state.pageSize;
    var slice = sorted.slice(start, start + state.pageSize);

    var focusedKey = null;
    if (document.activeElement && document.activeElement.classList.contains("th-btn")) {
      focusedKey = document.activeElement.dataset.key;
    }

    el.thead.textContent = "";
    var headerRow = document.createElement("tr");
    COLUMNS.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      th.setAttribute("aria-sort", state.sortKey === column.key
        ? (state.sortDir === "asc" ? "ascending" : "descending") : "none");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "th-btn";
      button.dataset.key = column.key;
      button.appendChild(document.createTextNode(column.label));
      if (state.sortKey === column.key) {
        var arrow = document.createElement("span");
        arrow.className = "arrow";
        arrow.textContent = state.sortDir === "asc" ? "▲" : "▼";
        button.appendChild(arrow);
      }
      button.addEventListener("click", function () {
        if (state.sortKey === column.key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = column.key;
          state.sortDir = column.type === "num" ? "desc" : "asc";
        }
        state.page = 0;
        render();
      });
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    el.thead.appendChild(headerRow);

    if (focusedKey) {
      var restored = el.thead.querySelector('.th-btn[data-key="' + focusedKey + '"]');
      if (restored) restored.focus({ preventScroll: true });
    }

    el.tbody.textContent = "";
    if (!slice.length) {
      var emptyRow = document.createElement("tr");
      var cell = document.createElement("td");
      cell.colSpan = COLUMNS.length;
      cell.className = "empty";
      cell.textContent = ROWS.length ? "无匹配数据" : "暂无数据";
      emptyRow.appendChild(cell);
      el.tbody.appendChild(emptyRow);
    } else {
      slice.forEach(function (row) {
        var tr = document.createElement("tr");
        COLUMNS.forEach(function (column) {
          var td = document.createElement("td");
          var value = row[column.key];
          if (column.type === "num") td.className = "num";
          if (column.key === "project") {
            td.textContent = value === "-" ? "（未标注）" : value;
            td.title = value;
          } else if (column.key === "model") {
            td.textContent = value;
            td.title = value;
          } else if (column.key === "cost_equiv_usd") {
            td.textContent = fmtCost(value);
          } else if (column.type === "num") {
            td.textContent = fmtInt(value);
            if (!number(value)) td.classList.add("zero");
          } else {
            td.textContent = value;
          }
          tr.appendChild(td);
        });
        el.tbody.appendChild(tr);
      });
    }

    var totalTokens = rows.reduce(function (acc, row) { return acc + row.total; }, 0);
    el.rowinfo.textContent = fmtInt(rows.length) + " 行 · 共 " + fmtInt(totalTokens) + " tokens";
    el.pageinfo.textContent = slice.length
      ? (start + 1) + "–" + (start + slice.length) + " / " + fmtInt(sorted.length)
      : "0 / 0";
    el.prev.disabled = state.page <= 0;
    el.next.disabled = state.page >= pages - 1;
  }

  function renderHint() {
    if (!state.start || !state.end) {
      el.hint.textContent = "";
      return;
    }
    var days = enumerateDays(state.start, state.end);
    var missing = days.filter(function (day) { return !DATA_DAYS.has(day); });
    if (!missing.length) {
      el.hint.textContent = "";
      return;
    }
    var shown = missing.slice(0, 10).join("、");
    el.hint.textContent = "范围内 " + missing.length + " 天无采集数据（图表按 0 显示）：" +
      shown + (missing.length > 10 ? " …" : "");
  }

  function renderFooter() {
    el.footer.textContent = "";
    (DATA.notices || []).forEach(function (notice) {
      var line = document.createElement("p");
      line.textContent = notice;
      el.footer.appendChild(line);
    });
    var scope = document.createElement("p");
    scope.textContent = "数据范围 " + (DATA_SINCE || "—") + " ~ " + (DATA_UNTIL || "—") +
      " · " + fmtInt(ROWS.length) + " 行日/来源/模型/项目聚合 · 页面不发起任何网络请求";
    el.footer.appendChild(scope);
    var generated = document.createElement("p");
    generated.textContent = "生成于 " + fmtDateTime(DATA.generated_at);
    el.footer.appendChild(generated);
  }

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    el.theme.textContent = theme === "dark" ? "浅色模式" : "深色模式";
  }

  el.theme.addEventListener("click", function () {
    var next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("usage-ledger-theme", next); } catch (e) {}
  });

  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { renderChart(filteredRows()); }, 150);
  });

  function render() {
    var rows = filteredRows();
    renderKpis(rows);
    renderChart(rows);
    renderBars(filteredRows("model"), filteredRows("project"));
    renderTable(rows);
    renderHint();
  }

  buildChips();
  buildControls();
  applyTheme(document.documentElement.dataset.theme || "light");
  el.generated.textContent = "生成于 " + fmtDateTime(DATA.generated_at);
  renderFooter();
  render();
})();
</script>
</body>
</html>
"""
