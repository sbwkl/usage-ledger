from __future__ import annotations

import json
from datetime import datetime

from .models import ACTIVITY_FIELDS, FIELDS

PLACEHOLDER = "__USAGE_LEDGER_PAYLOAD__"

# token：源日志里逐调用 token 真值；credits：服务端逐请求计费真值（token 仅可估算）；
# estimate：本地无真值，仅 hook 可见字符弱估算。
AGENT_KINDS = {
    "claude": "token",
    "codex": "token",
    "opencode": "token",
    "kilo": "token",
    "cline": "token",
    "qoder": "credits",
    "trae-cn": "estimate",
}


def build_payload(rows, dims, since, until, notices, generated_at=None,
                  activity=None, coverage=None, credits=None, quota=None,
                  credit_rows=None,
                  est_rows=None, est_totals=None, factor_version=None,
                  trae_est_rows=None, trae_est_totals=None,
                  trae_factor_version=None) -> dict:
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
    activity_rows = []
    for act in activity or []:
        item = {"day": act.day, "source": "qoder", "project": act.project or "-"}
        for field in ACTIVITY_FIELDS:
            item[field] = getattr(act, field)
        activity_rows.append(item)
    credit_data = credits or {}
    est_data = {"rows": list(est_rows or []), "totals": est_totals or {},
                "factor_version": factor_version or ""}
    return {
        "generated_at": generated_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "range": {"since": since, "until": until},
        "rows": payload_rows,
        "agents": dict(AGENT_KINDS),
        "activity": activity_rows,
        "credits": {
            "days": list(credit_data.get("days") or []),
            "rows": list(credit_rows or credit_data.get("rows") or []),
            "totals": credit_data.get("totals") or {},
            "quota": quota or {},
        },
        "est": est_data,
        "trae_est": {"rows": list(trae_est_rows or []),
                     "totals": trae_est_totals or {},
                     "factor_version": trae_factor_version or ""},
        "coverage": coverage or {},
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
[hidden]{display:none!important}
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

.agent-nav{display:flex;flex-wrap:wrap;align-items:center;gap:8px 10px;padding:10px 14px}
.agent-nav-label{font-size:11px;letter-spacing:.4px;color:var(--muted);white-space:nowrap}
.kpi-section{grid-column:1/-1;font-size:11px;letter-spacing:.4px;color:var(--muted);margin-top:4px}
.chart-panel+.chart-panel{margin-top:18px;padding-top:14px;border-top:1px solid var(--border)}
.chart-panel h3{font-size:12.5px;margin:0;letter-spacing:.2px}

.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px 14px;box-shadow:var(--shadow);min-width:0}
.kpi.primary{grid-column:span 2;background:linear-gradient(135deg,var(--accent-soft),var(--surface) 72%);border-color:var(--accent)}
.kpi.shadow{border-style:dashed;background:transparent;box-shadow:none}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:clamp(20px,2.1vw,27px);font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.3px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-sub{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.coverage{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0;padding:10px 14px;border:1px solid var(--accent);border-radius:12px;background:var(--accent-soft);color:var(--text);font-size:12.5px}

.agent-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.agent-title-row{display:flex;align-items:center;gap:9px;flex-wrap:wrap}
.agent-title-row h2{font-size:17px;margin:0;letter-spacing:.2px}
.agent-head p{margin:4px 0 0}
.kind-badge{border-radius:999px;padding:2px 9px;font-size:11px;font-weight:600;border:1px solid var(--border);background:var(--surface-2);color:var(--muted);white-space:nowrap}
.kind-badge.token{color:#0f766e;background:rgba(16,185,129,.1);border-color:rgba(16,185,129,.4)}
.kind-badge.credits{color:#be123c;background:rgba(225,29,72,.08);border-color:rgba(225,29,72,.4)}
.kind-badge.estimate{color:#b45309;background:rgba(245,158,11,.1);border-color:rgba(245,158,11,.45)}
.agent-head-actions{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.unit-tag{font-size:10.5px;color:var(--muted);border:1px solid var(--border);border-radius:999px;padding:1px 7px;font-weight:500;white-space:nowrap}
.switch{display:inline-flex;align-items:center;gap:8px;font-size:12px;color:var(--muted);cursor:pointer;user-select:none}
.switch input{position:absolute;opacity:0;pointer-events:none}
.switch-track{width:30px;height:17px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border);position:relative;transition:border-color .15s,background .15s;flex:none}
.switch-track::after{content:"";position:absolute;top:2px;left:2px;width:11px;height:11px;border-radius:50%;background:var(--muted);transition:left .15s,background .15s}
.switch input:checked+.switch-track{background:var(--accent-soft);border-color:var(--accent)}
.switch input:checked+.switch-track::after{left:15px;background:var(--accent)}
.switch input:focus-visible+.switch-track{outline:2px solid var(--accent);outline-offset:2px}

.grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,.85fr);gap:16px}
.chart-card{grid-column:1/-1}
.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;flex-wrap:wrap}
.card-head h2{font-size:14px;margin:0;letter-spacing:.2px}
.card-head .head-tags{display:inline-flex;align-items:center;gap:8px}
.muted{color:var(--muted);font-size:12px}
.legend{display:flex;flex-wrap:wrap;gap:14px;margin:0 0 4px;padding-left:2px}
.legend-item{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.legend-item b{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
.legend-dot{width:9px;height:9px;border-radius:3px;display:inline-block}
.legend-line{width:16px;height:0;border-top:2px dashed var(--muted);display:inline-block;opacity:.75}
.chart-wrap{position:relative;width:100%}
#chart,#agent-chart{width:100%;min-height:300px}
.chart-wrap svg{display:block;width:100%;height:auto}
.chart-wrap svg text{fill:var(--muted);font-size:11px;font-family:inherit}
.chart-wrap .grid-line{stroke:var(--border);stroke-width:1;shape-rendering:crispEdges}
.chart-wrap .seg{stroke:var(--surface);stroke-width:.6}
.chart-wrap .hit{fill:transparent;cursor:crosshair}
.chart-wrap .hover-line{stroke:var(--accent);stroke-width:1;stroke-dasharray:3 3;opacity:.45;pointer-events:none}
.chart-wrap .shadow-line{fill:none;stroke:var(--muted);stroke-width:1.5;stroke-dasharray:5 4;opacity:.55;pointer-events:none}
.chart-wrap .shadow-dot{fill:var(--muted);opacity:.55;pointer-events:none}
.chart-wrap .axis-right text{fill:var(--muted);font-size:10.5px;opacity:.85}
.empty{display:grid;place-items:center;min-height:200px;color:var(--muted);font-size:13px}
.tooltip{position:absolute;z-index:5;top:8px;left:0;transform:translateX(-50%);min-width:190px;max-width:290px;background:var(--surface);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 28px rgba(0,0,0,.18);padding:9px 11px;pointer-events:none;display:none}
.tt-head{font-size:12px;font-weight:650;margin-bottom:2px}
.tt-meta{font-size:11px;color:var(--muted);margin-bottom:6px}
.tt-row{display:flex;justify-content:space-between;gap:14px;font-size:12px;padding:1.5px 0}
.tt-name{display:inline-flex;align-items:center;gap:6px;color:var(--muted)}
.tt-name i{width:7px;height:7px;border-radius:2px;display:inline-block}
.tt-name i.dash{height:0;border-top:2px dashed var(--muted);border-radius:0;background:transparent}
.tt-val{font-variant-numeric:tabular-nums;color:var(--text)}
.tt-total{border-top:1px solid var(--border);margin-top:5px;padding-top:5px;font-weight:600}
.tt-shadow{color:var(--muted);font-style:italic}
.bars{display:flex;flex-direction:column;gap:11px;min-height:120px}
.bar-row{display:block;width:100%;border:0;background:transparent;padding:0;margin:0;text-align:left;cursor:pointer;border-radius:8px;font:inherit;color:inherit}
.bar-row:hover .bar-name{color:var(--accent)}
.bar-row:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.bar-row.selected .bar-name{color:var(--accent);font-weight:700}
.bar-row.selected .bar-track{box-shadow:0 0 0 1px var(--accent)}
.bar-top{display:flex;justify-content:space-between;gap:10px;font-size:12px;margin-bottom:4px}
.bar-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70%;font-family:var(--mono);font-size:11.5px}
.bar-value{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.bar-shadow{font-size:10.5px;color:var(--muted);opacity:.8;margin:-1px 0 4px;font-variant-numeric:tabular-nums}
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
th.shadow-col .th-btn{font-style:italic;font-weight:500}
td.shadow-col{color:var(--muted)}
.shadow-note{margin:8px 0 0}
.pager{display:flex;align-items:center;justify-content:flex-end;gap:10px;padding-top:10px}
.pager button{border:1px solid var(--border);background:var(--surface-2);color:var(--text);border-radius:8px;padding:5px 10px;font:inherit;font-size:12px;cursor:pointer}
.pager button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.pager button:disabled{opacity:.42;cursor:default}
#pageinfo{font-variant-numeric:tabular-nums}
.activity-block{padding:0}
.activity-block summary{cursor:pointer;padding:14px 16px;font-size:13.5px;font-weight:600;list-style:none;display:flex;align-items:center;gap:8px}
.activity-block summary::-webkit-details-marker{display:none}
.activity-block summary::before{content:"▸";color:var(--muted);transition:transform .15s}
.activity-block[open] summary::before{transform:rotate(90deg)}
.activity-body{display:flex;flex-direction:column;gap:14px;padding:0 16px 16px}
.quota-kpi .kpi-sub{white-space:normal;overflow:visible}
.quota-track{height:6px;border-radius:999px;background:var(--surface-2);overflow:hidden;margin-top:9px}
.quota-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#22c1a4)}
.quota-fill.warn{background:linear-gradient(90deg,#f59e0b,#ef4444)}
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
      <p class="sub">本地 AI 编码工具用量 · 多 Agent 按单位汇总 · 离线单文件</p>
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
      <label class="field">模型 <select id="model"></select></label>
      <label class="field">项目 <select id="project"></select></label>
      <label class="field">搜索 <input type="search" id="q" placeholder="日期 / 模型 / 项目"></label>
    </div>
  </section>

  <nav class="card agent-nav" id="agent-nav" aria-label="Agent 选择"></nav>

  <p id="coverage" class="coverage" hidden></p>

  <section class="agent-page" id="report-page" aria-label="用量报告">
    <section class="kpis" id="kpis" aria-label="汇总指标"></section>
    <section class="grid" style="margin-top:16px">
      <div class="card chart-card">
        <div class="card-head">
          <h2>每日用量</h2>
          <div class="head-tags">
            <label class="field" id="metric-field">Token 指标
              <select id="metric">
                <option value="total">总量</option>
                <option value="input">输入</option>
                <option value="output">输出</option>
                <option value="cache_read">缓存读</option>
                <option value="cache_write">缓存写</option>
                <option value="reasoning">推理</option>
              </select>
            </label>
            <label class="switch" id="shadow-switch" hidden>
              <input type="checkbox" id="shadow">
              <span class="switch-track" aria-hidden="true"></span>
              <span>影子：Qoder 估算 token</span>
            </label>
          </div>
        </div>
        <div class="chart-panel" id="panel-token">
          <div class="card-head"><div class="head-tags"><h3>Token</h3><span class="unit-tag">tokens</span></div></div>
          <div class="legend" id="legend-token"></div>
          <div class="chart-wrap">
            <div id="chart-token"></div>
            <div id="tooltip-token" class="tooltip"></div>
          </div>
          <p class="muted" id="hint-token" style="margin:8px 0 0"></p>
        </div>
        <div class="chart-panel" id="panel-credits" hidden>
          <div class="card-head"><div class="head-tags"><h3>Credits</h3><span class="unit-tag">credits</span></div></div>
          <div class="legend" id="legend-credits"></div>
          <div class="chart-wrap">
            <div id="chart-credits"></div>
            <div id="tooltip-credits" class="tooltip"></div>
          </div>
          <p class="muted" id="hint-credits" style="margin:8px 0 0"></p>
        </div>
        <div class="chart-panel" id="panel-est" hidden>
          <div class="card-head"><div class="head-tags"><h3>估算</h3><span class="unit-tag">est tokens</span></div></div>
          <div class="legend" id="legend-est"></div>
          <div class="chart-wrap">
            <div id="chart-est"></div>
            <div id="tooltip-est" class="tooltip"></div>
          </div>
          <p class="muted" id="hint-est" style="margin:8px 0 0"></p>
        </div>
      </div>
      <div class="card">
        <div class="card-head">
          <div class="head-tags"><h2>模型 Top 8</h2><span class="unit-tag" id="model-unit"></span></div>
          <span class="muted">点击筛选 / 再点取消</span>
        </div>
        <div class="bars" id="models"></div>
      </div>
      <div class="card">
        <div class="card-head">
          <div class="head-tags"><h2>项目 Top 8</h2><span class="unit-tag" id="project-unit"></span></div>
          <span class="muted">点击筛选 / 再点取消</span>
        </div>
        <div class="bars" id="projects"></div>
      </div>
    </section>

    <section class="card table-card" id="token-table" style="margin-top:16px">
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
      <p class="muted shadow-note" id="shadow-note" hidden></p>
    </section>

    <details class="card activity-block" id="activity-block" style="margin-top:16px" hidden>
      <summary>补充：活动指标（非 token，不可与任何用量相加）</summary>
      <div class="activity-body">
        <div class="card-head">
          <h2>活动指标</h2>
          <label class="field">指标
            <select id="activity-metric">
              <option value="tool_calls">工具调用</option>
              <option value="sessions">活跃会话</option>
              <option value="prompts">提示数</option>
              <option value="assistant_calls">assistant 调用</option>
            </select>
          </label>
        </div>
        <section class="kpis" id="activity-kpis" aria-label="Qoder 活动指标"></section>
        <div class="legend" id="activity-legend"></div>
        <div class="chart-wrap">
          <div id="activity-chart"></div>
          <div id="activity-tooltip" class="tooltip"></div>
        </div>
        <p class="muted" id="activity-hint" style="margin:0"></p>
        <div class="table-wrap">
          <table>
            <thead id="activity-thead"></thead>
            <tbody id="activity-tbody"></tbody>
          </table>
        </div>
        <p class="muted" id="activity-rowinfo" style="margin:0;text-align:right"></p>
      </div>
    </details>
  </section>

  <footer id="footer"></footer>
</main>

<script type="application/json" id="data">__USAGE_LEDGER_PAYLOAD__</script>
<script>
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("data").textContent || "{}");
  var FIELDS = ["input", "output", "cache_read", "cache_write", "reasoning"];
  var FIELD_LABELS = { input: "输入", output: "输出", cache_read: "缓存读",
                       cache_write: "缓存写", reasoning: "推理" };
  var ACTIVITY_FIELDS = ["sessions", "prompts", "assistant_calls", "assistant_with_metrics",
                         "turns", "tool_calls", "duration_ms"];
  var ACTIVITY_LABELS = { sessions: "活跃会话", prompts: "提示数", assistant_calls: "assistant 调用",
                          assistant_with_metrics: "带指标", turns: "turns",
                          tool_calls: "工具调用", duration_ms: "运行时长" };
  var KNOWN_COLORS = { claude: "#d97706", codex: "#0ea5e9", opencode: "#7c3aed",
                       kilo: "#10b981", cline: "#65a30d", qoder: "#e11d48", "trae-cn": "#0d9488" };
  var PALETTE = ["#ef4444", "#f59e0b", "#14b8a6", "#6366f1"];
  var KNOWN_ORDER = ["claude", "codex", "opencode", "kilo", "cline", "qoder", "trae-cn"];
  var AGENT_KINDS = DATA.agents || {};
  var KIND_LABELS = { token: "精确 Token", credits: "精确 Credits", estimate: "仅估算" };
  var CREDIT_BILLABLE_COLOR = "#e11d48";
  var CREDIT_FREE_COLOR = "#f59e0b";
  var EST_INPUT_COLOR = "#3b6cf6";
  var EST_OUTPUT_COLOR = "#14b8a6";
  var numberFormat = new Intl.NumberFormat("en-US");
  var $ = function (selector) { return document.querySelector(selector); };

  function agentKind(name) { return AGENT_KINDS[name] || "token"; }
  function number(value) {
    var parsed = Number(value);
    return isFinite(parsed) ? parsed : 0;
  }
  function sumField(rows, field) {
    return rows.reduce(function (acc, row) { return acc + number(row[field]); }, 0);
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
  var TOKEN_ROWS = ROWS.filter(function (row) { return agentKind(row.source) === "token"; });
  var QODER_TOKEN_ROWS = ROWS.filter(function (row) { return row.source === "qoder"; });

  var ACTIVITY = (Array.isArray(DATA.activity) ? DATA.activity : []).map(function (row) {
    var copy = {};
    Object.keys(row).forEach(function (key) { copy[key] = row[key]; });
    ACTIVITY_FIELDS.forEach(function (field) { copy[field] = number(row[field]); });
    copy.project = row.project || "-";
    return copy;
  });

  var CREDIT_DATA = DATA.credits || {};
  var CREDIT_ROWS = (Array.isArray(CREDIT_DATA.rows) ? CREDIT_DATA.rows : []).map(function (row) {
    var credits = number(row.credits);
    return {
      day: row.day, source: "qoder", model: row.model || "unknown",
      project: row.project || "-", credits: credits,
      free_credits: number(row.free_credits), requests: number(row.requests),
      free_requests: number(row.free_requests), total: credits
    };
  });
  var QUOTA = CREDIT_DATA.quota || {};

  var EST_DATA = DATA.est || {};
  var EST = (Array.isArray(EST_DATA.rows) ? EST_DATA.rows : []).map(function (row) {
    var input = number(row.est_input);
    var output = number(row.est_output);
    return {
      day: row.day, source: "qoder", model: row.model || "unknown",
      project: row.project || "-", est_input: input, est_output: output,
      requests: number(row.requests), chars_in: number(row.chars_in),
      chars_out: number(row.chars_out), missing_ratio: number(row.missing_ratio),
      total: input + output
    };
  });
  var EST_FACTOR = EST_DATA.factor_version || "v1";

  var TRAE_DATA = DATA.trae_est || {};
  var TRAE_EST = (Array.isArray(TRAE_DATA.rows) ? TRAE_DATA.rows : []).map(function (row) {
    var input = number(row.est_input);
    var output = number(row.est_output);
    return {
      day: row.day, source: "trae-cn", model: row.model || "trae-cn",
      project: row.project || "-", est_input: input, est_output: output,
      requests: number(row.requests), chars_in: number(row.chars_in),
      chars_out: number(row.chars_out), total: input + output
    };
  });
  var TRAE_FACTOR = TRAE_DATA.factor_version || "trae-hook-v1";
  var TRAE_NOTE = "Trae CN 弱估算（hook 可见内容，不含系统提示/工具定义）";
  var COVERAGE = DATA.coverage || {};

  var present = {};
  TOKEN_ROWS.forEach(function (row) { present[row.source] = true; });
  if (CREDIT_ROWS.length || EST.length || ACTIVITY.length) present.qoder = true;
  if (TRAE_EST.length) present["trae-cn"] = true;
  var AGENTS = KNOWN_ORDER.filter(function (name) { return present[name]; })
    .concat(Object.keys(present).filter(function (name) {
      return KNOWN_ORDER.indexOf(name) < 0;
    }).sort());
  var TOKEN_AGENTS = AGENTS.filter(function (name) { return agentKind(name) === "token"; });
  var CREDIT_AGENTS = AGENTS.filter(function (name) { return agentKind(name) === "credits"; });
  var ESTIMATE_AGENTS = AGENTS.filter(function (name) { return agentKind(name) === "estimate"; });
  var COLORS = {};
  AGENTS.forEach(function (name, index) {
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

  function earliestDay(a, b) {
    if (!a) return b || "";
    if (!b) return a;
    return a < b ? a : b;
  }

  function latestDay(a, b) {
    if (!a) return b || "";
    if (!b) return a;
    return a > b ? a : b;
  }

  var tokenBounds = minMaxDay(TOKEN_ROWS);
  var qoderTokenBounds = minMaxDay(QODER_TOKEN_ROWS);
  var activityBounds = minMaxDay(ACTIVITY);
  var creditBounds = minMaxDay(CREDIT_ROWS);
  var estBounds = minMaxDay(EST);
  var traeEstBounds = minMaxDay(TRAE_EST);
  var RANGE = DATA.range || {};
  var DATA_SINCE = RANGE.since || earliestDay(
    earliestDay(tokenBounds[0], qoderTokenBounds[0]),
    earliestDay(earliestDay(activityBounds[0], creditBounds[0]),
                earliestDay(estBounds[0], traeEstBounds[0])));
  var DATA_UNTIL = RANGE.until || latestDay(
    latestDay(tokenBounds[1], qoderTokenBounds[1]),
    latestDay(latestDay(activityBounds[1], creditBounds[1]),
              latestDay(estBounds[1], traeEstBounds[1])));
  var TODAY = localToday();
  var PICK_MAX = DATA_UNTIL > TODAY ? DATA_UNTIL : TODAY;

  function allBounds() {
    if (!DATA_SINCE || !DATA_UNTIL) return { start: DATA_SINCE, end: DATA_UNTIL };
    return { start: DATA_SINCE, end: DATA_UNTIL };
  }

  function selectedTokenAgents() {
    return TOKEN_AGENTS.filter(function (name) { return state.agents.has(name); });
  }
  function hasTokenSelected() { return selectedTokenAgents().length > 0; }
  function hasCreditsSelected() {
    return CREDIT_AGENTS.some(function (name) { return state.agents.has(name); });
  }
  function hasEstimateSelected() {
    return ESTIMATE_AGENTS.some(function (name) { return state.agents.has(name); });
  }

  var initialRange = allBounds();
  var state = {
    agents: new Set(AGENTS),
    start: initialRange.start,
    end: initialRange.end,
    model: "",
    project: "",
    q: "",
    metric: "total",
    activityMetric: "tool_calls",
    shadow: false,
    sortKey: "day",
    sortDir: "desc",
    page: 0,
    pageSize: 50
  };

  var el = {
    start: $("#start"), end: $("#end"), presets: $("#presets"), reset: $("#reset"),
    model: $("#model"), project: $("#project"), q: $("#q"),
    nav: $("#agent-nav"), coverage: $("#coverage"),
    kpis: $("#kpis"), metricField: $("#metric-field"), metric: $("#metric"),
    shadowSwitch: $("#shadow-switch"), shadow: $("#shadow"),
    panelToken: $("#panel-token"), panelCredits: $("#panel-credits"), panelEst: $("#panel-est"),
    chartToken: $("#chart-token"), tooltipToken: $("#tooltip-token"),
    legendToken: $("#legend-token"), hintToken: $("#hint-token"),
    chartCredits: $("#chart-credits"), tooltipCredits: $("#tooltip-credits"),
    legendCredits: $("#legend-credits"), hintCredits: $("#hint-credits"),
    chartEst: $("#chart-est"), tooltipEst: $("#tooltip-est"),
    legendEst: $("#legend-est"), hintEst: $("#hint-est"),
    modelUnit: $("#model-unit"), projectUnit: $("#project-unit"),
    models: $("#models"), projects: $("#projects"),
    thead: $("#thead"), tbody: $("#tbody"), rowinfo: $("#rowinfo"),
    pageinfo: $("#pageinfo"), prev: $("#prev"), next: $("#next"),
    shadowNote: $("#shadow-note"),
    activityBlock: $("#activity-block"), activityKpis: $("#activity-kpis"),
    activityMetric: $("#activity-metric"), activityLegend: $("#activity-legend"),
    activityChart: $("#activity-chart"), activityTooltip: $("#activity-tooltip"),
    activityHint: $("#activity-hint"), activityThead: $("#activity-thead"),
    activityTbody: $("#activity-tbody"), activityRowinfo: $("#activity-rowinfo"),
    generated: $("#generated"), footer: $("#footer"), theme: $("#theme")
  };

  function fmtInt(value) { return numberFormat.format(Math.round(number(value))); }

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

  function fmtCredits(value) {
    var parsed = number(value);
    return Math.abs(parsed - Math.round(parsed)) < 0.005
      ? fmtInt(parsed) : parsed.toFixed(2);
  }

  function fmtQuota(value) {
    var parsed = number(value);
    return Math.abs(parsed - Math.round(parsed)) < 0.005 ? fmtInt(parsed) : parsed.toFixed(2);
  }

  function fmtDuration(ms) {
    var seconds = Math.round(number(ms) / 1000);
    if (seconds >= 3600) {
      var minutes = Math.round((seconds % 3600) / 60);
      return Math.floor(seconds / 3600) + "h " + pad2(minutes) + "m";
    }
    if (seconds >= 60) return Math.floor(seconds / 60) + "m " + pad2(seconds % 60) + "s";
    return seconds + "s";
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

  function groupTotals(rows, key) {
    var map = new Map();
    rows.forEach(function (row) {
      var name = row[key] || "-";
      if (!map.has(name)) map.set(name, { key: name, total: 0, turns: 0 });
      var entry = map.get(name);
      entry.total += number(row.total);
      entry.turns += number(row.turns);
    });
    return Array.from(map.values());
  }

  function byTotal(a, b) { return b.total - a.total; }

  function matchesQuery(row) {
    if (!state.q) return true;
    var haystack = (row.day + " " + row.source + " " + row.model + " " + row.project).toLowerCase();
    return haystack.indexOf(state.q) >= 0;
  }

  function matchesFilters(row, ignore) {
    if (state.start && row.day < state.start) return false;
    if (state.end && row.day > state.end) return false;
    if (ignore !== "model" && state.model && row.model !== state.model) return false;
    if (ignore !== "project" && state.project && row.project !== state.project) return false;
    return matchesQuery(row);
  }

  function tokenRowsFor(ignore) {
    return TOKEN_ROWS.filter(function (row) {
      return state.agents.has(row.source) && matchesFilters(row, ignore);
    });
  }

  function creditRowsFor(ignore) {
    if (!hasCreditsSelected()) return [];
    return CREDIT_ROWS.filter(function (row) { return matchesFilters(row, ignore); });
  }

  function qoderEstRowsFor(ignore) {
    if (!state.shadow || !hasCreditsSelected()) return [];
    return EST.filter(function (row) { return matchesFilters(row, ignore); });
  }

  function traeRowsFor(ignore) {
    if (!hasEstimateSelected()) return [];
    return TRAE_EST.filter(function (row) { return matchesFilters(row, ignore); });
  }

  function dimensionRows() {
    var rows = TOKEN_ROWS.filter(function (row) { return state.agents.has(row.source); });
    if (hasCreditsSelected()) {
      rows = rows.concat(CREDIT_ROWS.map(function (row) {
        return { day: row.day, source: "qoder", model: row.model,
                 project: row.project, total: row.credits, turns: 0 };
      }));
    }
    if (hasEstimateSelected()) rows = rows.concat(TRAE_EST);
    return rows;
  }

  function pageMetric(row) {
    if (state.metric === "total") return number(row.total);
    return number(row[state.metric]);
  }

  function navTotal(agent) {
    if (agent === "all") return sumField(TOKEN_ROWS, "total");
    var kind = agentKind(agent);
    if (kind === "credits") return sumField(CREDIT_ROWS, "credits");
    if (kind === "estimate") return sumField(TRAE_EST, "total");
    return TOKEN_ROWS.reduce(function (acc, row) {
      return acc + (row.source === agent ? number(row.total) : 0);
    }, 0);
  }

  function navTotalText(agent) {
    var value = navTotal(agent);
    var kind = agent === "all" ? "token" : agentKind(agent);
    if (kind === "credits") return fmtCompact(value) + " cr";
    if (kind === "estimate") return fmtCompact(value) + " est";
    return fmtCompact(value);
  }

  function addKpiTo(host, label, value, sub, primary, className) {
    var card = document.createElement("div");
    card.className = "kpi" + (primary ? " primary" : "") + (className ? " " + className : "");
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
    host.appendChild(card);
  }

  function resolveAgentSelection(current, agent, additive) {
    if (additive) {
      var next = current.slice();
      var index = next.indexOf(agent);
      if (index >= 0) {
        if (next.length === 1) return next;
        next.splice(index, 1);
      } else {
        next.push(agent);
      }
      return next;
    }
    if (current.length === 1 && current[0] === agent) return AGENTS.slice();
    return [agent];
  }

  function applyAgentSelection(names) {
    state.agents = new Set(names);
    state.model = "";
    state.project = "";
    state.page = 0;
    rebuildDimensionSelects();
    syncAgentFilter();
    renderAll();
  }

  function buildAgentFilter() {
    el.nav.textContent = "";
    var label = document.createElement("span");
    label.className = "agent-nav-label";
    label.textContent = "Agent";
    el.nav.appendChild(label);
    AGENTS.forEach(function (agent) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "chip";
      button.dataset.agent = agent;
      button.title = agent + " · " + KIND_LABELS[agentKind(agent)] +
        "，单击只看，再次单击恢复全部；⌘/Ctrl/Shift+单击多选";
      var dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = COLORS[agent];
      var name = document.createElement("span");
      name.textContent = agent;
      var total = document.createElement("small");
      total.textContent = navTotalText(agent);
      button.appendChild(dot);
      button.appendChild(name);
      button.appendChild(total);
      button.addEventListener("click", function (event) {
        var additive = event.metaKey || event.ctrlKey || event.shiftKey;
        applyAgentSelection(resolveAgentSelection(Array.from(state.agents), agent, additive));
      });
      el.nav.appendChild(button);
    });
    var all = document.createElement("button");
    all.type = "button";
    all.className = "btn ghost small";
    all.textContent = "全选";
    all.addEventListener("click", function () { applyAgentSelection(AGENTS.slice()); });
    el.nav.appendChild(all);
    var tip = document.createElement("span");
    tip.className = "chip-tip";
    tip.textContent = navigator.platform.indexOf("Mac") >= 0
      ? "单击只看 · ⌘+单击多选；tokens/credits/est 分别汇总"
      : "单击只看 · Ctrl+单击多选；tokens/credits/est 分别汇总";
    el.nav.appendChild(tip);
    syncAgentFilter();
  }

  function syncAgentFilter() {
    Array.prototype.forEach.call(el.nav.querySelectorAll("[data-agent]"), function (button) {
      var active = state.agents.has(button.dataset.agent);
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

  function rebuildDimensionSelects() {
    var rows = dimensionRows();
    var models = groupTotals(rows, "model").sort(byTotal);
    var projects = groupTotals(rows, "project").sort(byTotal);
    fillSelect(el.model, models, "全部模型", function (key) { return key; });
    fillSelect(el.project, projects, "全部项目", function (key) {
      return key === "-" ? "（未标注）" : key;
    });
    if (!models.some(function (item) { return item.key === state.model; })) state.model = "";
    if (!projects.some(function (item) { return item.key === state.project; })) state.project = "";
    el.model.value = state.model;
    el.project.value = state.project;
  }

  function syncDateInputs() {
    el.start.value = state.start || "";
    el.end.value = state.end || "";
  }

  function buildControls() {
    el.start.min = DATA_SINCE || "";
    el.start.max = PICK_MAX;
    el.end.min = DATA_SINCE || "";
    el.end.max = PICK_MAX;
    syncDateInputs();

    [{ label: "今日", kind: "today" }, { label: "全部", kind: "all" },
     { label: "近 7 天", days: 7 },
     { label: "近 30 天", days: 30 }, { label: "近 90 天", days: 90 }].forEach(function (preset) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn ghost small";
      button.textContent = preset.label;
      button.addEventListener("click", function () {
        var bounds = allBounds();
        var end = preset.kind === "all" ? (bounds.end || DATA_UNTIL) : TODAY;
        var start = preset.kind === "today" ? TODAY
                  : preset.kind === "all" ? (bounds.start || DATA_SINCE)
                  : addDays(end, -(preset.days - 1));
        var minDay = bounds.start || DATA_SINCE;
        if (start < minDay) start = minDay;
        state.start = start;
        state.end = end;
        syncDateInputs();
        state.page = 0;
        renderAll();
      });
      el.presets.appendChild(button);
    });

    el.start.addEventListener("change", onDateChange);
    el.end.addEventListener("change", onDateChange);
    el.model.addEventListener("change", function () {
      state.model = el.model.value;
      state.page = 0;
      renderAll();
    });
    el.project.addEventListener("change", function () {
      state.project = el.project.value;
      state.page = 0;
      renderAll();
    });

    var searchTimer;
    el.q.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.q = el.q.value.trim().toLowerCase();
        state.page = 0;
        renderAll();
      }, 120);
    });

    el.metric.addEventListener("change", function () {
      state.metric = el.metric.value;
      renderAll();
    });
    el.shadow.addEventListener("change", function () {
      state.shadow = el.shadow.checked;
      state.page = 0;
      renderAll();
    });
    el.activityMetric.addEventListener("change", function () {
      state.activityMetric = el.activityMetric.value;
      renderActivity();
    });
    el.activityBlock.addEventListener("toggle", function () {
      if (el.activityBlock.open) renderActivity();
    });

    el.reset.addEventListener("click", resetFilters);
    el.prev.addEventListener("click", function () {
      if (state.page > 0) { state.page -= 1; renderAll(); }
    });
    el.next.addEventListener("click", function () { state.page += 1; renderAll(); });
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
    renderAll();
  }

  function resetFilters() {
    var range = allBounds();
    state.agents = new Set(AGENTS);
    state.start = range.start;
    state.end = range.end;
    state.model = "";
    state.project = "";
    state.q = "";
    state.metric = "total";
    state.shadow = false;
    state.sortKey = "day";
    state.sortDir = "desc";
    state.page = 0;
    syncDateInputs();
    el.model.value = "";
    el.project.value = "";
    el.q.value = "";
    el.metric.value = "total";
    el.shadow.checked = false;
    syncAgentFilter();
    rebuildDimensionSelects();
    renderAll();
  }

  function syncShell() {
    var units = [];
    if (hasTokenSelected()) units.push("tokens");
    if (hasCreditsSelected()) units.push(state.shadow ? "credits + 影子 est" : "credits");
    if (hasEstimateSelected()) units.push("trae 弱 est");
    el.panelToken.hidden = !hasTokenSelected();
    el.panelCredits.hidden = !hasCreditsSelected();
    el.panelEst.hidden = !hasEstimateSelected();
    el.metricField.hidden = !hasTokenSelected();
    el.shadowSwitch.hidden = !hasCreditsSelected() || !EST.length;
    el.shadow.checked = state.shadow;
    el.metric.value = state.metric;
    el.modelUnit.textContent = units.join(" / ");
    el.projectUnit.textContent = units.join(" / ");
    el.activityBlock.hidden = !hasCreditsSelected() || !ACTIVITY.length;
    if (!hasCreditsSelected()) {
      state.shadow = false;
      el.shadow.checked = false;
      el.shadowNote.hidden = true;
    }
  }

  function renderCoverage() {
    var parts = [];
    var qoder = COVERAGE.qoder || {};
    var qoderToken = qoderTokenBounds[0]
      ? qoderTokenBounds[0] + " ~ " + qoderTokenBounds[1] : "";
    parts.push("已选 Agent：" + Array.from(state.agents).join(" / "));
    var unitNames = [];
    if (hasTokenSelected()) unitNames.push("tokens");
    if (hasCreditsSelected()) unitNames.push("credits");
    if (hasEstimateSelected()) unitNames.push("est");
    if (unitNames.length > 1) {
      parts.push(unitNames.join("、") + " 单位不同，分别汇总，不跨单位相加");
    }
    if (hasCreditsSelected()) {
      if (creditBounds[0]) parts.push("credits " + creditBounds[0] + " ~ " + creditBounds[1]);
      else parts.push("本地无 credits 数据");
      if (estBounds[0]) parts.push("Qoder 影子估算 " + estBounds[0] + " ~ " + estBounds[1]);
      if (ACTIVITY.length) {
        var actBounds = minMaxDay(ACTIVITY);
        parts.push("活动 " + actBounds[0] + " ~ " + actBounds[1]);
      }
    }
    if (hasEstimateSelected() && traeEstBounds[0]) {
      parts.push("Trae CN 弱估算 " + traeEstBounds[0] + " ~ " + traeEstBounds[1] +
        "（仅覆盖安装 hook 后的请求）");
    }
    if (qoderToken && hasCreditsSelected()) {
      parts.push("Qoder 历史 token 真值 " + qoderToken + "，未并入本页");
    }
    if (hasEstimateSelected() || state.shadow) {
      parts.push("估算不与 token 真值或 credits 相加");
    }
    el.coverage.textContent = parts.join("；");
    el.coverage.hidden = false;
  }

  function emptyActivityTotals() {
    var totals = {};
    ACTIVITY_FIELDS.forEach(function (field) { totals[field] = 0; });
    return totals;
  }

  function renderTokenKpis(host, rows) {
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

    addKpiTo(host, "总 Token", fmtCompact(total), fmtInt(total), true);
    FIELDS.forEach(function (field) {
      addKpiTo(host, FIELD_LABELS[field], fmtCompact(sums[field]), fmtInt(sums[field]));
    });
    addKpiTo(host, "缓存占比", total ? pct(sums.cache_read / total) : "—", "cache_read / 总量");
    addKpiTo(host, "轮次", fmtCompact(turns), fmtInt(turns));
    if (costKnown) addKpiTo(host, "等价成本", "$" + cost.toFixed(2), "按 API 价折算，非实付");
  }

  function quotaSummary() {
    var addOn = QUOTA.add_on;
    if (addOn && (number(addOn.total) > 0 || number(addOn.remaining) > 0)) return addOn;
    var user = QUOTA.user;
    if (user && (number(user.total) > 0 || number(user.remaining) > 0)) return user;
    return null;
  }

  function addQuotaKpi(host, quota) {
    var card = document.createElement("div");
    card.className = "kpi primary quota-kpi";
    var label = document.createElement("div");
    label.className = "kpi-label";
    label.textContent = "最新额度余额";
    var value = document.createElement("div");
    value.className = "kpi-value";
    var sub = document.createElement("div");
    sub.className = "kpi-sub";
    card.appendChild(label);
    card.appendChild(value);
    card.appendChild(sub);
    if (quota) {
      var total = number(quota.total);
      var used = number(quota.used);
      var remaining = number(quota.remaining);
      var ratio = typeof quota.pct === "number" && quota.pct >= 0
        ? quota.pct : (total > 0 ? used / total : 0);
      value.textContent = fmtQuota(remaining) + " credits";
      sub.textContent = "used " + fmtQuota(used) + " / " + fmtQuota(total) +
        " · 已用 " + pct(ratio) + " · 快照 " + (quota.day || "—");
      value.title = sub.textContent;
      var track = document.createElement("div");
      track.className = "quota-track";
      track.setAttribute("role", "progressbar");
      track.setAttribute("aria-label", "Qoder 额度已用比例");
      track.setAttribute("aria-valuemin", "0");
      track.setAttribute("aria-valuemax", "100");
      track.setAttribute("aria-valuenow", String(Math.round(Math.max(0, Math.min(1, ratio)) * 100)));
      var fill = document.createElement("div");
      fill.className = "quota-fill" + (ratio >= 0.8 ? " warn" : "");
      fill.style.width = Math.max(0, Math.min(100, ratio * 100)) + "%";
      track.appendChild(fill);
      card.appendChild(track);
    } else {
      value.textContent = "—";
      sub.textContent = "本地日志无额度快照";
    }
    host.appendChild(card);
  }

  function renderCreditKpis(host, rows) {
    var billable = 0;
    var free = 0;
    var requests = 0;
    var freeRequests = 0;
    var days = {};
    rows.forEach(function (row) {
      billable += row.credits;
      free += row.free_credits;
      requests += row.requests;
      freeRequests += row.free_requests;
      days[row.day] = true;
    });
    var dayCount = Object.keys(days).length;
    addQuotaKpi(host, quotaSummary());
    addKpiTo(host, "区间 billable credits", fmtCredits(billable),
      fmtInt(requests) + " billable 请求 · 服务端计费真值");
    addKpiTo(host, "免费 credits", fmtCredits(free), fmtInt(freeRequests) + " 免费请求");
    addKpiTo(host, "区间日均", fmtCredits(dayCount ? billable / dayCount : 0),
      fmtInt(dayCount) + " 天有数据");
    if (state.shadow) {
      var estRows = qoderEstRowsFor();
      addKpiTo(host, "影子 est Token",
        fmtCompact(sumField(estRows, "total")),
        fmtInt(sumField(estRows, "requests")) + " 请求 · 不可与 credits 相加",
        false, "shadow");
    }
  }

  function renderEstimateKpis(host, rows, label) {
    var input = sumField(rows, "est_input");
    var output = sumField(rows, "est_output");
    var requests = sumField(rows, "requests");
    var days = {};
    var models = {};
    rows.forEach(function (row) {
      days[row.day] = true;
      models[row.model] = true;
    });
    addKpiTo(host, "est 总 Token", fmtCompact(input + output), fmtInt(input + output), true);
    addKpiTo(host, "est 输入", fmtCompact(input),
      label === "trae-cn" ? "hook 上下文累积字符 ÷ 系数"
        : "context_usage_ratio × 200K");
    addKpiTo(host, "est 输出", fmtCompact(output),
      label === "trae-cn" ? "输出字符 ÷ 系数" : "字符数 ÷ 模型系数");
    addKpiTo(host, "覆盖请求", fmtCompact(requests),
      fmtInt(Object.keys(days).length) + " 天 · " + fmtInt(Object.keys(models).length) + " 模型");
  }

  function addKpiSection(host, text) {
    var node = document.createElement("div");
    node.className = "kpi-section";
    node.textContent = text;
    host.appendChild(node);
  }

  function renderKpis() {
    var host = el.kpis;
    host.textContent = "";
    var groups = [hasTokenSelected(), hasCreditsSelected(), hasEstimateSelected()]
      .filter(Boolean).length;
    if (hasTokenSelected()) {
      if (groups > 1) addKpiSection(host, "精确 Token（tokens）");
      renderTokenKpis(host, tokenRowsFor());
    }
    if (hasCreditsSelected()) {
      if (groups > 1) addKpiSection(host, "精确 Credits（credits）");
      renderCreditKpis(host, creditRowsFor());
    }
    if (hasEstimateSelected()) {
      if (groups > 1) addKpiSection(host, "仅估算（est tokens，不可相加）");
      renderEstimateKpis(host, traeRowsFor(), "trae-cn");
    }
  }

  function buildStackBuckets(rows, seriesDefs, shadowDefs, shadowRows) {
    var days = enumerateDays(state.start, state.end);
    if (!days.length) return [];
    var weekly = days.length > 200;
    var buckets = [];
    var index = new Map();
    days.forEach(function (day) {
      var key = weekly ? weekStart(day) : day;
      if (!index.has(key)) {
        var bucket = { key: key, start: day, end: day };
        index.set(key, bucket);
        buckets.push(bucket);
      } else {
        index.get(key).end = day;
      }
    });
    buckets.forEach(function (bucket) {
      bucket.label = weekly ? bucket.start.slice(5) : bucket.start.slice(5);
      bucket.tooltip = weekly ? bucket.start + " ~ " + bucket.end : bucket.start;
      bucket.values = seriesDefs.map(function () { return 0; });
      bucket.shadowValue = 0;
    });
    rows.forEach(function (row) {
      var key = weekly ? weekStart(row.day) : row.day;
      var bucket = index.get(key);
      if (!bucket) return;
      seriesDefs.forEach(function (def, i) {
        bucket.values[i] += number(def.value(row));
      });
    });
    (shadowDefs || []).forEach(function (def) {
      (shadowRows || rows).forEach(function (row) {
        var key = weekly ? weekStart(row.day) : row.day;
        var bucket = index.get(key);
        if (bucket) bucket.shadowValue += number(def.value(row));
      });
    });
    buckets.forEach(function (bucket) {
      bucket.total = bucket.values.reduce(function (acc, value) { return acc + value; }, 0);
    });
    return buckets;
  }

  function renderStackChart(config) {
    var host = config.host;
    var tooltip = config.tooltip;
    var legend = config.legend;
    host.textContent = "";
    legend.textContent = "";
    tooltip.style.display = "none";
    var buckets = config.buckets;
    if (!buckets.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "所选范围内没有数据";
      host.appendChild(empty);
      return;
    }
    var series = config.series;
    var shadowLabel = config.shadowLabel || "";
    var hasShadow = !!shadowLabel;
    var width = Math.max(host.clientWidth || 900, 320);
    var height = 300;
    var margin = { top: 14, right: hasShadow ? 66 : 14, bottom: 28, left: 62 };
    var plotW = Math.max(width - margin.left - margin.right, 10);
    var plotH = height - margin.top - margin.bottom;
    var maximum = buckets.reduce(function (acc, bucket) {
      return Math.max(acc, bucket.total);
    }, 0);
    var scale = niceScale(maximum, 4);
    var shadowScale = hasShadow ? niceScale(buckets.reduce(function (acc, bucket) {
      return Math.max(acc, bucket.shadowValue);
    }, 0), 4) : null;
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": config.ariaLabel || "每日用量"
    });

    scale.ticks.forEach(function (value) {
      var y = margin.top + plotH - (value / scale.max) * plotH;
      svg.appendChild(svgEl("line", {
        x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "grid-line"
      }));
      var text = svgEl("text", {
        x: margin.left - 8, y: y + 3.5, "text-anchor": "end"
      });
      text.textContent = fmtCompact(value);
      svg.appendChild(text);
    });
    if (shadowScale) {
      var rightGroup = svgEl("g", { class: "axis-right" });
      shadowScale.ticks.forEach(function (value) {
        var y = margin.top + plotH - (value / shadowScale.max) * plotH;
        var text = svgEl("text", {
          x: width - margin.right + 8, y: y + 3.5, "text-anchor": "start"
        });
        text.textContent = fmtCompact(value);
        rightGroup.appendChild(text);
      });
      svg.appendChild(rightGroup);
    }

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
      series.forEach(function (def, i) {
        var value = bucket.values[i] || 0;
        if (value <= 0) return;
        var slice = (value / scale.max) * plotH;
        y -= slice;
        svg.appendChild(svgEl("rect", {
          x: x, y: y, width: barW, height: slice,
          fill: def.color, class: "seg", rx: barW > 4 ? 1.5 : 0
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
        tooltip.style.display = "none";
      });
      svg.appendChild(hit);
    });

    if (shadowScale) {
      var points = [];
      buckets.forEach(function (bucket, index) {
        var x = margin.left + band * index + band / 2;
        var value = bucket.shadowValue;
        var y = margin.top + plotH - (value / shadowScale.max) * plotH;
        points.push([x, y]);
        svg.appendChild(svgEl("circle", {
          cx: x, cy: y, r: 2.4, class: "shadow-dot"
        }));
      });
      if (points.length > 1) {
        svg.appendChild(svgEl("polyline", {
          points: points.map(function (p) { return p[0] + "," + p[1]; }).join(" "),
          class: "shadow-line"
        }));
      }
    }
    svg.appendChild(hoverLine);

    var labelCount = Math.min(buckets.length, Math.max(2, Math.floor(plotW / 90)));
    var step = labelCount <= 1 ? 1 : (buckets.length - 1) / (labelCount - 1);
    var used = new Set();
    for (var k = 0; k < labelCount; k += 1) {
      var idx = Math.round(k * step);
      if (used.has(idx)) continue;
      used.add(idx);
      var label = svgEl("text", {
        x: margin.left + band * idx + band / 2,
        y: height - 8,
        "text-anchor": "middle"
      });
      label.textContent = buckets[idx].label;
      svg.appendChild(label);
    }
    host.appendChild(svg);

    var legendFmt = config.legendFormat || fmtCompact;
    series.forEach(function (def, i) {
      var total = buckets.reduce(function (acc, bucket) {
        return acc + (bucket.values[i] || 0);
      }, 0);
      var item = document.createElement("span");
      item.className = "legend-item";
      var dot = document.createElement("i");
      dot.className = "legend-dot";
      dot.style.background = def.color;
      var name = document.createElement("span");
      name.textContent = def.label;
      var amount = document.createElement("b");
      amount.textContent = legendFmt(total);
      item.appendChild(dot);
      item.appendChild(name);
      item.appendChild(amount);
      legend.appendChild(item);
    });
    if (shadowScale) {
      var shadowItem = document.createElement("span");
      shadowItem.className = "legend-item";
      var dash = document.createElement("i");
      dash.className = "legend-line";
      var shadowName = document.createElement("span");
      shadowName.textContent = shadowLabel + "（右轴）";
      var shadowAmount = document.createElement("b");
      shadowAmount.textContent = fmtCompact(buckets.reduce(function (acc, bucket) {
        return acc + bucket.shadowValue;
      }, 0));
      shadowItem.appendChild(dash);
      shadowItem.appendChild(shadowName);
      shadowItem.appendChild(shadowAmount);
      legend.appendChild(shadowItem);
    }

    if (config.hint) config.hint.textContent = "";

    function showTooltip(bucket, event) {
      tooltip.textContent = "";
      var head = document.createElement("div");
      head.className = "tt-head";
      head.textContent = bucket.tooltip;
      tooltip.appendChild(head);
      if (config.metaText) {
        var meta = document.createElement("div");
        meta.className = "tt-meta";
        meta.textContent = config.metaText;
        tooltip.appendChild(meta);
      }
      series.forEach(function (def, i) {
        var row = document.createElement("div");
        row.className = "tt-row";
        var name = document.createElement("span");
        name.className = "tt-name";
        var dot = document.createElement("i");
        dot.style.background = def.color;
        name.appendChild(dot);
        name.appendChild(document.createTextNode(def.label));
        var value = document.createElement("span");
        value.className = "tt-val";
        value.textContent = (config.tooltipFormat || fmtInt)(bucket.values[i] || 0);
        row.appendChild(name);
        row.appendChild(value);
        tooltip.appendChild(row);
      });
      var totalRow = document.createElement("div");
      totalRow.className = "tt-row tt-total";
      var totalName = document.createElement("span");
      totalName.className = "tt-name";
      totalName.textContent = "合计";
      var totalValue = document.createElement("span");
      totalValue.className = "tt-val";
      totalValue.textContent = (config.tooltipFormat || fmtInt)(bucket.total);
      totalRow.appendChild(totalName);
      totalRow.appendChild(totalValue);
      tooltip.appendChild(totalRow);
      if (shadowScale) {
        var shadowRow = document.createElement("div");
        shadowRow.className = "tt-row tt-shadow";
        var shadowName = document.createElement("span");
        shadowName.className = "tt-name";
        var dash = document.createElement("i");
        dash.className = "dash";
        shadowName.appendChild(dash);
        shadowName.appendChild(document.createTextNode("影子：" + shadowLabel));
        var shadowValue = document.createElement("span");
        shadowValue.className = "tt-val";
        shadowValue.textContent = fmtInt(bucket.shadowValue);
        shadowRow.appendChild(shadowName);
        shadowRow.appendChild(shadowValue);
        tooltip.appendChild(shadowRow);
      }
      if (config.extraTooltip) {
        config.extraTooltip(tooltip, bucket);
      }
      tooltip.style.display = "block";
      positionTooltip(event);
    }

    function positionTooltip(event) {
      var rect = host.parentElement.getBoundingClientRect();
      var x = event.clientX - rect.left;
      var half = 110;
      x = Math.max(half, Math.min(x, rect.width - half));
      tooltip.style.left = x + "px";
    }
  }

  function renderCharts() {
    if (hasTokenSelected()) {
      var tokenAgents = selectedTokenAgents();
      var tokenRows = tokenRowsFor();
      var tokenBuckets = buildStackBuckets(tokenRows, tokenAgents.map(function (source) {
        return {
          label: source, color: COLORS[source],
          value: function (row) { return row.source === source ? pageMetric(row) : 0; }
        };
      }));
      renderStackChart({
        host: el.chartToken, tooltip: el.tooltipToken, legend: el.legendToken,
        buckets: tokenBuckets,
        series: tokenAgents.map(function (source) {
          return { label: source, color: COLORS[source] };
        }),
        metaText: "指标：" + (state.metric === "total" ? "总量" : FIELD_LABELS[state.metric]),
        ariaLabel: "按 Agent 堆叠的每日 token 用量",
        tooltipFormat: fmtInt
      });
      renderMissingHint(el.hintToken, tokenRows);
    }
    if (hasCreditsSelected()) {
      var creditRows = creditRowsFor();
      var creditDefs = [
        { label: "billable（计入配额）", color: CREDIT_BILLABLE_COLOR,
          value: function (row) { return row.credits; } },
        { label: "免费（不计配额）", color: CREDIT_FREE_COLOR,
          value: function (row) { return row.free_credits; } }
      ];
      var shadowRows = state.shadow ? qoderEstRowsFor() : null;
      var creditBuckets = buildStackBuckets(creditRows, creditDefs,
        state.shadow ? [{ value: function (row) { return row.total; } }] : [],
        shadowRows);
      renderStackChart({
        host: el.chartCredits, tooltip: el.tooltipCredits, legend: el.legendCredits,
        buckets: creditBuckets,
        series: creditDefs,
        shadowLabel: state.shadow ? "Qoder est" : "",
        metaText: "Qoder credits 为服务端计费真值，非 token",
        ariaLabel: "Qoder 每日 credits 用量",
        legendFormat: fmtCredits,
        tooltipFormat: fmtCredits
      });
      renderMissingHint(el.hintCredits, creditRows.concat(shadowRows || []));
    }
    if (hasEstimateSelected()) {
      var traeRows = traeRowsFor();
      var estDefs = [
        { label: "est 输入", color: EST_INPUT_COLOR,
          value: function (row) { return row.est_input; } },
        { label: "est 输出", color: EST_OUTPUT_COLOR,
          value: function (row) { return row.est_output; } }
      ];
      var estBuckets = buildStackBuckets(traeRows, estDefs);
      renderStackChart({
        host: el.chartEst, tooltip: el.tooltipEst, legend: el.legendEst,
        buckets: estBuckets,
        series: estDefs,
        metaText: TRAE_NOTE + " · 非 token 真值",
        ariaLabel: "Trae CN 每日弱估算 token",
        tooltipFormat: fmtInt
      });
      renderMissingHint(el.hintEst, traeRows);
    }
  }

  function renderMissingHint(hintEl, rows) {
    if (!state.start || !state.end) {
      hintEl.textContent = "";
      return;
    }
    var seen = {};
    rows.forEach(function (row) { seen[row.day] = true; });
    var days = enumerateDays(state.start, state.end);
    var missing = days.filter(function (day) { return !seen[day]; });
    if (!missing.length) {
      hintEl.textContent = "";
      return;
    }
    var shown = missing.slice(0, 10).join("、");
    hintEl.textContent = "范围内 " + missing.length + " 天无对应数据（图表按 0 显示）：" +
      shown + (missing.length > 10 ? " …" : "");
  }

  function aggregateTop(key, ignore) {
    var map = new Map();
    function entry(name) {
      if (!map.has(name)) {
        map.set(name, { key: name, tokens: 0, turns: 0, credits: 0,
                        creditRequests: 0, est: 0, estRequests: 0,
                        shadowEst: 0, shadowRequests: 0 });
      }
      return map.get(name);
    }
    tokenRowsFor(ignore).forEach(function (row) {
      var item = entry(row[key] || "-");
      item.tokens += pageMetric(row);
      item.turns += number(row.turns);
    });
    creditRowsFor(ignore).forEach(function (row) {
      var item = entry(row[key] || "-");
      item.credits += row.credits;
      item.creditRequests += row.requests;
    });
    traeRowsFor(ignore).forEach(function (row) {
      var item = entry(row[key] || "-");
      item.est += row.total;
      item.estRequests += row.requests;
    });
    qoderEstRowsFor(ignore).forEach(function (row) {
      var item = entry(row[key] || "-");
      item.shadowEst += row.total;
      item.shadowRequests += row.requests;
    });
    return Array.from(map.values());
  }

  function primaryUnit() {
    if (hasTokenSelected()) return "tokens";
    if (hasCreditsSelected()) return "credits";
    return "est";
  }

  function primaryGrandTotal(unit) {
    if (unit === "tokens") {
      return tokenRowsFor().reduce(function (acc, row) { return acc + pageMetric(row); }, 0);
    }
    if (unit === "credits") {
      return creditRowsFor().reduce(function (acc, row) { return acc + row.credits; }, 0);
    }
    return traeRowsFor().reduce(function (acc, row) {
      return acc + row.total;
    }, 0);
  }

  function topValue(item, unit) {
    if (unit === "tokens") return item.tokens;
    if (unit === "credits") return item.credits;
    return item.est;
  }

  function topValueText(item, unit) {
    if (unit === "tokens") return fmtCompact(item.tokens) + " tokens";
    if (unit === "credits") return fmtCredits(item.credits) + " credits";
    return fmtCompact(item.est) + " est";
  }

  function topSecondary(item, unit) {
    var parts = [];
    if (unit !== "tokens" && item.tokens > 0) {
      parts.push(fmtCompact(item.tokens) + " tokens");
    }
    if (unit !== "credits" && item.credits > 0) {
      parts.push(fmtCredits(item.credits) + " credits · " +
        fmtInt(item.creditRequests) + " 请求");
    }
    if (unit !== "est" && item.est > 0) {
      parts.push("trae 弱 est " + fmtCompact(item.est) + "（不可相加）");
    }
    if (item.shadowEst > 0) {
      parts.push("影子 est " + fmtCompact(item.shadowEst) + "（不可相加）");
    }
    return parts.join(" · ");
  }

  function renderTopList(host, items, grandTotal, unit, selected, onPick) {
    host.textContent = "";
    if (!items.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "无数据";
      host.appendChild(empty);
      return;
    }
    var maximum = Math.max(topValue(items[0], unit), 1);
    items.forEach(function (item) {
      var value = topValue(item, unit);
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
      var amount = document.createElement("span");
      amount.className = "bar-value";
      amount.textContent = topValueText(item, unit) + " · " +
        pct(grandTotal ? value / grandTotal : 0);
      top.appendChild(name);
      top.appendChild(amount);
      button.appendChild(top);
      var secondary = topSecondary(item, unit);
      if (secondary) {
        var sub = document.createElement("div");
        sub.className = "bar-shadow";
        sub.textContent = secondary;
        button.appendChild(sub);
      }
      var track = document.createElement("div");
      track.className = "bar-track";
      var fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = value > 0
        ? Math.max(value / maximum * 100, 1.5).toFixed(1) + "%" : "0%";
      track.appendChild(fill);
      button.appendChild(track);
      button.title = "筛选：" + item.key;
      button.addEventListener("click", function () { onPick(item.key); });
      host.appendChild(button);
    });
  }

  function renderTopLists() {
    var unit = primaryUnit();
    var total = primaryGrandTotal(unit);
    var tag = unit === "tokens" ? "tokens" : unit === "credits" ? "credits" : "trae 弱 est";
    if (activeUnits().size > 1) tag = "主单位 " + tag;
    el.modelUnit.textContent = tag;
    el.projectUnit.textContent = tag;
    var modelItems = aggregateTop("model").sort(function (a, b) {
      return topValue(b, unit) - topValue(a, unit);
    }).slice(0, 8);
    var projectItems = aggregateTop("project").sort(function (a, b) {
      return topValue(b, unit) - topValue(a, unit);
    }).slice(0, 8);
    renderTopList(el.models, modelItems, total, unit, state.model, function (key) {
      state.model = state.model === key ? "" : key;
      el.model.value = state.model;
      state.page = 0;
      renderAll();
    });
    renderTopList(el.projects, projectItems, total, unit, state.project, function (key) {
      state.project = state.project === key ? "" : key;
      el.project.value = state.project;
      state.page = 0;
      renderAll();
    });
  }

  function columnFmt(column, value) {
    if (column.fmt) return column.fmt(value);
    return fmtInt(value);
  }

  function renderDataTable(config) {
    var columns = config.columns;
    var rows = config.rows;
    var numericKeys = {};
    columns.forEach(function (column) {
      if (column.type === "num") numericKeys[column.key] = true;
    });
    if (!columns.some(function (column) { return column.key === state.sortKey; })) {
      state.sortKey = "day";
      state.sortDir = "desc";
    }
    var sorted = rows.slice().sort(function (a, b) {
      var av = a[state.sortKey];
      var bv = b[state.sortKey];
      var aNull = av === null || av === undefined || av === "";
      var bNull = bv === null || bv === undefined || bv === "";
      if (aNull || bNull) {
        if (aNull && bNull) return 0;
        return aNull ? 1 : -1;
      }
      var cmp;
      if (numericKeys[state.sortKey]) cmp = number(av) - number(bv);
      else cmp = String(av).localeCompare(String(bv), "zh-CN");
      if (cmp === 0 && state.sortKey !== "day") {
        cmp = String(a.unitLabel || "").localeCompare(String(b.unitLabel || ""), "zh-CN");
      }
      return state.sortDir === "asc" ? cmp : -cmp;
    });
    var pages = Math.max(1, Math.ceil(sorted.length / state.pageSize));
    if (state.page >= pages) state.page = pages - 1;
    if (state.page < 0) state.page = 0;
    var start = state.page * state.pageSize;
    var slice = sorted.slice(start, start + state.pageSize);

    var focusedKey = null;
    if (document.activeElement && document.activeElement.classList.contains("th-btn")) {
      focusedKey = document.activeElement.dataset.key;
    }

    config.thead.textContent = "";
    var headerRow = document.createElement("tr");
    columns.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      if (column.shadow) th.classList.add("shadow-col");
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
        renderAll();
      });
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    config.thead.appendChild(headerRow);

    if (focusedKey) {
      var restored = config.thead.querySelector('.th-btn[data-key="' + focusedKey + '"]');
      if (restored) restored.focus({ preventScroll: true });
    }

    config.tbody.textContent = "";
    if (!slice.length) {
      var emptyRow = document.createElement("tr");
      var cell = document.createElement("td");
      cell.colSpan = columns.length;
      cell.className = "muted";
      cell.style.padding = "24px 10px";
      cell.style.textAlign = "center";
      cell.textContent = config.emptyText || "无匹配数据";
      emptyRow.appendChild(cell);
      config.tbody.appendChild(emptyRow);
    } else {
      slice.forEach(function (row) {
        var tr = document.createElement("tr");
        columns.forEach(function (column) {
          var td = document.createElement("td");
          var value = row[column.key];
          if (column.type === "num") td.className = "num";
          if (column.shadow) td.classList.add("shadow-col");
          if (column.unit && row.unit !== column.unit) {
            td.textContent = "—";
            td.classList.add("zero");
          } else if (column.key === "project") {
            td.textContent = value === "-" ? "（未标注）" : value;
            td.title = value;
          } else if (column.key === "model") {
            td.textContent = value;
            td.title = value;
          } else if (column.key === "cost_equiv_usd") {
            td.textContent = fmtCost(value);
          } else if (column.type === "num") {
            td.textContent = columnFmt(column, value);
            if (!number(value)) td.classList.add("zero");
          } else {
            td.textContent = value;
          }
          tr.appendChild(td);
        });
        config.tbody.appendChild(tr);
      });
    }

    config.rowinfo.textContent = config.info(sorted);
    config.pageinfo.textContent = slice.length
      ? (start + 1) + "–" + (start + slice.length) + " / " + fmtInt(sorted.length)
      : "0 / 0";
    config.prev.disabled = state.page <= 0;
    config.next.disabled = state.page >= pages - 1;
  }

  var COST_KNOWN = ROWS.some(function (row) {
    return row.cost_equiv_usd !== null && row.cost_equiv_usd !== undefined;
  });

  function estimateRows() {
    var rows = [];
    traeRowsFor().forEach(function (row) {
      rows.push({
        day: row.day, source: "trae-cn", model: row.model, project: row.project,
        unit: "est", unitLabel: "trae-cn 弱估算",
        est_input: row.est_input, est_output: row.est_output,
        est_total: row.total, est_requests: row.requests
      });
    });
    qoderEstRowsFor().forEach(function (row) {
      rows.push({
        day: row.day, source: "qoder", model: row.model, project: row.project,
        unit: "est", unitLabel: "qoder 影子 est",
        est_input: row.est_input, est_output: row.est_output,
        est_total: row.total, est_requests: row.requests
      });
    });
    return rows;
  }

  function reportRows() {
    var rows = tokenRowsFor().map(function (row) {
      var copy = {};
      Object.keys(row).forEach(function (key) { copy[key] = row[key]; });
      copy.unit = "token";
      copy.unitLabel = "tokens";
      return copy;
    });
    creditRowsFor().forEach(function (row) {
      rows.push({
        day: row.day, source: "qoder", model: row.model, project: row.project,
        unit: "credit", unitLabel: "credits",
        credits: row.credits, free_credits: row.free_credits,
        credit_requests: row.requests, free_requests: row.free_requests
      });
    });
    return rows.concat(estimateRows());
  }

  function activeUnits() {
    var units = new Set();
    if (hasTokenSelected()) units.add("token");
    if (hasCreditsSelected()) units.add("credit");
    if (hasEstimateSelected() || (state.shadow && hasCreditsSelected())) units.add("est");
    return units;
  }

  function reportColumns(units) {
    var columns = [
      { key: "day", label: "日期", type: "text" },
      { key: "source", label: "Agent", type: "text" }
    ];
    if (units.size > 1) columns.push({ key: "unitLabel", label: "单位", type: "text" });
    columns.push({ key: "model", label: "模型", type: "text" });
    columns.push({ key: "project", label: "项目", type: "text" });
    if (units.has("token")) {
      FIELDS.forEach(function (field) {
        columns.push({ key: field, label: FIELD_LABELS[field], type: "num", unit: "token" });
      });
      columns.push({ key: "total", label: "Tokens 合计", type: "num", unit: "token" });
      columns.push({ key: "turns", label: "轮次", type: "num", unit: "token" });
    }
    if (units.has("credit")) {
      columns.push({ key: "credits", label: "billable credits", type: "num",
                     unit: "credit", fmt: fmtCredits });
      columns.push({ key: "free_credits", label: "免费 credits", type: "num",
                     unit: "credit", fmt: fmtCredits });
      columns.push({ key: "credit_requests", label: "billable 请求", type: "num", unit: "credit" });
      columns.push({ key: "free_requests", label: "免费请求", type: "num", unit: "credit" });
    }
    if (units.has("est")) {
      columns.push({ key: "est_input", label: "est 输入", type: "num", unit: "est" });
      columns.push({ key: "est_output", label: "est 输出", type: "num", unit: "est" });
      columns.push({ key: "est_total", label: "est 合计", type: "num", unit: "est" });
      columns.push({ key: "est_requests", label: "请求", type: "num", unit: "est" });
    }
    if (units.has("token") && COST_KNOWN) {
      columns.push({ key: "cost_equiv_usd", label: "等价成本", type: "num", unit: "token" });
    }
    return columns;
  }

  function tableInfo(rows, units) {
    var tokens = 0;
    var credits = 0;
    var traeEst = 0;
    var shadowEst = 0;
    rows.forEach(function (row) {
      if (row.unit === "token") tokens += number(row.total);
      else if (row.unit === "credit") credits += number(row.credits);
      else if (row.unitLabel === "qoder 影子 est") shadowEst += number(row.est_total);
      else traeEst += number(row.est_total);
    });
    var parts = [fmtInt(rows.length) + " 行"];
    if (units.has("token")) parts.push(fmtInt(tokens) + " tokens");
    if (units.has("credit")) parts.push("billable " + fmtCredits(credits) + " credits");
    if (shadowEst > 0) parts.push("影子 est " + fmtInt(shadowEst) + "（不可相加）");
    if (traeEst > 0) parts.push("trae 弱 est " + fmtInt(traeEst) + "（不可相加）");
    return parts.join(" · ");
  }

  function renderShadowNote() {
    if (!hasCreditsSelected() || !state.shadow) {
      el.shadowNote.hidden = true;
      return;
    }
    el.shadowNote.hidden = false;
    el.shadowNote.textContent = "影子 est 由转录文本与 context_usage_ratio 推算（" +
      EST_FACTOR + "，±30~40%），按 天 × 模型 × 项目 聚合；仅覆盖带 ratio 的请求，" +
      "不可与 credits 相加。";
  }

  function renderReport() {
    renderKpis();
    renderCharts();
    renderTopLists();
    var units = activeUnits();
    var rows = reportRows();
    renderDataTable({
      thead: el.thead, tbody: el.tbody, rowinfo: el.rowinfo, pageinfo: el.pageinfo,
      prev: el.prev, next: el.next, columns: reportColumns(units), rows: rows,
      emptyText: "无匹配数据",
      info: function (all) { return tableInfo(all, units); }
    });
    renderShadowNote();
    renderActivity();
  }

  function filteredActivity() {
    return ACTIVITY.filter(function (row) {
      if (state.start && row.day < state.start) return false;
      if (state.end && row.day > state.end) return false;
      if (state.project && row.project !== state.project) return false;
      if (state.q) {
        var haystack = (row.day + " qoder " + row.project).toLowerCase();
        if (haystack.indexOf(state.q) < 0) return false;
      }
      return true;
    });
  }

  function renderActivity() {
    if (!hasCreditsSelected() || !ACTIVITY.length) return;
    var rows = filteredActivity();
    var totals = emptyActivityTotals();
    rows.forEach(function (row) {
      ACTIVITY_FIELDS.forEach(function (field) { totals[field] += number(row[field]); });
    });
    el.activityKpis.textContent = "";
    addKpiTo(el.activityKpis, "活跃会话", fmtCompact(totals.sessions),
      "按天去重求和（会话·天）", true);
    addKpiTo(el.activityKpis, "提示数", fmtCompact(totals.prompts), fmtInt(totals.prompts));
    addKpiTo(el.activityKpis, "assistant 调用", fmtCompact(totals.assistant_calls),
      "turnMetrics 覆盖 " + (totals.assistant_calls
        ? pct(totals.assistant_with_metrics / totals.assistant_calls) : "—"));
    addKpiTo(el.activityKpis, "工具调用", fmtCompact(totals.tool_calls),
      fmtInt(totals.tool_calls));
    addKpiTo(el.activityKpis, "运行时长", fmtDuration(totals.duration_ms),
      "agent 运行时长（含工具）");
    renderActivityChart(rows);
    renderActivityTable(rows);
  }

  function renderActivityChart(rows) {
    el.activityChart.textContent = "";
    el.activityTooltip.style.display = "none";
    var byDay = new Map();
    rows.forEach(function (row) {
      if (!byDay.has(row.day)) byDay.set(row.day, emptyActivityTotals());
      var bucket = byDay.get(row.day);
      ACTIVITY_FIELDS.forEach(function (field) { bucket[field] += number(row[field]); });
    });
    var days = Array.from(byDay.keys()).sort();
    el.activityLegend.textContent = "";
    if (!days.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "所选范围内没有活动数据";
      el.activityChart.appendChild(empty);
      return;
    }

    var metric = state.activityMetric;
    var width = Math.max(el.activityChart.clientWidth || 900, 320);
    var height = 240;
    var margin = { top: 14, right: 14, bottom: 28, left: 62 };
    var plotW = Math.max(width - margin.left - margin.right, 10);
    var plotH = height - margin.top - margin.bottom;
    var maximum = days.reduce(function (acc, day) {
      return Math.max(acc, byDay.get(day)[metric]);
    }, 0);
    var scale = niceScale(maximum, 4);
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": "Qoder 每日活动（非 token）"
    });

    scale.ticks.forEach(function (value) {
      var y = margin.top + plotH - (value / scale.max) * plotH;
      svg.appendChild(svgEl("line", {
        x1: margin.left, x2: width - margin.right, y1: y, y2: y, class: "grid-line"
      }));
      var text = svgEl("text", {
        x: margin.left - 8, y: y + 3.5, "text-anchor": "end"
      });
      text.textContent = fmtCompact(value);
      svg.appendChild(text);
    });

    var band = plotW / days.length;
    var barW = Math.max(1.5, Math.min(26, band * 0.66));
    var color = COLORS.qoder || "#e11d48";
    var hoverLine = svgEl("line", {
      x1: 0, x2: 0, y1: margin.top, y2: margin.top + plotH, class: "hover-line"
    });

    function showTooltip(day, event) {
      var bucket = byDay.get(day);
      var tip = el.activityTooltip;
      tip.textContent = "";
      var head = document.createElement("div");
      head.className = "tt-head";
      head.textContent = day;
      tip.appendChild(head);
      var meta = document.createElement("div");
      meta.className = "tt-meta";
      meta.textContent = "Qoder 活动（非 token）";
      tip.appendChild(meta);
      ACTIVITY_FIELDS.forEach(function (field) {
        var row = document.createElement("div");
        row.className = "tt-row";
        var name = document.createElement("span");
        name.className = "tt-name";
        name.textContent = ACTIVITY_LABELS[field];
        var value = document.createElement("span");
        value.className = "tt-val";
        value.textContent = field === "duration_ms"
          ? fmtDuration(bucket[field]) : fmtInt(bucket[field]);
        row.appendChild(name);
        row.appendChild(value);
        tip.appendChild(row);
      });
      tip.style.display = "block";
      positionTooltip(event);
    }

    function positionTooltip(event) {
      var rect = el.activityChart.parentElement.getBoundingClientRect();
      var x = event.clientX - rect.left;
      var half = 110;
      x = Math.max(half, Math.min(x, rect.width - half));
      el.activityTooltip.style.left = x + "px";
    }

    days.forEach(function (day, index) {
      var value = byDay.get(day)[metric];
      var x = margin.left + band * index + (band - barW) / 2;
      var slice = (value / scale.max) * plotH;
      if (slice > 0) {
        svg.appendChild(svgEl("rect", {
          x: x, y: margin.top + plotH - slice, width: barW, height: slice,
          fill: color, class: "seg", rx: barW > 4 ? 1.5 : 0
        }));
      }
      var hit = svgEl("rect", {
        x: margin.left + band * index, y: margin.top,
        width: Math.max(band, 1), height: plotH, class: "hit"
      });
      hit.addEventListener("mouseenter", function (event) {
        var center = margin.left + band * index + band / 2;
        hoverLine.setAttribute("x1", center);
        hoverLine.setAttribute("x2", center);
        showTooltip(day, event);
      });
      hit.addEventListener("mousemove", positionTooltip);
      hit.addEventListener("mouseleave", function () {
        hoverLine.setAttribute("x1", 0);
        hoverLine.setAttribute("x2", 0);
        el.activityTooltip.style.display = "none";
      });
      svg.appendChild(hit);
    });
    svg.appendChild(hoverLine);

    var labelCount = Math.min(days.length, Math.max(2, Math.floor(plotW / 90)));
    var step = labelCount <= 1 ? 1 : (days.length - 1) / (labelCount - 1);
    var used = new Set();
    for (var k = 0; k < labelCount; k += 1) {
      var idx = Math.round(k * step);
      if (used.has(idx)) continue;
      used.add(idx);
      var label = svgEl("text", {
        x: margin.left + band * idx + band / 2,
        y: height - 8,
        "text-anchor": "middle"
      });
      label.textContent = days[idx].slice(5);
      svg.appendChild(label);
    }
    el.activityChart.appendChild(svg);

    var metricTotal = days.reduce(function (acc, day) {
      return acc + byDay.get(day)[metric];
    }, 0);
    var item = document.createElement("span");
    item.className = "legend-item";
    var dot = document.createElement("i");
    dot.className = "legend-dot";
    dot.style.background = color;
    var name = document.createElement("span");
    name.textContent = "Qoder · " + ACTIVITY_LABELS[metric];
    var amount = document.createElement("b");
    amount.textContent = fmtCompact(metricTotal);
    item.appendChild(dot);
    item.appendChild(name);
    item.appendChild(amount);
    el.activityLegend.appendChild(item);

    var withMetrics = days.reduce(function (acc, day) {
      return acc + byDay.get(day).assistant_with_metrics;
    }, 0);
    var assistant = days.reduce(function (acc, day) {
      return acc + byDay.get(day).assistant_calls;
    }, 0);
    el.activityHint.textContent = "turnMetrics 覆盖 " +
      (assistant ? pct(withMetrics / assistant) : "—") +
      "；未带 metrics 的 assistant 其 turns/时长为 0，不代表没使用；活动与 credits 口径不同，不可相加。";
  }

  var ACTIVITY_COLUMNS = [
    { key: "day", label: "日期", type: "text" },
    { key: "project", label: "项目", type: "text" },
    { key: "sessions", label: "会话·天", type: "num" },
    { key: "prompts", label: "提示", type: "num" },
    { key: "assistant_calls", label: "assistant", type: "num" },
    { key: "assistant_with_metrics", label: "带指标", type: "num" },
    { key: "turns", label: "turns", type: "num" },
    { key: "tool_calls", label: "工具调用", type: "num" },
    { key: "duration_ms", label: "运行时长", type: "num" }
  ];

  function renderActivityTable(rows) {
    var sorted = rows.slice().sort(function (a, b) {
      if (a.day !== b.day) return a.day < b.day ? 1 : -1;
      return String(a.project).localeCompare(String(b.project), "zh-CN");
    });
    el.activityThead.textContent = "";
    var headerRow = document.createElement("tr");
    ACTIVITY_COLUMNS.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "th-btn";
      button.appendChild(document.createTextNode(column.label));
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    el.activityThead.appendChild(headerRow);

    el.activityTbody.textContent = "";
    var toolTotal = 0;
    sorted.forEach(function (row) {
      var tr = document.createElement("tr");
      toolTotal += row.tool_calls;
      ACTIVITY_COLUMNS.forEach(function (column) {
        var td = document.createElement("td");
        var value = row[column.key];
        if (column.type === "num") td.className = "num";
        if (column.key === "project") {
          td.textContent = value === "-" ? "（未标注）" : value;
          td.title = value;
        } else if (column.key === "duration_ms") {
          td.textContent = fmtDuration(value);
          if (!number(value)) td.classList.add("zero");
        } else if (column.type === "num") {
          td.textContent = fmtInt(value);
          if (!number(value)) td.classList.add("zero");
        } else {
          td.textContent = value;
        }
        tr.appendChild(td);
      });
      el.activityTbody.appendChild(tr);
    });
    el.activityRowinfo.textContent = fmtInt(sorted.length) + " 行 · 工具调用 " +
      fmtInt(toolTotal) + " · 会话按天去重";
  }

  function renderFooter() {
    el.footer.textContent = "";
    (DATA.notices || []).forEach(function (notice) {
      var line = document.createElement("p");
      line.textContent = notice;
      el.footer.appendChild(line);
    });
    var classify = document.createElement("p");
    classify.textContent = "Agent 可多选：Token 计费（" +
      (TOKEN_AGENTS.length ? TOKEN_AGENTS.join(" / ") : "无数据") +
      "）与 Credits 计费（Qoder）分别按各自单位汇总，同一页面并列展示但不跨单位相加；" +
      "Qoder 的影子 token 与 Trae CN 的弱估算单独归入 est，同样不可相加。";
    el.footer.appendChild(classify);
    if (QODER_TOKEN_ROWS.length) {
      var history = document.createElement("p");
      history.textContent = "Qoder 历史 token 真值 " +
        (qoderTokenBounds[0] + " ~ " + qoderTokenBounds[1]) + "（" +
        fmtInt(sumField(QODER_TOKEN_ROWS, "total")) +
        " tokens）保留在库中，未并入本页；可用 usage report --source qoder 查询。";
      el.footer.appendChild(history);
    }
    if (CREDIT_ROWS.length) {
      var creditNote = document.createElement("p");
      creditNote.textContent = "Qoder credits 为服务端每请求计费真值；免费 credits 不计配额；" +
        "余额来自本地日志快照；credits、估算与活动口径不同，不可相加。";
      el.footer.appendChild(creditNote);
    }
    if (EST.length) {
      var estNote = document.createElement("p");
      estNote.textContent = "Qoder 估算 token 由转录文本与上下文比例推算（" + EST_FACTOR +
        "，±30~40% 误差），不可与 token 真值或额度相加。";
      el.footer.appendChild(estNote);
    }
    if (TRAE_EST.length) {
      var traeNote = document.createElement("p");
      traeNote.textContent = TRAE_NOTE + "；仅覆盖安装 hook 后的请求，" +
        "误差可能数倍且方向不定，只适合看趋势，不可与 token 真值或额度相加。";
      el.footer.appendChild(traeNote);
    }
    var scope = document.createElement("p");
    scope.textContent = "数据范围 " + (DATA_SINCE || "—") + " ~ " + (DATA_UNTIL || "—") +
      " · " + fmtInt(ROWS.length) + " 行 token 聚合" +
      (CREDIT_ROWS.length ? " · " + fmtInt(CREDIT_ROWS.length) + " 行 credits 聚合" : "") +
      (ACTIVITY.length ? " · " + fmtInt(ACTIVITY.length) + " 行活动聚合" : "") +
      (EST.length ? " · " + fmtInt(EST.length) + " 行估算聚合" : "") +
      (TRAE_EST.length ? " · " + fmtInt(TRAE_EST.length) + " 行 Trae 弱估算聚合" : "") +
      " · 页面不发起任何网络请求";
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
    resizeTimer = setTimeout(function () {
      renderAll();
    }, 150);
  });

  function renderAll() {
    syncShell();
    renderCoverage();
    renderReport();
  }

  buildAgentFilter();
  buildControls();
  rebuildDimensionSelects();
  applyTheme(document.documentElement.dataset.theme || "light");
  el.activityMetric.value = state.activityMetric;
  el.generated.textContent = "生成于 " + fmtDateTime(DATA.generated_at);
  renderFooter();
  renderAll();
})();
</script>
</body>
</html>
"""
