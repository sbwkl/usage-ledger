# usage-ledger

> macOS 上的**极轻量**跨 AI 编码工具 **token 用量台账**。零 UI、零社交、零云同步、零第三方依赖。

一个只读本地日志、只写本地 SQLite、算出"我今天每个平台每个模型花了多少 token"的离线工具。

**状态**：v0.5 已实现并通过验收——7 个源采集（含 Qoder 四轨、Trae CN hook 弱估算、Cline）、SQLite 归档、`sync/backfill/report/activity/credits/est/top/doctor/live/prune/export/html/hooks`、`--stateless` 一致性、查看命令自动增量刷新、launchd 调度管理。86 个单测覆盖 PROBE 校正后的采集规则、Qoder token/活动/额度/估算四轨、Qoder 模型显示名映射、Trae CN hooks/弱估算、Cline 会话 metrics、HTML 报表与自动刷新。计价与 WorkBuddy 采集按 PROBE 建议推后。

---

## 它解决什么

你同时用 opencode / qoder / chatgpt / claude code / kilo / trae CN / workbuddy，桌面版和 CLI 都用。想知道**每个平台、每个模型**的 token 用量。

现有工具都不合适：ccusage 极简但只覆盖 18 个源；tokscale 覆盖 60 个但带 TUI 和排行榜；TokenTracker / Token Monitor 带桌面宠物和多设备同步。

**本项目的立场**：采集层用成熟做法，报表层自己做；不为缺失数据编造 token，不爬私有 API，无任何网络行为。Qoder 新客户端断供 token 后，额度走服务端每请求计费真值，token 另设**显式标注的估算轨**（`est`），永不与真值相加。

---

## 覆盖能力（含现实边界）

| 平台 | token 统计 | 说明 |
|---|---|---|
| Claude Code | ✅ | 含 cache read/write |
| OpenCode（CLI + 桌面） | ✅ | 兼容新版 `session_message` 表（旧 `message` 表仍回读未迁移记录），与 Kilo 一个 adapter |
| Kilo（CLI + 桌面） | ✅ | |
| Cline（CLI + Desktop） | ✅ | 读 `~/.cline/data/sessions/**/<id>.messages.json` 中 assistant 的 `metrics`（input/output/cache read/write）；`inputTokens` 已含缓存，采集时扣除 |
| Codex CLI | ✅ | 注意"增量 vs 累计"口径 |
| Qoder | ✅ 历史 token + ✅ 活动 + ✅ 额度 + ✅ 估算 | token 来自 IDE 旧库（2026-06-01 ~ 2026-09-16）；桌面端提供**活动指标**（会话/提示/工具调用/时长）、**credits 额度真值**（服务端每请求计费）与 **est 估算 token**（转录 + 上下文比例）。四轨口径不同、永不互加，见 [docs/QODER-DESIGN.md](docs/QODER-DESIGN.md)、[docs/QODER-CREDITS-DESIGN.md](docs/QODER-CREDITS-DESIGN.md) |
| WorkBuddy | ✅ | P1，需先安装核实样本 |
| Trae CN | ⚠️ 弱估算 | 加密库无本地密钥、额度不落盘；通过官方 hooks 记录字符数与事件元数据，重放为 **hook 弱估算**（`trae-cn.est`）。只覆盖安装 hook 后的请求，误差可能数倍，不可与 token 真值或额度相加 |
| ChatGPT 桌面端 | ❌ | 无本地数据，只有配额 |

> 缺口是**厂商不下发**，不是解析器写不出来。任何工具都无法凭空造出这些平台的 token 数。工具会在 `doctor` 与报告页脚显式说明，避免"看起来没花"与"没采到"混淆。Qoder 新版本客户端已不再写 token，只保留活动元数据；活动指标用于观察 agent 使用强度，不参与 token 与成本统计。

---

## 核心设计要点

- **源是唯一事实来源**。DB 是可插拔的"归档 + 索引"层，不是权威副本
  - `NullStore`（零 DB、零定时任务）/ `SqliteStore`（归档 + 索引，默认）
  - `usage report`（读库）与 `usage --stateless report`（读源）输出必须完全一致
- **拉取式采集**，不需要常驻进程：数据由 agent 自己落盘，任何时刻读盘都拿得到已落盘的全部数据
- **实时性三档**：`usage live`（直读源，<0.3s）→ `--live` 合并 → 读库（自动检测新数据）
- **查看即最新**：`report/export/top/html` 先比对源文件 mtime，发现新数据自动增量 sync，再出结果（见下文）
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
│   ├── QODER-DESIGN.md Qoder 双轨设计（token + 活动指标）
│   ├── QODER-CREDITS-DESIGN.md Qoder 额度 + 估算 token 设计
│   ├── TRAE-CN-DESIGN.md Trae CN 接入与 hook 弱估算设计
│   ├── CLINE-DESIGN.md Cline 会话 metrics 采集设计
│   ├── RESEARCH.md     调研报告（竞品横评 + 本机数据可得性实测）
│   ├── PROBE.md        实测探针报告（真实 token 台账 + 9 处规格偏差 + Q 的答案）
│   └── DISCUSSION.md   讨论纪要（决策链 + 文档修订记录 + 待决问题）
├── scripts/
│   └── probe.py        只读探针：全量扫 4 源，产出 token 表（0.72s，标准库 only）
├── src/usage_ledger/
│   ├── collectors.py   7 源采集（Claude/Codex/OpenCode/Kilo/Cline/Qoder 双轨/Trae CN 弱估算）
│   ├── trae_hooks.py   Trae CN hook 脚本生成、安装/合并/卸载、事件日志
│   ├── store.py        SQLite 归档、去重、prune、usage_daily / usage_activity 汇总
│   ├── aggregation.py  报表聚合与过滤
│   ├── qoder_models.py Qoder 模型内部键 → 界面显示名（展示层映射，参考 perch）
│   ├── html_report.py  离线单文件交互报表（内联 CSS/JS/SVG）
│   ├── scheduler.py    launchd 任务生成/安装/查询
│   ├── cli.py          命令行入口
│   └── pricing.py      模型别名与价格表（价格表当前为空）
└── tests/              单测 + 脱敏 fixtures（Claude/Codex/OpenCode/Qoder/Trae CN/Cline）
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
usage activity --since 30d      # Qoder 活动指标：会话/提示/工具调用/时长（非 token）
usage credits --since 7d        # Qoder 配额消耗：每请求 billable credits（服务端真值）
usage est --group-by day,model  # Qoder 估算 token（est，±30~40%，不可与真值相加）
usage hooks install trae-cn --scope global  # 安装 Trae CN hooks（只记字符数与元数据）
usage hooks status trae-cn      # hook 配置、事件文件、最近事件
usage sync --source trae-cn     # 重放 hook 事件并写入 trae-cn.est
usage est --source trae-cn      # Trae CN 弱估算 token（只覆盖安装 hook 后）
usage report --source cline     # Cline 会话 token（input/output/cache read/write）
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

## 数据新鲜度：查看即最新

`report` / `export` / `top` / `html` 在出结果前会先做一次**新鲜度检查**：

1. 取各源最新文件的 mtime（Claude/Codex 看 `*.jsonl`，OpenCode/Kilo 看 `*.db` 与 `-wal`，Cline 看会话 `*.messages.json`），
   与库中 `source_state.last_file_mtime` 比对；
2. 只有 mtime 变新的源才触发增量 `sync`（写法与手动 `usage sync` 完全一致，幂等）；
3. 同步提示走 **stderr**，因此 `--format json|csv` 的 stdout 始终是干净的数据。

```bash
usage report --since 7d        # stderr: auto-sync: 检测到 claude 有新数据，正在刷新…
usage report --source claude    # 显式限定来源时只检查 claude，其他源不触发
usage --stateless report        # 绕过数据库与自动刷新，直读源
```

- 检查成本是一次目录遍历 + stat，不解析日志；无新数据时零额外开销。
- 如果指定了 `--source` 或 `--filter source=...`，只检查/刷新该源。
- 数据库不存在时仍按原逻辑降级为直读源，不会自动建库。
- 升级到本版本后首次运行会把所有源标记为"有新数据"并刷新一次，之后转入增量。

---

## Qoder 额度（credits）与估算 token（est）

Qoder 新版客户端不再写 token，但转录 JSONL 保留了每请求的服务端计费字段与上下文比例：

```bash
usage credits                       # 每天 billable credits / 请求数 / 免费 credits / 快照数
usage credits --since 7d --format json
usage est --group-by day,model      # 估算输入/输出 token 与覆盖请求数
usage est --stateless --group-by model   # 绕过数据库直读转录
```

- **credits 是服务端真值**：`billable=true` 的 `usage.credits` 逐请求累计，已与 main.log 配额快照增量核对（+18.16 vs +20、+31.62 vs +32 等）；免费请求单独列出，不计配额。
- **余额来自日志快照**：`main.log` 的 `用量响应摘要` 仅保留约一周、`used` 非单调，因此只用于展示当前余额/总量，不用来推导日消耗。
- **est 是估算值**：`est_input = context_usage_ratio × 200K`，`est_output = 字符数 ÷ 模型系数`（gfmodel 3.85 / dfmodel 4.58 / 其他 3.8）。旧版无 `ratio` 的转录跳过，避免与历史 token 真值重复。
- **模型显示名**：库里保留 Qoder 内部键（`dfmodel`、`gfmodel` 等），报表 / HTML / `top models` 在展示层映射为界面名
  （如 `dfmodel` → DeepSeek-Flash、`gfmodel` → GLM-5.3-Flash，键取自 Qoder `dynamic-text/qoder.json`，与 perch 一致）；
  未收录的历史/未知键原样显示；`--model` 过滤同时接受原始键和显示名。
- 四轨（token 真值 / 活动 / 额度 / 估算）分表、分示，任何两轨都不相加；`doctor` 会显示 credits、快照数、估算覆盖与交叉校验。

---

## Cline（CLI / Desktop）

Cline 的会话文件保留了每个 assistant 响应真实返回的 `metrics`，可直接作为 token 真值：

```bash
usage report --source cline
usage report --source cline --group-by day,model --format json
```

- **路径**：`~/.cline/data/sessions/<session>/<session>.messages.json`；只提取 assistant 消息的
  `metrics`（`inputTokens` / `outputTokens` / `cacheReadTokens` / `cacheWriteTokens`），不落正文。
- **口径**：Cline 的 `inputTokens` **包含**缓存 token，入库时按
  `input = inputTokens − cacheRead − cacheWrite` 拆分，与 Claude/Codex 的非重叠口径一致；
  `outputTokens` 含推理 token，暂不单列。
- **归属**：`model` 取消息的 `modelInfo.id`，缺失时回退会话元数据的 `model`；`project` 取
  `workspace_root`/`cwd` 的 basename；去重键 `cline:<message.id>`。
- **缺失**：没有 `metrics` 的消息（中断/失败）跳过并计数，不伪造 0；Cline 压缩后移出
  `.messages.json` 的历史会由每日全量 sync 标记 `archived=1` 保留，不会重复计入。
- **边界**：当前只接入 Cline CLI/Desktop 的会话文件；VS Code 扩展旧版
  `saoudrizwan.claude-dev/tasks/*/ui_messages.json` 形态尚无本机样本，未接入。

---

## Trae CN hooks 弱估算（est）

Trae CN 的 token 真值与额度都不可本地读取，但官方 hooks 能看到会话、工具调用与文本**长度**。
本项目安装一个只算字符数的 hook，把事件元数据写入本地 JSONL，再重放为 `trae-cn.est`：

```bash
usage hooks install trae-cn --scope global   # 合并写入 /Users/wayne/.trae-cn/hooks.json（带备份）
usage hooks status trae-cn                   # 配置、事件文件、最近事件、覆盖会话
usage sync --source trae-cn                  # 幂等重放事件文件
usage est --source trae-cn --group-by day,model
usage hooks uninstall trae-cn --scope global # 只删除本项目安装的 hook 组
```

- **隐私**：hook 只写 `event`、`session`、`project` basename、`tool`、`chars_in/out`、可选 `model` 与时间戳；
  不落 prompt、tool_input、tool_response、last_assistant_message 正文，不读加密库、JWT 或私有 API。
- **口径**：每个 `PreToolUse` 与 `Stop` 各记一次模型调用边界；`est_input = min(上下文累积字符 ÷ factor, window)`，
  `est_output = 输出字符 ÷ factor`。默认 `factor=3.8`、`overhead=0`、`window=200000`，可用
  `USAGE_LEDGER_TRAE_EST_FACTOR/_OVERHEAD/_WINDOW` 校准。
- **边界**：hook 看不到系统提示、工具定义、Skills/Memory/MCP schema，也看不到工具调用之间的 assistant 文本；
  并行工具会重复计输入。该轨是**弱估算/可见内容下限 + 部分重复**，误差可能数倍且方向不定，
  只适合看趋势，**永不与 token 真值或额度相加**。
- **覆盖**：只从安装 hook 之后的会话开始记录，不回溯加密库历史；额度仍不可得。
- 未安装 hook 时 `usage doctor` 会显示未安装/事件目录不存在，不影响其他源。

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
- **补充口径（非 token）区块**：置于主明细表之后，按可用数据显示来源切换：「Qoder」与「Trae CN」
  - Qoder：页头标签页切换「活动 / 额度 / 估算」三个面板，与主报表同一套卡片/图表样式
    - 活动：KPI（活跃会话/提示/assistant 调用/工具调用/运行时长）、可切换指标的每日活动柱状图、按天 × 项目的活动明细表
    - 额度：最新余额卡片（余额/已用/总量/进度条/快照日）+ 区间 billable/免费/日均 KPI、每日 billable + 免费堆叠柱状图、按天明细表（credits/请求/免费/快照）。credits 为服务端真值，非 token
    - 估算：est 总/输入/输出、覆盖请求；按天 × 模型明细表，固定标注 `est` 与误差范围
  - Trae CN：hook 弱估算 KPI（est 总/输入/输出、覆盖请求）与按天 × 模型明细表，
    固定标注「弱估算（hook 可见内容，不含系统提示/工具定义）」与「不可与 token 真值或额度相加」
- 顶部覆盖提示：Qoder token、活动、额度、估算与 Trae CN 弱估算各自的时间范围，并注明口径不可相加；有补充数据时提供「查看补充 ↓」跳转
- 来源 chip：单击只看该来源、再点恢复全部；⌘/Ctrl/Shift+单击多选。Trae CN 无 token 真值，chip 显示弱估算总量；选中它时隐藏 token 主视图，只展示弱估算补充区
- 补充区跟随来源筛选：Qoder 补充数据只在 Qoder 被选中时出现；Trae CN 弱估算只在 Trae CN 被选中时出现，单独查看其他 agent 时不展示
- 模型 Top 8 / 项目 Top 8，点击筛选、再点取消（列表不会被自身筛选折叠）
- 快捷区间：今日 / 全部 / 近 7·30·90 天；日期选择上界为打开页面的当天（数据未产生也能选"今日"）
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
2. Trae CN H0 真实捕获验收：`usage hooks install trae-cn --scope global` 后，在 Trae CN 设置 > Hooks 确认已加载，
   发一条带工具调用的 prompt，再运行 `usage hooks status trae-cn` / `usage sync --source trae-cn` /
   `usage est --source trae-cn` 核对事件字段与估算结果
3. 计价（可选）：价格表目前为空，`cost_equiv_usd` 恒为 `unknown`——PROBE 证明本机 18/21 个模型是 free/别名，成本列价值低
4. WorkBuddy collector（需先安装 WorkBuddy 采集样本）
5. v2 可选项：`NullStore`、zstd 归档、L3 FSEvents daemon；Qoder 估算系数用新样本定期校准

> 完整快照随时可复现：`python3 scripts/probe.py`
> 验收命令：`python3 -m unittest discover -s tests -t .`
