from __future__ import annotations

import json
from datetime import datetime

from .models import ACTIVITY_FIELDS, FIELDS

PLACEHOLDER = "__USAGE_LEDGER_PAYLOAD__"


def build_payload(rows, dims, since, until, notices, generated_at=None,
                  activity=None, coverage=None, credits=None, quota=None,
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
        "activity": activity_rows,
        "credits": {
            "days": list(credit_data.get("days") or []),
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
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));gap:12px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px 14px;box-shadow:var(--shadow);min-width:0}
.kpi.primary{grid-column:span 2;background:linear-gradient(135deg,var(--accent-soft),var(--surface) 72%);border-color:var(--accent)}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:clamp(20px,2.1vw,27px);font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.3px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi-sub{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.coverage{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0;padding:10px 14px;border:1px solid var(--accent);border-radius:12px;background:var(--accent-soft);color:var(--text);font-size:12.5px}
.coverage-jump{color:var(--accent);text-decoration:none;font-weight:600;white-space:nowrap}
.coverage-jump:hover{text-decoration:underline}
.section-tag{font-size:11px;font-weight:600;color:#fff;background:var(--accent);border-radius:999px;padding:2px 8px;margin-left:8px;vertical-align:2px}
.section-tag.quiet{background:var(--surface-2);border:1px solid var(--border);color:var(--muted);font-weight:500}
.qoder-extra{display:flex;flex-direction:column;gap:16px}
.qoder-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;flex-wrap:wrap;padding:0 4px}
.qoder-head h2{font-size:15px;margin:0;letter-spacing:.2px}
.qoder-head p{margin:3px 0 0}
.qoder-head-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tabs{display:inline-flex;gap:3px;padding:3px;background:var(--surface-2);border:1px solid var(--border);border-radius:10px}
.tab{border:0;background:transparent;color:var(--muted);font:inherit;font-size:12.5px;padding:5px 13px;border-radius:7px;cursor:pointer;transition:background .15s,color .15s}
.tab:hover:not(:disabled){color:var(--text)}
.tab.active{background:var(--surface);color:var(--text);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.tab:disabled{opacity:.35;cursor:default}
.qoder-panel{display:flex;flex-direction:column;gap:16px}
.quota-kpi .kpi-sub{white-space:normal;overflow:visible}
.quota-track{height:6px;border-radius:999px;background:var(--surface-2);overflow:hidden;margin-top:9px}
.quota-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#22c1a4)}
.quota-fill.warn{background:linear-gradient(90deg,#f59e0b,#ef4444)}
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
.chart-wrap svg{display:block;width:100%;height:auto}
.chart-wrap svg text{fill:var(--muted);font-size:11px;font-family:inherit}
.chart-wrap .grid-line{stroke:var(--border);stroke-width:1;shape-rendering:crispEdges}
.chart-wrap .seg{stroke:var(--surface);stroke-width:.6}
.chart-wrap .hit{fill:transparent;cursor:crosshair}
.chart-wrap .hover-line{stroke:var(--accent);stroke-width:1;stroke-dasharray:3 3;opacity:.45;pointer-events:none}
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

  <p id="coverage" class="coverage" hidden></p>

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

  <section class="qoder-extra" id="qoder-extra" aria-label="补充口径" hidden>
    <div class="qoder-head">
      <div>
        <h2>补充口径<span class="section-tag quiet">非 token</span></h2>
        <p class="muted">Qoder 活动、额度、估算与 token 真值口径不同，不可相加；Trae CN 为 hook 弱估算，同样不可相加。</p>
      </div>
      <div class="qoder-head-actions">
        <div class="tabs" id="supp-source-tabs" role="tablist" aria-label="补充口径来源" hidden>
          <button type="button" class="tab active" data-supp-source="qoder" role="tab" aria-selected="true">Qoder</button>
          <button type="button" class="tab" data-supp-source="trae-cn" role="tab" aria-selected="false">Trae CN</button>
        </div>
        <div class="tabs" id="qoder-tabs" role="tablist" aria-label="Qoder 补充指标">
          <button type="button" class="tab active" data-qoder-tab="activity" role="tab" aria-selected="true">活动</button>
          <button type="button" class="tab" data-qoder-tab="credits" role="tab" aria-selected="false">额度</button>
          <button type="button" class="tab" data-qoder-tab="est" role="tab" aria-selected="false">估算</button>
        </div>
      </div>
    </div>

    <div class="qoder-panel" data-qoder-panel="activity">
      <section class="kpis" id="activity-kpis" aria-label="Qoder 活动指标" hidden></section>
      <section class="card chart-card" id="activity-chart-card" hidden>
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
        <div class="legend" id="activity-legend"></div>
        <div class="chart-wrap">
          <div id="activity-chart"></div>
          <div id="activity-tooltip" class="tooltip"></div>
        </div>
        <p class="muted" id="activity-hint" style="margin:8px 0 0"></p>
      </section>
      <section class="card table-card" id="activity-table-card" hidden>
        <div class="card-head">
          <h2>活动明细</h2>
          <span class="muted" id="activity-rowinfo"></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead id="activity-thead"></thead>
            <tbody id="activity-tbody"></tbody>
          </table>
        </div>
      </section>
    </div>

    <div class="qoder-panel" data-qoder-panel="credits" hidden>
      <section class="kpis" id="credit-kpis" aria-label="Qoder 额度指标" hidden></section>
      <section class="card chart-card" id="credit-chart-card" hidden>
        <div class="card-head">
          <h2>额度消耗（credits）</h2>
          <span class="muted" id="credit-range"></span>
        </div>
        <div class="legend" id="credit-legend"></div>
        <div class="chart-wrap">
          <div id="credit-chart"></div>
          <div id="credit-tooltip" class="tooltip"></div>
        </div>
        <p class="muted" id="credit-hint" style="margin:8px 0 0"></p>
      </section>
      <section class="card table-card" id="credit-table-card" hidden>
        <div class="card-head">
          <h2>额度明细</h2>
          <span class="muted" id="credit-rowinfo"></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead id="credit-thead"></thead>
            <tbody id="credit-tbody"></tbody>
          </table>
        </div>
      </section>
    </div>

    <div class="qoder-panel" data-qoder-panel="est" hidden>
      <section class="kpis" id="est-kpis" aria-label="Qoder 估算 token" hidden></section>
      <section class="card table-card" id="est-table-card" hidden>
        <div class="card-head">
          <h2>估算 token（est）</h2>
          <span class="muted" id="est-rowinfo"></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead id="est-thead"></thead>
            <tbody id="est-tbody"></tbody>
          </table>
        </div>
        <p class="muted" id="est-hint" style="margin:8px 0 0"></p>
      </section>
    </div>

    <div class="qoder-panel" data-trae-panel hidden>
      <section class="kpis" id="trae-est-kpis" aria-label="Trae CN 弱估算 token" hidden></section>
      <section class="card table-card" id="trae-est-table-card" hidden>
        <div class="card-head">
          <h2>Trae CN 弱估算（est）</h2>
          <span class="muted" id="trae-est-rowinfo"></span>
        </div>
        <div class="table-wrap">
          <table>
            <thead id="trae-est-thead"></thead>
            <tbody id="trae-est-tbody"></tbody>
          </table>
        </div>
        <p class="muted" id="trae-est-hint" style="margin:8px 0 0"></p>
      </section>
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
  var ACTIVITY_FIELDS = ["sessions", "prompts", "assistant_calls", "assistant_with_metrics",
                         "turns", "tool_calls", "duration_ms"];
  var ACTIVITY_LABELS = { sessions: "活跃会话", prompts: "提示数", assistant_calls: "assistant 调用",
                          assistant_with_metrics: "带指标", turns: "turns",
                          tool_calls: "工具调用", duration_ms: "运行时长" };
  var KNOWN_COLORS = { claude: "#d97706", codex: "#0ea5e9", opencode: "#7c3aed",
                       kilo: "#10b981", cline: "#65a30d", qoder: "#e11d48", "trae-cn": "#0d9488" };
  var PALETTE = ["#ef4444", "#f59e0b", "#14b8a6", "#6366f1"];
  var KNOWN_ORDER = ["claude", "codex", "opencode", "kilo", "cline", "qoder", "trae-cn"];
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

  var ACTIVITY = (Array.isArray(DATA.activity) ? DATA.activity : []).map(function (row) {
    var copy = {};
    Object.keys(row).forEach(function (key) { copy[key] = row[key]; });
    ACTIVITY_FIELDS.forEach(function (field) { copy[field] = number(row[field]); });
    copy.project = row.project || "-";
    return copy;
  });

  var CREDIT_DATA = DATA.credits || {};
  var CREDITS = (Array.isArray(CREDIT_DATA.days) ? CREDIT_DATA.days : []).map(function (row) {
    return {
      day: row.day,
      credits: number(row.credits),
      requests: number(row.requests),
      free_credits: number(row.free_credits),
      snapshots: number(row.snapshots)
    };
  });
  var CREDIT_TOTALS = CREDIT_DATA.totals || {};
  var QUOTA = CREDIT_DATA.quota || {};

  var EST_DATA = DATA.est || {};
  var EST = (Array.isArray(EST_DATA.rows) ? EST_DATA.rows : []).map(function (row) {
    return {
      day: row.day,
      model: row.model || "unknown",
      est_input: number(row.est_input),
      est_output: number(row.est_output),
      requests: number(row.requests),
      chars_in: number(row.chars_in),
      chars_out: number(row.chars_out),
      missing_ratio: number(row.missing_ratio)
    };
  });
  var EST_TOTALS = EST_DATA.totals || {};
  var EST_FACTOR = EST_DATA.factor_version || "v1";

  var TRAE_EST_DATA = DATA.trae_est || {};
  var TRAE_EST = (Array.isArray(TRAE_EST_DATA.rows) ? TRAE_EST_DATA.rows : []).map(function (row) {
    return {
      day: row.day,
      model: row.model || "trae-cn",
      est_input: number(row.est_input),
      est_output: number(row.est_output),
      requests: number(row.requests),
      chars_in: number(row.chars_in),
      chars_out: number(row.chars_out)
    };
  });
  var TRAE_EST_FACTOR = TRAE_EST_DATA.factor_version || "trae-hook-v1";
  var TRAE_EST_NOTE = "Trae CN 弱估算（hook 可见内容，不含系统提示/工具定义）";
  var COVERAGE = DATA.coverage || {};

  var PRESENT = [];
  ROWS.forEach(function (row) {
    if (PRESENT.indexOf(row.source) < 0) PRESENT.push(row.source);
  });
  ACTIVITY.forEach(function (row) {
    if (PRESENT.indexOf(row.source) < 0) PRESENT.push(row.source);
  });
  if ((CREDITS.length || EST.length) && PRESENT.indexOf("qoder") < 0) PRESENT.push("qoder");
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

  var tokenBounds = minMaxDay(ROWS);
  var activityBounds = minMaxDay(ACTIVITY);
  var creditBounds = minMaxDay(CREDITS);
  var estBounds = minMaxDay(EST);
  var traeEstBounds = minMaxDay(TRAE_EST);
  var RANGE = DATA.range || {};
  var DATA_SINCE = RANGE.since || earliestDay(
    earliestDay(tokenBounds[0], activityBounds[0]),
    earliestDay(creditBounds[0], earliestDay(estBounds[0], traeEstBounds[0])));
  var DATA_UNTIL = RANGE.until || latestDay(
    latestDay(tokenBounds[1], activityBounds[1]),
    latestDay(creditBounds[1], latestDay(estBounds[1], traeEstBounds[1])));
  var DATA_DAYS = new Set(ROWS.map(function (row) { return row.day; }));
  CREDITS.forEach(function (row) { DATA_DAYS.add(row.day); });
  EST.forEach(function (row) { DATA_DAYS.add(row.day); });
  TRAE_EST.forEach(function (row) { DATA_DAYS.add(row.day); });
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
    activityMetric: "tool_calls",
    qoderTab: "activity",
    suppSource: "qoder",
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
    coverage: $("#coverage"), activityKpis: $("#activity-kpis"),
    activityChart: $("#activity-chart"), activityChartCard: $("#activity-chart-card"),
    activityLegend: $("#activity-legend"), activityMetric: $("#activity-metric"),
    activityTooltip: $("#activity-tooltip"), activityHint: $("#activity-hint"),
    activityTableCard: $("#activity-table-card"), activityThead: $("#activity-thead"),
    activityTbody: $("#activity-tbody"), activityRowinfo: $("#activity-rowinfo"),
    creditKpis: $("#credit-kpis"), creditChartCard: $("#credit-chart-card"),
    creditChart: $("#credit-chart"), creditLegend: $("#credit-legend"),
    creditTooltip: $("#credit-tooltip"), creditHint: $("#credit-hint"),
    creditRange: $("#credit-range"), creditTableCard: $("#credit-table-card"),
    creditThead: $("#credit-thead"), creditTbody: $("#credit-tbody"),
    creditRowinfo: $("#credit-rowinfo"),
    estKpis: $("#est-kpis"), estTableCard: $("#est-table-card"),
    estThead: $("#est-thead"), estTbody: $("#est-tbody"),
    estRowinfo: $("#est-rowinfo"), estHint: $("#est-hint"),
    traeEstKpis: $("#trae-est-kpis"), traeEstTableCard: $("#trae-est-table-card"),
    traeEstThead: $("#trae-est-thead"), traeEstTbody: $("#trae-est-tbody"),
    traeEstRowinfo: $("#trae-est-rowinfo"), traeEstHint: $("#trae-est-hint"),
    traePanel: $("[data-trae-panel]"), suppSourceTabs: $("#supp-source-tabs"),
    qoderExtra: $("#qoder-extra"), qoderTabs: $("#qoder-tabs"),
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

  function fmtDuration(ms) {
    var seconds = Math.round(number(ms) / 1000);
    if (seconds >= 3600) {
      var minutes = Math.round((seconds % 3600) / 60);
      return Math.floor(seconds / 3600) + "h " + pad2(minutes) + "m";
    }
    if (seconds >= 60) return Math.floor(seconds / 60) + "m " + pad2(seconds % 60) + "s";
    return seconds + "s";
  }

  function emptyActivityTotals() {
    var totals = {};
    ACTIVITY_FIELDS.forEach(function (field) { totals[field] = 0; });
    return totals;
  }

  function hasQoderData() {
    return ROWS.some(function (row) { return row.source === "qoder"; }) ||
      ACTIVITY.length > 0 || CREDITS.length > 0 || EST.length > 0;
  }

  function hasCoverage() {
    return hasQoderData() || TRAE_EST.length > 0;
  }

  function renderCoverage() {
    var qoder = (COVERAGE && COVERAGE.qoder) || {};
    if (!hasCoverage()) {
      el.coverage.hidden = true;
      return;
    }
    var qoderParts = [];
    if (hasQoderData()) {
      if (qoder.token_since) {
        qoderParts.push("token " + qoder.token_since + " ~ " + qoder.token_until);
      } else {
        qoderParts.push("本地无 token 真值");
      }
      if (qoder.activity_since) {
        qoderParts.push("活动 " + qoder.activity_since + " ~ " + qoder.activity_until);
      }
      if (creditBounds[0]) {
        qoderParts.push("额度 " + creditBounds[0] + " ~ " + creditBounds[1]);
      }
      if (estBounds[0]) {
        qoderParts.push("估算 " + estBounds[0] + " ~ " + estBounds[1]);
      }
    }
    var textParts = [];
    if (qoderParts.length) textParts.push("Qoder 覆盖：" + qoderParts.join(" · "));
    if (traeEstBounds[0]) {
      textParts.push("Trae CN 弱估算 " + traeEstBounds[0] + " ~ " + traeEstBounds[1]);
    }
    var text = textParts.join("；") + (qoderParts.length
      ? " —— 活动 / 额度 / 估算与 token 口径不同，不可相加"
      : " —— 弱估算不可与 token 真值相加");
    if (qoderParts.length && qoder.token_until) {
      text += "；" + qoder.token_until + " 之后本地无 token 数据";
    }
    el.coverage.textContent = "";
    var span = document.createElement("span");
    span.textContent = text;
    el.coverage.appendChild(span);
    if (filteredActivity().length || filteredCredits().length ||
        filteredEstimates().length || filteredTraeEstimates().length) {
      var jump = document.createElement("a");
      jump.className = "coverage-jump";
      jump.href = "#qoder-extra";
      jump.textContent = "查看补充 ↓";
      el.coverage.appendChild(jump);
    }
    el.coverage.hidden = false;
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

    if (el.activityMetric) {
      el.activityMetric.addEventListener("change", function () {
        state.activityMetric = el.activityMetric.value;
        renderActivity();
      });
    }

    if (el.qoderTabs) {
      el.qoderTabs.addEventListener("click", function (event) {
        var button = event.target.closest("[data-qoder-tab]");
        if (!button || button.disabled) return;
        state.qoderTab = button.getAttribute("data-qoder-tab");
        syncSupplement(true);
      });
    }

    if (el.suppSourceTabs) {
      el.suppSourceTabs.addEventListener("click", function (event) {
        var button = event.target.closest("[data-supp-source]");
        if (!button || button.disabled) return;
        state.suppSource = button.getAttribute("data-supp-source");
        syncSupplement(true);
      });
    }

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

  function filteredActivity() {
    if (!ACTIVITY.length || !state.sources.has("qoder")) return [];
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

  function filteredCredits() {
    if (!CREDITS.length || !state.sources.has("qoder")) return [];
    return CREDITS.filter(function (row) {
      if (state.start && row.day < state.start) return false;
      if (state.end && row.day > state.end) return false;
      if (state.q) {
        var haystack = (row.day + " qoder credits").toLowerCase();
        if (haystack.indexOf(state.q) < 0) return false;
      }
      return true;
    });
  }

  function filteredEstimates() {
    if (!EST.length || !state.sources.has("qoder")) return [];
    return EST.filter(function (row) {
      if (state.start && row.day < state.start) return false;
      if (state.end && row.day > state.end) return false;
      if (state.q) {
        var haystack = (row.day + " " + row.model + " qoder est").toLowerCase();
        if (haystack.indexOf(state.q) < 0) return false;
      }
      return true;
    });
  }

  function filteredTraeEstimates() {
    if (!TRAE_EST.length) return [];
    return TRAE_EST.filter(function (row) {
      if (state.start && row.day < state.start) return false;
      if (state.end && row.day > state.end) return false;
      if (state.q) {
        var haystack = (row.day + " " + row.model + " trae cn").toLowerCase();
        if (haystack.indexOf(state.q) < 0) return false;
      }
      return true;
    });
  }

  function addKpiTo(host, label, value, sub, primary) {
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
    host.appendChild(card);
  }

  function addKpi(label, value, sub, primary) {
    addKpiTo(el.kpis, label, value, sub, primary);
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

  function renderActivity() {
    var rows = filteredActivity();
    var visible = rows.length > 0;
    el.activityKpis.hidden = !visible;
    el.activityChartCard.hidden = !visible;
    el.activityTableCard.hidden = !visible;
    if (!visible) return;

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
      var index = Math.round(k * step);
      if (used.has(index)) continue;
      used.add(index);
      var label = svgEl("text", {
        x: margin.left + band * index + band / 2,
        y: height - 8,
        "text-anchor": "middle"
      });
      label.textContent = days[index].slice(5);
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
      "；未带 metrics 的 assistant 其 turns/时长为 0，不代表没使用";
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

  function fmtCredits(value) {
    return number(value).toFixed(2);
  }

  function fmtQuota(value) {
    var parsed = number(value);
    return Math.abs(parsed - Math.round(parsed)) < 0.005 ? fmtInt(parsed) : parsed.toFixed(2);
  }

  var CREDIT_BILLABLE_COLOR = "#e11d48";
  var CREDIT_FREE_COLOR = "#f59e0b";

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

  function renderCredits() {
    var rows = filteredCredits();
    var visible = rows.length > 0;
    el.creditKpis.hidden = !visible;
    el.creditChartCard.hidden = !visible;
    el.creditTableCard.hidden = !visible;
    if (!visible) return;

    var billable = 0;
    var free = 0;
    var requests = 0;
    rows.forEach(function (row) {
      billable += row.credits;
      free += row.free_credits;
      requests += row.requests;
    });
    var quota = quotaSummary();

    el.creditKpis.textContent = "";
    addQuotaKpi(el.creditKpis, quota);
    addKpiTo(el.creditKpis, "区间 billable", fmtCredits(billable),
      fmtInt(requests) + " billable 请求 · 服务端计费真值");
    addKpiTo(el.creditKpis, "免费 credits", fmtCredits(free), "不计入配额");
    addKpiTo(el.creditKpis, "区间日均", fmtCredits(rows.length ? billable / rows.length : 0),
      fmtInt(rows.length) + " 天有数据");
    el.creditRange.textContent = "区间合计 " + fmtCredits(billable) + " credits";
    renderCreditChart(rows);
    renderCreditTable(rows);
  }

  function renderCreditChart(rows) {
    el.creditChart.textContent = "";
    el.creditTooltip.style.display = "none";
    el.creditLegend.textContent = "";
    if (!rows.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "所选范围内没有额度数据";
      el.creditChart.appendChild(empty);
      return;
    }

    var width = Math.max(el.creditChart.clientWidth || 900, 320);
    var height = 230;
    var margin = { top: 14, right: 14, bottom: 28, left: 62 };
    var plotW = Math.max(width - margin.left - margin.right, 10);
    var plotH = height - margin.top - margin.bottom;
    var maximum = rows.reduce(function (acc, row) {
      return Math.max(acc, row.credits + row.free_credits);
    }, 0);
    var scale = niceScale(maximum, 4);
    var svg = svgEl("svg", {
      viewBox: "0 0 " + width + " " + height,
      role: "img",
      "aria-label": "Qoder 每日配额消耗（credits）"
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

    var band = plotW / rows.length;
    var barW = Math.max(1.5, Math.min(26, band * 0.66));
    var hoverLine = svgEl("line", {
      x1: 0, x2: 0, y1: margin.top, y2: margin.top + plotH, class: "hover-line"
    });

    function showTooltip(row, event) {
      var tip = el.creditTooltip;
      tip.textContent = "";
      var head = document.createElement("div");
      head.className = "tt-head";
      head.textContent = row.day;
      tip.appendChild(head);
      var meta = document.createElement("div");
      meta.className = "tt-meta";
      meta.textContent = "Qoder 配额（credits，非 token）";
      tip.appendChild(meta);
      [["billable", row.credits], ["免费", row.free_credits]].forEach(function (pair) {
        var line = document.createElement("div");
        line.className = "tt-row";
        var name = document.createElement("span");
        name.className = "tt-name";
        var dot = document.createElement("i");
        dot.style.background = pair[0] === "billable" ? CREDIT_BILLABLE_COLOR : CREDIT_FREE_COLOR;
        name.appendChild(dot);
        name.appendChild(document.createTextNode(pair[0]));
        var value = document.createElement("span");
        value.className = "tt-val";
        value.textContent = fmtCredits(pair[1]);
        line.appendChild(name);
        line.appendChild(value);
        tip.appendChild(line);
      });
      var total = document.createElement("div");
      total.className = "tt-row tt-total";
      var totalName = document.createElement("span");
      totalName.className = "tt-name";
      totalName.textContent = "合计";
      var totalValue = document.createElement("span");
      totalValue.className = "tt-val";
      totalValue.textContent = fmtCredits(row.credits + row.free_credits);
      total.appendChild(totalName);
      total.appendChild(totalValue);
      tip.appendChild(total);
      var meta2 = document.createElement("div");
      meta2.className = "tt-meta";
      meta2.style.margin = "5px 0 0";
      meta2.textContent = fmtInt(row.requests) + " 请求 · " +
        fmtInt(row.snapshots) + " 次额度快照";
      tip.appendChild(meta2);
      tip.style.display = "block";
      positionTooltip(event);
    }

    function positionTooltip(event) {
      var rect = el.creditChart.parentElement.getBoundingClientRect();
      var x = event.clientX - rect.left;
      var half = 110;
      x = Math.max(half, Math.min(x, rect.width - half));
      el.creditTooltip.style.left = x + "px";
    }

    rows.forEach(function (row, index) {
      var x = margin.left + band * index + (band - barW) / 2;
      var baseY = margin.top + plotH;
      var freeH = (row.free_credits / scale.max) * plotH;
      var billableH = (row.credits / scale.max) * plotH;
      if (freeH > 0) {
        svg.appendChild(svgEl("rect", {
          x: x, y: baseY - freeH, width: barW, height: freeH,
          fill: CREDIT_FREE_COLOR, class: "seg", rx: barW > 4 ? 1.5 : 0
        }));
      }
      if (billableH > 0) {
        svg.appendChild(svgEl("rect", {
          x: x, y: baseY - freeH - billableH, width: barW, height: billableH,
          fill: CREDIT_BILLABLE_COLOR, class: "seg", rx: barW > 4 ? 1.5 : 0
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
        showTooltip(row, event);
      });
      hit.addEventListener("mousemove", positionTooltip);
      hit.addEventListener("mouseleave", function () {
        hoverLine.setAttribute("x1", 0);
        hoverLine.setAttribute("x2", 0);
        el.creditTooltip.style.display = "none";
      });
      svg.appendChild(hit);
    });
    svg.appendChild(hoverLine);

    var labelCount = Math.min(rows.length, Math.max(2, Math.floor(plotW / 90)));
    var step = labelCount <= 1 ? 1 : (rows.length - 1) / (labelCount - 1);
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
      label.textContent = rows[index].day.slice(5);
      svg.appendChild(label);
    }
    el.creditChart.appendChild(svg);

    var billableTotal = rows.reduce(function (acc, row) { return acc + row.credits; }, 0);
    var freeTotal = rows.reduce(function (acc, row) { return acc + row.free_credits; }, 0);
    [
      ["billable（计入配额）", billableTotal, CREDIT_BILLABLE_COLOR],
      ["免费（不计配额）", freeTotal, CREDIT_FREE_COLOR]
    ].forEach(function (pair) {
      var item = document.createElement("span");
      item.className = "legend-item";
      var dot = document.createElement("i");
      dot.className = "legend-dot";
      dot.style.background = pair[2];
      var name = document.createElement("span");
      name.textContent = pair[0];
      var amount = document.createElement("b");
      amount.textContent = fmtCredits(pair[1]);
      item.appendChild(dot);
      item.appendChild(name);
      item.appendChild(amount);
      el.creditLegend.appendChild(item);
    });

    el.creditHint.textContent = "credits 为服务端每请求计费真值；免费 credits 不计配额；" +
      "余额来自最新日志快照。额度按天汇总，不受模型/项目筛选影响。";
  }

  var CREDIT_COLUMNS = [
    { key: "day", label: "日期", type: "text" },
    { key: "credits", label: "billable", type: "num" },
    { key: "requests", label: "请求", type: "num" },
    { key: "free_credits", label: "免费", type: "num" },
    { key: "snapshots", label: "快照", type: "num" }
  ];

  function renderCreditTable(rows) {
    var sorted = rows.slice().sort(function (a, b) {
      return a.day < b.day ? 1 : a.day > b.day ? -1 : 0;
    });
    el.creditThead.textContent = "";
    var headerRow = document.createElement("tr");
    CREDIT_COLUMNS.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "th-btn";
      button.appendChild(document.createTextNode(column.label));
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    el.creditThead.appendChild(headerRow);

    el.creditTbody.textContent = "";
    var billable = 0;
    var free = 0;
    var requests = 0;
    sorted.forEach(function (row) {
      billable += row.credits;
      free += row.free_credits;
      requests += row.requests;
      var tr = document.createElement("tr");
      CREDIT_COLUMNS.forEach(function (column) {
        var td = document.createElement("td");
        if (column.type === "num") td.className = "num";
        if (column.type === "num") {
          td.textContent = fmtCredits(row[column.key]);
          if (column.key === "requests" || column.key === "snapshots") {
            td.textContent = fmtInt(row[column.key]);
          }
          if (!number(row[column.key])) td.classList.add("zero");
        } else {
          td.textContent = row[column.key];
        }
        tr.appendChild(td);
      });
      el.creditTbody.appendChild(tr);
    });
    el.creditRowinfo.textContent = fmtInt(sorted.length) + " 天 · billable " +
      fmtCredits(billable) + " · 免费 " + fmtCredits(free) + " · " + fmtInt(requests) + " 请求";
  }

  function renderEstimates() {
    var rows = filteredEstimates();
    var visible = rows.length > 0;
    el.estKpis.hidden = !visible;
    el.estTableCard.hidden = !visible;
    if (!visible) return;

    var input = 0;
    var output = 0;
    var requests = 0;
    var missing = 0;
    var models = new Set();
    rows.forEach(function (row) {
      input += row.est_input;
      output += row.est_output;
      requests += row.requests;
      missing += row.missing_ratio;
      models.add(row.model);
    });

    el.estKpis.textContent = "";
    addKpiTo(el.estKpis, "est 总 Token", fmtCompact(input + output),
      fmtInt(input + output), true);
    addKpiTo(el.estKpis, "est 输入", fmtCompact(input), "context_usage_ratio × 200K");
    addKpiTo(el.estKpis, "est 输出", fmtCompact(output), "字符数 ÷ 模型系数");
    addKpiTo(el.estKpis, "覆盖请求", fmtCompact(requests),
      "ratio 缺失 " + fmtInt(missing) + " · 模型 " + fmtInt(models.size));
    renderEstTable(rows);
  }

  var EST_COLUMNS = [
    { key: "day", label: "日期", type: "text" },
    { key: "model", label: "模型", type: "text" },
    { key: "est_input", label: "est 输入", type: "num" },
    { key: "est_output", label: "est 输出", type: "num" },
    { key: "requests", label: "请求", type: "num" },
    { key: "missing_ratio", label: "ratio 缺失", type: "num" }
  ];

  function renderEstTable(rows) {
    var sorted = rows.slice().sort(function (a, b) {
      if (a.day !== b.day) return a.day < b.day ? 1 : -1;
      return String(a.model).localeCompare(String(b.model), "zh-CN");
    });
    el.estThead.textContent = "";
    var headerRow = document.createElement("tr");
    EST_COLUMNS.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "th-btn";
      button.appendChild(document.createTextNode(column.label));
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    el.estThead.appendChild(headerRow);

    el.estTbody.textContent = "";
    var input = 0;
    var output = 0;
    var requests = 0;
    sorted.forEach(function (row) {
      input += row.est_input;
      output += row.est_output;
      requests += row.requests;
      var tr = document.createElement("tr");
      EST_COLUMNS.forEach(function (column) {
        var td = document.createElement("td");
        if (column.type === "num") td.className = "num";
        if (column.type === "num") {
          td.textContent = fmtInt(row[column.key]);
          if (!number(row[column.key])) td.classList.add("zero");
        } else if (column.key === "model") {
          td.textContent = row.model;
          td.title = row.model;
        } else {
          td.textContent = row[column.key];
        }
        tr.appendChild(td);
      });
      el.estTbody.appendChild(tr);
    });
    el.estRowinfo.textContent = fmtInt(sorted.length) + " 行 · est 总 Token " +
      fmtInt(input + output) + " · " + fmtInt(requests) + " 请求";
    el.estHint.textContent = "由转录文本 + context_usage_ratio × 200K 估算（系数 " + EST_FACTOR +
      "）；±30~40% 误差，仅覆盖带 ratio 的新客户端转录。";
  }

  function renderTraeEstimates() {
    var rows = filteredTraeEstimates();
    var visible = rows.length > 0;
    el.traeEstKpis.hidden = !visible;
    el.traeEstTableCard.hidden = !visible;
    if (!visible) return;

    var input = 0;
    var output = 0;
    var requests = 0;
    var models = new Set();
    rows.forEach(function (row) {
      input += row.est_input;
      output += row.est_output;
      requests += row.requests;
      models.add(row.model);
    });

    el.traeEstKpis.textContent = "";
    addKpiTo(el.traeEstKpis, "est 总 Token", fmtCompact(input + output),
      fmtInt(input + output), true);
    addKpiTo(el.traeEstKpis, "est 输入", fmtCompact(input), "hook 字符累积 ÷ 系数");
    addKpiTo(el.traeEstKpis, "est 输出", fmtCompact(output), "assistant / 工具响应字符 ÷ 系数");
    addKpiTo(el.traeEstKpis, "覆盖请求", fmtCompact(requests),
      "弱估算 · 模型 " + fmtInt(models.size));
    renderTraeEstTable(rows);
  }

  var TRAE_EST_COLUMNS = [
    { key: "day", label: "日期", type: "text" },
    { key: "model", label: "模型", type: "text" },
    { key: "est_input", label: "est 输入", type: "num" },
    { key: "est_output", label: "est 输出", type: "num" },
    { key: "chars_in", label: "上下文字符", type: "num" },
    { key: "chars_out", label: "输出字符", type: "num" },
    { key: "requests", label: "请求", type: "num" }
  ];

  function renderTraeEstTable(rows) {
    var sorted = rows.slice().sort(function (a, b) {
      if (a.day !== b.day) return a.day < b.day ? 1 : -1;
      return String(a.model).localeCompare(String(b.model), "zh-CN");
    });
    el.traeEstThead.textContent = "";
    var headerRow = document.createElement("tr");
    TRAE_EST_COLUMNS.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "th-btn";
      button.appendChild(document.createTextNode(column.label));
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    el.traeEstThead.appendChild(headerRow);

    el.traeEstTbody.textContent = "";
    var input = 0;
    var output = 0;
    var requests = 0;
    sorted.forEach(function (row) {
      input += row.est_input;
      output += row.est_output;
      requests += row.requests;
      var tr = document.createElement("tr");
      TRAE_EST_COLUMNS.forEach(function (column) {
        var td = document.createElement("td");
        if (column.type === "num") td.className = "num";
        if (column.type === "num") {
          td.textContent = fmtInt(row[column.key]);
          if (!number(row[column.key])) td.classList.add("zero");
        } else if (column.key === "model") {
          td.textContent = row.model;
          td.title = row.model;
        } else {
          td.textContent = row[column.key];
        }
        tr.appendChild(td);
      });
      el.traeEstTbody.appendChild(tr);
    });
    el.traeEstRowinfo.textContent = fmtInt(sorted.length) + " 行 · est 总 Token " +
      fmtInt(input + output) + " · " + fmtInt(requests) + " 请求";
    el.traeEstHint.textContent = TRAE_EST_NOTE + "；由 hook 事件字符数重放估算（" +
      TRAE_EST_FACTOR + "），仅覆盖安装 hook 后的请求，误差可能数倍且方向不定，" +
      "不可与 token 真值或额度相加。";
  }

  var QODER_TABS = ["activity", "credits", "est"];

  function qoderAvailability() {
    return {
      activity: filteredActivity().length > 0,
      credits: filteredCredits().length > 0,
      est: filteredEstimates().length > 0
    };
  }

  function syncSupplement(rerenderCharts) {
    var available = qoderAvailability();
    var qoderAny = QODER_TABS.some(function (name) { return available[name]; });
    var traeAny = filteredTraeEstimates().length > 0;
    var any = qoderAny || traeAny;
    el.qoderExtra.hidden = !any;
    if (!any) return;

    el.suppSourceTabs.hidden = !(qoderAny && traeAny);
    if (!qoderAny) state.suppSource = "trae-cn";
    else if (!traeAny) state.suppSource = "qoder";
    else if (state.suppSource !== "qoder" && state.suppSource !== "trae-cn") {
      state.suppSource = "qoder";
    }

    Array.prototype.forEach.call(el.suppSourceTabs.querySelectorAll("[data-supp-source]"), function (button) {
      var name = button.getAttribute("data-supp-source");
      var active = name === state.suppSource;
      button.disabled = name === "qoder" ? !qoderAny : !traeAny;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    el.qoderTabs.hidden = state.suppSource !== "qoder";
    el.traePanel.hidden = state.suppSource !== "trae-cn";

    if (qoderAny && !available[state.qoderTab]) {
      state.qoderTab = QODER_TABS.filter(function (name) { return available[name]; })[0];
    }
    Array.prototype.forEach.call(el.qoderTabs.querySelectorAll("[data-qoder-tab]"), function (button) {
      var name = button.getAttribute("data-qoder-tab");
      var active = name === state.qoderTab && state.suppSource === "qoder";
      button.disabled = !available[name];
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
    Array.prototype.forEach.call(el.qoderExtra.querySelectorAll("[data-qoder-panel]"), function (panel) {
      panel.hidden = state.suppSource !== "qoder" ||
        panel.getAttribute("data-qoder-panel") !== state.qoderTab;
    });
    if (rerenderCharts && state.suppSource === "qoder") {
      if (state.qoderTab === "activity") renderActivityChart(filteredActivity());
      if (state.qoderTab === "credits") renderCreditChart(filteredCredits());
    }
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
    if (ACTIVITY.length) {
      var note = document.createElement("p");
      note.textContent = "Qoder Agent 活动指标与 token 口径不同，不可相加；活动数据不参与等价成本计算。";
      el.footer.appendChild(note);
    }
    if (CREDITS.length) {
      var creditNote = document.createElement("p");
      creditNote.textContent = "Qoder credits 为服务端每请求计费真值；免费 credits 不计配额；" +
        "余额来自本地日志快照；非 token、不可与 token 相加。";
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
      traeNote.textContent = TRAE_EST_NOTE + "；仅覆盖安装 hook 后的请求，" +
        "误差可能数倍且方向不定，只适合看趋势，不可与 token 真值或额度相加。";
      el.footer.appendChild(traeNote);
    }
    var scope = document.createElement("p");
    scope.textContent = "数据范围 " + (DATA_SINCE || "—") + " ~ " + (DATA_UNTIL || "—") +
      " · " + fmtInt(ROWS.length) + " 行日/来源/模型/项目聚合" +
      (ACTIVITY.length ? " · " + fmtInt(ACTIVITY.length) + " 行活动聚合" : "") +
      (CREDITS.length ? " · " + fmtInt(CREDITS.length) + " 天额度" : "") +
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
      renderChart(filteredRows());
      if (!el.qoderExtra.hidden && state.suppSource === "qoder" &&
          state.qoderTab === "activity") {
        renderActivityChart(filteredActivity());
      }
      if (!el.qoderExtra.hidden && state.suppSource === "qoder" &&
          state.qoderTab === "credits") {
        renderCreditChart(filteredCredits());
      }
    }, 150);
  });

  function render() {
    var rows = filteredRows();
    renderKpis(rows);
    renderActivity();
    renderCredits();
    renderEstimates();
    renderTraeEstimates();
    syncSupplement(false);
    renderCoverage();
    renderChart(rows);
    renderBars(filteredRows("model"), filteredRows("project"));
    renderTable(rows);
    renderHint();
  }

  buildChips();
  buildControls();
  applyTheme(document.documentElement.dataset.theme || "light");
  if (el.activityMetric) el.activityMetric.value = state.activityMetric;
  el.generated.textContent = "生成于 " + fmtDateTime(DATA.generated_at);
  renderFooter();
  render();
})();
</script>
</body>
</html>
"""
