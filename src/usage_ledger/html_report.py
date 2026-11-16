from __future__ import annotations

import json
from datetime import datetime

from .models import ACTIVITY_FIELDS, FIELDS

PLACEHOLDER = "__USAGE_LEDGER_PAYLOAD__"

# token：源日志里逐调用 token 真值；credits：服务端逐请求计费真值（token 仅可估算）。
AGENT_KINDS = {
    "claude": "token",
    "codex": "token",
    "opencode": "token",
    "kilo": "token",
    "cline": "token",
    "qoder": "credits",
    "trae-cn": "credits",
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
.filter-shell{position:relative;z-index:20;display:flex;flex-direction:column;gap:10px}
.filter-shell.sticky-enabled{position:sticky;top:0;background:linear-gradient(var(--bg) 78%,transparent);padding-top:6px}
.filter-shell.stuck .presets,.filter-shell.stuck .chip-tip{display:none}
.filter-shell.stuck .dimension-line{grid-template-columns:minmax(0,1fr)}
.filter-shell.stuck .dimension-line .field:not(.search-field){display:none}
.filter-shell.stuck .filters{padding:10px 14px}
.filter-shell.stuck .agent-nav{padding:8px 14px}
.filters{display:flex;flex-direction:column;gap:12px}
.filter-line{display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center}
.date-line{flex-wrap:wrap}
.dimension-line{display:grid;grid-template-columns:220px 220px minmax(200px,1fr);gap:10px 14px;align-items:center}
.dimension-line .field{min-width:0;display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px;align-items:center;white-space:nowrap}
.dimension-line select,.dimension-line input[type="search"]{width:100%;max-width:none}
label.field{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12.5px}
input[type="date"],input[type="search"],select{
  background:var(--surface-2);color:var(--text);border:1px solid var(--border);border-radius:9px;
  padding:7px 9px;font:inherit;font-size:13px;outline:none;max-width:230px;
}
select{text-overflow:ellipsis}
#page-size,#page-jump,#activity-page-size{width:70px;max-width:70px}
#page-jump{width:76px;max-width:76px}
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
.kpi-group{margin-top:12px}
.kpi-group:first-child{margin-top:0}
.kpi-group-title{font-size:11px;letter-spacing:.4px;color:var(--muted);margin:0 0 8px}
.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.kpi-subgroup{grid-column:1/-1;font-size:11px;color:var(--muted);margin:2px 0 -4px}
.kpi-grid > .kpi:only-child{grid-column:1/-1}
.chart-panel+.chart-panel{margin-top:18px;padding-top:14px;border-top:1px solid var(--border)}
.chart-panel h3{font-size:12.5px;margin:0;letter-spacing:.2px}

.kpis{display:flex;flex-direction:column;gap:0}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:12px 14px;box-shadow:var(--shadow);min-width:0}
.kpi.primary{background:linear-gradient(135deg,var(--accent-soft),var(--surface) 72%);border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),var(--shadow)}
.kpi.shadow{border-style:dashed;background:transparent;box-shadow:none}
.kpi-label{font-size:12px;color:var(--muted)}
.kpi-value{font-size:clamp(19px,2vw,27px);font-weight:650;font-variant-numeric:tabular-nums;letter-spacing:-.3px;margin-top:2px;white-space:normal;overflow:visible;overflow-wrap:anywhere}
.kpi-sub{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;margin-top:2px;white-space:normal;overflow:visible;overflow-wrap:anywhere}
.kpi.credit .kpi-sub{white-space:normal;overflow:visible}
.coverage-block{padding:0}
.coverage-block summary{cursor:pointer;padding:13px 16px;font-size:13.5px;font-weight:600;list-style:none;display:flex;align-items:center;gap:8px}
.coverage-block summary::-webkit-details-marker{display:none}
.coverage-block summary::before{content:"▸";color:var(--muted);transition:transform .15s}
.coverage-block[open] summary::before{transform:rotate(90deg)}
.coverage-body{display:flex;flex-direction:column;gap:8px;padding:0 16px 16px}
.coverage-body p{margin:0}
.coverage{display:block;margin:0;padding:10px 14px;border:1px solid var(--accent);border-radius:12px;background:var(--accent-soft);color:var(--text);font-size:12.5px}
.trae-status{border-color:rgba(13,148,136,.45);background:rgba(13,148,136,.08);margin-top:-4px}
.trae-status.warn{border-color:rgba(245,158,11,.55);background:rgba(245,158,11,.1)}
.trae-status.error{border-color:rgba(239,68,68,.55);background:rgba(239,68,68,.1)}

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
.chart-wrap .axis-title{fill:var(--muted);font-size:10px;letter-spacing:.2px}
.empty{display:grid;place-items:center;min-height:200px;color:var(--muted);font-size:13px}
.empty-state{padding:28px 20px;text-align:center}
.empty-state h2{font-size:16px;margin:0 0 6px}
.empty-state p{margin:4px 0}
.empty-actions{display:flex;justify-content:center;gap:10px;flex-wrap:wrap;margin-top:14px}
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
.top-group-title{font-size:11px;letter-spacing:.4px;color:var(--muted);font-weight:600;margin:12px 0 5px}
.top-group-title:first-child{margin-top:0}
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
.table-wrap{overflow-x:auto;overflow-y:visible;border:1px solid var(--border);border-radius:10px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:12.5px;min-width:900px}
#detail-table{table-layout:fixed}
thead th{position:sticky;top:0;background:var(--surface-2);z-index:2;border-bottom:1px solid var(--border);padding:0;text-align:left;white-space:nowrap}
thead tr:nth-child(2) th{top:31px}
th.num{text-align:right}
th.group-head{font-size:11px;letter-spacing:.3px;color:var(--muted);font-weight:600;padding:7px 10px;text-align:center;border-left:1px solid var(--border)}
th.group-head:first-child{border-left:0}
.sticky-col{position:sticky;background:var(--surface);z-index:3}
thead .sticky-col{background:var(--surface-2);z-index:5}
tbody tr:hover .sticky-col{background:var(--surface-2)}
tfoot .sticky-col{background:var(--surface-2);z-index:3}
tfoot td{background:var(--surface-2);border-top:1px solid var(--border);padding:7px 10px;font-weight:600;white-space:nowrap}
tfoot td.zero{color:var(--muted);font-weight:400}
th.identity,td.identity{box-shadow:1px 0 0 var(--border)}
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
.activity-table-wrap td.sticky-col,.activity-table-wrap th.sticky-col{z-index:4}
.chart-wrap .hit:focus-visible{outline:2px solid var(--accent);outline-offset:-2px;stroke:var(--accent);stroke-width:1}
.top-sort-note{font-size:11px;white-space:nowrap}
.filter-toggle,.sheet-close{display:none}
.back-top{position:fixed;right:18px;bottom:18px;z-index:45;box-shadow:var(--shadow);background:var(--surface)}
.filter-shell.sheet{position:fixed;inset:0;z-index:60;overflow:auto;background:var(--bg);padding:16px;display:flex;flex-direction:column;gap:12px}
.filter-shell.sheet .sheet-close{display:inline-flex;align-self:flex-end}
body.sheet-open{overflow:hidden}
.quota-kpi .kpi-sub{white-space:normal;overflow:visible}
.quota-track{height:6px;border-radius:999px;background:var(--surface-2);overflow:hidden;margin-top:9px}
.quota-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#22c1a4)}
.quota-fill.warn{background:linear-gradient(90deg,#f59e0b,#ef4444)}
footer{padding:4px 4px 0;color:var(--muted);font-size:11.5px}
footer p{margin:3px 0}
@media (max-width:1100px){
  .kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
}
@media (max-width:940px){
  .grid{grid-template-columns:1fr}
  .chart-card{grid-column:auto}
  .dimension-line{grid-template-columns:1fr 1fr}
  .dimension-line .search-field{grid-column:1/-1}
}
@media (max-width:640px){
  main{padding:8px 14px 32px}
  .topbar{padding:16px 14px 8px}
  .filter-shell.sticky-enabled{position:static;background:none;padding-top:0}
  .filter-toggle{display:inline-flex;position:sticky;top:8px;left:auto;bottom:auto;align-self:flex-start;z-index:45;box-shadow:var(--shadow);background:var(--surface)}
  .filter-shell{display:none}
  .filter-shell.sheet{display:flex}
  .sheet-close{display:inline-flex;align-self:flex-end}
  .filter-shell .filters,.filter-shell .agent-nav{max-width:100%}
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
  .kpi{padding:10px}
  .kpi-value{font-size:19px}
  .kpi-sub{font-size:11px}
  .table-wrap{max-height:60vh;overflow:auto}
  .table-wrap .sticky-wide{position:static!important;left:auto!important;box-shadow:none!important}
  .back-top{bottom:66px}
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
    <span id="data-until" class="muted"></span>
    <button id="theme" class="btn ghost small" type="button">深色模式</button>
  </div>
</header>

<main>
  <button id="filter-toggle" class="btn filter-toggle" type="button"
          aria-controls="filter-shell" aria-expanded="false">筛选</button>
  <div class="filter-shell" id="filter-shell">
    <section class="card filters" id="filters" aria-label="筛选">
      <button id="sheet-close" class="btn ghost small sheet-close" type="button">关闭筛选</button>
      <div class="filter-line date-line">
        <label class="field">起 <input type="date" id="start"></label>
        <label class="field">止 <input type="date" id="end"></label>
        <div class="presets" id="presets"></div>
        <label class="switch" id="focus-range-field">
          <input type="checkbox" id="focus-range">
          <span class="switch-track" aria-hidden="true"></span>
          <span>聚焦有数据区间</span>
        </label>
        <span id="focus-note" class="muted" aria-live="polite"></span>
        <button id="reset" class="btn ghost small" type="button">重置筛选</button>
      </div>
      <div class="filter-line dimension-line">
        <label class="field">模型 <select id="model" aria-label="模型筛选"></select></label>
        <label class="field">项目 <select id="project" aria-label="项目筛选"></select></label>
        <label class="field search-field">搜索 <input type="search" id="q" placeholder="日期 / 模型 / 项目" aria-label="搜索明细"></label>
      </div>
    </section>

    <nav class="card agent-nav" id="agent-nav" aria-label="Agent 选择"></nav>
  </div>

  <details class="card coverage-block" id="coverage-block">
    <summary>口径与数据覆盖</summary>
    <div class="coverage-body">
      <p id="coverage" class="coverage" hidden></p>
      <p id="trae-status" class="coverage trae-status" hidden></p>
      <div id="coverage-extra"></div>
      <p id="generated" class="muted"></p>
    </div>
  </details>

  <section class="agent-page" id="report-page" aria-label="用量报告">
    <section class="card empty-state" id="empty-state" hidden>
      <h2 id="empty-title">当前区间无数据</h2>
      <p id="empty-message" class="muted"></p>
      <p id="empty-quota" class="muted" hidden></p>
      <div class="empty-actions">
        <button id="empty-all" class="btn" type="button">查看全部</button>
        <button id="empty-shadow" class="btn ghost" type="button" hidden>打开影子估算</button>
        <button id="empty-reset" class="btn ghost" type="button">重置筛选</button>
      </div>
    </section>
    <section class="kpis" id="kpis" aria-label="汇总指标"></section>
    <section class="grid" id="report-grid" style="margin-top:16px">
      <div class="card chart-card">
        <div class="card-head"><h2>每日用量</h2></div>
        <div class="chart-panel" id="panel-token">
          <div class="card-head">
            <div class="head-tags"><h3>Token</h3><span class="unit-tag">tokens</span></div>
            <label class="field" id="metric-field">Token 指标
              <select id="metric" aria-label="Token 指标">
                <option value="total">总量</option>
                <option value="input">输入</option>
                <option value="output">输出</option>
                <option value="cache_read">缓存读</option>
                <option value="cache_write">缓存写</option>
                <option value="reasoning">推理</option>
              </select>
            </label>
          </div>
          <div class="legend" id="legend-token"></div>
          <div class="chart-wrap">
            <div id="chart-token"></div>
            <div id="tooltip-token" class="tooltip"></div>
          </div>
          <p class="muted" id="hint-token" style="margin:8px 0 0"></p>
        </div>
        <div class="chart-panel" id="panel-credits" hidden>
          <div class="card-head">
            <div class="head-tags"><h3>Credits</h3><span class="unit-tag">credits</span></div>
            <label class="switch" id="shadow-switch" hidden>
              <input type="checkbox" id="shadow" aria-label="显示 Qoder 影子估算">
              <span class="switch-track" aria-hidden="true"></span>
              <span>影子：Qoder 估算 token</span>
            </label>
          </div>
          <div class="legend" id="legend-credits"></div>
          <div class="chart-wrap">
            <div id="chart-credits"></div>
            <div id="tooltip-credits" class="tooltip"></div>
          </div>
          <p class="muted" id="hint-credits" style="margin:8px 0 0"></p>
        </div>
        <div class="chart-panel" id="panel-est" hidden>
          <div class="card-head"><div class="head-tags"><h3>Trae 弱估算</h3><span class="unit-tag">估算 tokens</span></div></div>
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
          <span class="muted top-sort-note" id="model-note" title="点击筛选 / 再点取消"></span>
        </div>
        <div class="bars" id="models"></div>
      </div>
      <div class="card">
        <div class="card-head">
          <div class="head-tags"><h2>项目 Top 8</h2><span class="unit-tag" id="project-unit"></span></div>
          <span class="muted top-sort-note" id="project-note" title="点击筛选 / 再点取消"></span>
        </div>
        <div class="bars" id="projects"></div>
      </div>
    </section>

    <section class="card table-card" id="token-table" style="margin-top:16px">
      <div class="card-head">
        <h2>明细</h2>
        <span class="muted" id="rowinfo"></span>
      </div>
      <div class="table-wrap" id="table-wrap">
        <table id="detail-table">
          <colgroup id="colgroup"></colgroup>
          <thead id="thead"></thead>
          <tbody id="tbody"></tbody>
          <tfoot id="tfoot"></tfoot>
        </table>
      </div>
      <div class="pager">
        <label class="field">每页
          <select id="page-size" aria-label="每页行数">
            <option value="25">25</option>
            <option value="50">50</option>
            <option value="100">100</option>
          </select>
        </label>
        <button id="prev" type="button">上一页</button>
        <span id="pageinfo" class="muted"></span>
        <label class="field">跳至
          <input id="page-jump" type="number" min="1" inputmode="numeric" aria-label="跳转页码">
        </label>
        <button id="page-jump-go" type="button">跳转</button>
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
        <section class="kpi-grid" id="activity-kpis" aria-label="Qoder 活动指标"></section>
        <div class="legend" id="activity-legend"></div>
        <div class="chart-wrap">
          <div id="activity-chart"></div>
          <div id="activity-tooltip" class="tooltip"></div>
        </div>
        <p class="muted" id="activity-hint" style="margin:0"></p>
        <div class="table-wrap activity-table-wrap">
          <table id="activity-table">
            <thead id="activity-thead"></thead>
            <tbody id="activity-tbody"></tbody>
          </table>
        </div>
        <div class="pager">
          <label class="field">每页
            <select id="activity-page-size" aria-label="活动每页行数">
              <option value="30">30</option>
              <option value="50">50</option>
              <option value="100">100</option>
            </select>
          </label>
          <button id="activity-prev" type="button">上一页</button>
          <span id="activity-pageinfo" class="muted"></span>
          <button id="activity-next" type="button">下一页</button>
        </div>
        <p class="muted" id="activity-rowinfo" style="margin:0;text-align:right"></p>
      </div>
    </details>
  </section>

</main>
<button id="back-top" class="btn back-top" type="button" hidden>回到顶部</button>

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
                          assistant_with_metrics: "带指标", turns: "轮次",
                          tool_calls: "工具调用", duration_ms: "运行时长" };
  var KNOWN_COLORS = { claude: "#d97706", codex: "#0ea5e9", opencode: "#7c3aed",
                       kilo: "#10b981", cline: "#65a30d", qoder: "#e11d48", "trae-cn": "#0d9488" };
  var PALETTE = ["#ef4444", "#f59e0b", "#14b8a6", "#6366f1"];
  var KNOWN_ORDER = ["claude", "codex", "opencode", "kilo", "cline", "qoder", "trae-cn"];
  var AGENT_KINDS = DATA.agents || {};
  var KIND_LABELS = { token: "精确 Token", credits: "精确 Credits", estimate: "仅估算" };
  var AGENT_LABELS = { claude: "Claude", codex: "Codex", opencode: "OpenCode",
                       kilo: "Kilo", cline: "Cline", qoder: "Qoder", "trae-cn": "Trae CN" };
  var DISPLAY_NAMES = { "trae-cn": "Trae CN", qoder: "Qoder", turns: "记录数",
                        est: "估算", used: "已用", sessions: "会话",
                        assistant_calls: "assistant 调用" };
  var METRIC_KEYS = ["total", "input", "output", "cache_read", "cache_write", "reasoning"];
  var ACTIVITY_METRIC_KEYS = ["tool_calls", "sessions", "prompts", "assistant_calls"];
  var PAGE_SIZES = [25, 50, 100];
  var ACTIVITY_PAGE_SIZES = [30, 50, 100];
  var STATE_KEY = "usage-ledger-state";

  function displayName(key) {
    return Object.prototype.hasOwnProperty.call(DISPLAY_NAMES, key)
      ? DISPLAY_NAMES[key] : String(key);
  }

  function modelLabel(key) {
    if (key === "-" || key === "unknown") return "（未标注）";
    return displayName(key);
  }

  function sourceLabel(source) {
    return Object.prototype.hasOwnProperty.call(AGENT_LABELS, source)
      ? AGENT_LABELS[source] : String(source);
  }
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
      day: row.day, source: row.source || "qoder", model: row.model || "unknown",
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
  CREDIT_ROWS.forEach(function (row) { present[row.source] = true; });
  if (EST.length || ACTIVITY.length) present.qoder = true;
  if (TRAE_EST.length) present["trae-cn"] = true;
  var AGENTS = KNOWN_ORDER.filter(function (name) { return present[name]; })
    .concat(Object.keys(present).filter(function (name) {
      return KNOWN_ORDER.indexOf(name) < 0;
    }).sort());
  var TOKEN_AGENTS = AGENTS.filter(function (name) { return agentKind(name) === "token"; });
  var CREDIT_AGENTS = AGENTS.filter(function (name) { return agentKind(name) === "credits"; });
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
  var creditBoundsBySource = {};
  CREDIT_AGENTS.forEach(function (name) {
    creditBoundsBySource[name] = minMaxDay(CREDIT_ROWS.filter(function (row) {
      return row.source === name;
    }));
  });
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
  var PICK_MAX = DATA_UNTIL || TODAY;

  function allBounds() {
    if (!DATA_SINCE || !DATA_UNTIL) return { start: DATA_SINCE, end: DATA_UNTIL };
    return { start: DATA_SINCE, end: DATA_UNTIL };
  }

  function selectedTokenAgents() {
    return TOKEN_AGENTS.filter(function (name) { return state.agents.has(name); });
  }
  function selectedCreditAgents() {
    return CREDIT_AGENTS.filter(function (name) { return state.agents.has(name); });
  }
  function hasTokenSelected() { return selectedTokenAgents().length > 0; }
  function hasCreditsSelected() { return selectedCreditAgents().length > 0; }
  function hasCreditAgent(name) {
    return state.agents.has(name) && agentKind(name) === "credits";
  }
  function hasTraeEstimateSelected() {
    return state.agents.has("trae-cn") && TRAE_EST.length > 0;
  }
  function hasQoderShadowSelected() {
    return state.shadow && state.agents.has("qoder") && EST.length > 0;
  }

  var initialRange = defaultDateRange(DATA_SINCE, DATA_UNTIL, TODAY);
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
    focusRange: false,
    sortKey: "day",
    sortDir: "desc",
    activitySortKey: "day",
    activitySortDir: "desc",
    page: 0,
    pageSize: 50,
    activityPage: 0,
    activityPageSize: 30
  };

  function normalizeAgentKeys(raw, allowed) {
    return String(raw || "").split(",").map(function (name) {
      return name.trim();
    }).filter(function (name) { return allowed.indexOf(name) >= 0; });
  }

  function normalizePageSize(raw, allowed, fallback) {
    var size = parseInt(raw, 10);
    return allowed.indexOf(size) >= 0 ? size : fallback;
  }

  function readPersistedState() {
    var params = new URLSearchParams((location.hash || "").replace(/^#/, ""));
    var hasHash = Array.from(params.keys()).length > 0;
    if (hasHash) {
      var fromHash = {};
      params.forEach(function (value, key) { fromHash[key] = value; });
      return fromHash;
    }
    try {
      var raw = localStorage.getItem(STATE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function applyPersistedState(target, raw, fallback) {
    if (!raw || typeof raw !== "object") return;
    var start = String(raw.start || "");
    var end = String(raw.end || "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(start) && /^\d{4}-\d{2}-\d{2}$/.test(end)) {
      var range = clampDateRange(start, end, DATA_SINCE, DATA_UNTIL, TODAY);
      target.start = range.start;
      target.end = range.end;
    }
    var agents = normalizeAgentKeys(raw.agents, AGENTS);
    if (agents.length) target.agents = new Set(agents);
    ["model", "project", "q"].forEach(function (key) {
      if (typeof raw[key] === "string") {
        target[key] = raw[key].slice(0, key === "q" ? 120 : 200);
      }
    });
    target.q = target.q.toLowerCase();
    if (METRIC_KEYS.indexOf(raw.metric) >= 0) target.metric = raw.metric;
    if (ACTIVITY_METRIC_KEYS.indexOf(raw.activityMetric) >= 0) {
      target.activityMetric = raw.activityMetric;
    }
    target.shadow = raw.shadow === true || raw.shadow === "1";
    target.focusRange = raw.focusRange === true || raw.focusRange === "1";
    ["sortKey", "activitySortKey"].forEach(function (key) {
      if (typeof raw[key] === "string" && raw[key]) target[key] = raw[key];
    });
    target.sortDir = raw.sortDir === "asc" ? "asc" : "desc";
    target.activitySortDir = raw.activitySortDir === "asc" ? "asc" : "desc";
    var page = parseInt(raw.page, 10);
    if (isFinite(page) && page >= 0) target.page = page;
    var activityPage = parseInt(raw.activityPage, 10);
    if (isFinite(activityPage) && activityPage >= 0) target.activityPage = activityPage;
    target.pageSize = normalizePageSize(raw.pageSize, PAGE_SIZES, target.pageSize);
    target.activityPageSize = normalizePageSize(
      raw.activityPageSize, ACTIVITY_PAGE_SIZES, target.activityPageSize);
    target.focusRange = target.focusRange && hasFocusableData();
  }

  function stateSnapshot() {
    return {
      start: state.start, end: state.end,
      agents: Array.from(state.agents).join(","),
      model: state.model, project: state.project, q: state.q,
      metric: state.metric, activityMetric: state.activityMetric,
      shadow: state.shadow, focusRange: state.focusRange,
      sortKey: state.sortKey, sortDir: state.sortDir,
      activitySortKey: state.activitySortKey, activitySortDir: state.activitySortDir,
      page: state.page, pageSize: state.pageSize,
      activityPage: state.activityPage, activityPageSize: state.activityPageSize
    };
  }

  function persistState() {
    var snapshot = stateSnapshot();
    try { localStorage.setItem(STATE_KEY, JSON.stringify(snapshot)); } catch (e) {}
    try {
      var params = new URLSearchParams();
      Object.keys(snapshot).forEach(function (key) {
        params.set(key, snapshot[key]);
      });
      history.replaceState(null, "", "#" + params.toString());
    } catch (e) {}
  }

  applyPersistedState(state, readPersistedState(), initialRange);

  var el = {
    start: $("#start"), end: $("#end"), presets: $("#presets"), reset: $("#reset"),
    focusRange: $("#focus-range"), focusNote: $("#focus-note"),
    filterShell: $("#filter-shell"), filterToggle: $("#filter-toggle"),
    sheetClose: $("#sheet-close"), backTop: $("#back-top"),
    model: $("#model"), project: $("#project"), q: $("#q"),
    nav: $("#agent-nav"), coverage: $("#coverage"), traeStatus: $("#trae-status"),
    coverageBlock: $("#coverage-block"), coverageExtra: $("#coverage-extra"),
    dataUntil: $("#data-until"),
    emptyState: $("#empty-state"), emptyTitle: $("#empty-title"),
    emptyMessage: $("#empty-message"), emptyQuota: $("#empty-quota"),
    emptyAll: $("#empty-all"), emptyShadow: $("#empty-shadow"),
    emptyReset: $("#empty-reset"), reportGrid: $("#report-grid"),
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
    modelNote: $("#model-note"), projectNote: $("#project-note"),
    models: $("#models"), projects: $("#projects"),
    thead: $("#thead"), tbody: $("#tbody"), tfoot: $("#tfoot"),
    colgroup: $("#colgroup"), table: $("#detail-table"), tableWrap: $("#table-wrap"),
    rowinfo: $("#rowinfo"), tokenTable: $("#token-table"),
    pageinfo: $("#pageinfo"), prev: $("#prev"), next: $("#next"),
    pageSize: $("#page-size"), pageJump: $("#page-jump"), pageJumpGo: $("#page-jump-go"),
    shadowNote: $("#shadow-note"),
    activityBlock: $("#activity-block"), activityKpis: $("#activity-kpis"),
    activityMetric: $("#activity-metric"), activityLegend: $("#activity-legend"),
    activityChart: $("#activity-chart"), activityTooltip: $("#activity-tooltip"),
    activityHint: $("#activity-hint"), activityThead: $("#activity-thead"),
    activityTbody: $("#activity-tbody"), activityRowinfo: $("#activity-rowinfo"),
    activityPageSize: $("#activity-page-size"), activityPrev: $("#activity-prev"),
    activityNext: $("#activity-next"), activityPageinfo: $("#activity-pageinfo"),
    generated: $("#generated"), theme: $("#theme")
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
    if (value === null || value === undefined) return "—";
    var parsed = number(value);
    return Math.abs(parsed - Math.round(parsed)) < 0.005
      ? fmtInt(parsed) : parsed.toFixed(2);
  }

  function fmtQuota(value) {
    return fmtCredits(value);
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

  function defaultDateRange(dataSince, dataUntil, today) {
    var end = dataUntil || today;
    var start = addDays(end, -6);
    if (dataSince && start < dataSince) start = dataSince;
    return { start: start, end: end };
  }

  function presetDateRange(kind, days, dataSince, dataUntil, today) {
    var end = dataUntil || today;
    if (kind === "latest") return { start: end, end: end };
    if (kind === "all") return { start: dataSince || "", end: dataUntil || "" };
    var start = addDays(end, -(number(days || 7) - 1));
    if (dataSince && start < dataSince) start = dataSince;
    return { start: start, end: end };
  }

  function clampDateRange(start, end, dataSince, dataUntil, today) {
    var lo = dataSince || "";
    var hi = dataUntil || today;
    if (!start) start = lo || hi;
    if (!end) end = hi;
    if (lo && start < lo) start = lo;
    if (lo && end < lo) end = lo;
    if (hi && start > hi) start = hi;
    if (hi && end > hi) end = hi;
    if (start > end) end = start;
    return { start: start, end: end };
  }

  function activityBuckets(rows, start, end, fields) {
    var days = enumerateDays(start, end);
    if (!days.length) return [];
    var weekly = days.length > 200;
    var buckets = [];
    var index = new Map();
    days.forEach(function (day) {
      var key = weekly ? weekStart(day) : day;
      if (!index.has(key)) {
        var values = {};
        (fields || []).forEach(function (field) { values[field] = 0; });
        var bucket = { key: key, start: day, end: day, values: values };
        index.set(key, bucket);
        buckets.push(bucket);
      } else {
        index.get(key).end = day;
      }
    });
    (rows || []).forEach(function (row) {
      var key = weekly ? weekStart(row.day) : row.day;
      var bucket = index.get(key);
      if (!bucket) return;
      (fields || []).forEach(function (field) {
        bucket.values[field] += number(row[field]);
      });
    });
    buckets.forEach(function (bucket) {
      bucket.label = bucket.start.slice(5);
      bucket.tooltip = weekly ? bucket.start + " ~ " + bucket.end : bucket.start;
    });
    return buckets;
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
      if (!map.has(name)) map.set(name, { key: name, total: 0, turns: 0, rows: 0 });
      var entry = map.get(name);
      entry.total += number(row.total);
      entry.turns += number(row.turns);
      entry.rows += 1;
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
    return CREDIT_ROWS.filter(function (row) {
      return state.agents.has(row.source) && matchesFilters(row, ignore);
    });
  }

  function qoderEstRowsFor(ignore) {
    if (!hasQoderShadowSelected()) return [];
    return EST.filter(function (row) { return matchesFilters(row, ignore); });
  }

  function traeRowsFor(ignore) {
    if (!state.agents.has("trae-cn")) return [];
    return TRAE_EST.filter(function (row) { return matchesFilters(row, ignore); });
  }

  function dimensionRows(ignore) {
    var rows = TOKEN_ROWS.filter(function (row) {
      return state.agents.has(row.source) && matchesFilters(row, ignore);
    });
    if (hasCreditsSelected()) {
      rows = rows.concat(CREDIT_ROWS.filter(function (row) {
        return state.agents.has(row.source) && matchesFilters(row, ignore);
      }).map(function (row) {
        return { day: row.day, source: row.source, model: row.model,
                 project: row.project, total: row.credits, turns: 0 };
      }));
    }
    if (state.agents.has("trae-cn")) {
      rows = rows.concat(TRAE_EST.filter(function (row) {
        return matchesFilters(row, ignore);
      }));
    }
    return rows;
  }

  function pageMetric(row) {
    if (state.metric === "total") return number(row.total);
    return number(row[state.metric]);
  }

  function navTotal(agent) {
    if (agent === "all") {
      return TOKEN_ROWS.reduce(function (acc, row) {
        return acc + (matchesFilters(row) ? number(row.total) : 0);
      }, 0);
    }
    var kind = agentKind(agent);
    if (kind === "credits") {
      return CREDIT_ROWS.reduce(function (acc, row) {
        return acc + (row.source === agent && matchesFilters(row) ? number(row.credits) : 0);
      }, 0);
    }
    if (kind === "estimate") {
      return TRAE_EST.reduce(function (acc, row) {
        return acc + (matchesFilters(row) ? number(row.total) : 0);
      }, 0);
    }
    return TOKEN_ROWS.reduce(function (acc, row) {
      return acc + (row.source === agent && matchesFilters(row) ? number(row.total) : 0);
    }, 0);
  }

  function navHasRows(agent) {
    if (agent === "all") return TOKEN_ROWS.some(function (row) { return matchesFilters(row); });
    var kind = agentKind(agent);
    if (kind === "credits") {
      return CREDIT_ROWS.some(function (row) {
        return row.source === agent && matchesFilters(row);
      });
    }
    if (kind === "estimate") {
      return TRAE_EST.some(function (row) { return matchesFilters(row); });
    }
    return TOKEN_ROWS.some(function (row) {
      return row.source === agent && matchesFilters(row);
    });
  }

  function navTotalText(agent) {
    if (!navHasRows(agent)) return "—";
    var value = navTotal(agent);
    var kind = agent === "all" ? "token" : agentKind(agent);
    if (kind === "credits") return fmtCompact(value) + " cr";
    if (kind === "estimate") return fmtCompact(value) + " 估算";
    return fmtCompact(value);
  }

  function syncAgentTotals() {
    Array.prototype.forEach.call(el.nav.querySelectorAll("[data-agent]"), function (button) {
      var small = button.querySelector("small");
      if (small) small.textContent = navTotalText(button.dataset.agent);
      button.title = sourceLabel(button.dataset.agent) + " · " +
        KIND_LABELS[agentKind(button.dataset.agent)] +
        "，数字为当前区间汇总；单击只看，再次单击恢复全部；⌘/Ctrl/Shift+单击多选";
    });
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
    state.page = 0;
    refreshFocusAfterFilterChange();
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
      button.title = sourceLabel(agent) + " · " + KIND_LABELS[agentKind(agent)] +
        "，单击只看，再次单击恢复全部；⌘/Ctrl/Shift+单击多选";
      var dot = document.createElement("span");
      dot.className = "dot";
      dot.style.background = COLORS[agent];
      var name = document.createElement("span");
      name.textContent = sourceLabel(agent);
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
      ? "单击只看 · ⌘+单击多选；tokens / credits / 估算分别汇总"
      : "单击只看 · Ctrl+单击多选；tokens / credits / 估算分别汇总";
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

  function fillSelect(select, options, allLabel, labelFn, emptyLabel) {
    select.textContent = "";
    var all = document.createElement("option");
    all.value = "";
    all.textContent = allLabel;
    select.appendChild(all);
    options.forEach(function (option) {
      var item = document.createElement("option");
      item.value = option.key;
      item.textContent = labelFn(option.key) + " · " + fmtInt(option.rows) + " 行";
      select.appendChild(item);
    });
    if (!options.length && emptyLabel) {
      var empty = document.createElement("option");
      empty.value = "";
      empty.textContent = emptyLabel;
      empty.disabled = true;
      select.appendChild(empty);
    }
  }

  function rebuildDimensionSelects() {
    var models = groupTotals(dimensionRows("model"), "model")
      .filter(function (item) { return item.rows > 0; }).sort(byTotal);
    var projects = groupTotals(dimensionRows("project"), "project")
      .filter(function (item) { return item.rows > 0; }).sort(byTotal);
    fillSelect(el.model, models, "全部模型", modelLabel,
               "无可用模型");
    fillSelect(el.project, projects, "全部项目", function (key) {
      return key === "-" ? "（未标注）" : key;
    }, "无可用项目");
    if (!models.some(function (item) { return item.key === state.model; })) state.model = "";
    if (!projects.some(function (item) { return item.key === state.project; })) state.project = "";
    el.model.value = state.model;
    el.project.value = state.project;
    el.model.title = el.model.selectedOptions.length
      ? el.model.selectedOptions[0].textContent : "全部模型";
    el.project.title = el.project.selectedOptions.length
      ? el.project.selectedOptions[0].textContent : "全部项目";
  }

  function syncDateInputs() {
    el.start.value = state.start || "";
    el.end.value = state.end || "";
  }

  function matchesDimensionFilters(row) {
    if (state.model && row.model !== state.model) return false;
    if (state.project && row.project !== state.project) return false;
    return matchesQuery(row);
  }

  function focusRows() {
    var rows = [];
    if (hasTokenSelected()) {
      rows = rows.concat(TOKEN_ROWS.filter(function (row) {
        return state.agents.has(row.source) && matchesDimensionFilters(row);
      }));
    }
    if (hasCreditsSelected()) {
      rows = rows.concat(CREDIT_ROWS.filter(function (row) {
        return state.agents.has(row.source) && matchesDimensionFilters(row);
      }));
    }
    if (state.shadow && state.agents.has("qoder")) {
      rows = rows.concat(EST.filter(function (row) {
        return matchesDimensionFilters(row);
      }));
    }
    if (state.agents.has("trae-cn")) {
      rows = rows.concat(TRAE_EST.filter(function (row) {
        return matchesDimensionFilters(row);
      }));
    }
    return rows;
  }

  function focusBounds() {
    return minMaxDay(focusRows());
  }

  function hasFocusableData() {
    var bounds = focusBounds();
    return !!(bounds[0] && bounds[1]);
  }

  function syncFocusControls() {
    var bounds = focusBounds();
    var available = !!(bounds[0] && bounds[1]);
    el.focusRange.disabled = !available;
    el.focusRange.checked = state.focusRange && available;
    el.focusRange.title = available
      ? "把范围收缩到有数据的最早 / 最晚日"
      : "所选 Agent / 模型 / 项目没有可用数据";
    if (state.focusRange && available) {
      el.focusNote.textContent = "聚焦 " + bounds[0] + " ~ " + bounds[1];
    } else if (!available) {
      el.focusNote.textContent = "无可聚焦的数据区间";
    } else {
      el.focusNote.textContent = "";
    }
  }

  function refreshFocusAfterFilterChange() {
    if (!state.focusRange) {
      syncFocusControls();
      return;
    }
    var bounds = focusBounds();
    if (!bounds[0] || !bounds[1]) {
      state.focusRange = false;
      el.focusRange.checked = false;
      syncFocusControls();
      return;
    }
    state.start = bounds[0];
    state.end = bounds[1];
    syncDateInputs();
    syncFocusControls();
  }

  function applyFocusRange(enable) {
    state.focusRange = !!enable;
    if (state.focusRange) {
      var bounds = focusBounds();
      if (!bounds[0] || !bounds[1]) {
        state.focusRange = false;
        syncFocusControls();
        return;
      }
      state.start = bounds[0];
      state.end = bounds[1];
    } else {
      var range = defaultDateRange(DATA_SINCE, DATA_UNTIL, TODAY);
      state.start = range.start;
      state.end = range.end;
    }
    state.page = 0;
    syncDateInputs();
    rebuildDimensionSelects();
    syncFocusControls();
    renderAll();
  }

  function updateChrome() {
    var scrollY = window.scrollY || document.documentElement.scrollTop || 0;
    var tall = document.documentElement.scrollHeight > window.innerHeight + 240;
    el.filterShell.classList.toggle("sticky-enabled", tall && window.innerWidth > 640);
    el.filterShell.classList.toggle("stuck", scrollY > 120);
    el.backTop.hidden = !(tall && scrollY > 420);
  }

  function openFilterSheet(open) {
    el.filterShell.classList.toggle("sheet", open);
    document.body.classList.toggle("sheet-open", open);
    el.filterToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      var focusable = el.filterShell.querySelector("input,select,button");
      if (focusable) focusable.focus({ preventScroll: true });
    }
  }

  function buildControls() {
    el.start.min = DATA_SINCE || "";
    el.start.max = PICK_MAX;
    el.end.min = DATA_SINCE || "";
    el.end.max = PICK_MAX;
    syncDateInputs();
    el.q.value = state.q;

    [{ label: "最新", kind: "latest" }, { label: "全部", kind: "all" },
     { label: "近 7 天", days: 7 },
     { label: "近 30 天", days: 30 }, { label: "近 90 天", days: 90 }].forEach(function (preset) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn ghost small";
      button.textContent = preset.label;
      button.addEventListener("click", function () {
        var range = presetDateRange(preset.kind, preset.days, DATA_SINCE, DATA_UNTIL, TODAY);
        state.start = range.start;
        state.end = range.end;
        state.focusRange = false;
        el.focusRange.checked = false;
        syncDateInputs();
        syncFocusControls();
        state.page = 0;
        rebuildDimensionSelects();
        renderAll();
      });
      el.presets.appendChild(button);
    });

    el.start.addEventListener("change", onDateChange);
    el.end.addEventListener("change", onDateChange);
    el.model.addEventListener("change", function () {
      state.model = el.model.value;
      state.page = 0;
      refreshFocusAfterFilterChange();
      rebuildDimensionSelects();
      renderAll();
    });
    el.project.addEventListener("change", function () {
      state.project = el.project.value;
      state.page = 0;
      refreshFocusAfterFilterChange();
      rebuildDimensionSelects();
      renderAll();
    });

    var searchTimer;
    el.q.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.q = el.q.value.trim().toLowerCase();
        state.page = 0;
        refreshFocusAfterFilterChange();
        rebuildDimensionSelects();
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
      refreshFocusAfterFilterChange();
      renderAll();
    });
    el.activityMetric.addEventListener("change", function () {
      state.activityMetric = el.activityMetric.value;
      state.activityPage = 0;
      renderActivity();
    });
    el.activityBlock.addEventListener("toggle", function () {
      if (el.activityBlock.open) renderActivity();
    });

    el.reset.addEventListener("click", resetFilters);
    el.emptyAll.addEventListener("click", function () {
      state.start = DATA_SINCE;
      state.end = DATA_UNTIL;
      state.focusRange = false;
      el.focusRange.checked = false;
      syncDateInputs();
      syncFocusControls();
      state.page = 0;
      rebuildDimensionSelects();
      renderAll();
    });
    el.emptyReset.addEventListener("click", resetFilters);
    el.emptyShadow.addEventListener("click", function () {
      state.shadow = true;
      el.shadow.checked = true;
      refreshFocusAfterFilterChange();
      renderAll();
    });
    el.prev.addEventListener("click", function () {
      if (state.page > 0) { state.page -= 1; renderAll(); }
    });
    el.next.addEventListener("click", function () { state.page += 1; renderAll(); });
    el.pageSize.value = String(state.pageSize);
    el.pageSize.addEventListener("change", function () {
      state.pageSize = parseInt(el.pageSize.value, 10) || 50;
      state.page = 0;
      renderAll();
    });
    function jumpToPage() {
      var page = parseInt(el.pageJump.value, 10);
      if (!isFinite(page)) return;
      state.page = Math.max(0, page - 1);
      renderAll();
    }
    el.pageJumpGo.addEventListener("click", jumpToPage);
    el.pageJump.addEventListener("keydown", function (event) {
      if (event.key === "Enter") jumpToPage();
    });
    el.activityPageSize.value = String(state.activityPageSize);
    el.activityPageSize.addEventListener("change", function () {
      state.activityPageSize = parseInt(el.activityPageSize.value, 10) || 30;
      state.activityPage = 0;
      renderActivity();
    });
    el.activityPrev.addEventListener("click", function () {
      if (state.activityPage > 0) { state.activityPage -= 1; renderActivity(); }
    });
    el.activityNext.addEventListener("click", function () {
      state.activityPage += 1;
      renderActivity();
    });
    el.focusRange.addEventListener("change", function () {
      applyFocusRange(el.focusRange.checked);
    });
    el.filterToggle.addEventListener("click", function () {
      openFilterSheet(!el.filterShell.classList.contains("sheet"));
    });
    el.sheetClose.addEventListener("click", function () { openFilterSheet(false); });
    el.backTop.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && el.filterShell.classList.contains("sheet")) {
        openFilterSheet(false);
      }
    });
    window.addEventListener("scroll", updateChrome, { passive: true });
    updateChrome();
  }

  function onDateChange(event) {
    var start = el.start.value;
    var end = el.end.value;
    if (!start) start = DATA_SINCE;
    if (!end) end = DATA_UNTIL;
    if (start && end && start > end) {
      if (event.target === el.start) end = start;
      else start = end;
    }
    var range = clampDateRange(start, end, DATA_SINCE, DATA_UNTIL, TODAY);
    el.start.value = range.start;
    el.end.value = range.end;
    state.start = range.start;
    state.end = range.end;
    state.focusRange = false;
    el.focusRange.checked = false;
    syncFocusControls();
    state.page = 0;
    rebuildDimensionSelects();
    renderAll();
  }

  function resetFilters() {
    var range = defaultDateRange(DATA_SINCE, DATA_UNTIL, TODAY);
    state.agents = new Set(AGENTS);
    state.start = range.start;
    state.end = range.end;
    state.model = "";
    state.project = "";
    state.q = "";
    state.metric = "total";
    state.shadow = false;
    state.focusRange = false;
    state.sortKey = "day";
    state.sortDir = "desc";
    state.activitySortKey = "day";
    state.activitySortDir = "desc";
    state.page = 0;
    syncDateInputs();
    el.model.value = "";
    el.project.value = "";
    el.q.value = "";
    el.metric.value = "total";
    el.shadow.checked = false;
    el.focusRange.checked = false;
    syncFocusControls();
    syncAgentFilter();
    rebuildDimensionSelects();
    renderAll();
  }

  function syncShell() {
    var units = [];
    if (hasTokenSelected()) units.push("tokens");
    if (hasCreditsSelected()) {
      var creditUnits = [];
      if (state.agents.has("qoder")) {
        creditUnits.push(EST.length && state.shadow
          ? "Qoder credits + 影子估算" : "Qoder credits");
      }
      if (state.agents.has("trae-cn")) {
        creditUnits.push(TRAE_EST.length
          ? "Trae credits + 弱估算" : "Trae credits");
      }
      units.push(creditUnits.join(" / "));
    }
    el.panelToken.hidden = !hasTokenSelected();
    el.panelCredits.hidden = !hasCreditsSelected();
    el.panelEst.hidden = !hasTraeEstimateSelected();
    el.metricField.hidden = !hasTokenSelected();
    el.shadowSwitch.hidden = !state.agents.has("qoder") || !EST.length;
    el.shadow.checked = state.shadow;
    el.metric.value = state.metric;
    el.modelUnit.textContent = units.join(" / ");
    el.projectUnit.textContent = units.join(" / ");
    if (!state.agents.has("qoder") || !EST.length) {
      state.shadow = false;
      el.shadow.checked = false;
      el.shadowNote.hidden = true;
    }
  }

  function renderCoverage() {
    var parts = [];
    var qoderToken = qoderTokenBounds[0]
      ? qoderTokenBounds[0] + " ~ " + qoderTokenBounds[1] : "";
    parts.push("已选 Agent：" + Array.from(state.agents).map(sourceLabel).join(" / "));
    var unitNames = [];
    if (hasTokenSelected()) unitNames.push("tokens");
    if (hasCreditsSelected()) unitNames.push("credits");
    if (hasTraeEstimateSelected() || hasQoderShadowSelected()) {
      unitNames.push("est");
    }
    if (unitNames.length > 1) {
      parts.push(unitNames.map(function (name) {
        return name === "est" ? "估算" : name;
      }).join("、") + " 单位不同，分别汇总，不跨单位相加");
    }
    if (state.agents.has("qoder") && hasCreditsSelected()) {
      var qoderCredit = creditBoundsBySource.qoder || ["", ""];
      if (qoderCredit[0]) parts.push("Qoder credits " + qoderCredit[0] + " ~ " + qoderCredit[1]);
      else parts.push("Qoder 本地无 credits 数据");
      if (state.shadow && estBounds[0]) {
        parts.push("Qoder 影子估算 " + estBounds[0] + " ~ " + estBounds[1]);
      } else if (EST.length) {
        parts.push("Qoder 影子估算未计入（开关关闭）");
      }
      if (ACTIVITY.length) {
        var actBounds = minMaxDay(ACTIVITY);
        parts.push("活动 " + actBounds[0] + " ~ " + actBounds[1]);
      }
    }
    if (state.agents.has("trae-cn") && hasCreditsSelected()) {
      var traeCredit = creditBoundsBySource["trae-cn"] || ["", ""];
      if (traeCredit[0]) parts.push("Trae credits " + traeCredit[0] + " ~ " + traeCredit[1]);
      else parts.push("Trae credits " + traeUnavailableWord());
      if (traeEstBounds[0]) {
        parts.push("Trae 弱估算 " + traeEstBounds[0] + " ~ " + traeEstBounds[1] +
          "（仅覆盖安装 hook 后的请求）");
      }
    }
    if (qoderToken && state.agents.has("qoder")) {
      parts.push("Qoder 历史 token 真值 " + qoderToken + "，未并入本页");
    }
    if (hasTraeEstimateSelected() || state.shadow) {
      parts.push("估算不与 token 真值或 credits 相加");
    }
    el.coverage.textContent = parts.join("；");
    el.coverage.hidden = false;
  }

  function traeUnavailableWord() {
    var cov = COVERAGE["trae-cn.credits"] || {};
    return cov.refresh_error ? "刷新失败" : "未同步";
  }

  function renderTraeStatus() {
    var cov = COVERAGE["trae-cn.credits"];
    var node = el.traeStatus;
    node.className = "coverage trae-status";
    if (!state.agents.has("trae-cn") || !cov) {
      node.hidden = true;
      return;
    }
    var last = cov.last_sync_at ? fmtDateTime(cov.last_sync_at) : "—";
    var text;
    if (cov.refresh_error) {
      text = "Trae credits 刷新失败，" +
        (cov.available ? "当前为缓存数据" : "暂无缓存数据");
      if (cov.available) text += " · " + last;
      text += " · " + cov.refresh_error;
      node.classList.add("error");
    } else if (!cov.available) {
      text = "Trae credits 未同步 · 运行 usage html（默认刷新）或 " +
        "usage sync --source trae-cn --remote";
      node.classList.add("warn");
    } else if (cov.refresh_mode === "offline") {
      text = "Trae credits 离线缓存 · " + last;
      if (cov.stale) {
        text += " · 数据可能过期";
        node.classList.add("warn");
      }
    } else if (cov.refresh_mode === "stateless") {
      text = "Trae credits 需要 SQLite 缓存 · 当前为无库模式";
      node.classList.add("warn");
    } else {
      text = "Trae credits 已刷新 · " + last;
      if (cov.stale) {
        text += " · 数据可能过期";
        node.classList.add("warn");
      }
    }
    if (cov.available && cov.sessions !== undefined && cov.sessions !== null) {
      text += " · " + fmtInt(cov.sessions) + " 会话";
    }
    node.textContent = text;
    node.hidden = false;
  }

  function emptyActivityTotals() {
    var totals = {};
    ACTIVITY_FIELDS.forEach(function (field) { totals[field] = 0; });
    return totals;
  }

  function addKpiGroup(host, title) {
    var section = document.createElement("section");
    section.className = "kpi-group";
    var heading = document.createElement("h3");
    heading.className = "kpi-group-title";
    heading.textContent = title;
    var grid = document.createElement("div");
    grid.className = "kpi-grid";
    section.appendChild(heading);
    section.appendChild(grid);
    host.appendChild(section);
    return grid;
  }

  function addKpiNoData(host, label, sub, primary) {
    addKpiTo(host, label, "—", sub, !!primary);
  }

  function addKpiSubgroup(host, text) {
    var node = document.createElement("div");
    node.className = "kpi-subgroup";
    node.textContent = text;
    host.appendChild(node);
  }

  function renderTokenKpis(host, rows, primary) {
    if (!rows.length) {
      addKpiNoData(host, "Token · 无数据", "当前区间没有 token 行", primary);
      return;
    }
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

    addKpiTo(host, "总 Token", fmtCompact(total), fmtInt(total), primary);
    FIELDS.forEach(function (field) {
      addKpiTo(host, FIELD_LABELS[field], fmtCompact(sums[field]), fmtInt(sums[field]));
    });
    addKpiTo(host, "缓存占比", total ? pct(sums.cache_read / total) : "—", "cache_read / 总量");
    addKpiTo(host, "记录数", fmtCompact(turns), fmtInt(turns) + " 条日志记录");
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
    card.className = "kpi quota-kpi";
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
      sub.textContent = "已用 " + fmtQuota(used) + " / " + fmtQuota(total) +
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

  function shouldShowEmptyState(counts) {
    return number(counts.token) + number(counts.credit) + number(counts.est) +
      number(counts.activity) <= 0;
  }

  function traeCreditState(rows, cacheRows, coverage) {
    if (rows && rows.length) return null;
    var cov = coverage || {};
    if (cacheRows && cacheRows.length) {
      return {
        label: "当前区间无 Trae credits",
        sub: "缓存中有 " + fmtInt(cacheRows.length) +
          " 行，当前范围没有会话",
        tone: "warn"
      };
    }
    if (cov.refresh_error) {
      return {
        label: "刷新失败",
        sub: (cov.available ? "使用缓存 · " : "暂无缓存数据 · ") + cov.refresh_error,
        tone: "error"
      };
    }
    if (cov.available) {
      return {
        label: "无 credits 数据",
        sub: "刷新成功，但本地没有 Trae 会话",
        tone: "warn"
      };
    }
    return {
      label: "未同步",
      sub: "运行 usage html（默认刷新）或 usage sync --source trae-cn --remote",
      tone: "warn"
    };
  }

  function renderEmptyState(empty, counts) {
    el.emptyState.hidden = !empty;
    if (!empty) return;
    var hasBounds = !!(DATA_SINCE || DATA_UNTIL);
    el.emptyTitle.textContent = hasBounds ? "当前区间无数据" : "报告没有可用数据";
    var rangeText = state.start && state.end ? state.start + " ~ " + state.end : "未选择范围";
    var message = hasBounds
      ? "数据截至 " + (DATA_UNTIL || "—") + "；当前范围 " + rangeText + " 没有可展示的数据。"
      : "没有可用的 token、credits、估算或活动数据；请先运行 usage backfill 或检查源路径。";
    if (state.agents.has("qoder") && !state.shadow && EST.some(function (row) {
      return matchesFilters(row);
    })) {
      message += " 当前区间只有 Qoder 影子估算，打开后可查看。";
    }
    el.emptyMessage.textContent = message;
    var quota = quotaSummary();
    if (quota) {
      el.emptyQuota.hidden = false;
      el.emptyQuota.textContent = "最新额度快照：" + fmtQuota(quota.remaining) +
        " credits（与区间无关）";
    } else {
      el.emptyQuota.hidden = true;
      el.emptyQuota.textContent = "";
    }
    var shadowPossible = state.agents.has("qoder") && !state.shadow && EST.some(function (row) {
      return matchesFilters(row);
    });
    el.emptyShadow.hidden = !shadowPossible;
  }

  function renderQoderCreditKpis(host, rows, primary) {
    if (!rows.length) {
      addKpiNoData(host, "Qoder credits · 无数据", "当前区间没有 Qoder credits 行", primary);
      return;
    }
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
      fmtInt(requests) + " billable 请求 · 服务端逐请求计费真值", primary, "credit");
    addKpiTo(host, "免费 credits", fmtCredits(free), fmtInt(freeRequests) + " 免费请求",
      false, "credit");
    addKpiTo(host, "区间日均", fmtCredits(dayCount ? billable / dayCount : 0),
      fmtInt(dayCount) + " 天有数据", false, "credit");
  }

  function renderTraeCreditKpis(host, rows, primary) {
    var cov = COVERAGE["trae-cn.credits"] || {};
    if (!rows.length) {
      var cacheRows = CREDIT_ROWS.filter(function (row) { return row.source === "trae-cn"; });
      var stateInfo = traeCreditState(rows, cacheRows, cov);
      addKpiTo(host, "区间 credits", stateInfo.label, stateInfo.sub, !!primary, "credit");
      return;
    }
    var credits = 0;
    var sessions = 0;
    var days = {};
    var models = {};
    rows.forEach(function (row) {
      credits += row.credits;
      sessions += row.requests;
      days[row.day] = true;
      models[row.model] = true;
    });
    var dataState = "";
    if (cov.refresh_error) dataState = " · 缓存数据（" + fmtDateTime(cov.last_sync_at) + "）";
    else if (cov.refresh_mode === "offline") dataState = " · 离线缓存";
    if (cov.stale && !dataState) dataState = " · 数据可能过期";
    addKpiTo(host, "区间 credits", fmtCredits(credits),
      fmtInt(sessions) + " 会话 · 服务端会话级计费真值" + dataState, !!primary, "credit");
    addKpiTo(host, "会话数", fmtCompact(sessions), fmtInt(sessions) + " 会话");
    addKpiTo(host, "覆盖天数", fmtInt(Object.keys(days).length),
      fmtInt(Object.keys(days).length) + " 天有数据");
    addKpiTo(host, "模型数", fmtInt(Object.keys(models).length),
      fmtInt(Object.keys(models).length) + " 个模型");
  }

  function renderEstKpis(host, primary) {
    var traeRows = traeRowsFor();
    var shadowRows = qoderEstRowsFor();
    var used = false;
    if (!traeRows.length && !shadowRows.length) {
      addKpiNoData(host, "估算 · 无数据", "当前区间没有估算行", primary);
      return;
    }
    if (traeRows.length) {
      addKpiTo(host, "Trae 弱估算 Token", fmtCompact(sumField(traeRows, "total")),
        fmtInt(sumField(traeRows, "requests")) + " 请求 · 不可与 credits 相加",
        !!primary, "shadow credit");
      used = true;
    } else if (state.agents.has("trae-cn")) {
      addKpiTo(host, "Trae 弱估算 Token", "—", "当前区间无 hook 估算", !!primary,
        "shadow credit");
      used = true;
    }
    if (state.shadow) {
      if (shadowRows.length) {
        addKpiTo(host, "Qoder 影子估算 Token", fmtCompact(sumField(shadowRows, "total")),
          fmtInt(sumField(shadowRows, "requests")) + " 请求 · 不可与 credits 相加",
          !!primary && !used, "shadow credit");
      } else {
        addKpiTo(host, "Qoder 影子估算 Token", "—", "当前区间无影子估算数据",
          !!primary && !used, "shadow credit");
      }
      used = true;
    }
    if (!used) addKpiNoData(host, "估算 · 无数据", "未选择估算来源", primary);
  }

  function renderCreditKpis(host, rows, primary) {
    var sources = selectedCreditAgents();
    if (!sources.length) return;
    if (!rows.length && sources.length > 1) {
      addKpiNoData(host, "Credits · 无数据", "当前区间没有 credits 行", primary);
      return;
    }
    var labeled = sources.length > 1;
    var first = true;
    sources.forEach(function (source) {
      if (labeled) {
        addKpiSubgroup(host, source === "qoder"
          ? "Qoder · 精确 Credits（逐请求）"
          : "Trae CN · 精确 Credits（会话级）");
      }
      var subset = rows.filter(function (row) { return row.source === source; });
      var isPrimary = !!primary && first;
      if (source === "qoder") renderQoderCreditKpis(host, subset, isPrimary);
      else renderTraeCreditKpis(host, subset, isPrimary);
      if (subset.length) first = false;
    });
  }

  function renderKpis() {
    var host = el.kpis;
    host.textContent = "";
    var tokenRows = tokenRowsFor();
    var creditRows = creditRowsFor();
    var estSelected = hasTraeEstimateSelected() || state.shadow;
    var primaryUnit = "";
    if (hasTokenSelected() && tokenRows.length) primaryUnit = "token";
    else if (hasCreditsSelected() && creditRows.length) primaryUnit = "credit";
    else if (estSelected) primaryUnit = "est";
    if (hasTokenSelected()) {
      renderTokenKpis(addKpiGroup(host, "精确 Token（tokens）"), tokenRows,
        primaryUnit === "token");
    }
    if (hasCreditsSelected()) {
      renderCreditKpis(addKpiGroup(host, "精确 Credits（credits）"), creditRows,
        primaryUnit === "credit");
    }
    if (estSelected) {
      renderEstKpis(addKpiGroup(host, "估算（弱估算 / 影子）"), primaryUnit === "est");
    }
  }

  function clampTooltipX(x, width, tooltipWidth) {
    var half = tooltipWidth ? tooltipWidth / 2 : 145;
    return Math.max(half, Math.min(x, Math.max(half, width - half)));
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
    if (!buckets.length || config.hasRows === false) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = config.emptyText || "当前区间没有数据";
      host.appendChild(empty);
      return;
    }
    var series = config.series;
    var grouped = config.mode === "grouped";
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
      var axisTitle = svgEl("text", {
        x: width - margin.right + 8, y: 10, "text-anchor": "start", class: "axis-title"
      });
      axisTitle.textContent = config.shadowAxisTitle || "影子估算（右轴）";
      svg.appendChild(axisTitle);
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
    var groupBarW = Math.max(1, Math.min(20, band * 0.72 / Math.max(series.length, 1)));
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

    function bucketAria(bucket) {
      var bits = [bucket.tooltip];
      series.forEach(function (def, i) {
        bits.push(def.label + " " + (config.tooltipFormat || fmtInt)(bucket.values[i] || 0));
      });
      if (shadowLabel) bits.push(shadowLabel + " " + fmtInt(bucket.shadowValue));
      return bits.join("，");
    }

    buckets.forEach(function (bucket, index) {
      var groupStart = margin.left + band * index + (band - groupBarW * series.length) / 2;
      var stackedY = margin.top + plotH;
      series.forEach(function (def, i) {
        var value = bucket.values[i] || 0;
        if (value <= 0) return;
        var slice = (value / scale.max) * plotH;
        var x = grouped ? groupStart + groupBarW * i
          : margin.left + band * index + (band - barW) / 2;
        var y;
        if (grouped) {
          y = margin.top + plotH - slice;
        } else {
          stackedY -= slice;
          y = stackedY;
        }
        svg.appendChild(svgEl("rect", {
          x: x, y: y, width: grouped ? groupBarW : barW, height: slice,
          fill: def.color, class: "seg", rx: (grouped ? groupBarW : barW) > 4 ? 1.5 : 0
        }));
      });
      var hit = svgEl("rect", {
        x: margin.left + band * index, y: margin.top,
        width: Math.max(band, 1), height: plotH, class: "hit",
        tabindex: "0", focusable: "true", role: "button"
      });
      hit.setAttribute("aria-label", bucketAria(bucket));
      var pinned = false;
      function hideTip() {
        moveHover(-1);
        tooltip.style.display = "none";
      }
      hit.addEventListener("pointerenter", function (event) {
        if (pinned) return;
        moveHover(index);
        showTooltip(bucket, event);
      });
      hit.addEventListener("pointermove", function (event) {
        if (!pinned) positionTooltip(event);
      });
      hit.addEventListener("pointerleave", function () {
        if (!pinned) hideTip();
      });
      hit.addEventListener("click", function (event) {
        event.preventDefault();
        pinned = !pinned;
        if (pinned) {
          moveHover(index);
          showTooltip(bucket, event);
        } else {
          hideTip();
        }
      });
      hit.addEventListener("focus", function () {
        moveHover(index);
        showTooltip(bucket, null);
      });
      hit.addEventListener("blur", function () {
        if (!pinned) hideTip();
      });
      hit.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          pinned = false;
          hideTip();
        }
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
    svg.addEventListener("click", function (event) {
      if (event.target && event.target.classList && event.target.classList.contains("hit")) return;
      tooltip.style.display = "none";
    });

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
      if (!grouped) {
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
      }
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
      var x = event && event.clientX !== undefined
        ? event.clientX - rect.left : rect.width / 2;
      x = clampTooltipX(x, rect.width, tooltip.offsetWidth);
      tooltip.style.left = x + "px";
    }
  }

  function renderCharts() {
    if (hasTokenSelected()) {
      var tokenAgents = selectedTokenAgents();
      var tokenRows = tokenRowsFor();
      var tokenBuckets = buildStackBuckets(tokenRows, tokenAgents.map(function (source) {
        return {
          label: sourceLabel(source), color: COLORS[source],
          value: function (row) { return row.source === source ? pageMetric(row) : 0; }
        };
      }));
      renderStackChart({
        host: el.chartToken, tooltip: el.tooltipToken, legend: el.legendToken,
        buckets: tokenBuckets,
        series: tokenAgents.map(function (source) {
          return { label: sourceLabel(source), color: COLORS[source] };
        }),
        metaText: "指标：" + (state.metric === "total" ? "总量" : FIELD_LABELS[state.metric]),
        ariaLabel: "按 Agent 堆叠的每日 token 用量",
        tooltipFormat: fmtInt, hasRows: tokenRows.length > 0,
        emptyText: "当前区间无 Token 数据"
      });
      renderMissingHint(el.hintToken, tokenRows);
    }
    if (hasCreditsSelected()) {
      var creditRows = creditRowsFor();
      var creditSources = selectedCreditAgents();
      var qoderOnly = creditSources.length === 1 && creditSources[0] === "qoder";
      var traeOnly = creditSources.length === 1 && creditSources[0] === "trae-cn";
      var shadowRows = state.shadow && creditSources.indexOf("qoder") >= 0
        ? qoderEstRowsFor() : null;
      var hintBits = [];
      if (qoderOnly) {
        var creditDefs = [
          { label: "billable（计入配额）", color: CREDIT_BILLABLE_COLOR,
            value: function (row) { return row.credits; } },
          { label: "免费（不计配额）", color: CREDIT_FREE_COLOR,
            value: function (row) { return row.free_credits; } }
        ];
        var creditBuckets = buildStackBuckets(creditRows, creditDefs,
          state.shadow ? [{ value: function (row) { return row.total; } }] : [],
          shadowRows);
        renderStackChart({
          host: el.chartCredits, tooltip: el.tooltipCredits, legend: el.legendCredits,
          buckets: creditBuckets,
          series: creditDefs,
          shadowLabel: state.shadow ? "Qoder 影子估算" : "",
          shadowAxisTitle: "影子估算（右轴）",
          metaText: "Qoder credits 为服务端逐请求计费真值，非 token",
          ariaLabel: "Qoder 每日 credits 用量",
          legendFormat: fmtCredits,
          tooltipFormat: fmtCredits, hasRows: creditRows.length > 0,
          emptyText: "当前区间无 Qoder credits"
        });
      } else if (traeOnly) {
        var traeDefs = [
          { label: "Trae credits", color: COLORS["trae-cn"] || "#0d9488",
            value: function (row) { return row.credits; } }
        ];
        renderStackChart({
          host: el.chartCredits, tooltip: el.tooltipCredits, legend: el.legendCredits,
          buckets: buildStackBuckets(creditRows, traeDefs),
          series: traeDefs,
          metaText: "Trae CN credits 为服务端会话级计费真值（按会话归属日），非 token",
          ariaLabel: "Trae CN 每日 credits 用量",
          legendFormat: fmtCredits,
          tooltipFormat: fmtCredits, hasRows: creditRows.length > 0,
          emptyText: "当前区间无 Trae credits"
        });
        hintBits.push("Trae 为会话级归属日，不是逐请求日");
      } else {
        var groupedDefs = creditSources.map(function (source) {
          return {
            label: source === "qoder" ? "Qoder" : "Trae CN",
            color: COLORS[source],
            value: function (row) {
              return row.source === source ? row.credits : 0;
            }
          };
        });
        renderStackChart({
          host: el.chartCredits, tooltip: el.tooltipCredits, legend: el.legendCredits,
          buckets: buildStackBuckets(creditRows, groupedDefs,
            state.shadow ? [{ value: function (row) { return row.total; } }] : [],
            shadowRows),
          series: groupedDefs,
          mode: "grouped",
          shadowLabel: state.shadow ? "Qoder 影子估算" : "",
          shadowAxisTitle: "影子估算（右轴）",
          metaText: "credits 按 Agent 分列，不可相加（Qoder 逐请求 / Trae 会话级）",
          ariaLabel: "按 Agent 分组的每日 credits 用量",
          legendFormat: fmtCredits,
          tooltipFormat: fmtCredits, hasRows: creditRows.length > 0,
          emptyText: "当前区间无 credits 数据"
        });
        hintBits.push("credits 按 Agent 分列，不可相加");
      }
      renderMissingHint(el.hintCredits, creditRows.concat(shadowRows || []));
      if (creditSources.indexOf("trae-cn") >= 0) {
        if (!CREDIT_ROWS.some(function (row) { return row.source === "trae-cn"; })) {
          hintBits.push("缺 Trae credits，运行 usage html 或 " +
            "usage sync --source trae-cn --remote");
        }
        var traeCov = COVERAGE["trae-cn.credits"] || {};
        if (traeCov.available && (traeCov.stale || traeCov.refresh_error)) {
          hintBits.push("Trae 当前为缓存数据（" +
            (fmtDateTime(traeCov.last_sync_at) || "无同步时间") + "）");
        }
      }
      if (hintBits.length) {
        el.hintCredits.textContent = (el.hintCredits.textContent
          ? el.hintCredits.textContent + "；" : "") + hintBits.join("；");
      }
    }
    if (hasTraeEstimateSelected()) {
      var traeRows = traeRowsFor();
      var estDefs = [
        { label: "估算输入", color: EST_INPUT_COLOR,
          value: function (row) { return row.est_input; } },
        { label: "估算输出", color: EST_OUTPUT_COLOR,
          value: function (row) { return row.est_output; } }
      ];
      var estBuckets = buildStackBuckets(traeRows, estDefs);
      renderStackChart({
        host: el.chartEst, tooltip: el.tooltipEst, legend: el.legendEst,
        buckets: estBuckets,
        series: estDefs,
        metaText: TRAE_NOTE + " · 非 token 真值",
        ariaLabel: "Trae CN 每日弱估算 token",
        tooltipFormat: fmtInt, hasRows: traeRows.length > 0,
        emptyText: "当前区间无 Trae 弱估算数据"
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
      hintEl.textContent = "数据覆盖 " + days.length + "/" + days.length + " 天";
      return;
    }
    hintEl.textContent = "数据覆盖 " + (days.length - missing.length) + "/" + days.length +
      " 天（缺 " + missing.length + " 天，图表按 0 显示）";
  }

  function aggregateTop(key, ignore, options) {
    var opts = options || {};
    var map = new Map();
    function entry(name) {
      if (!map.has(name)) {
        map.set(name, { key: name, tokens: 0, turns: 0, credits: 0,
                        creditRequests: 0, creditSources: {}, creditRequestsBySource: {},
                        est: 0, estRequests: 0,
                        shadowEst: 0, shadowRequests: 0 });
      }
      return map.get(name);
    }
    if (!opts.creditsOnly) {
      tokenRowsFor(ignore).forEach(function (row) {
        var item = entry(row[key] || "-");
        item.tokens += pageMetric(row);
        item.turns += number(row.turns);
      });
    }
    creditRowsFor(ignore).forEach(function (row) {
      if (opts.creditSources && !opts.creditSources.has(row.source)) return;
      var item = entry(row[key] || "-");
      item.credits += row.credits;
      item.creditRequests += row.requests;
      item.creditSources[row.source] = (item.creditSources[row.source] || 0) + row.credits;
      item.creditRequestsBySource[row.source] =
        (item.creditRequestsBySource[row.source] || 0) + row.requests;
    });
    if (!opts.creditsOnly) {
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
    }
    return Array.from(map.values());
  }

  function creditRequestLabel(source) {
    return source === "trae-cn" ? "会话" : "请求";
  }

  function creditParts(item) {
    var parts = [];
    Object.keys(item.creditSources).forEach(function (source) {
      var value = item.creditSources[source];
      if (!(value > 0)) return;
      parts.push(sourceLabel(source) + " " + fmtCredits(value) + " credits · " +
        fmtInt(item.creditRequestsBySource[source] || 0) + " " +
        creditRequestLabel(source));
    });
    return parts;
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
    return fmtCompact(item.est) + " 估算 tokens";
  }

  function topShare(value, maximum) {
    if (!(maximum > 0) || !(value > 0)) return { text: "—", width: 0 };
    var ratio = value / maximum;
    return { text: pct(ratio), width: Math.max(ratio * 100, 1.5) };
  }

  function filterTopItems(items, unit) {
    return items.filter(function (item) { return topValue(item, unit) > 0; });
  }

  function topSecondary(item, unit) {
    var parts = [];
    if (unit !== "tokens" && item.tokens > 0) {
      parts.push(fmtCompact(item.tokens) + " tokens");
    }
    if (unit !== "credits") {
      var creditBits = creditParts(item);
      if (creditBits.length) parts.push(creditBits.join(" · "));
    } else {
      var counts = Object.keys(item.creditSources).map(function (source) {
        return sourceLabel(source) + " " +
          fmtInt(item.creditRequestsBySource[source] || 0) + " " +
          creditRequestLabel(source);
      });
      if (counts.length) parts.push(counts.join(" · "));
    }
    if (unit !== "est" && item.est > 0) {
      parts.push("Trae 弱估算 " + fmtCompact(item.est) + "（不可相加）");
    }
    if (item.shadowEst > 0) {
      parts.push("影子估算 " + fmtCompact(item.shadowEst) + "（不可相加）");
    }
    return parts.join(" · ");
  }

  function renderTopList(host, items, grandTotal, unit, selected, onPick, options) {
    var opts = options || {};
    if (!opts.append) host.textContent = "";
    if (opts.title) {
      var title = document.createElement("div");
      title.className = "top-group-title";
      title.textContent = opts.title;
      host.appendChild(title);
    }
    if (!items.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "无数据";
      host.appendChild(empty);
      return;
    }
    var maximum = items.reduce(function (acc, item) {
      return Math.max(acc, topValue(item, unit));
    }, 0);
    maximum = Math.max(maximum, 1);
    items.forEach(function (item) {
      var value = topValue(item, unit);
      var share = topShare(value, maximum);
      var button = document.createElement("button");
      button.type = "button";
      button.className = "bar-row" + (item.key === selected ? " selected" : "");
      button.setAttribute("aria-pressed", item.key === selected ? "true" : "false");
      var top = document.createElement("div");
      top.className = "bar-top";
      var name = document.createElement("span");
      name.className = "bar-name";
      name.textContent = item.key === "-" || item.key === "unknown" ? "（未标注）" : displayName(item.key);
      name.title = item.key === "-" || item.key === "unknown" ? "（未标注）" : displayName(item.key);
      var amount = document.createElement("span");
      amount.className = "bar-value";
      amount.textContent = topValueText(item, unit) + " · " + share.text;
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
      fill.style.width = share.width.toFixed(1) + "%";
      track.appendChild(fill);
      button.appendChild(track);
      button.title = "筛选：" + (item.key === "-" || item.key === "unknown" ? "（未标注）" : displayName(item.key));
      button.addEventListener("click", function () { onPick(item.key); });
      host.appendChild(button);
    });
  }

  function pickModel(key) {
    state.model = state.model === key ? "" : key;
    el.model.value = state.model;
    state.page = 0;
    renderAll();
  }

  function pickProject(key) {
    state.project = state.project === key ? "" : key;
    el.project.value = state.project;
    state.page = 0;
    renderAll();
  }

  function renderTopLists() {
    var unit = primaryUnit();
    var creditSources = selectedCreditAgents();
    var groupedCredits = unit === "credits" && creditSources.length > 1;
    var tag = unit === "tokens" ? "tokens" : unit === "credits" ? "credits" : "估算 tokens";
    if (activeUnits().size > 1) tag = "主单位 " + tag;
    el.modelUnit.textContent = tag;
    el.projectUnit.textContent = tag;
    var noteUnit = unit === "tokens" ? "tokens" : unit === "credits" ? "credits" : "估算";
    var note = "相对第一 · 按 " + noteUnit + " 排序 · 当前区间";
    el.modelNote.textContent = note;
    el.projectNote.textContent = note;
    if (groupedCredits) {
      var firstModel = true;
      var firstProject = true;
      creditSources.forEach(function (source) {
        var sourceRows = creditRowsFor().filter(function (row) {
          return row.source === source;
        });
        var sourceTotal = sourceRows.reduce(function (acc, row) {
          return acc + row.credits;
        }, 0);
        var creditOptions = { creditsOnly: true, creditSources: new Set([source]) };
        var modelItems = filterTopItems(aggregateTop("model", null, creditOptions).sort(function (a, b) {
          return topValue(b, unit) - topValue(a, unit);
        }), unit).slice(0, 8);
        var projectItems = filterTopItems(aggregateTop("project", null, creditOptions).sort(function (a, b) {
          return topValue(b, unit) - topValue(a, unit);
        }), unit).slice(0, 8);
        renderTopList(el.models, modelItems, sourceTotal, unit, state.model, pickModel,
          { append: !firstModel, title: sourceLabel(source) + " · 模型 Top 8" });
        renderTopList(el.projects, projectItems, sourceTotal, unit, state.project, pickProject,
          { append: !firstProject, title: sourceLabel(source) + " · 项目 Top 8" });
        firstModel = false;
        firstProject = false;
      });
      return;
    }
    var total = primaryGrandTotal(unit);
    var modelItems = filterTopItems(aggregateTop("model").sort(function (a, b) {
      return topValue(b, unit) - topValue(a, unit);
    }), unit).slice(0, 8);
    var projectItems = filterTopItems(aggregateTop("project").sort(function (a, b) {
      return topValue(b, unit) - topValue(a, unit);
    }), unit).slice(0, 8);
    renderTopList(el.models, modelItems, total, unit, state.model, pickModel);
    renderTopList(el.projects, projectItems, total, unit, state.project, pickProject);
  }

  function columnFmt(column, value) {
    if (column.key === "cost_equiv_usd") return fmtCost(value);
    if (column.fmt) return column.fmt(value);
    return fmtInt(value);
  }

  function sortRows(rows, key, dir, numericKeys, tieKey) {
    return rows.slice().sort(function (a, b) {
      var av = a[key];
      var bv = b[key];
      var aNull = av === null || av === undefined || av === "";
      var bNull = bv === null || bv === undefined || bv === "";
      if (aNull || bNull) {
        if (aNull && bNull) return 0;
        return aNull ? 1 : -1;
      }
      var cmp;
      if (numericKeys[key]) cmp = number(av) - number(bv);
      else cmp = String(av).localeCompare(String(bv), "zh-CN");
      if (cmp === 0 && tieKey) {
        cmp = String(a[tieKey] || "").localeCompare(String(b[tieKey] || ""), "zh-CN");
      }
      return dir === "asc" ? cmp : -cmp;
    });
  }

  var STICKY_WIDTHS = { day: 96, source: 90, unitLabel: 90, model: 170, project: 160 };
  var STICKY_ORDER = ["day", "source", "unitLabel", "model", "project"];

  function stickyLayout(columns) {
    var left = 0;
    var layout = {};
    STICKY_ORDER.forEach(function (key) {
      var found = columns.some(function (column) {
        return column.key === key && column.identity;
      });
      if (!found) return;
      layout[key] = left;
      left += STICKY_WIDTHS[key];
    });
    return { left: layout, total: left };
  }

  function pruneColumns(columns, rows) {
    var kept = columns.filter(function (column) {
      if (column.identity) return true;
      if (!rows.length) return false;
      return rows.some(function (row) {
        if (column.unit && row.unit !== column.unit) return false;
        var value = row[column.key];
        if (value === null || value === undefined || value === "") return false;
        if (column.type === "num") return number(value) !== 0;
        return true;
      });
    });
    if (!kept.some(function (column) { return column.key === "day"; })) {
      kept.unshift(columns.find(function (column) { return column.key === "day"; }));
    }
    if (!kept.some(function (column) { return column.key === "source"; })) {
      kept.splice(1, 0, columns.find(function (column) { return column.key === "source"; }));
    }
    return kept;
  }

  function groupHeader(columns) {
    var groups = [];
    columns.forEach(function (column) {
      if (column.identity) {
        groups.push({ identity: column, label: column.label, span: 1 });
        return;
      }
      var label = column.group || "";
      var last = groups[groups.length - 1];
      if (last && !last.identity && last.label === label) {
        last.span += 1;
      } else {
        groups.push({ label: label, span: 1 });
      }
    });
    return groups;
  }

  function paginateRows(rows, page, size) {
    var pageSize = Math.max(1, number(size) || 50);
    var pages = Math.max(1, Math.ceil(rows.length / pageSize));
    var current = Math.min(Math.max(0, number(page) || 0), pages - 1);
    var start = current * pageSize;
    return { pages: pages, page: current, start: start,
             slice: rows.slice(start, start + pageSize) };
  }

  function tableTotals(rows, columns, units, creditSources) {
    var out = [];
    function valuesFor(unit, source) {
      var values = {};
      columns.forEach(function (column) {
        if (column.unit !== unit) return;
        values[column.key] = rows.reduce(function (acc, row) {
          if (row.unit !== unit) return acc;
          if (source && row.source !== source) return acc;
          return acc + number(row[column.key]);
        }, 0);
      });
      return values;
    }
    function has(unit, source) {
      return rows.some(function (row) {
        return row.unit === unit && (!source || row.source === source);
      });
    }
    if (units.has("token") && has("token")) {
      out.push({ label: "Token 合计", unit: "token", values: valuesFor("token") });
    }
    if (units.has("credit")) {
      ["qoder", "trae-cn"].forEach(function (source) {
        if (creditSources.indexOf(source) < 0 || !has("credit", source)) return;
        out.push({ label: sourceLabel(source) + " credits 合计", unit: "credit",
                   source: source, values: valuesFor("credit", source) });
      });
    }
    if (units.has("est")) {
      ["trae-cn", "qoder"].forEach(function (source) {
        if (!has("est", source)) return;
        out.push({
          label: (source === "qoder" ? "Qoder 影子估算合计" : "Trae 弱估算合计"),
          unit: "est", source: source, values: valuesFor("est", source)
        });
      });
    }
    return out;
  }

  function renderDataTable(config) {
    var columns = pruneColumns(config.columns, config.rows);
    var numericKeys = {};
    columns.forEach(function (column) {
      if (column.type === "num") numericKeys[column.key] = true;
    });
    if (!columns.some(function (column) { return column.key === state.sortKey; })) {
      state.sortKey = "day";
      state.sortDir = "desc";
    }
    var sorted = sortRows(config.rows, state.sortKey, state.sortDir, numericKeys, "unitLabel");
    var paging = paginateRows(sorted, state.page, state.pageSize);
    state.page = paging.page;
    var slice = paging.slice;
    var sticky = stickyLayout(columns);

    var focusedKey = null;
    if (document.activeElement && document.activeElement.classList.contains("th-btn")) {
      focusedKey = document.activeElement.dataset.key;
    }

    config.colgroup.textContent = "";
    var totalWidth = 0;
    columns.forEach(function (column) {
      var width = sticky.left[column.key] !== undefined
        ? STICKY_WIDTHS[column.key] : (column.type === "num" ? 74 : 108);
      totalWidth += width;
      var col = document.createElement("col");
      col.style.width = width + "px";
      config.colgroup.appendChild(col);
    });
    config.table.style.width = totalWidth + "px";
    config.table.style.minWidth = totalWidth + "px";

    function makeHeaderCell(column, rowspan) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      if (column.identity) th.classList.add("identity", "sticky-col");
      if (column.identity && column.key !== "day" && column.key !== "source") {
        th.classList.add("sticky-wide");
      }
      if (sticky.left[column.key] !== undefined) th.style.left = sticky.left[column.key] + "px";
      if (rowspan) th.rowSpan = rowspan;
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
      return th;
    }

    config.thead.textContent = "";
    var groupRow = document.createElement("tr");
    var labelRow = document.createElement("tr");
    groupHeader(columns).forEach(function (group) {
      if (group.identity) {
        groupRow.appendChild(makeHeaderCell(group.identity, 2));
        return;
      }
      var th = document.createElement("th");
      th.className = "group-head";
      th.colSpan = group.span;
      th.scope = "colgroup";
      th.textContent = group.label;
      groupRow.appendChild(th);
    });
    columns.filter(function (column) { return !column.identity; }).forEach(function (column) {
      labelRow.appendChild(makeHeaderCell(column, 1));
    });
    config.thead.appendChild(groupRow);
    if (labelRow.children.length) config.thead.appendChild(labelRow);

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
          if (column.identity) {
            td.classList.add("identity", "sticky-col");
            if (column.key !== "day" && column.key !== "source") td.classList.add("sticky-wide");
            td.style.left = sticky.left[column.key] + "px";
          }
          if (column.unit && row.unit !== column.unit) {
            td.textContent = "—";
            td.classList.add("zero");
          } else if (column.key === "day") {
            td.textContent = value;
          } else if (column.key === "source") {
            td.textContent = sourceLabel(value);
          } else if (column.key === "project") {
            td.textContent = value === "-" ? "（未标注）" : value;
            td.title = value;
          } else if (column.key === "model") {
            td.textContent = modelLabel(value);
            td.title = modelLabel(value);
          } else if (column.key === "unitLabel") {
            td.textContent = value;
            td.title = value;
          } else if (column.key === "cost_equiv_usd") {
            td.textContent = fmtCost(value);
          } else if (column.type === "num") {
            if (value === null || value === undefined) {
              td.textContent = "—";
              td.classList.add("zero");
            } else {
              td.textContent = columnFmt(column, value);
              if (!number(value)) td.classList.add("zero");
            }
          } else {
            td.textContent = value;
          }
          tr.appendChild(td);
        });
        config.tbody.appendChild(tr);
      });
    }

    config.tfoot.textContent = "";
    if (columns.length && config.rows.length) {
      tableTotals(config.rows, columns, config.units, config.creditSources)
        .forEach(function (total) {
          var tr = document.createElement("tr");
          var labelCell = document.createElement("td");
          labelCell.colSpan = columns.filter(function (column) {
            return column.identity;
          }).length;
          labelCell.className = "identity sticky-col";
          labelCell.style.left = "0px";
          labelCell.textContent = total.label;
          tr.appendChild(labelCell);
          columns.filter(function (column) { return !column.identity; })
            .forEach(function (column) {
              var td = document.createElement("td");
              if (column.type === "num") td.className = "num";
              if (column.unit !== total.unit) {
                td.textContent = "—";
                td.classList.add("zero");
              } else if (total.values[column.key] === undefined) {
                td.textContent = "—";
                td.classList.add("zero");
              } else {
                td.textContent = columnFmt(column, total.values[column.key]);
              }
              tr.appendChild(td);
            });
          config.tfoot.appendChild(tr);
        });
    }

    config.rowinfo.textContent = config.info(sorted);
    config.pageinfo.textContent = slice.length
      ? "第 " + (paging.page + 1) + " / " + paging.pages + " 页 · " +
        (paging.start + 1) + "–" + (paging.start + slice.length) + " / " + fmtInt(sorted.length)
      : "0 / 0";
    config.prev.disabled = paging.page <= 0;
    config.next.disabled = paging.page >= paging.pages - 1;
    config.pageSize.value = String(state.pageSize);
    config.pageJump.max = String(paging.pages);
    config.pageJump.value = String(paging.page + 1);
    config.pageJump.disabled = !slice.length;
    config.pageJumpGo.disabled = !slice.length;
  }

  var COST_KNOWN = ROWS.some(function (row) {
    return row.cost_equiv_usd !== null && row.cost_equiv_usd !== undefined;
  });

  function estimateRows() {
    var rows = [];
    traeRowsFor().forEach(function (row) {
      rows.push({
        day: row.day, source: "trae-cn", model: row.model, project: row.project,
        unit: "est", unitLabel: "Trae 弱估算",
        est_input: row.est_input, est_output: row.est_output,
        est_total: row.total, est_requests: row.requests
      });
    });
    qoderEstRowsFor().forEach(function (row) {
      rows.push({
        day: row.day, source: "qoder", model: row.model, project: row.project,
        unit: "est", unitLabel: "Qoder 影子估算",
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
      var qoder = row.source === "qoder";
      rows.push({
        day: row.day, source: row.source, model: row.model, project: row.project,
        unit: "credit", unitLabel: "credits",
        credits: row.credits,
        free_credits: qoder ? row.free_credits : null,
        credit_requests: qoder ? row.requests : null,
        free_requests: qoder ? row.free_requests : null,
        credit_sessions: qoder ? null : row.requests
      });
    });
    return rows.concat(estimateRows());
  }

  function activeUnits() {
    var units = new Set();
    if (hasTokenSelected()) units.add("token");
    if (hasCreditsSelected()) units.add("credit");
    if (hasTraeEstimateSelected() || hasQoderShadowSelected()) {
      units.add("est");
    }
    return units;
  }

  function reportColumns(units, creditSources) {
    var qoderCredit = creditSources.indexOf("qoder") >= 0;
    var traeCredit = creditSources.indexOf("trae-cn") >= 0;
    var columns = [
      { key: "day", label: "日期", type: "text", identity: true },
      { key: "source", label: "Agent", type: "text", identity: true }
    ];
    if (units.size > 1) {
      columns.push({ key: "unitLabel", label: "单位", type: "text", identity: true });
    }
    columns.push({ key: "model", label: "模型", type: "text", identity: true });
    columns.push({ key: "project", label: "项目", type: "text", identity: true });
    if (units.has("token")) {
      FIELDS.forEach(function (field) {
        columns.push({ key: field, label: FIELD_LABELS[field], type: "num",
                       unit: "token", group: "Token" });
      });
      columns.push({ key: "total", label: "Token 合计", type: "num",
                     unit: "token", group: "Token" });
      columns.push({ key: "turns", label: "记录数", type: "num",
                     unit: "token", group: "Token" });
    }
    if (units.has("credit")) {
      columns.push({ key: "credits", label: "credits", type: "num",
                     unit: "credit", fmt: fmtCredits, group: "Credits" });
      if (qoderCredit) {
        columns.push({ key: "free_credits", label: "免费 credits", type: "num",
                       unit: "credit", fmt: fmtCredits, group: "Credits" });
        columns.push({ key: "credit_requests", label: "请求", type: "num",
                       unit: "credit", fmt: fmtInt, group: "Credits" });
        columns.push({ key: "free_requests", label: "免费请求", type: "num",
                       unit: "credit", fmt: fmtInt, group: "Credits" });
      }
      if (traeCredit) {
        columns.push({ key: "credit_sessions", label: "会话", type: "num",
                       unit: "credit", fmt: fmtInt, group: "Credits" });
      }
    }
    if (units.has("est")) {
      columns.push({ key: "est_input", label: "估算输入", type: "num",
                     unit: "est", group: "估算" });
      columns.push({ key: "est_output", label: "估算输出", type: "num",
                     unit: "est", group: "估算" });
      columns.push({ key: "est_total", label: "估算合计", type: "num",
                     unit: "est", group: "估算" });
      columns.push({ key: "est_requests", label: "估算请求", type: "num",
                     unit: "est", group: "估算" });
    }
    if (units.has("token") && COST_KNOWN) {
      columns.push({ key: "cost_equiv_usd", label: "等价成本", type: "num",
                     unit: "token", group: "Token" });
    }
    return columns;
  }

  function tableInfo(rows, units) {
    var tokens = 0;
    var creditsBySource = {};
    var traeEst = 0;
    var shadowEst = 0;
    rows.forEach(function (row) {
      if (row.unit === "token") {
        tokens += number(row.total);
      } else if (row.unit === "credit") {
        if (!creditsBySource[row.source]) {
          creditsBySource[row.source] = { credits: 0, requests: 0 };
        }
        creditsBySource[row.source].credits += number(row.credits);
        creditsBySource[row.source].requests +=
          number(row.source === "trae-cn" ? row.credit_sessions : row.credit_requests);
      } else if (row.unitLabel === "Qoder 影子估算") {
        shadowEst += number(row.est_total);
      } else {
        traeEst += number(row.est_total);
      }
    });
    var parts = [fmtInt(rows.length) + " 行"];
    if (units.has("token")) parts.push(fmtInt(tokens) + " tokens");
    Object.keys(creditsBySource).sort().forEach(function (source) {
      var item = creditsBySource[source];
      parts.push(sourceLabel(source) + " " + fmtCredits(item.credits) + " credits · " +
        fmtInt(item.requests) + " " + creditRequestLabel(source));
    });
    if (shadowEst > 0) parts.push("影子估算 " + fmtInt(shadowEst) + "（不可相加）");
    if (traeEst > 0) parts.push("Trae 弱估算 " + fmtInt(traeEst) + "（不可相加）");
    return parts.join(" · ");
  }

  function renderShadowNote() {
    if (!hasQoderShadowSelected()) {
      el.shadowNote.hidden = true;
      return;
    }
    el.shadowNote.hidden = false;
    el.shadowNote.textContent = "Qoder 影子估算由转录文本与 context_usage_ratio 推算（" +
      EST_FACTOR + "，±30~40%），按 天 × 模型 × 项目 聚合；仅覆盖带 ratio 的请求，" +
      "不可与 credits 相加。Trae 弱估算是另一套影子，二者不能合并。";
  }

  function visibleCounts() {
    return {
      token: tokenRowsFor().length,
      credit: creditRowsFor().length,
      est: (state.shadow ? qoderEstRowsFor().length : 0) + traeRowsFor().length,
      activity: state.agents.has("qoder") ? filteredActivity().length : 0
    };
  }

  function renderReport() {
    var counts = visibleCounts();
    var empty = shouldShowEmptyState(counts);
    var hasNumeric = counts.token + counts.credit + counts.est > 0;
    var hasActivity = counts.activity > 0;
    renderEmptyState(empty, counts);
    el.kpis.hidden = !hasNumeric;
    el.reportGrid.hidden = !hasNumeric;
    el.tokenTable.hidden = !hasNumeric;
    el.activityBlock.hidden = !hasActivity;
    if (el.activityBlock.hidden) el.activityBlock.open = false;
    if (empty) return;
    if (hasNumeric) {
      renderKpis();
      renderCharts();
      renderTopLists();
      var units = activeUnits();
      var rows = reportRows();
      var creditSources = selectedCreditAgents();
      renderDataTable({
        thead: el.thead, tbody: el.tbody, tfoot: el.tfoot, colgroup: el.colgroup,
        table: el.table, rowinfo: el.rowinfo, pageinfo: el.pageinfo,
        prev: el.prev, next: el.next, pageSize: el.pageSize,
        pageJump: el.pageJump, pageJumpGo: el.pageJumpGo,
        columns: reportColumns(units, creditSources), rows: rows,
        units: units, creditSources: creditSources,
        emptyText: "无匹配数据",
        info: function (all) { return tableInfo(all, units); }
      });
      renderShadowNote();
    }
    if (el.activityBlock.open && hasActivity) renderActivity();
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
    if (!el.activityBlock.open) return;
    if (!state.agents.has("qoder") || !ACTIVITY.length) return;
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
    persistState();
  }

  function renderActivityChart(rows) {
    el.activityChart.textContent = "";
    el.activityTooltip.style.display = "none";
    el.activityLegend.textContent = "";
    if (!rows.length) {
      var empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = "所选范围内没有活动数据";
      el.activityChart.appendChild(empty);
      el.activityHint.textContent = "";
      return;
    }

    var buckets = activityBuckets(rows, state.start, state.end, ACTIVITY_FIELDS);
    var metric = state.activityMetric;
    var width = Math.max(el.activityChart.clientWidth || 900, 320);
    var height = 240;
    var margin = { top: 14, right: 14, bottom: 28, left: 62 };
    var plotW = Math.max(width - margin.left - margin.right, 10);
    var plotH = height - margin.top - margin.bottom;
    var maximum = buckets.reduce(function (acc, bucket) {
      return Math.max(acc, number(bucket.values[metric]));
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

    var band = plotW / buckets.length;
    var barW = Math.max(1.5, Math.min(26, band * 0.66));
    var color = COLORS.qoder || "#e11d48";
    var hoverLine = svgEl("line", {
      x1: 0, x2: 0, y1: margin.top, y2: margin.top + plotH, class: "hover-line"
    });

    function showTooltip(bucket, event) {
      var tip = el.activityTooltip;
      tip.textContent = "";
      var head = document.createElement("div");
      head.className = "tt-head";
      head.textContent = bucket.tooltip;
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
          ? fmtDuration(bucket.values[field]) : fmtInt(bucket.values[field]);
        row.appendChild(name);
        row.appendChild(value);
        tip.appendChild(row);
      });
      tip.style.display = "block";
      positionTooltip(event);
    }

    function positionTooltip(event) {
      var rect = el.activityChart.parentElement.getBoundingClientRect();
      var x = event && event.clientX !== undefined
        ? event.clientX - rect.left : rect.width / 2;
      x = clampTooltipX(x, rect.width, el.activityTooltip.offsetWidth);
      el.activityTooltip.style.left = x + "px";
    }

    function bucketAria(bucket) {
      var bits = [bucket.tooltip];
      ACTIVITY_FIELDS.forEach(function (field) {
        bits.push(ACTIVITY_LABELS[field] + " " +
          (field === "duration_ms" ? fmtDuration(bucket.values[field])
            : fmtInt(bucket.values[field])));
      });
      return bits.join("，");
    }

    buckets.forEach(function (bucket, index) {
      var value = number(bucket.values[metric]);
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
        width: Math.max(band, 1), height: plotH, class: "hit",
        tabindex: "0", focusable: "true", role: "button"
      });
      hit.setAttribute("aria-label", bucketAria(bucket));
      var pinned = false;
      function hideTip() {
        hoverLine.setAttribute("x1", 0);
        hoverLine.setAttribute("x2", 0);
        el.activityTooltip.style.display = "none";
      }
      hit.addEventListener("pointerenter", function (event) {
        if (pinned) return;
        var center = margin.left + band * index + band / 2;
        hoverLine.setAttribute("x1", center);
        hoverLine.setAttribute("x2", center);
        showTooltip(bucket, event);
      });
      hit.addEventListener("pointermove", function (event) {
        if (!pinned) positionTooltip(event);
      });
      hit.addEventListener("pointerleave", function () {
        if (!pinned) hideTip();
      });
      hit.addEventListener("click", function (event) {
        event.preventDefault();
        pinned = !pinned;
        if (pinned) {
          var center = margin.left + band * index + band / 2;
          hoverLine.setAttribute("x1", center);
          hoverLine.setAttribute("x2", center);
          showTooltip(bucket, event);
        } else {
          hideTip();
        }
      });
      hit.addEventListener("focus", function () {
        var center = margin.left + band * index + band / 2;
        hoverLine.setAttribute("x1", center);
        hoverLine.setAttribute("x2", center);
        showTooltip(bucket, null);
      });
      hit.addEventListener("blur", function () {
        if (!pinned) hideTip();
      });
      hit.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          pinned = false;
          hideTip();
        }
      });
      svg.appendChild(hit);
    });
    svg.appendChild(hoverLine);
    svg.addEventListener("click", function (event) {
      if (event.target && event.target.classList && event.target.classList.contains("hit")) return;
      el.activityTooltip.style.display = "none";
    });

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
    el.activityChart.appendChild(svg);

    var metricTotal = buckets.reduce(function (acc, bucket) {
      return acc + number(bucket.values[metric]);
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

    var withMetrics = buckets.reduce(function (acc, bucket) {
      return acc + number(bucket.values.assistant_with_metrics);
    }, 0);
    var assistant = buckets.reduce(function (acc, bucket) {
      return acc + number(bucket.values.assistant_calls);
    }, 0);
    var activeBuckets = buckets.filter(function (bucket) {
      return ACTIVITY_FIELDS.some(function (field) {
        return number(bucket.values[field]) > 0;
      });
    }).length;
    var unit = buckets.length && buckets[0].end !== buckets[0].start ? "周" : "天";
    el.activityHint.textContent = "活跃 " + activeBuckets + " " + unit + " / 共 " +
      buckets.length + " " + unit + "（完整日期轴，缺失显示 0）；turnMetrics 覆盖 " +
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
    { key: "turns", label: "轮次", type: "num" },
    { key: "tool_calls", label: "工具调用", type: "num" },
    { key: "duration_ms", label: "运行时长", type: "num" }
  ];

  var ACTIVITY_STICKY = { day: 96, project: 160 };

  function renderActivityTable(rows) {
    var numericKeys = {};
    ACTIVITY_COLUMNS.forEach(function (column) {
      if (column.type === "num") numericKeys[column.key] = true;
    });
    if (!ACTIVITY_COLUMNS.some(function (column) {
      return column.key === state.activitySortKey;
    })) {
      state.activitySortKey = "day";
      state.activitySortDir = "desc";
    }
    var sorted = sortRows(rows, state.activitySortKey, state.activitySortDir,
                          numericKeys, "project");
    var paging = paginateRows(sorted, state.activityPage, state.activityPageSize);
    state.activityPage = paging.page;
    var slice = paging.slice;
    var focusedKey = null;
    if (document.activeElement && document.activeElement.classList.contains("th-btn")) {
      focusedKey = document.activeElement.dataset.key;
    }
    el.activityThead.textContent = "";
    var headerRow = document.createElement("tr");
    ACTIVITY_COLUMNS.forEach(function (column) {
      var th = document.createElement("th");
      if (column.type === "num") th.className = "num";
      if (column.key === "day" || column.key === "project") {
        th.classList.add("identity", "sticky-col");
        th.style.left = (column.key === "day" ? 0 : ACTIVITY_STICKY.day) + "px";
        th.style.width = ACTIVITY_STICKY[column.key] + "px";
        th.style.minWidth = ACTIVITY_STICKY[column.key] + "px";
      }
      th.setAttribute("aria-sort", state.activitySortKey === column.key
        ? (state.activitySortDir === "asc" ? "ascending" : "descending") : "none");
      var button = document.createElement("button");
      button.type = "button";
      button.className = "th-btn";
      button.dataset.key = column.key;
      button.appendChild(document.createTextNode(column.label));
      if (state.activitySortKey === column.key) {
        var arrow = document.createElement("span");
        arrow.className = "arrow";
        arrow.textContent = state.activitySortDir === "asc" ? "▲" : "▼";
        button.appendChild(arrow);
      }
      button.addEventListener("click", function () {
        if (state.activitySortKey === column.key) {
          state.activitySortDir = state.activitySortDir === "asc" ? "desc" : "asc";
        } else {
          state.activitySortKey = column.key;
          state.activitySortDir = column.type === "num" ? "desc" : "asc";
        }
        state.activityPage = 0;
        renderActivity();
      });
      th.appendChild(button);
      headerRow.appendChild(th);
    });
    el.activityThead.appendChild(headerRow);
    if (focusedKey) {
      var restored = el.activityThead.querySelector('.th-btn[data-key="' + focusedKey + '"]');
      if (restored) restored.focus({ preventScroll: true });
    }

    el.activityTbody.textContent = "";
    var toolTotal = 0;
    rows.forEach(function (row) { toolTotal += row.tool_calls; });
    slice.forEach(function (row) {
      var tr = document.createElement("tr");
      ACTIVITY_COLUMNS.forEach(function (column) {
        var td = document.createElement("td");
        var value = row[column.key];
        if (column.type === "num") td.className = "num";
        if (column.key === "day" || column.key === "project") {
          td.classList.add("identity", "sticky-col");
          td.style.left = (column.key === "day" ? 0 : ACTIVITY_STICKY.day) + "px";
          td.style.width = ACTIVITY_STICKY[column.key] + "px";
          td.style.minWidth = ACTIVITY_STICKY[column.key] + "px";
        }
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
    el.activityPageinfo.textContent = slice.length
      ? "第 " + (paging.page + 1) + " / " + paging.pages + " 页 · " +
        (paging.start + 1) + "–" + (paging.start + slice.length) + " / " + fmtInt(sorted.length)
      : "0 / 0";
    el.activityPrev.disabled = paging.page <= 0;
    el.activityNext.disabled = paging.page >= paging.pages - 1;
    el.activityPageSize.value = String(state.activityPageSize);
  }

  function renderFooter() {
    var host = el.coverageExtra;
    host.textContent = "";
    (DATA.notices || []).forEach(function (notice) {
      var line = document.createElement("p");
      line.textContent = notice;
      host.appendChild(line);
    });
    var classify = document.createElement("p");
    classify.textContent = "Agent 可多选：Token 计费（" +
      (TOKEN_AGENTS.length ? TOKEN_AGENTS.map(sourceLabel).join(" / ") : "无数据") +
      "）与 Credits 计费（" +
      (CREDIT_AGENTS.length ? CREDIT_AGENTS.map(sourceLabel).join(" / ") : "无数据") +
      "）分别按各自单位汇总，同一页面并列展示但不跨单位相加；" +
      "Qoder 影子 token 与 Trae 弱估算归入估算，同样不可相加。";
    host.appendChild(classify);
    if (QODER_TOKEN_ROWS.length) {
      var history = document.createElement("p");
      history.textContent = "Qoder 历史 token 真值 " +
        (qoderTokenBounds[0] + " ~ " + qoderTokenBounds[1]) + "（" +
        fmtInt(sumField(QODER_TOKEN_ROWS, "total")) +
        " tokens）保留在库中，未并入本页；可用 usage report --source qoder 查询。";
      host.appendChild(history);
    }
    if (CREDIT_ROWS.length) {
      var creditNote = document.createElement("p");
      creditNote.textContent = "Credits 按 Agent 分列：Qoder 为服务端逐请求计费真值，" +
        "Trae CN 为服务端会话级计费真值；不同 Agent 的 credits 不可相加；" +
        "免费 credits 仅 Qoder 提供；Qoder 余额来自本地日志快照。";
      host.appendChild(creditNote);
    }
    var traeCreditRows = CREDIT_ROWS.filter(function (row) {
      return row.source === "trae-cn";
    });
    var traeCov = COVERAGE["trae-cn.credits"];
    if (traeCreditRows.length || traeCov) {
      var traeCreditNote = document.createElement("p");
      var bits = ["Trae credits 来源：本机 opt-in API 同步"];
      if (traeCov && traeCov.last_sync_at) {
        bits.push("最近成功同步 " + fmtDateTime(traeCov.last_sync_at));
      } else {
        bits.push("尚未同步");
      }
      bits.push("本次模式 " + (traeCov && traeCov.refresh_mode
        ? traeCov.refresh_mode : "—"));
      bits.push("usage html 默认刷新，失败时回退缓存");
      bits.push("不保存 prompt/正文");
      var traeMapped = CREDIT_ROWS.some(function (row) {
        return row.source === "trae-cn" && row.project && row.project !== "-";
      });
      bits.push("Trae API 无 project 字段，" + (traeMapped
        ? "项目为 hook 尽力映射"
        : "当前 hook session 与 credits session 无法关联，项目显示 -"));
      traeCreditNote.textContent = bits.join("；") + "。";
      host.appendChild(traeCreditNote);
    }
    if (EST.length) {
      var estNote = document.createElement("p");
      estNote.textContent = "Qoder 影子估算 token 由转录文本与上下文比例推算（" + EST_FACTOR +
        "，±30~40% 误差），不可与 token 真值或额度相加。";
      host.appendChild(estNote);
    }
    if (TRAE_EST.length) {
      var traeNote = document.createElement("p");
      traeNote.textContent = TRAE_NOTE + "；仅覆盖安装 hook 后的请求，" +
        "误差可能数倍且方向不定，只适合看趋势，不可与 token 真值或额度相加。";
      host.appendChild(traeNote);
    }
    var scope = document.createElement("p");
    var qoderCreditRows = CREDIT_ROWS.filter(function (row) {
      return row.source === "qoder";
    }).length;
    var pageDetailRows = reportRows().length;
    var pageActivityRows = state.agents.has("qoder") ? filteredActivity().length : 0;
    scope.textContent = "库内：" + fmtInt(ROWS.length) + " 行 token 聚合" +
      (CREDIT_ROWS.length
        ? " / " + fmtInt(CREDIT_ROWS.length) + " 行 credits 聚合（Qoder " +
          fmtInt(qoderCreditRows) + " / Trae CN " + fmtInt(traeCreditRows.length) + "）"
        : "") +
      (ACTIVITY.length ? " / " + fmtInt(ACTIVITY.length) + " 行活动聚合" : "") +
      (EST.length ? " / " + fmtInt(EST.length) + " 行影子估算聚合" : "") +
      (TRAE_EST.length ? " / " + fmtInt(TRAE_EST.length) + " 行 Trae 弱估算聚合" : "") +
      "；本页：" + fmtInt(pageDetailRows) + " 行明细 / " + fmtInt(pageActivityRows) +
      " 行活动（当前筛选）。";
    host.appendChild(scope);
    var definitions = document.createElement("p");
    definitions.textContent = "术语：明细的“记录数”是日志完成记录数；活动的“轮次”是 " +
      "assistant turn 数，两者口径不同。筛选词会写入本页 URL hash，请勿分享含敏感项目名的链接。";
    host.appendChild(definitions);
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
    syncAgentTotals();
    renderCoverage();
    renderTraeStatus();
    renderReport();
    persistState();
    updateChrome();
  }

  buildAgentFilter();
  buildControls();
  rebuildDimensionSelects();
  if (state.focusRange) {
    var initialFocus = focusBounds();
    if (initialFocus[0] && initialFocus[1]) {
      state.start = initialFocus[0];
      state.end = initialFocus[1];
      syncDateInputs();
    } else {
      state.focusRange = false;
      el.focusRange.checked = false;
    }
  }
  syncFocusControls();
  applyTheme(document.documentElement.dataset.theme || "light");
  el.activityMetric.value = state.activityMetric;
  el.activityPageSize.value = String(state.activityPageSize);
  el.pageSize.value = String(state.pageSize);
  el.dataUntil.textContent = DATA_UNTIL ? "数据截至 " + DATA_UNTIL : "无可用数据";
  el.generated.textContent = "生成于 " + fmtDateTime(DATA.generated_at);
  renderFooter();
  renderAll();
})();
</script>
</body>
</html>
"""
