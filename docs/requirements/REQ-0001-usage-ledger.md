# REQ-0001 本地 AI 编码工具用量台账

| 项 | 内容 |
|---|---|
| ID | REQ-0001 |
| 类型 | 功能卡 |
| 状态 | 活跃 |
| Owner | wayne |
| 关联 | [CHG-0001](../changes/CHG-0001-docs-alignment.md)、[CHG-0003](../changes/CHG-0003-docs-status.md)、[ADR-0001](../adr/ADR-0001-source-of-truth-db-as-archive.md)、[ADR-0002](../adr/ADR-0002-pull-collection-no-daemon.md)、[ARCHITECTURE.md](../ARCHITECTURE.md) |
| 代码基线 | usage-ledger v0.6.0（main `820a6f2`，2026-11-15） |
| 平台 | macOS（Apple Silicon），单机、单用户、本地 |
| 最后更新 | 2026-11-16 |

> 本文是**当前需求事实源**。设计沿革见 [DESIGN.md](../DESIGN.md)（历史方案稿）与各源设计文档；当前实现见 [ARCHITECTURE.md](../ARCHITECTURE.md)。

## 摘要

usage-ledger 是 macOS 上的本地 AI 编码工具用量台账，统一采集 Claude Code、Codex、OpenCode、Kilo、Cline、Qoder 与 Trae CN 的 token、credits、估算和活动数据。它默认离线、只读源、只写本地 SQLite，并通过 CLI 与单文件 HTML 报表提供按天 / 源 / 模型 / 项目的视图。核心约束是 token 真值、credits、估算与活动分轨展示，任何两轨都不相加；Trae CN credits 的两条显式刷新路径是唯一联网例外。本文记录 v0.6.0 的当前事实与验收，不承担历史变更记录。

---

## 1. 问题与证据

### 1.1 谁、什么场景、现在怎么做

- 用户同时使用 Claude Code、Codex CLI、OpenCode、Kilo、Cline、Qoder、Trae CN（桌面版 + CLI），需要回答“某天 / 某周 / 某月，每个平台、每个模型、每个项目用了多少 token / credits”。
- 现状：各工具各自落盘；没有统一视图；想看用量只能在多个日志、数据库、厂商页面之间切换，或临时写脚本。
- 订阅制下，token 数量与 credits 额度是两套口径；用户需要同时看到“服务端真值”和“本地估算”，并且两者**不能相加**。

### 1.2 代价

- 无法核对厂商账单 / 额度消耗，无法判断哪个工具、哪个模型成本最高。
- 源日志会被轮转、迁移、压缩或删除；不持续采集就会永久丢失历史。
- 把“本地取不到”误读为“没使用”，导致决策偏差。

### 1.3 证据

- [RESEARCH.md](../RESEARCH.md)：ccusage / tokscale / TokenTracker 等竞品横评；结论是采集层不值得重写，报表层没有合口味的产品。
- [PROBE.md](../PROBE.md)：2026-10-22 本机全量只读扫描 4 源、16,799 条记录、约 2.14B token；发现 9 处规格偏差。
- [DISCUSSION.md](../DISCUSSION.md)：原始需求与决策链（不自研采集层；全平台在数据层不成立；不需要常驻进程）。
- 现实边界：Qoder 新客户端自 2026-09-16 起不再写 token 真值；Trae CN 本地库为 SQLCipher 加密；ChatGPT 桌面端无本地数据；Cline 1,806/1,821 条 assistant 消息带 `metrics`。详见 [README.md](../../README.md) 与各源设计文档。

### 1.4 不做的后果

- 继续靠零散脚本 / 厂商页面拼接，无法形成长期台账。
- 源日志被清理后无法回填，历史永久缺失。
- 更容易把估算值当真值、把缺失当零，做出错误的成本判断。

---

## 2. 目标与非目标

### 2.1 目标

- **G1 统一台账**：用 `usage report` / `usage html` 在一个视图里回答“某段时间、每个源、每个模型、每个项目的 token / credits / est 用量”，并明确标注口径。
- **G2 可持续**：安装后 `backfill` 导入历史；日常每小时增量 + 每日全量重扫；源删除 / 轮转后仍能从归档中保留。
- **G3 轻量、离线、隐私**：默认零网络、零第三方依赖、无常驻进程；只读源、不落正文；唯一联网例外是 Trae CN credits 的两条显式前台刷新路径。

### 2.2 非目标

- 产品形态：GUI / TUI / 菜单栏 / 桌面宠物 / 社交 / 排行榜 / 云同步 / 多用户 / 遥测。
- 数据获取：不逆向厂商私有 API、不解密加密库、不为“无本地数据”的平台估算 token、不伪造 0。
- 口径：不把 token 真值、credits、估算 token、活动指标任何两轨相加；不把 Qoder 与 Trae CN 的 credits 相加。
- **当前不做（后续 opt-in）**：计价与预算告警（价格表为空，`cost_equiv_usd` 当前为 unknown）、WorkBuddy 采集（缺本机样本）、`NullStore` / zstd 归档 / L3 daemon、项目路径哈希模式、macOS 之外的平台。

> 以上“当前不做”不是永久非目标；有真实需求和数据时按新 CHG 追加。

---

## 3. 当前功能（As-Built，v0.6.0）

> 本节回答“这个工具具体做什么、数据从哪来、命令输出什么”。只写 v0.6.0 已实现并验证的行为；验收条款在 §5，已知缺口在 §6。默认路径可用 `USAGE_LEDGER_SOURCE_HOME`、`USAGE_LEDGER_HOME`、`USAGE_LEDGER_DB` 等环境变量覆盖。

### 3.1 交付形态与功能清单

- **交付物**：一个 Python CLI（`usage` / `usage-ledger`）、一个本地 SQLite 档案、一个可离线分发的单文件 HTML 报表、一组 launchd 任务。无常驻采集进程、无 GUI / TUI、无云同步。
- **数据流**：源 JSONL / SQLite / hook 事件 → collector（只读、逐条计数、按源去重）→ `SourceResult` → `SqliteStore`（`usage_turn` 等表）→ aggregation → CLI / HTML。`--stateless` 跳过 store，直接从源聚合。

| 功能 | 用户得到什么 | 主要入口 | 当前边界 |
|---|---|---|---|
| F1 精确 token 台账 | Claude、Codex、OpenCode、Kilo、Cline、Qoder 历史 token，按天 × 源 × 模型 × 项目 × 会话聚合 input / output / cache read / cache write / reasoning 与调用数；可过滤、导出、排行 | `usage report`、`usage export`、`usage top` | 只覆盖本地仍有记录的源；Qoder 2026-09-16 后无 token 真值 |
| F2 回填、增量与归档 | 首次导入历史；后续 sync 重复扫描并幂等 upsert，已有记录不重复；源删除后仍保留归档记录 | `usage backfill`、`usage sync`、`usage schedule install` | 丢失窗口取决于 launchd 是否安装；`prune` 有已知 P0 重复汇总问题，见 §6 |
| F3 查看即最新 / 直读 | 打开报表前自动检查源文件 mtime 并增量 sync；也可完全绕开数据库直读源 | `report` / `export` / `top` / `html` 的自动刷新；`usage live`；全局 `--stateless`；`--live` | `--live` 当前只合并 token 轨，不合并活动 / 额度 / 估算 |
| F4 Qoder 四轨 | token 历史、活动指标、credits 额度、估算 token 分表分示，任何两轨都不相加 | `usage report`、`usage activity`、`usage credits`、`usage est` | 新客户端不再写 token；credits 只有逐请求真值，没有 token 真值 |
| F5 Trae CN credits | 按会话拉取服务端 credits 真值，按本地日归属；无缓存或刷新失败时显式标注 | `usage sync --source trae-cn --remote`、`usage credits --source trae-cn`、`usage html` | 只有两条显式联网路径；会话级、跨天不可拆；项目维度依赖 hook 映射 |
| F6 Trae CN hooks 弱估算 | 安装官方 hook 后，把可见字符数重放为 `trae-cn.est`，用于看趋势 | `usage hooks install/status`、`usage sync --source trae-cn`、`usage est --source trae-cn` | 看不到系统提示 / 工具定义 / 工具间文本；误差可能数倍，永不与 credits 或 token 相加 |
| F7 离线 HTML 报表 | 单文件、零外部请求的交互报表；多 Agent 多选，token / credits / est 分单位展示 | `usage html`、`usage html --open` | 生成时快照；Trae credits 刷新受联网与凭证影响 |
| F8 健康检查 | 每个源可用性、最近同步、归档量、credits / est 覆盖、额度快照、Trae 凭证、hooks、schema 漂移告警 | `usage doctor`、`usage doctor --probe <source>` | 只诊断，不自动修复；部分检查依赖 db 存在 |
| F9 维护与调度 | 清理明细、安装 launchd、安装 / 卸载 Trae hooks、查看模型别名与价格状态 | `usage prune`、`usage schedule`、`usage hooks`、`usage pricing` | 计价表为空，所有模型价格为 unknown；预算告警未实现 |

**典型使用路径**：

```bash
# 首次安装与历史导入
uv tool install .
usage backfill
usage report --since 7d
usage html --open

# 日常查看
usage report --weekly
usage top models --since 30d
usage credits --since 7d
usage est --source qoder --since 7d
usage activity --since 30d

# Trae CN credits（显式联网）
usage sync --source trae-cn --remote --days 30
usage credits --source trae-cn
usage html --offline --open

# Trae CN hooks 弱估算（离线）
usage hooks install trae-cn --scope global
usage hooks status trae-cn
usage sync --source trae-cn
usage est --source trae-cn --group-by day,model
```

### 3.2 数据源契约

所有采集器只读源；不写源目录、不修改源数据库。以下路径为 macOS 默认值。

#### 精确 token 源

- **claude** — `~/.claude/projects/**/*.jsonl`，包括 `subagents/` 下的转录。
  - 提取：只处理 `type=assistant` 且 `message.usage.iterations` 存在的消息；取 `input_tokens`、`output_tokens`、`cache_read_input_tokens`、`cache_creation_input_tokens`；模型取 `message.model`，项目取 `cwd` 的 basename，会话取 `sessionId`。
  - 去重：`claude:<message.id 或 uuid>`；缺失 id 或时间戳的消息计入错误并跳过；零 token 记录跳过。
  - 边界：中间态消息（有 usage 但无 `iterations`）跳过并计数；不读正文。
- **codex** — `~/.codex/sessions/**/*.jsonl` 与 `~/.codex/archived_sessions/**/*.jsonl`。
  - 提取：`session_meta` / `turn_context` 提供会话、项目、模型；`event_msg.token_count` 同时含 `total_token_usage`（累计）和 `last_token_usage`（单次）。首条用 `last`，后续用相邻累计值差分；缓存读、推理输出、缓存写分别从累计差中拆出，input 扣除缓存。
  - 去重：`codex:<文件名 stem>:<累计 total_tokens>`；同一 rollout 同时存在于 sessions 与 archived 时只计一次。
  - 边界：`.jsonl.zst` 只统计数量、不解析；累计值回退时按 0 处理，不做负值。
- **opencode** — `~/.local/share/opencode/opencode.db`（或 `opencode-stable.db`）。
  - 提取：优先读 `session_message` 表中 `type=assistant` 的消息，兼容旧 `message` 表；取 `tokens.input` / `output` / `cache.read` / `cache.write` / `reasoning`；模型取 `model.id` 或 `modelID`，项目取 `path.cwd` 或 `session_v2.directory` 的 basename。
  - 去重：`opencode:<message.id>`；消息跨新旧表同时存在时只计一次。
- **kilo** — `~/.local/share/kilo/kilo.db`。
  - 提取与去重：与 OpenCode 同一 adapter，去重键 `kilo:<message.id>`。
- **cline** — `~/.cline/data/sessions/<session>/<session>.messages.json`，配套 `<session>.json` 元数据。
  - 提取：只处理 assistant 消息的 `metrics`；`input = inputTokens − cacheReadTokens − cacheWriteTokens`，`output = outputTokens`（含推理 token，不单列）；模型取 `modelInfo.id`，缺失回退元数据 `model`；项目取 `workspace_root` / `cwd` 的 basename。
  - 去重：`cline:<message.id>`；无 id 时回退 `cline:<session>:<ts>:<index>`。
  - 边界：无 `metrics` 的消息（中断 / 失败）跳过并计数，不伪造 0；VS Code 扩展旧版 `tasks/*/ui_messages.json` 未接入。
- **qoder（历史 token）** — `~/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db`（只读打开）。
  - 提取：`chat_message` 中 `role=assistant` 且 `token_info` 非空的行；`input = prompt_tokens − cached_tokens`，`output = completion_tokens`，`cache_read = cached_tokens`；模型取 `model_info.model_key` 或会话首选模型；项目取 `project_name` 或 `project_uri` 的 basename。
  - 去重：`qoder:<message.id>`；本机历史覆盖 2026-06-01 ~ 2026-09-16。

#### Qoder 另外三轨

- **qoder.activity（活动，不是 token）** — `~/Library/Application Support/com.qoder.app.stable/main.sqlite`。
  - 提取：`chat_session_messages` 按 `created_at` 归属本地日；`role=user` 计 `prompts` 与会话数，`role=assistant` 计 `assistant_calls`；`payload_json.turnMetrics.turnCount` / `durationMs` 分别计 `turns` / `duration`；`parts` 中 `type=tool` 计 `tool_calls`；有 `turnMetrics` 的 assistant 单独计 `assistant_with_metrics`。
  - 存储：按 `source + day + project` 整日替换，不做逐条 request 去重；每日全量重建受影响日期。
  - 边界：只用于观察使用强度，不参与 token、成本或 credits 计算；仅 Qoder 有活动数据。
- **qoder.credits（额度真值）** — 两条只读来源：
  - 转录 `~/.qoder/projects/**/*.jsonl`：每条 assistant 响应的 `usage.request_id`、`usage.credits`、`usage.billable`；`billable=true` 计入日消耗与请求数，免费请求单列 `free_credits`；归属响应时间所在本地日；项目取 `cwd` basename。
  - 桌面端 `main.sqlite.chat_session_messages`：2026-11-13 晚间起新客户端把每轮金额写在 `turn_credits`；每条非空值（含 0）按 `qoder-turn:<session_id>:<message_id>` 输出 `billable=true` 的 credit，项目 / 模型取 `chat_sessions.cwd` basename / `chat_sessions.model`，归属 `created_at` 本地日；`turn_credits_request_set_id` 命中转录 `request_id` 时跳过，避免重复。
  - 去重：转录按 `request_id`；DB 行使用 `qoder-turn:` 前缀；两源重复解析幂等覆盖。
  - 额度余额：另从 `~/Library/Application Support/com.qoder.app.stable/logs/*/main*.log*` 的 `用量响应摘要` 提取快照；只展示当前余额 / 总量，不用非单调快照差分推导日消耗。 `qoder.credits` 的源签名同时跟踪转录、日志、活动库及 WAL。
- **qoder.est（估算 token）** — 同一批 Qoder 转录。
  - 提取：要求响应带 `usage.context_usage_ratio`；`est_input = round(ratio × 200000)`，`est_output = round(输出字符数 ÷ 模型系数)`；系数 `gfmodel=3.85`、`dfmodel=4.58`、其他 `3.8`。
  - 去重 / 跳过：键为 `<session>:<响应时间戳>`；无 `ratio` 的旧版转录跳过，避免与历史 token 真值重复。
  - 边界：误差约 ±30~40%，只作趋势；永不与 credits 或 token 真值相加。

#### Trae CN 两轨

- **trae-cn.credits（会话级真值，定向联网）**
  - 入口：只有 `usage sync --source trae-cn --remote` 与报告范围内包含 Trae 的 `usage html` 会请求客户端同源 usage 接口；其余命令离线。
  - 凭证：默认读取 Trae CN 登录态 `~/Library/Application Support/Trae CN/User/globalStorage/storage.json` 中的 `iCubeAuthInfo://icube.cloudide`；优先级 `--jwt-file` > `TRAE_CN_JWT` > `TRAE_CN_JWT_FILE` > `storage.json`。
  - 提取：按会话拉取 credits，归属 `usage_time` 所在本地日；`request_id = trae-cn:<session_id>`，重复拉取幂等覆盖；项目用 hook 事件的 `session → project` 尽力映射，未命中显示 `-`。
  - 窗口：默认最近 30 天；`--days N` 或 `--full`（365 天）可扩大；`--since` 不能与 `--days/--full` 同用。
- **trae-cn.est（hook 弱估算，离线）**
  - 事件：hook 安装后写入 `~/.local/share/usage-ledger/trae-cn/events-YYYY-MM-DD.jsonl`（目录 0700、文件 0600）；事件类型 `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`Stop`。
  - 提取：hook 只记录 `event`、`session`、项目 basename、`tool`、`tool_use_id`、`loop`、`chars_in`、`chars_out`、可选 `model`、时间戳；不记录 prompt、tool input / response、assistant 正文。
  - 重放：按会话累计可见上下文；`PreToolUse` 与 `Stop` 各产生一次估算；`est_input = min(round(上下文累计字符 ÷ factor) + overhead, window)`，`est_output = round(输出字符 ÷ factor)`；默认 `factor=3.8`、`overhead=0`、`window=200000`，可用 `USAGE_LEDGER_TRAE_EST_FACTOR` / `_OVERHEAD` / `_WINDOW` 校准。
  - 去重：事件 `uid`；只覆盖 hook 安装后的会话，不回溯加密库历史。

#### 明确未接入

- **ChatGPT 桌面端**：无本地 token 数据，只存在配额；报表中不出现该源，不显示为 0。
- **WorkBuddy**：当前 7 个采集源不包含；未实现前 `doctor` / 报表都不会出现该源。
- **Qoder 新客户端 token**：2026-09-16 后不再写 token；只能看 credits 与 est。
- **Trae CN 本地加密库**：SQLCipher 不可读；不尝试解密，credits 走同源 API，token 只有 hook 弱估算。

### 3.3 CLI 命令参考

全局选项：`usage --version` 显示版本；`usage --stateless <命令>` 不读库、不落库，直接读源。除 `sync --remote` 与包含 Trae 的 `html` 外，所有命令默认离线。

| 命令 | 作用 | 关键参数 | 输出 / 副作用 |
|---|---|---|---|
| `sync` | 扫描本地源并写入 SQLite；`--source` 可重复 | `--source`、`--since`、`--full`、`--dry-run`、`--remote`、`--days`、`--jwt-file` | 逐源摘要；`synced N records -> DB`；`--full` 时源中消失的记录标 `archived=1`；`--dry-run` 不写库、不联网 |
| `backfill` | 首次历史导入，等价于 `sync --full` | `--source`、`--since` | 写入 SQLite；可重复执行，幂等 |
| `live` | 直读源，显示最近完成的调用；不写库 | `--source`、`--session`、`--watch [秒]` | 最近 50 条（source / session / model / tokens / updated）、今日合计；`--watch` 循环刷新 |
| `report` | 聚合 token 台账；出结果前自动检查源 mtime 并增量刷新 | `--since` / `--until` / `--range`、`--daily` / `--weekly` / `--monthly`、`--group-by`、`--filter`、`--source`、`--model`、`--project`、`--live`、`--format` | 维度列 + token 字段 + `cost_equiv_usd`、`cost_source`、`turns`；`table` / `json` / `csv`；说明写 stderr |
| `export` | 同 `report` 的 CSV 导出 | 同 `report` | 当前实现固定 CSV；`--format json` 会被覆盖（P2） |
| `top` | 按模型 / 源 / 项目 / 会话排行 | `models` / `sources` / `projects` / `sessions`、`--since`、`--until`、`--limit`（默认 20）、`--format` | 按 token 总量降序；table 为制表符分隔，json 额外含各 token 字段 |
| `activity` | Qoder 活动指标 | `--range` / `--since` / `--until`、`--source`、`--project`、`--group-by`、`--format` | 默认 `day,source,project`；字段 `sessions`、`prompts`、`assistant_calls`、`assistant_with_metrics`、`turns`、`tool_calls`、`duration` |
| `credits` | Qoder / Trae CN credits 日表 | `--source`（`qoder` / `trae-cn`）、`--range` / `--since` / `--until`、`--format` | Qoder：day / credits / requests / free_credits / snapshots；Trae：day / credits / sessions；默认分列，不跨厂商合计；不联网 |
| `est` | Qoder 或 Trae CN 估算 token | `--source`（默认 `qoder`）、`--range`、`--group-by`、`--format` | 默认 `day,model`；列 `est_input`、`est_output`、`requests`；Qoder 另报 ratio 缺失数 |
| `html` | 生成单文件离线报表 | `--range` / `--since` / `--until`、`--source`、`--model`、`--project`、`--filter`、`--live`、`--offline`、`--max-age`、`--strict-refresh`、`--jwt-file`、`--output`、`--open` | 默认写 `./usage-report.html`；含 Trae 时默认刷新 credits；`--offline` / `--stateless` 不联网；`--strict-refresh` 刷新失败时退出码非 0 |
| `doctor` | 检查 DB、源、归档、credits / est、额度、凭证、hooks | `--probe <source>` | 诊断输出，不触发 sync、不写源：turns / daily 数、archived 数、activity、credits / quota / est 计数、DB / WAL 大小、逐源状态、最近全量扫描、Trae 凭证、hook 事件、漂移告警 |
| `pricing` | 查看模型别名与价格状态 | 可选模型名 | 无参数时列出别名；当前价格表为空，所有模型显示 `unknown`，不估算、不填 0 |
| `prune` | 把过期明细汇总进日表并删除明细 | `--keep-days`（默认 90）、`--dry-run` | 输出 cutoff / candidate / deleted / kept_archived；`archived=1` 明细保留；不能与 `--stateless` 同用 |
| `schedule` | 安装 / 卸载 / 查看 launchd 任务 | `install` / `uninstall` / `status`、`--dry-run` | 每小时第 7 分钟 `sync`；每天 00:15 `sync --full`；每天 00:20 `prune --keep-days 90`；plist 写入 `~/Library/LaunchAgents/` |
| `hooks` | 安装 / 卸载 / 查看 Trae CN hook | `install` / `uninstall` / `status`、`trae-cn`、`--scope global/project`、`--project`、`--dry-run` | global 写 `~/.trae-cn/hooks.json`，project 写 `<project>/.trae/hooks.json`；安装前备份；只管理本项目安装的 hook 组 |

### 3.4 报表字段与口径

- **维度**：`day`、`week`（ISO 周，如 `2026-W45`）、`month`（`YYYY-MM`）、`source`、`model`、`project`、`session`。默认 `day,source,model`；HTML 固定按 `day,source,model,project` 聚合。
- **token 字段**：`input` 为非缓存输入，`output` 为输出，`cache_read` / `cache_write` 为缓存读写，`reasoning` 为可分离的推理 token；总量为五项之和。各源统一为“缓存不重复计入 input”的口径。
- **`turns`**：聚合到的记录 / 消息条数；用于和 `--stateless`、归档数据对照，不是“对话轮次”。
- **`cost_equiv_usd` / `cost_source`**：用价格表折算的等价成本，不是实付。价格表为空时恒为 `null` / `unknown`；部分记录可计价时标 `partial`。当前没有预算告警。
- **日期归属**：所有源按本地时区的自然日归属；周 / 月按本地日期再分桶。Trae 会话级 credits 不能跨天拆分。
- **过滤**：`--filter` 支持 `source=...`、`model=...`、`project=...`、`session=...`，多个条件用逗号；`--source` / `--model` / `--project` 是快捷方式。Qoder 的 `--model` 同时接受内部键与界面显示名。
- **缺失数据**：缺失日期只在 stderr 输出 `no data: ...`，不把缺失补成 0；源不可用时由 `doctor` 和 HTML 状态条说明。
- **模型显示名**：Qoder 内部键在展示层映射为界面名（如 `dfmodel` → DeepSeek-Flash、`gfmodel` → GLM-5.3-Flash）；未知键原样显示。库里保留原始键。
- **口径隔离**：token 真值、Qoder credits、Trae credits、Qoder est、Trae est、Qoder activity 各自独立；`credits` 不跨厂商相加，任何估算都不与真值相加。

### 3.5 SQLite 存储与保留策略

数据库默认 `~/.local/share/usage-ledger/usage.db`，WAL 模式。表结构：

| 表 | 内容 | 主键 / 去重 |
|---|---|---|
| `source_state` | 每个源的同步状态、最近同步时间、最近事件时间、文件 mtime、记录数、错误 | `source` |
| `usage_turn` | 逐条 token 明细：源、时间、本地日、项目、会话、模型、五项 token、成本、`archived`、首次见到时间 | `id`（各源去重键） |
| `usage_daily` | 日 × 源 × 模型 × 项目 × 会话的 token 汇总与 `turn_count` | 联合主键 |
| `usage_activity` | Qoder 活动：天 × 项目 × 会话 / 提示 / assistant / 工具调用 / 时长 | `source + day + project` |
| `usage_credit` | 逐请求 / 会话 credits：`source`（qoder / trae-cn）、时间、日、项目、模型、credits、`billable` | `request_id` |
| `usage_quota` | Qoder 额度快照：总量、已用、剩余、单位、原始百分比、过期时间 | `request_id + quota_kind` |
| `usage_est` | 估算 token：`source`（qoder.est / trae-cn.est）、输入 / 输出估算、字符数、上下文比例 | `request_id` |
| `meta` | activity cursor、全量扫描时间、Trae 刷新窗口等内部状态 | `key` |

- **每日全量重扫**：源中已不存在的记录标 `archived=1` 保留，不随源删除而消失；源不可用时跳过归档判定，避免误标。
- **`prune --keep-days 90`**：把 cutoff 之前、未归档的明细按 `day/source/model/project/session` 汇总进 `usage_daily`，再删除这些明细；`archived=1` 明细不压缩、不删除。**当前存在 prune → sync → prune 重复累加 `usage_daily` 的 P0 缺陷，见 §6。**
- **`price_override`**：schema 中存在该表，但当前没有写入路径；计价未启用。

### 3.6 HTML 报表

- **文件形态**：单文件 HTML，CSS / JS / SVG 全内联，CSP `default-src 'none'`，无外部请求；可离线分发或归档。
- **Agent 多选**：页面顶部唯一选择区，列出 claude、codex、opencode、kilo、cline、qoder、trae-cn，chip 上带各自汇总值；至少保留一个。单击只看该 Agent，再次单击恢复全选；⌘ / Ctrl / Shift+单击增减成员；另有“全选”按钮。
- **KPI 分块**：`精确 Token（tokens）`、`精确 Credits（credits）`、`估算` 按单位分组；每组内卡片保持连续，整个 KPI 区只有一张主卡；区间无行的单位合并为一张“无数据”卡，不铺零卡；500px 下数值完整显示、不省略。Qoder 与 Trae credits 使用同一组四张卡：`区间 credits`（主卡；Qoder 为 billable，Trae 为会话级）、`免费 credits`、`区间日均`、`最新额度余额`；Trae 不提供的免费额度 / 额度快照显示 `—` 并说明原因，Qoder 的余额 / 请求数、Trae 的会话数 / 模型数放在副文案。Trae 无缓存时显示“未同步”或“刷新失败”卡片与刷新命令。
- **每日图表**：Token 按 Agent 堆叠；credits 单选时使用同一图表容器与坐标轴，Qoder 为 billable / 免费双序列，Trae 为 billable 单序列（不伪造免费序列）；Qoder + Trae 同时选中时改为分组柱状图，不堆叠成一个总数；Qoder 影子估算与 Trae 弱估算默认隐藏，打开“估算”开关后分别显示，且不与 credits 相加。
- **Top 8**：模型与项目各 Top 8，按主单位（优先 tokens → credits → 估算）排序；Qoder + Trae 同时选中时按 Agent 分组排名，不做跨厂商合计；条形与百分比同用“相对第一”口径并明示，排序标签写明单位与当前区间，总计为 0 时百分比显示 `—`；估算只作为同一 Agent 行的次要标注，不把只有估算的行显示成 `0 credits`。
- **明细表**：统一一张表，`Agent` 与 `单位` 列区分来源和口径；不适用的列显示 `—`；Trae credits 的计数列叫“会话”，Qoder 叫“请求”；按天 × Agent × 模型 × 项目聚合，Token / Credits / 估算列使用分组表头。默认只显示 token / credits 行；Qoder 影子估算与 Trae 弱估算由同一个“估算”开关控制，打开后才追加估算行。宽于容器时冻结日期 / Agent（>640px 再冻结模型 / 项目），隐藏当前筛选下全空的列；窄于卡片内容宽度时扩大非冻结数据列填满卡片，冻结列宽与偏移不变；按单位和厂商分别显示合计行，Qoder 与 Trae credits 不合并，来源专用列在对方明细 / 合计行显示 `—` 而非 `0`；分页提供页大小与直接跳转，1440px 下不使用表内纵向滚动。
- **估算开关**：Qoder 影子估算与 Trae 弱估算默认关闭，仅在选中对应 Agent 且存在估算数据时显示开关；开关文案与 `aria-label` 随选中 Agent 生成。关闭时估算不进入 KPI、图表、Top 8、明细表和页脚计数；打开后 Qoder 显示影子 est、Trae 显示弱估算，始终注明不可与 credits 相加。
- **活动指标**：仅选中 qoder 时显示，折叠在页面底部，不参与任何用量计算；展开后分页并冻结日期 / 项目，折叠时跳过重绘，只挂载当前页行。Trae 没有活动数据时不渲染空活动区。
- **数据新鲜度**：Trae credits 状态（已刷新 / 离线缓存 / 刷新失败 / 未同步）放入页首问号按钮打开的“口径与数据覆盖”说明层，且仅选中 Trae 时渲染；由后端 `coverage["trae-cn.credits"]` 驱动，不在前端猜测；有 warn / error 时问号按钮显示提醒点。
- **日期范围**：默认取截至数据日的近 7 个自然日（含端点，起点不早于数据起点），并保留“全部”为全量，避免把单日 / 短周期 Agent 的图压成一条线；日期预设与选择器锚定数据截止日，不允许未来日期；可选“聚焦有数据区间”默认关闭，关闭时恢复近 7 天。见 [CHG-0004](../changes/CHG-0004-html-report-empty-state-and-filters.md)。
- **展示与交互**：覆盖说明、Trae 状态、生成时间与行数口径不再单独占据报告卡片，统一收进页首问号按钮（`?`）打开的说明层；生成时间只出现一次，帮助层的“本页”计数随筛选刷新。筛选行使用固定宽度，切换 Agent 不改变模型 / 项目 / 搜索控件的宽高与换行；图表 tooltip 支持触控与键盘；页面滚动后保留紧凑粘性筛选条与回到顶部，≤640px 折叠为“筛选”抽屉；筛选 / 排序 / 页码写入 URL hash 与 `localStorage`，URL 优先，布尔开关接受 `true` / `"1"`，无效状态丢弃或夹紧；主题仍单独持久化。见 [CHG-0005](../changes/CHG-0005-html-report-display-and-interaction.md)、[CHG-0008](../changes/CHG-0008-coverage-help-popover.md)、[CHG-0011](../changes/CHG-0011-html-boolean-state.md)、[CHG-0012](../changes/CHG-0012-html-filter-sync.md)。
- **快照属性**：HTML 是生成时快照，再次打开旧文件不会更新；生成过程中可能按联网规则刷新 Trae credits。

### 3.7 新鲜度与调度

- **新鲜度检查**：`report` / `export` / `top` / `html` 出结果前取各源最新文件 mtime，与 `source_state.last_file_mtime` 比对；只有变新的源才触发一次该源的幂等 sync。普通 JSONL 源会重扫文件、靠 DB 去重；Qoder 转录按文件偏移增量读取。检查成本是一次目录遍历 + stat，不解析日志。
- **检查范围**：指定 `--source` 或 `--filter source=...` 时只检查 / 刷新该源；否则检查全部源。
- **提示位置**：自动同步提示走 stderr，因此 `--format json/csv` 的 stdout 始终是干净数据。
- **库不存在**：`report` / `top` / `html` 降级为直读源并提示；`credits` / `est` 当前会静默新建空库，行为不一致是已知 P1。
- **`--stateless`**：不读库、不落库、不自动 sync；Trae credits 显示未同步（不读 SQLite 缓存）。
- **`--live`**：在库结果上合并源中最新 token 记录，按去重键以源为准；当前不合并活动 / 额度 / 估算（P1）。
- **launchd**：`usage schedule install` 安装三个任务：每小时第 7 分钟增量 `sync`；每天 00:15 `sync --full`；每天 00:20 `prune --keep-days 90`。`status` 查看 installed / loaded，`uninstall` 卸载；`--dry-run` 只打印 plist 不写入。

### 3.8 隐私与安全

- **只读源**：JSONL 以只读方式打开；OpenCode / Kilo / Qoder 的 SQLite 以 `mode=ro` 和 `PRAGMA query_only` 打开；不写源目录、不修改源数据库。
- **不落正文**：DB 只存 token、模型、项目 basename、会话 id、时间等元数据；不存 prompt、assistant 文本、tool input / response。Qoder est 只在内存中统计字符数；Trae hook 只落事件元数据与字符数。
- **项目标识**：当前只存项目目录 basename；路径哈希模式未实现（后续 opt-in）。
- **凭证**：Trae JWT 只在刷新进程内使用，不落库、不写日志、不进 HTML；拒绝符号链接和 group/world-writable（`mode & 0o022`）凭证文件；认证 / API 错误经脱敏后输出。凭证过期需重新登录 Trae CN。
- **联网**：默认零网络；唯一例外是 `usage sync --source trae-cn --remote` 与包含 Trae 的 `usage html`。`--offline` / `--stateless` 可完全避免联网。
- **HTML**：CSP 禁止外部资源；所有注入页面的数据做转义；页面本身不发起网络请求。
- **无遥测**：不向任何服务发送使用数据；不读浏览器 Cookie、不读 Keychain、不解密 SQLCipher、不逆向私有 API。
- **失败隔离**：单个源缺失 / 损坏 / 解析失败时，记录错误并继续处理其他源；坏行跳过并计数，不中断整次同步。

---

## 4. 成功指标

**主指标**：7 个外部源在 `usage doctor` 中可用，且 `usage report` 与 `usage --stateless report` 对同一范围 / 源输出一致。

| 指标 | 基线（v0.6.0） | 目标 | 统计口径 / 证据 |
|---|---|---|---|
| 外部源覆盖 | 7 个：claude / codex / opencode / kilo / cline / qoder / trae-cn | 保持 7 个可用；新增源不破坏现有源 | `usage doctor`；`tests/test_collectors.py` |
| 回归测试 | 159 tests OK | 全绿；新增行为必须有测试 | `python3 -m unittest discover -s tests -t .` |
| 读写一致 | `report` 与 `--stateless report` 同范围同结果 | 保持一致 | `tests/test_cli.py::CliConsistencyTest` |
| 数据丢失窗口 | 每小时增量 + 每日全量（设计目标 ≤1h） | 安装 launchd 后实测 ≤1h | `usage schedule install`；待真实运行验证 |
| 默认联网次数 | 0（除 Trae credits 显式路径） | 保持 0 | `test_sync_without_remote_does_not_call_network` 等 |
| 隐私 | 不写源、不落 prompt / 正文；project 仅存 basename | 保持；哈希模式待实现 | 代码审计 + hook / collector 测试 |
| 口径隔离 | Qoder 四轨、Trae credits/est、跨厂商 credits 分开 | 任何两轨都不相加 | `test_credit_sources_are_separated`、`test_est_source_migration_separates_trae`、HTML 测试 |

**护栏指标**：

- 任何报表 / 页面不得把缺失源显示为 0；必须显示 `-` / 未同步 / 未安装，并在 `doctor` 或页脚解释。
- 任何刷新失败不得删除已有缓存；默认软回退并显式标注。
- 估算轨必须带 `est` 标注；不得与真值同列相加。

---

## 5. 当前需求与验收（EARS）

> 每条 R 至少映射一个测试或验收步骤。测试命令统一为：
> `python3 -m unittest discover -s tests -t .`

### 5.1 采集、归档与报表

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R1 | When the user runs `usage report`, the system shall output daily × source × model token rows for all available sources, including input/output/cache_read/cache_write/reasoning and cost fields, with `--since/--until/--range/--weekly/--monthly`, `--group-by`, `--filter`, and `json/csv` output. | `tests/test_cli.py::CliConsistencyTest.test_report_grouping_and_filtering`；手工 `usage report --since 7d` |
| R2 | While a SQLite archive exists, the system shall produce the same result from the DB and from `--stateless` direct source reads for the same range/source; `--stateless` shall not read or write the DB. | `test_backfill_idempotent_and_report_consistency`、`test_stateless_does_not_touch_db` |
| R3 | When `report` / `export` / `top` / `html` is invoked and a source file mtime is newer than the stored signature, the system shall incrementally sync only the requested sources before output, and write progress to stderr so stdout stays machine-readable. | `test_report_auto_syncs_when_source_has_new_data`、`test_auto_sync_only_checks_requested_source`、`test_report_auto_syncs_new_cline_messages`、`test_report_does_not_resync_unchanged_trae_events` |
| R4 | When the user runs `backfill` or `sync`, the system shall import existing source history idempotently with source-specific dedup keys, so repeated runs do not duplicate rows. | `test_backfill_idempotent_and_report_consistency`、`tests/test_store.py::StoreTest.test_upsert_is_idempotent`、`test_sync_and_est_are_idempotent`、`test_duplicate_rollout_in_archived_is_counted_once` |
| R5 | While a record disappears from its source, the system shall mark it `archived=1` on a daily full rescan and retain it; when `prune --keep-days 90` runs, it shall roll up expired detail into daily aggregates while keeping archived detail. | `StoreTest.test_mark_archived_and_restore`、`test_prune_rolls_up_and_keeps_archived_detail`、`test_archived_detection_skips_unavailable_source`；**已知缺口见 §6 P0-1** |
| R6 | When the user runs `usage doctor`, the system shall report per-source availability, last sync state, archive/turn counts, credits/est coverage, Trae auth status, and explicit warnings for stale or missing data. | `test_doctor_reports_gaps`、`test_doctor_reports_both_ledgers`、`test_doctor_reports_hooks_and_estimates`、`test_doctor_reports_storage_auth`、`test_doctor_warns_group_or_world_readable_storage` |

### 5.2 Qoder 四轨

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R7 | When Qoder IDE history is available, the system shall import its token truth into the `qoder` source with the same schema/口径 as other token sources, covering 2026-06-01 ~ 2026-09-16. | `tests/test_collectors.py::QoderTokenTest`、`test_backfill_stores_tokens_and_activity` |
| R8 | While Qoder desktop activity data is available, the system shall store sessions/prompts/tool calls/turns/duration in the separate `qoder.activity` track, show it only when Qoder is selected, and exclude it from token/cost calculations. | `QoderActivityTest`、`test_activity_only_refresh_when_activity_db_touches`、`test_html_contains_activity_and_coverage` |
| R9 | When Qoder transcripts contain per-request billing fields or the desktop database contains `turn_credits`, the system shall aggregate both into `qoder.credits`, use quota snapshots only for current balance/cross-check (not daily derivation), and expose the merged rows via `usage credits` / `usage html`. | `QoderCreditsTest`、`QoderTurnCreditsTest`、`test_backfill_stores_credits_and_estimates`、`StoreTest.test_credit_sources_are_separated` |
| R41 | When Qoder desktop `chat_session_messages` carries numeric `turn_credits` (including 0), the system shall emit one billable credit per row keyed `qoder-turn:<session_id>:<message_id>`, attribute it to the local day of `created_at`, take project from `chat_sessions.cwd` basename and model from `chat_sessions.model`, merge it with transcript credits, skip a DB row whose `turn_credits_request_set_id` matches a transcript `request_id` from the current scan or from previously persisted Qoder credits, delete a previously persisted duplicate `qoder-turn:*` row, tolerate an older schema without the column, and include the activity DB / WAL in the `qoder.credits` source signature. | `tests.test_collectors.QoderTurnCreditsTest`、`tests.test_collectors.QoderSignatureTest`、`tests.test_cli.QoderCliTest.test_incremental_backfill_skips_turn_request_seen_in_transcript` |
| R10 | When Qoder transcripts have `context_usage_ratio` and text, the system shall compute `qoder.est` input/output estimates, label them as `est`, skip records without ratio, and never add them to credits or token truth. | `QoderCreditsTest`、`test_estimate_only_rows_not_ranked_as_zero_credit`、`test_model_labels_follow_qoder_display_names` |

### 5.3 Trae CN

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R11 | When the user explicitly runs `usage sync --source trae-cn --remote` or `usage html` with Trae CN in scope, the system shall fetch session-level credits from the Trae CN same-origin usage API using the local login credential; all other commands shall remain offline. It shall persist credits idempotently by `trae-cn:<session_id>`, attribute them to the local day of `usage_time`, reuse cache within `--max-age`, and soft-fallback with explicit warning on failure (`--strict-refresh` exits non-zero). | `test_sync_remote_calls_trae_refresh`、`test_sync_without_remote_does_not_call_network`、`test_html_default_refreshes_trae_credits`、`test_html_source_qoder_skips_trae_refresh`、`test_html_stateless_skips_trae_refresh`、`tests/test_trae_credits.py::SyncTest.test_sync_is_idempotent_and_maps_project`、`test_html_max_age_reuses_fresh_cache`、`test_html_refresh_failure_uses_cache_and_strict_exits_nonzero` |
| R12 | While reading Trae CN credentials, the system shall read them only in-process, never persist/log/embed them in HTML, reject symlinked or group/world-writable (`mode & 0o022`) credential files, and redact auth/API errors. Credential precedence shall be `--jwt-file` > `TRAE_CN_JWT` > `TRAE_CN_JWT_FILE` > `storage.json`. | `StorageCredentialTest`、`test_rejects_symlinked_file`、`test_rejects_world_writable_file`、`test_storage_info_is_secret_free`、`test_remote_sync_failure_is_redacted`、`test_html_refresh_error_and_cli_errors_are_redacted`、`tests/test_trae_credits.py::JwtTest` |
| R13 | When Trae CN hooks are installed and events are recorded, the system shall record only event/session/project basename/tool/char counts/optional model/timestamp (never prompt, tool input/output, or assistant text), replay them into `trae-cn.est` as a weak estimate, and never add them to credits or token truth. | `tests/test_trae_hooks.py::HookInstallTest`、`HookScriptTest.test_capture_is_private_and_counts_chars`、`tests/test_trae_collector.py::TraeReplayTest.test_design_example`、`test_env_factor_overhead_and_window`、`test_capture_replays_through_collector` |

### 5.4 Cline、HTML 与调度

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R14 | When Cline session files are present, the system shall extract assistant `metrics` as token truth, subtract cache read/write from `inputTokens`, use `cline:<message.id>` as the dedup key, and skip messages without metrics without fabricating 0. | `tests/test_collectors.py::ClineTest`、`tests/test_cli.py::ClineCliTest.test_backfill_and_report_match_stateless`、`test_metrics_mapping_and_fallbacks`、`test_broken_session_file_is_isolated` |
| R15 | When `usage html` runs, the system shall generate a single-file offline page with inline CSS/JS/SVG and CSP `default-src 'none'`, support agent multi-select and per-unit separate summaries (tokens / credits / est), and label all estimation/credits/activity boundaries. | `tests/test_html.py::HtmlRenderTest.test_payload_escaped_and_offline`、`AgentSelectionTest`、`SourceAwareCreditsTest`、`TraeStatusCopyTest`、`HtmlCommandTest`、`QoderHtmlTest` |
| R16 | When `usage schedule install` runs, the system shall install launchd jobs for hourly incremental sync, daily full rescan at 00:15, and daily prune at 00:20 with `--keep-days 90`; `--dry-run` shall write nothing. | `tests/test_scheduler.py::SchedulerTest.test_plists_have_calendar_and_environment`、`test_dry_run_writes_nothing` |

### 5.5 横切要求

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R17 | If a source root/file is missing, broken, or unparsable, then the system shall isolate the failure, count/skip bad records, and continue producing results from other sources rather than aborting the whole run. | `test_missing_root_is_unavailable`、`test_broken_session_file_is_isolated`、`test_bad_lines_and_shapes_are_skipped`、`test_missing_db_is_unavailable` |
| R18 | When `usage live` runs, the system shall read sources directly without DB writes and show the latest completed turns; target latency <0.3s. | 手工 `usage live` 计时；**当前实测约 2.3s，未达标，见 §6 P1-1** |

### 5.6 HTML 报表体验（CHG-0004）

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R19 | When the report is opened after the data-until date, the system shall anchor the “最新 / 7 / 30 / 90 天” presets and the date pickers to `DATA_UNTIL`, display “数据截至 YYYY-MM-DD”, and reject or clamp dates after `DATA_UNTIL`; the preset previously labeled “今日” shall be labeled “最新”. | `tests.test_html.HtmlDateRangeTest` |
| R20 | While Trae CN is selected and the current range has no Trae credit rows but cached credit data exists outside the range, the system shall show “当前区间无 Trae credits” instead of “未同步”; it shall show “未同步” only when no credit cache exists, and “刷新失败（使用缓存）” only when refresh failed and cache is being used. | `tests.test_html.HtmlEmptyStateTest` |
| R21 | When the current range has no token, credit, estimate, or activity rows, the system shall render one page-level empty state, hide zero-only KPI blocks, blank charts, the empty main table, and the activity block; a quota snapshot shown in this state shall be labeled “最新快照，与区间无关”. | `tests.test_html.HtmlEmptyStateTest` |
| R22 | When the activity chart renders for a selected range, the system shall use the same full-date buckets as the token / credits charts, plot zero for days without activity, and display “活跃 N 天 / 共 M 天” coverage; it shall not compress gaps by enumerating only days with data. | `tests.test_html.HtmlActivityTest` |
| R23 | When a user activates an activity table column header, the system shall sort rows by that column in ascending / descending order and expose `aria-sort`; if a column is not sortable, the header shall be a plain `th` without button styling. | `tests.test_html.HtmlActivityTest` |
| R24 | When the date range or search changes, the system shall rebuild model and project options from rows matching all other active filters, show each option’s row count, exclude zero-row options, and clear a selected value that no longer matches; rebuilding on search input shall be debounced. | `tests.test_html.HtmlFilterLinkageTest` |
| R25 | While a date range is active, agent chips shall show totals for the current range and use the same unit / scope as the KPI blocks; if all-time totals are kept, the chip label shall explicitly say “全部时间”. | `tests.test_html.HtmlFilterLinkageTest` |
| R26 | When the user activates “全选”, the system shall only change agent selection and shall not clear model, project, or search; “重置筛选” shall clear all filters including search. | `tests.test_html.HtmlFilterLinkageTest` |
| R39 | When the report loads without a valid persisted filter state, the system shall set the initial range to the last 7 calendar days ending at `DATA_UNTIL` (inclusive), clamp the start to `DATA_SINCE` when fewer than 7 days exist, keep the “全部” preset available, and apply the same range to all unit panels; a valid persisted state shall take precedence over the default. | `tests.test_html.HtmlDateRangeTest` |

### 5.7 HTML 报表展示与交互（CHG-0005）

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R27 | When the detail table is wider than its container, the system shall keep the identity columns visible while scrolling horizontally, and group token / credits / est columns under labeled headers; it shall remain one table. At widths above 640px, day / agent / model / project are frozen; at 640px and below, day / agent are frozen and model / project remain reachable by horizontal scroll. | `tests.test_html.HtmlTableLayoutTest` |
| R28 | The detail table shall show a totals row per unit and per vendor (Qoder credits and Trae credits shall not be summed together), hide columns that are empty for all rows in the current filter, and prevent cross-unit totals. Pagination shall offer page size and direct page jump; at 1440px the table shall not add a second vertical scroll container (pagination replaces the inner vertical scroll; at ≤640 an inner scroll is allowed). | `tests.test_html.HtmlTableLayoutTest` |
| R29 | The KPI area shall group cards by unit (Token / Credits / Est), use exactly one primary card, keep each unit’s cards together, avoid orphan rows at 1440px and 500px, and render values fully at 500px without ellipsis. A unit with no rows in the current range shall collapse into one “无数据” card instead of N zero cards. | `tests.test_html.HtmlKpiLayoutTest` |
| R30 | The system shall consolidate coverage, Trae status, generation time, and row-count explanations into one help panel opened from a question-mark icon, not a standalone report block; Trae status shall be shown only when trae-cn is selected; the Qoder shadow range shall be shown only when the shadow toggle is on or explicitly marked “未计入”; footer counts shall distinguish “库内 / 本页” and the “本页” detail / activity counts shall refresh after any filter change; generation time shall appear once. Missing-day hints shall be summarized as coverage (“活跃 N/M 天”), not a 10-date list. | `tests.test_html.HtmlCoverageBlockTest`、`tests.test_html.HtmlFocusRangeTest.test_footer_refreshes_after_filters` |
| R31 | In Top 8, bar length and percentage shall use the same denominator, or the label shall explicitly say “相对第一”; the sort label shall name the active unit and scope (“按 tokens 排序 · 当前区间”). If the grand total is 0, percentages shall show `—` rather than `0%` / `NaN`. | `tests.test_html.HtmlTopListTest` |
| R32 | The token metric selector shall live in the Token panel, the Qoder shadow toggle in the Credits panel, the estimate panel shall be labeled “Trae 弱估算”, and the shadow axis shall have a title; each control shall have an accessible name and its scope shall be visible. If shadow data is unavailable, the toggle shall be hidden or disabled with a reason; if a panel has no rows, it shall show one empty card rather than a blank chart. | `tests.test_html.HtmlChartControlsTest` |
| R33 | While the user scrolls past the top bar, a compact sticky filter bar (date, agents, search) shall remain available, with a back-to-top control; at ≤640px it shall collapse into a button / sheet that can be dismissed with Escape, and shall not cover content when the page is short. | `tests.test_html.HtmlNavigationTest` |
| R34 | Chart tooltips and data points shall support pointer / tap and keyboard focus, with clamped positioning based on the actual tooltip width; a focused point shall expose an accessible label, and Escape or focus loss shall dismiss the tooltip. No chart information shall be available only on mouse hover. | `tests.test_html.HtmlChartA11yTest` |
| R35 | The activity table shall paginate (or show top N with “展开全部”), keep date / project visible while scrolling, and show the current row count and page. It shall not render when the activity block is collapsed or the range has no activity; rows above the current page shall not be mounted in the DOM. | `tests.test_html.HtmlActivityPagingTest` |
| R36 | All user-facing labels shall use one display-name map and formatter; internal keys (`trae-cn`, `turns`, `used`, `est`) shall not appear raw; credits / quota decimals and units shall be consistent. If token-row `turns` and activity `turns` have different semantics, they shall be labeled “记录数” and “轮次” respectively and defined in the coverage block. Unknown keys may fall back to the raw value, but known keys must use the map. | `tests.test_html.HtmlLabelsTest` |
| R37 | When filters, sort, or page change, the system shall persist them in the URL hash or `localStorage` and restore them on load; URL state shall win when both exist. Boolean fields (`shadow`, `focusRange`) shall round-trip from native booleans, `1`, `"1"`, and `"true"`. Invalid agents, dates, models, projects, or page numbers shall be dropped or clamped; persisted state shall not contain token, credit, quota, or session values. The theme toggle shall remain persisted. | `tests.test_html.HtmlStatePersistenceTest`、`tests.test_html.HtmlStatePersistenceTest.test_url_boolean_state_round_trip` |
| R38 | The system shall provide an opt-in “聚焦有数据区间” toggle that sets the range to the union of days with data for the selected units and shows the resulting start / end; the default is the last 7 days per CHG-0004 R39, and disabling the toggle restores that default range. If no selected unit has data, the toggle shall be disabled with a reason. Selecting a model or project from Top 8 shall use the same focus recalculation and dimension-select rebuild path as the dropdown filters. | `tests.test_html.HtmlFocusRangeTest`、`tests.test_html.HtmlFocusRangeTest.test_top8_dimension_pick_refreshes_focus_and_selects` |
| R40 | When the agent selection changes, the system shall keep the model / project / search row’s control widths and positions stable; select controls shall use fixed widths (or fixed flex-basis) so option changes do not resize the row, long values shall truncate with ellipsis while the dropdown still shows full text, and the search input shall keep a stable width. At ≤640px the row may wrap at fixed breakpoints, but switching agents shall not change the wrapping or order. | `tests.test_html.HtmlFilterLayoutTest` |
| R42 | While a credits agent is selected, the system shall render the same four-card credit KPI sequence for Qoder and Trae CN — `区间 credits` (the only primary card), `免费 credits`, `区间日均`, `最新额度余额` — use the same credits chart container and a credit-only detail table by default; fields Trae CN does not provide (free credits, quota snapshot) shall show `—` with a reason, source-specific columns (Qoder free credits / requests / free requests, Trae sessions) shall show `—` in the other vendor’s detail and total rows rather than `0`, and Qoder / Trae credits shall never be summed. | `tests.test_html.HtmlCreditParityTest`、`tests.test_html.HtmlTableLayoutTest` |
| R43 | The HTML report shall hide both Qoder shadow estimates and Trae CN weak estimates by default and expose them through one `估算` switch whose label and `aria-label` follow the selected agents; while off, estimates shall not appear in KPIs, charts, Top 8, the detail table, or footer page counts; while on, each source’s estimates shall remain separately labeled and shall not be added to credits or token truth. | `tests.test_html.HtmlCreditParityTest` |
| R44 | While explanatory/coverage content is closed, it shall not occupy a standalone card in the report flow; a question-mark button shall open it, `aria-expanded` shall reflect the state, Escape or an outside click shall close it, Escape / close shall return focus to the button, and the button shall show a warning dot when Trae status is warn or error. At ≤640px the panel may use a fixed sheet layout. | `tests.test_html.HtmlCoverageBlockTest` |
| R45 | When the detail table's natural column width is narrower than its card content width, the table shall expand non-frozen data columns to fill the available width while keeping frozen identity column widths and sticky offsets unchanged; the extra width shall be distributed across non-frozen columns so that column widths sum to the table width. When the natural width is greater than or equal to the available width, the table shall keep its natural width and horizontal scrolling, without compressing frozen columns. | `tests.test_html.HtmlTableLayoutTest` |

---

## 6. 风险与兔子洞

### 6.1 当前已知缺口（必须先看）

| 级别 | 问题 | 影响 | 证据 / 跟踪 |
|---|---|---|---|
| P0-1 | `prune` 后再次 `sync` 会重放旧记录，下一次 `prune` 把同一段数据重复累加进 `usage_daily`（100 → 200） | 报表数据错误；已用最小用例复现 | [ARCHITECTURE.md §11](../ARCHITECTURE.md) |
| P1-1 | `usage live` 实测约 2.3s，未达 `<0.3s`；且扫描了不需要的 Qoder 轨 | 实时体验不达标 | [ARCHITECTURE.md §11](../ARCHITECTURE.md) |
| P1-2 | 读命令降级行为不一致：`report` 库不存在时降级读源，`credits` / `est` 会静默新建空库 | 用户可能误以为已归档 | [ARCHITECTURE.md §11](../ARCHITECTURE.md) |
| P1-3 | `report --live` 只合并 token，不合并活动/额度/估算 | 同一次 `html --live` 中四轨新鲜度不一致 | [ARCHITECTURE.md §11](../ARCHITECTURE.md) |
| P2 | `archived=1` 明细不压缩、死代码、`export --format json` 被覆盖、`top` 过滤能力缺失、`activity --source` 静默空等 9 项 | 可维护性与一致性 | [ARCHITECTURE.md §11](../ARCHITECTURE.md) |

> 上述问题需要独立 CHG 修复，不在本次文档整理范围内；修复前不得在 README / 报告中宣称已解决。

> HTML 报表的交互缺口（2026-11-16 实测）见 [CHG-0004](../changes/CHG-0004-html-report-empty-state-and-filters.md) 与 [CHG-0005](../changes/CHG-0005-html-report-display-and-interaction.md)；它们是独立变更，不与上表的 P0/P1 编号混用。

### 6.2 持续风险

- **上游 schema 漂移**：厂商随时改日志格式；靠 `doctor`、每日全量重扫、解析失败跳过并计数兜底。
- **日志轮转 / 删除**：每小时增量只能把丢失窗口压到约 1h；`backfill` 只能补仍存在的历史。
- **Qoder token 断供**：2026-09-16 后没有 token 真值；credits 与 est 只能显式替代，不能伪造 token。
- **Trae CN**：加密库不可读；credits 依赖登录凭证，过期后需重新登录；API 为会话级，跨天不可拆分；项目维度依赖 hook 映射，当前实测 session 零重叠（2026-11-15）。
- **Trae CN hook 弱估算**：看不到系统提示、工具定义、Skills/Memory/MCP schema，也看不到工具间 assistant 文本；并行工具会重复计输入；误差可能数倍且方向不定。
- **Cline**：VS Code 扩展旧版 `tasks/*/ui_messages.json` 形态尚无本机样本，未接入。
- **估算误差**：Qoder est ±30~40%；Trae hook est 误差不定；两者都只能看趋势。
- **计价缺失**：价格表为空，`cost_equiv_usd` 为 unknown；预算告警未实现。
- **平台限制**：仅 macOS / launchd；单机单用户；无云同步。
- **隐私**：project 当前只存 basename；哈希模式未实现；凭证只在刷新进程内使用。

### 6.3 兔子洞（明确不要做）

- 不要尝试解密 Trae CN SQLCipher 库或逆向厂商私有 API。
- 不要用非单调的 quota 快照差分推导日消耗。
- 不要把 est 与 credits / token 真值相加，也不要把 Qoder 与 Trae CN 的 credits 相加。
- 不要回填 2026-09-16 之后的 Qoder token 真值（源已不存在）。
- 不要试图把跨天 Trae 会话拆到逐日 / 逐请求。
- 不要宣称能看到流式生成中的 in-flight token（源端不落中间态）。

---

## 7. 关键决策

| 决策 | 结论 | 载体 |
|---|---|---|
| 事实源与存储 | 源是唯一事实来源；SQLite 只做归档 + 索引；`--stateless` 可完全绕过 DB | [ADR-0001](../adr/ADR-0001-source-of-truth-db-as-archive.md) |
| 采集模型 | 拉取式、无常驻进程；每小时增量 + 每日全量；`live` 直读源 | [ADR-0002](../adr/ADR-0002-pull-collection-no-daemon.md) |
| 口径隔离 | token 真值 / credits / est / activity 分轨；任何两轨不相加；跨厂商 credits 不相加 | 本文 §2.2、[QODER-CREDITS-DESIGN.md](../QODER-CREDITS-DESIGN.md)、[TRAE-CN-CREDITS-DESIGN.md](../TRAE-CN-CREDITS-DESIGN.md) |
| 联网例外 | 仅 Trae CN credits 的两条前台刷新路径联网；其余默认离线 | 本文 R11、[TRAE-CN-CREDITS-DESIGN.md](../TRAE-CN-CREDITS-DESIGN.md) |
| 技术选型 | Python ≥3.11、标准库 only、零第三方依赖、SQLite WAL、launchd | [pyproject.toml](../../pyproject.toml)、[ARCHITECTURE.md](../ARCHITECTURE.md) |

---

## 8. 变更索引

| CHG ID | 标题 | 状态 | 链接 |
|---|---|---|---|
| CHG-0001 | 需求 / 变更文档体系对齐 | 已验证 | [CHG-0001](../changes/CHG-0001-docs-alignment.md) |
| CHG-0003 | 修正 CHG-0001 / REQ-0001 的合并状态 | 已验证 | [CHG-0003](../changes/CHG-0003-docs-status.md) |
| CHG-0004 | HTML 报表空状态与筛选联动修复 | 已验证 | [CHG-0004](../changes/CHG-0004-html-report-empty-state-and-filters.md) |
| CHG-0005 | HTML 报表展示与交互优化 | 已验证 | [CHG-0005](../changes/CHG-0005-html-report-display-and-interaction.md) |
| CHG-0006 | 补齐 Qoder 桌面端 turn credits | 已验证 | [CHG-0006](../changes/CHG-0006-qoder-turn-credits.md) |
| CHG-0007 | Trae CN credits 展示结构对齐 Qoder | 已验证 | [CHG-0007](../changes/CHG-0007-trae-report-parity.md) |
| CHG-0008 | 口径说明改为问号帮助层 | 已验证 | [CHG-0008](../changes/CHG-0008-coverage-help-popover.md) |
| CHG-0009 | 明细表填满卡片宽度 | 已验证 | [CHG-0009](../changes/CHG-0009-detail-table-fill-width.md) |
| CHG-0010 | Qoder turn credits 增量去重与历史重复清理 | 已验证 | [CHG-0010](../changes/CHG-0010-qoder-incremental-turn-dedup.md) |
| CHG-0011 | HTML 布尔筛选状态恢复 | 已验证 | [CHG-0011](../changes/CHG-0011-html-boolean-state.md) |
| CHG-0012 | HTML 筛选后的页脚与 Top 8 同步 | 已验证 | [CHG-0012](../changes/CHG-0012-html-filter-sync.md) |
| CHG-0013 | 明细合计的来源专用列显示 | 已验证 | [CHG-0013](../changes/CHG-0013-html-total-source-columns.md) |
| CHG-0014 | 审计清理：重复键、死代码与过期文档引用 | 已验证 | [CHG-0014](../changes/CHG-0014-audit-cleanup.md) |
| CHG-0015 | 审计清理（二）：死代码、过期注释与测试文档校准 | 已验证 | [CHG-0015](../changes/CHG-0015-audit-cleanup-2.md) |

> REQ-0001 建立于 v0.6.0（2026-11-15）。此前变更未补 CHG，证据为 git log、设计文档与本文测试基线；后续变更必须新建 CHG 并登记到本表。CHG-0001 已通过 PR #2 合并 main（`5b5f987`）；文档变更无部署产物，状态保持“已验证”。

> 2026-11-16：CHG-0004（R19–R26、R39，commit `530d311`）与 CHG-0005（R27–R38、R40，commit `ebc48fe`）均已实现并验证；AC 同步写入 §5.6 / §5.7 与 `tests/ac_map.json`。
>
> 2026-11-16：CHG-0006（R9 / R41，commit `735d00a`）与 CHG-0007（R42 / R43，commit `735d00a`）已实现并验证：276 tests / 0 skip、覆盖率 93.3%、AC map 43 criteria / 91 identifiers；Qoder 11-14..16 credits 与 Trae 默认页结构均已实测。
>
> 2026-11-16：CHG-0008（R30 / R44，commit `7ff22fb`）把独立“口径与数据覆盖”卡片收进页首问号帮助层；277 tests / 0 skip、覆盖率 93.3%、AC map 44 criteria / 92 identifiers。
>
> 2026-11-16：CHG-0009（R45）让明细表在卡片更宽时把剩余宽度分给非冻结数据列；278 tests / 0 skip、覆盖率 93.3%、AC map 45 criteria / 93 identifiers，1440px 填充与 500px 横向滚动实测通过。
>
> 2026-11-16：CHG-0010～0013 修复 code review 发现的问题：Qoder 增量 turn credits 去重 / 历史重复清理（R41）、HTML 布尔状态恢复（R37）、筛选后页脚与 Top 8 同步（R30 / R38）、来源专用合计列显示 `—`（R42）；282 tests / 0 skip、覆盖率 93.4%、AC map 45 criteria / 98 identifiers，浏览器实测通过。
>
> 2026-11-17：CHG-0014 全项目审计清理（无 AC 变更）：删除 ALIASES 重复键并新增 AST 护栏测试、简化 HTML 死三元、修正 README / ARCHITECTURE 过期引用与行数；284 tests / 0 skip、覆盖率 93.4%、AC map 45 criteria / 98 identifiers。审计发现的其余问题登记在 ARCHITECTURE §11（新增 P2-10 ~ P2-15），另行立项。
>
> 2026-11-20：CHG-0015 审计清理（二，无 AC 变更）：删除 `scan_qoder_transcripts` 的 `max_ts`、`scan_codex` 未用的 `models` 列表与过期注释、`load_storage_credential` 未用的返回值赋值，以及 4 个未用测试导入；校准 README 状态行与 ARCHITECTURE §3 / §9 的实测行数和测试计数。284 tests / 0 skip、覆盖率 93.4%、AC map 45 criteria / 98 identifiers；ARCHITECTURE §11 P2-2 的 `max_ts` 部分随之关闭。

---

## 9. 链接

- 当前实现：[ARCHITECTURE.md](../ARCHITECTURE.md)
- 历史设计：[DESIGN.md](../DESIGN.md)、[QODER-DESIGN.md](../QODER-DESIGN.md)、[QODER-CREDITS-DESIGN.md](../QODER-CREDITS-DESIGN.md)、[TRAE-CN-DESIGN.md](../TRAE-CN-DESIGN.md)、[TRAE-CN-CREDITS-DESIGN.md](../TRAE-CN-CREDITS-DESIGN.md)、[CLINE-DESIGN.md](../CLINE-DESIGN.md)
- 调研 / 实测 / 讨论：[RESEARCH.md](../RESEARCH.md)、[PROBE.md](../PROBE.md)、[DISCUSSION.md](../DISCUSSION.md)
- 文档索引：[docs/README.md](../README.md)
- 使用说明：[README.md](../../README.md)
