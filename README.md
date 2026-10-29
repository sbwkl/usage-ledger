# usage-ledger

> macOS 上的**极轻量**跨 AI 编码工具 **token 用量台账**。零 UI、零社交、零云同步、零第三方依赖。

一个只读本地日志、只写本地 SQLite、算出"我今天每个平台每个模型花了多少 token"的离线工具。

**状态**：v0.2 已实现并通过验收——4 个 collector、SQLite 归档、`sync/backfill/report/top/doctor/live/prune/export/html`、`--stateless` 一致性、launchd 调度管理。24 个单测覆盖 PROBE 校正后的采集规则与 HTML 报表。计价与 WorkBuddy 采集按 PROBE 建议推后。

---

## 它解决什么

你同时用 opencode / qoder / chatgpt / claude code / kilo / trae CN / workbuddy，桌面版和 CLI 都用。想知道**每个平台、每个模型**的 token 用量。

现有工具都不合适：ccusage 极简但只覆盖 18 个源；tokscale 覆盖 60 个但带 TUI 和排行榜；TokenTracker / Token Monitor 带桌面宠物和多设备同步。

**本项目的立场**：采集层用成熟做法，报表层自己做；不估算、不爬私有 API、无任何网络行为。

---

## 覆盖能力（含现实边界）

| 平台 | token 统计 | 说明 |
|---|---|---|
| Claude Code | ✅ | 含 cache read/write |
| OpenCode（CLI + 桌面） | ✅ | 与 Kilo 同构，一个 adapter |
| Kilo（CLI + 桌面） | ✅ | |
| Codex CLI | ✅ | 注意"增量 vs 累计"口径 |
| WorkBuddy | ✅ | P1，需先安装核实样本 |
| Qoder | ❌ | **订阅套餐本地 token 恒为 0**（实测 6898 条），只有 credits |
| Trae CN | ❌ | 本地只有额度键，无 token 字段 |
| ChatGPT 桌面端 | ❌ | 无本地数据，只有配额 |

> 缺口是**厂商不下发**，不是解析器写不出来。任何工具都无法凭空造出这三个平台的 token 数。工具会在 `doctor` 与报告页脚显式说明，避免"看起来没花"与"没采到"混淆。

---

## 核心设计要点

- **源是唯一事实来源**。DB 是可插拔的"归档 + 索引"层，不是权威副本
  - `NullStore`（零 DB、零定时任务）/ `SqliteStore`（归档 + 索引，默认）
  - `usage report`（读库）与 `usage --stateless report`（读源）输出必须完全一致
- **拉取式采集**，不需要常驻进程：数据由 agent 自己落盘，任何时刻读盘都拿得到已落盘的全部数据
- **实时性三档**：`usage live`（直读源，<0.3s）→ `--live` 合并 → 读库（≤1h）
- **丢失窗口 ≤ 1h**：每小时增量 + 每日全量重扫，路径显式覆盖 `archived_sessions/` `.zst` `storage/` `subagents/`
- **历史可回填**：`usage backfill` 一次性导入既有日志
- **只读、隐私**：不写源目录，不存 prompt/正文，项目路径可哈希

---

## 目录结构

```
usage-ledger/
├── pyproject.toml     Python 包定义与 usage / usage-ledger 两个 CLI 入口
├── docs/
│   ├── DESIGN.md       实现方案（v0.4，含 DDL / CLI / 计价 / 里程碑 / 风险）
│   ├── RESEARCH.md     调研报告（竞品横评 + 本机数据可得性实测）
│   ├── PROBE.md        实测探针报告（真实 token 台账 + 9 处规格偏差 + Q 的答案）
│   └── DISCUSSION.md   讨论纪要（决策链 + 文档修订记录 + 待决问题）
├── scripts/
│   └── probe.py        只读探针：全量扫 4 源，产出 token 表（0.72s，标准库 only）
├── src/usage_ledger/
│   ├── collectors.py   4 源采集（Claude/Codex/OpenCode/Kilo）
│   ├── store.py        SQLite 归档、去重、prune、usage_daily 汇总
│   ├── aggregation.py  报表聚合与过滤
│   ├── html_report.py  离线单文件交互报表（内联 CSS/JS/SVG）
│   ├── scheduler.py    launchd 任务生成/安装/查询
│   ├── cli.py          命令行入口
│   └── pricing.py      模型别名与价格表（价格表当前为空）
└── tests/              单测 + 脱敏 fixtures（Claude/Codex/OpenCode）
```

## 安装

```bash
cd /Users/wayne/workspace/playground/usage-ledger
uv tool install .          # 推荐：隔离环境，usage 命令落在 ~/.local/bin
# 或：pipx install .
```

安装后 `usage` 与 `usage-ledger` 两个命令等价：

```bash
usage --version
usage backfill                  # 首次导入历史（幂等，可重复跑）
usage report --since 7d         # 日报：天 × 源 × 模型
usage top models                # 模型排行
usage html --open               # 生成 usage-report.html 并在浏览器打开
usage live                      # 直读源的实时视图
usage doctor                    # 源健康 + 归档自检
usage schedule install          # 每小时增量 + 每日全量 + prune
```

修改源码后重装 / 卸载（uv 会缓存本地构建，重装需 `--no-cache`）：

```bash
uv tool install --force --no-cache .
uv tool uninstall usage-ledger
```

开发时也可以不安装，直接运行：

```bash
PYTHONPATH=src python3 -m usage_ledger report --since 7d
```

常用变体：`report --weekly|--monthly|--range 2026-06-01..2026-10-29`、
`--group-by source,model`、`--filter source=codex`、`--format json|csv`、
`report --live`（源 ∪ 库）、`--stateless report`（不读库不落库）。

---

## 交互式 HTML 报表

```bash
usage html                                  # 生成 ./usage-report.html（打印绝对路径）
usage html --open                           # 生成后自动在浏览器打开
usage html --range 2026-10-01..2026-10-29 --output /tmp/usage.html
usage html --source codex --live            # 只看 codex，并合并源里的最新数据
usage --stateless html --output /tmp/usage.html   # 不读库，直接读源
```

页面是**单文件、离线、零外部请求**（CSP `default-src 'none'`，CSS/JS/SVG 全内联），
可随时发给别人或归档，不需要起服务。内容：

- KPI：总 token、输入/输出/缓存读/缓存写/推理、缓存占比、轮次
- 可切换指标的每日堆叠柱状图（按来源），悬停查看当天明细；区间超过 200 天自动按周聚合
- 模型 Top 8 / 项目 Top 8，点击筛选、再点取消（列表不会被自身筛选折叠）
- 日期范围、来源、模型、项目、全文搜索联合过滤
- 可排序、可分页的明细表；缺失日期显式标注（图表按 0 显示）
- 浅色/深色主题，选择记在 `localStorage`

数据来自与 `report` 相同的聚合链路（天 × 来源 × 模型 × 项目），所以页面数字与 CLI 报表一致。

---

## 技术选型

Python ≥3.11，**标准库 only**（`sqlite3` / `json` / `argparse` / `plistlib`），零第三方包；通过 `pyproject.toml` 安装为 `usage` CLI；SQLite（WAL）存储；launchd 调度。

---

## 下一步

1. 安装 launchd：`usage schedule install`（hourly sync / 00:15 full rescan / 00:20 prune）
2. 计价（可选）：价格表目前为空，`cost_equiv_usd` 恒为 `unknown`——PROBE 证明本机 18/21 个模型是 free/别名，成本列价值低
3. WorkBuddy collector（需先安装 WorkBuddy 采集样本）
4. v2 可选项：`NullStore`、zstd 归档、L3 FSEvents daemon、额度轴

> 完整快照随时可复现：`python3 scripts/probe.py`
> 验收命令：`python3 -m unittest discover -s tests -t .`
