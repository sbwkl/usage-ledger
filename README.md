# usage-ledger

> macOS 上的**极轻量**跨 AI 编码工具 **token / credits 用量台账**。零常驻 UI（HTML 为单文件静态报表）、零社交、零云同步、零第三方依赖。

一个默认离线、只读本地日志、只写本地 SQLite 的用量工具；仅 Trae CN credits 的两条前台刷新路径会显式联网。

**状态**：v0.10.0。在 v0.9 基础上新增腾讯 CodeBuddy CN 采集——单源 `codebuddy` 只读两处镜像扩展日志的 `Step execution metrics` 逐 step token 真值，按 `(traceId, step)` 去重；`inputTokens` 含 cache read 故取 `cachedMissTokens`，`credit` 实测恒 0 故不采集额度。在 v0.8 基础上新增 CodeArts（码道）采集——单源 `codearts` 复用共享 SQLite adapter 读 `~/.codeartsdoer/codearts-data/opencode.db`（OpenCode 旧版 schema），逐 assistant 消息 token 真值；额度本地不落盘故不采集。在 v0.7 基础上新增 MiniMax Code 采集——单源 `minimax` 读会话 `messages.jsonl` 里 assistant 的 `usage`（实测 `input` 已排除 cache read，与其它源非重叠口径一致），项目维度取运行库 `local_runtime_sessions.workspace_dir`；额度本地不落盘故不采集。在 v0.6 基础上新增 Antigravity 采集——单源 `antigravity` 合并 IDE / hub 与 `agy` CLI 两个**不共用**的 app data dir，用 `Record.agent` 区分 `ide` / `cli`；逐 turn token 来自 `transcript_full.jsonl`，额度本地不落盘故不采集。在 v0.5 基础上新增 Trae CN credits 同步与报告改造——`trae-cn` 改为 credits 主指标（服务端会话级真值），hook 字符弱估算保留为 token 影子；`usage html` 默认刷新最新 credits，`--offline` 可跳过。Qoder credits 同时读取转录逐请求 `usage.credits` 与桌面端 `turn_credits`（2026-11-13 起新客户端来源），合并去重后写入同一轨。11 个源采集（含 Qoder 四轨、Trae CN credits + 弱估算、Cline、Antigravity 双目录、CodeArts、MiniMax Code、CodeBuddy CN）、SQLite 归档、`sync/backfill/report/activity/credits/est/top/doctor/live/prune/export/html/hooks`、`--stateless` 一致性、查看命令自动增量刷新、launchd 调度管理。单测覆盖采集规则、Qoder 四轨、Trae CN credits/hooks、Cline、Antigravity 双目录、CodeArts、MiniMax Code、CodeBuddy CN、HTML 报表与刷新回退。计价与 WorkBuddy 采集按 PROBE 建议推后。

---

## 它解决什么

你同时用 opencode / qoder / chatgpt / claude code / kilo / trae CN / workbuddy / codearts（码道），桌面版和 CLI 都用。想知道**每个平台、每个模型**的 token 用量。

现有工具都不合适：ccusage 极简但只覆盖 18 个源；tokscale 覆盖 60 个但带 TUI 和排行榜；TokenTracker / Token Monitor 带桌面宠物和多设备同步。

**本项目的立场**：采集层用成熟做法，报表层自己做；不为缺失数据编造 token，不爬第三方私有 API，默认无任何网络行为。Qoder 新客户端断供 token 后，额度走服务端每请求计费真值，token 另设**显式标注的估算轨**（`est`），永不与真值相加。Trae CN 同理：credits 来自客户端同源 usage 接口（**唯一定向联网例外**，仅 `sync --remote` / `usage html` 前台刷新），token 仍只有 hook 弱估算。任何两轴都不相加。

---

## 覆盖能力（含现实边界）

| 平台 | 统计能力 | 说明 |
|---|---|---|
| Claude Code | ✅ | 含 cache read/write |
| OpenCode（CLI + 桌面） | ✅ | 兼容新版 `session_message` 表（旧 `message` 表仍回读未迁移记录），与 Kilo 一个 adapter |
| Kilo（CLI + 桌面） | ✅ | |
| Cline（CLI + Desktop） | ✅ | 读 `~/.cline/data/sessions/**/<id>.messages.json` 中 assistant 的 `metrics`（input/output/cache read/write）；`inputTokens` 已含缓存，采集时扣除 |
| Codex CLI | ✅ | 注意"增量 vs 累计"口径 |
| Qoder | ✅ 历史 token + ✅ 活动 + ✅ 额度 + ✅ 估算 | token 来自 IDE 旧库（2026-06-01 ~ 2026-09-16）；桌面端提供**活动指标**（会话/提示/工具调用/时长）、**credits 额度真值**（转录逐请求 + 新客户端桌面端 turn_credits，合并去重）与 **est 估算 token**（转录 + 上下文比例）。四轨口径不同、永不互加，见 [docs/design-docs/QODER-DESIGN.md](docs/design-docs/QODER-DESIGN.md)、[docs/design-docs/QODER-CREDITS-DESIGN.md](docs/design-docs/QODER-CREDITS-DESIGN.md) |
| Antigravity（IDE + agy CLI） | ✅ token | 单源 `antigravity` 合并 `~/.gemini/antigravity`（IDE / hub）与 `~/.gemini/antigravity-cli`（CLI）两个**不共用**的 app data dir，读 `brain/<会话>/.system_generated/logs/transcript_full.jsonl` 里 `source=MODEL` 的 `input_tokens` / `cache_read_tokens` / `output_tokens`，用 `agent` 字段区分 `ide` / `cli`。实测两者不重叠的 `input` / `cache_read` 可直接映射；**额度本地不落盘**，不采集。只有 2026-11-20 起的会话带 token，之前的用量本地不可得 |
| CodeArts（码道） | ✅ token | 复用共享 SQLite adapter 读 `~/.codeartsdoer/codearts-data/opencode.db`（OpenCode 旧版 `message` 表，`role` / `tokens` 在 `data` JSON 内）；`input` 不含 cache read，`tokens.total` 不采（口径与 opencode 一致）。**额度本地不落盘**，不采集。只有 2026-11-20 起的会话，之前的用量本地不可得 |
| MiniMax Code（`mcode`） | ✅ token | 读 `~/.minimax/v2/sessions/<YYYY>/<MM>/<DD>/<会话>/messages.jsonl` 里 assistant 的 `usage`（`input` / `output` / `cacheRead` / `cacheWrite`）；实测 `totalTokens == input + output + cacheRead`，即 **`input` 已排除 cache read**，与 Claude / Codex 的非重叠口径一致。项目维度取运行库 `local_runtime_sessions.workspace_dir` 的 basename；`session_id` 优先读 `manifest.json`，缺失回退会话目录名后缀的 base64url 解码。**额度本地不落盘**，不采集；本机接入前的用量本地不可得 |
| 腾讯 CodeBuddy CN（`codebuddy`） | ✅ token | 只读两处镜像扩展日志里 `[AgentReporter] ... Step execution metrics: ... usage={...}` 的逐 step 真值，按 `(traceId, step)` 去重；`inputTokens` / `totalTokens` 含 cache read 故不采，改采 `cachedMissTokens`（= `input − cache`）+ `cacheTokens` + `outputTokens`；模型 / 项目分别取日志 `Preparing model` 与 `genie-history` 映射的 workspace basename；`credit` 实测恒 0 故不采集额度。本机接入前日志无该字段，之前的用量本地不可得 |
| WorkBuddy | ⏸ 未接入 | P1，需先安装 WorkBuddy 并核实样本；当前 11 个采集源不包含该源，未实现前不会出现在 doctor / 报表中 |
| Trae CN | ⚠️ token 弱估算 + ✅ credits | 本机加密库不可读、额度不落盘；**credits** 通过客户端同源 usage 接口按会话拉取（服务端真值，需登录 JWT），**token** 通过官方 hooks 记录字符数重放为 **hook 弱估算**（`trae-cn.est`）。credits 为会话级、归属 `usage_time` 所在日；弱估算只覆盖安装 hook 后的请求，误差可能数倍，二者不可相加。见 [docs/design-docs/TRAE-CN-CREDITS-DESIGN.md](docs/design-docs/TRAE-CN-CREDITS-DESIGN.md) |
| ChatGPT 桌面端 | ❌ | 无本地数据，只有配额 |

> 缺口是**厂商不下发**，不是解析器写不出来。任何工具都无法凭空造出这些平台的 token 数。工具会在 `doctor` 与报告页脚显式说明，避免"看起来没花"与"没采到"混淆。Qoder 新版本客户端已不再写 token，只保留活动元数据；活动指标用于观察 agent 使用强度，不参与 token 与成本统计。

---

## 核心设计要点

- **源是唯一事实来源**。DB 是可插拔的"归档 + 索引"层，不是权威副本
  - 当前实现为 `SqliteStore`（归档 + 索引，默认）；`--stateless` 提供零 DB 路径，`NullStore` 类尚未实现
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
├── README.md          项目说明、开发约定与测试门禁
├── pyproject.toml     Python 包定义与 usage / usage-ledger 两个 CLI 入口
├── docs/
│   ├── README.md        文档索引与阅读顺序（REQ / CHG / ADR / 设计文档）
│   ├── requirements/
│   │   ├── usage-ledger.md  功能卡（产品行为）
│   │   └── ARCHITECTURE.md#9-测试体系       功能卡（测试体系）
│   ├── changes/
│   │   └── CHG-0001 ~ CHG-0018      变更记录（均已验证，状态以各 CHG 首部为准）
│   ├── adr/
│   │   ├── ADR-0001-source-of-truth-db-as-archive.md
│   │   └── ADR-0002-pull-collection-no-daemon.md
│   ├── rfcs/            跨团队 / 高不确定方案（按需）
│   ├── DESIGN.md        历史设计稿（v0.4；当前需求见 requirements/usage-ledger.md）
│   ├── QODER-DESIGN.md  Qoder 双轨设计（token + 活动指标）
│   ├── QODER-CREDITS-DESIGN.md Qoder 额度 + 估算 token 设计
│   ├── TRAE-CN-DESIGN.md Trae CN 接入与 hook 弱估算设计
│   ├── TRAE-CN-CREDITS-DESIGN.md Trae CN credits 同步与报告改造设计（已实现）
│   ├── CLINE-DESIGN.md  Cline 会话 metrics 采集设计
│   ├── RESEARCH.md      调研报告（竞品横评 + 本机数据可得性实测）
│   ├── PROBE.md         实测探针报告（真实 token 台账 + 9 处规格偏差 + Q 的答案）
│   └── DISCUSSION.md    讨论纪要（决策链 + 文档修订记录 + 待决问题）
├── scripts/
│   └── probe.py        只读探针：全量扫 4 源，产出 token 表（0.72s，标准库 only）
├── src/usage_ledger/
│   ├── collectors.py   11 源采集（Claude/Codex/OpenCode/Kilo/Cline/Qoder 双轨/Trae CN 弱估算/Antigravity/CodeArts/MiniMax Code/CodeBuddy）
│   ├── trae_hooks.py   Trae CN hook 脚本生成、安装/合并/卸载、事件日志
│   ├── trae_credits.py Trae CN 同源 usage API 客户端、JWT 读取、分块/分页与幂等同步
│   ├── store.py        SQLite 归档、去重、prune、usage_daily / usage_activity 汇总
│   ├── aggregation.py  报表聚合与过滤
│   ├── qoder_models.py Qoder 模型内部键 → 界面显示名（展示层映射，参考 perch）
│   ├── html_report.py  离线单文件交互报表（内联 CSS/JS/SVG）
│   ├── scheduler.py    launchd 任务生成/安装/查询
│   ├── cli.py          命令行入口
│   └── pricing.py      模型别名与价格表（价格表当前为空）
└── tests/              单测 + 脱敏 fixtures（Claude/Codex/OpenCode/Qoder/Trae CN/Cline）
```

## 需求、变更与决策

- 功能事实源：产品行为见 [usage-ledger.md](docs/product-specs/usage-ledger.md)，测试体系见 [ARCHITECTURE.md §9](ARCHITECTURE.md#9-测试体系)。
- 变更记录：[docs/exec-plans/completed/](docs/exec-plans/completed/)（CHG-0001 ~ CHG-0019，均已验证；完整索引见 [docs/design-docs/index.md](docs/design-docs/index.md) 与 [usage-ledger.md §8](docs/product-specs/usage-ledger.md)）。
- 架构决策：[ADR-0001](docs/design-docs/ADR-0001-source-of-truth-db-as-archive.md)、[ADR-0002](docs/design-docs/ADR-0002-pull-collection-no-daemon.md)；只有已做出、难回退的架构 / 技术选型才建 ADR；跨团队、不可逆、影响公共接口 / 数据模型 / 安全隐私的方案放 `docs/design-docs/rfcs/`。
- 文档阅读顺序与支撑文档：[docs/design-docs/index.md](docs/design-docs/index.md)。`docs/design-docs/DESIGN.md` 是历史设计稿，`ARCHITECTURE.md` 是 As-Built；不要拿 DESIGN 里的未实现项当当前 AC。
- 新变更先建 CHG，登记到对应 REQ 的变更索引，再写代码；设计文档只作支撑，不再作为需求事实源。
- ID 按类型递增、不复用。当前下一批：`REQ-0003`、`CHG-0020`、`ADR-0003`。
- 文档是事实源；issue/PR 不存在时，用 commit、测试结果、release note 作为证据。状态以 REQ / CHG 文档首部为准；代码合并不等于已发布，没有部署 / 验证证据不得标“已发布 / 已验证”。

## 开发约定

工作流：`main` 是保护分支，只接受合并；新特性从最新 `main` 切 `feat/<特性名>`，集成走 `sit`；有未提交改动时用 `git worktree` 并行开发；合并 `main` 前必须获得用户同意。工作区根 `AGENTS.md` 的通用流程（TDD、DoR/DoD、需求管理）同时适用；在本工作区内冲突时以根 `AGENTS.md` 为准。项目补充如下：

- 新特性先满足 DoR：REQ / CHG 已更新，AC delta 覆盖正常 / 异常 / 边界，依赖已链接；实现中不得扩大 CHG 范围。
- 测试命令与门禁见下文「测试与门禁」；完成后运行全量测试，更新 CHG 状态与证据，没有部署 / 监控证据不得标“已发布”。
- CHG 标“已验证”前证据必须写全：精确命令、环境（OS / Python / Node / commit）、通过 / 失败 / 跳过数、覆盖率与基线变化、日志或 artifact 链接；缺任一项保持“开发中”。
- 提交信息引用 CHG ID；PR 标题 / 描述引用 CHG 和 REQ。
- 本地重装：`uv tool install --force --no-cache .`；直接运行：`PYTHONPATH=src python3 -m usage_ledger <cmd>`。
- 边界：不要顺手修复 [ARCHITECTURE.md](ARCHITECTURE.md) §11 的 P0 / P1 / P2 问题，它们需要独立 CHG；不要逆向厂商私有 API、解密 Trae CN SQLCipher 库，或把估算值 / credits / token 真值相加；默认离线，只有 Trae CN credits 的两条显式前台刷新路径可以联网。

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
usage credits --since 7d        # Qoder / Trae CN 的 credits 消耗（按 Agent 分列，不跨厂商相加）
usage credits --source trae-cn  # 只看 Trae CN credits（会话级真值；本命令不联网）
usage est --group-by day,model  # Qoder 估算 token（est，±30~40%，不可与真值相加）
usage hooks install trae-cn --scope global  # 安装 Trae CN hooks（只记字符数与元数据）
usage hooks status trae-cn      # hook 配置、事件文件、最近事件
usage sync --source trae-cn     # 只重放 hook 事件并写入 trae-cn.est（不联网）
usage sync --source trae-cn --remote  # 显式联网刷新 Trae CN credits（默认最近 30 天）
usage est --source trae-cn      # Trae CN 弱估算 token（只覆盖安装 hook 后）
usage report --source cline     # Cline 会话 token（input/output/cache read/write）
usage top models                # 模型排行
usage html --open               # 生成 usage-report.html；含 Trae 时默认先刷新 credits
usage html --offline --open    # 不联网，只读已有 credits 缓存
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

Qoder 新版客户端不再写 token；转录 JSONL 在 2026-11-13 之前保留每请求的服务端计费字段与上下文比例，之后把每轮金额写入桌面端 `main.sqlite` 的 `chat_session_messages.turn_credits`。两条来源合并后进入同一个 `qoder.credits` 轨：

```bash
usage credits                       # 每天 billable credits / 请求数 / 免费 credits / 快照数
usage credits --since 7d --format json
usage est --group-by day,model      # 估算输入/输出 token 与覆盖请求数
usage est --stateless --group-by model   # 绕过数据库直读转录
```

- **credits 是服务端真值**：转录中 `billable=true` 的 `usage.credits` 逐请求累计；桌面端 `turn_credits` 按轮累计，`request_id = qoder-turn:<session>:<message>`，两源用 `request_set_id` / `request_id` 精确去重；增量同步会使用库中已持久化的 Qoder request ID 去重，并清理历史上已写入的重复 turn 行。免费请求单独列出，不计配额；`turn_credits` 无免费拆分，按 billable 计入。
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

## MiniMax Code（mcode）

MiniMax Code 把每次模型响应落盘在自己的会话目录里，assistant 消息自带 `usage`，可直接作为 token 真值：

```bash
usage report --source minimax
usage report --source minimax --group-by project,model
usage doctor --probe minimax
```

- **路径**：`~/.minimax/v2/sessions/<YYYY>/<MM>/<DD>/<会话>/messages.jsonl`，外层是
  `{message_id, turn_id, message}`，`message` 内含 `role` / `model` / `provider` / `usage` / `timestamp`。
- **口径**：实测 `totalTokens == input + output + cacheRead`（83/83 条成立），即 **`input` 已排除
  cache read**，与 Claude / Codex 的非重叠口径一致，可直接相加；`cacheWrite` 实测恒为 0（源未提供）。
- **去重**：`minimax:<session_id>:<message_id>`；`session_id` 优先读会话目录的 `manifest.json`，
  缺失时回退会话目录名后缀的 base64url 解码。
- **项目维度**：会话文件不含 cwd，取运行库 `~/.minimax/v2/sqlite/runtime-state.sqlite` 的
  `local_runtime_sessions.workspace_dir` basename（回退 `project_workspace_dir`）。运行库读不到时
  降级为无项目并把源状态标为 `partial`，**token 真值不受影响**。
- **边界**：`usage.cost` 恒为 0（客户端未计价），不据此算金额；额度只在服务端，本地不可得，不采集。
  无 `usage` 或零 token 的 assistant 消息跳过并计数，不伪造 0；坏行只计数不中断。
- **缺口**：本机 2026-11-20 接入前的用量本地不可得。

---

## 腾讯 CodeBuddy CN（`codebuddy`）

CodeBuddy 把每次模型调用的 token 写进扩展日志；本系统只读日志，不读 prompt 正文、不联网：

```bash
usage report --source codebuddy
usage report --source codebuddy --group-by day,project --format json
usage doctor --probe codebuddy
```

- **两处镜像目录**：`~/Library/Application Support/CodeBuddy CN/logs/**/Tencent-Cloud.coding-copilot/*.log`（ISO 时间戳）与 `~/Library/Application Support/CodeBuddyExtension/Logs/CodeBuddyIDE/**/*.log`（方括号时间戳）。两个目录写同一批事件，按 `(traceId, step)` 去重，不会翻倍。
- **识别**：`[AgentReporter] [<traceId>] Step execution metrics: step=<n>, duration=<ms>, usage=<json>`；同内容不带 `usage=` 的摘要行与终端命令回显都不算用量。
- **口径**：实测 `inputTokens == cacheTokens + cachedMissTokens`，即 `inputTokens` 已含 cache read；取 `input = cachedMissTokens`、`cache_read = cacheTokens`、`output = outputTokens`、`cache_write = cachedWriteTokens`、`reasoning = 0`（`thinkingTokens` 已含在 output 中）。不采含 cache read 的 `inputTokens` / `totalTokens` / `lastTokens`。
- **元数据**：模型取同 trace 的 `Preparing model: <显示名> (<modelId>)`，缺失记 `unknown`；会话取同 trace 的 `onAgentStart` `conversationId`，缺失回退 traceId；项目取 `genie-history/<base64url(cwd)>/current.json` 的 conversationId → workspace basename，映射不到则无项目。厂商把目录名的 base64 padding `=` 写成 `_`、部分目录还追加 `__`，解码时先剥尾部 `_` 再补 padding（本机 20/20 目录验证通过）。
- **额度**：`usage.credit` 实测恒为 0，不是服务端计费真值；订阅额度本地不可得，**不采集**。
- **边界**：本机接入前（2026-11-20 之前）的日志不带 usage 字段，之前的用量本地不可得；step 非整数 / usage 坏 JSON / 全零行只计数不中断；任一目录缺失只降级，都不存在则源不可用。

---

## Trae CN credits（真值）与 hooks 弱估算（est）

Trae CN 的本机加密库不可读、额度不落盘；本系统有两条互不相加的数据轨：

### Credits（服务端会话级真值，定向联网）

```bash
usage sync --source trae-cn --remote          # 显式联网刷新最近 30 天
usage sync --source trae-cn --remote --days 365   # 首次回填一年
usage sync --source trae-cn --remote --dry-run    # 只打印计划，不读凭证、不请求
usage credits --source trae-cn                # 查看缓存（本命令不联网）
usage html --open                             # 含 Trae 时默认先刷新再出报告
usage html --offline --open                   # 只读缓存，不联网
usage html --max-age 300 --open               # 300 秒内成功同步过则复用
usage html --strict-refresh --open            # 刷新失败时命令非 0（仍写回退报告）
```

- **入口**：只有 `usage sync --source trae-cn --remote` 与 `usage html`（Trae 在报告范围内）会联网；
  `report` / `credits` / `doctor` / `live` / 自动同步 / `html --offline` 全部离线。
- **凭证**：默认读取 Trae CN 客户端登录态 `~/Library/Application Support/Trae CN/User/globalStorage/storage.json`
  中的 `iCubeAuthInfo://icube.cloudide`（tc v5，本地解密）；优先级 `--jwt-file` > `TRAE_CN_JWT` >
  `TRAE_CN_JWT_FILE` > `storage.json`。`~/.trae-cn/trae-jwt-token` 是客户端临时 token，usage 接口会返回 401，
  不再作为默认来源。凭证只在刷新进程内使用，不落库、不写日志、不进 HTML；不读 Keychain、不读浏览器 Cookie、
  不解密 SQLCipher 库。凭证过期后需重新登录 Trae CN。
- **口径**：API 是**会话级**，credits 归属 `usage_time` 所在本地日；一个会话跨天无法拆分。
  `request_id = trae-cn:<session_id>`，重复拉取幂等覆盖；报告按 Agent 分列，不与 Qoder credits 相加。
- **项目维度**：API 无 project 字段，用 hook 事件的 `session → project` 尽力映射，未命中显示 `-`；2026-11-15 本机实测两者 session 零重叠，当前项目维度实际不可用。
- **失败**：`html` 默认软回退缓存并在页面/命令行标注刷新失败与数据时间；`--strict-refresh` 才非 0。
  HTML 是生成时快照，旧文件不会因再次打开而更新。
- **边界**：首版不做 Trae 余额/套餐配额，不落 API 的 token 字段，不做后台轮询、多账号或自动登录。
  详见 [docs/design-docs/TRAE-CN-CREDITS-DESIGN.md](docs/design-docs/TRAE-CN-CREDITS-DESIGN.md)。

### Hooks 弱估算（token 影子，离线）

官方 hooks 能看到会话、工具调用与文本**长度**。本项目安装一个只算字符数的 hook，
把事件元数据写入本地 JSONL，再重放为 `trae-cn.est`：

```bash
usage hooks install trae-cn --scope global   # 合并写入 /Users/wayne/.trae-cn/hooks.json（带备份）
usage hooks status trae-cn                   # 配置、事件文件、最近事件、覆盖会话
usage sync --source trae-cn                  # 幂等重放事件文件（不联网）
usage est --source trae-cn --group-by day,model
usage hooks uninstall trae-cn --scope global # 只删除本项目安装的 hook 组
```

- **隐私**：hook 只写 `event`、`session`、`project` basename、`tool`、`chars_in/out`、可选 `model` 与时间戳；
  不落 prompt、tool_input、tool_response、last_assistant_message 正文；hook 本身不读加密库、JWT 或私有 API。
- **口径**：每个 `PreToolUse` 与 `Stop` 各记一次模型调用边界；`est_input = min(上下文累积字符 ÷ factor, window)`，
  `est_output = 输出字符 ÷ factor`。默认 `factor=3.8`、`overhead=0`、`window=200000`，可用
  `USAGE_LEDGER_TRAE_EST_FACTOR/_OVERHEAD/_WINDOW` 校准。
- **边界**：hook 看不到系统提示、工具定义、Skills/Memory/MCP schema，也看不到工具调用之间的 assistant 文本；
  并行工具会重复计输入。该轨是**弱估算/可见内容下限 + 部分重复**，误差可能数倍且方向不定，
  只适合看趋势，**永不与 credits 真值或 token 相加**。
- **覆盖**：只从安装 hook 之后的会话开始记录，不回溯加密库历史。
- 未安装 hook 时 `usage doctor` 会显示未安装/事件目录不存在，不影响其他源。

---

## 交互式 HTML 报表

```bash
usage html                                  # 生成 ./usage-report.html；含 Trae 时默认先刷新 credits
usage html --offline                        # 强制离线，只读 credits 缓存
usage html --max-age 300                    # 成功同步未超过 300 秒且窗口覆盖时复用缓存
usage html --strict-refresh                 # 刷新失败时命令非 0（仍写回退报告）
usage html --open                           # 生成后自动在浏览器打开
usage html --range 2026-10-01..2026-10-29 --output /tmp/usage.html
usage html --source codex --live            # 只看 codex，并合并源里的最新数据
usage --stateless html --output /tmp/usage.html   # 不读库、不联网；Trae credits 显示需缓存
```

生成后的页面是**单文件、零外部请求**（CSP `default-src 'none'`，CSS/JS/SVG 全内联），
可随时发给别人或归档，不需要起服务。注意它是**生成时快照**：再次打开旧文件不会更新；
生成过程中 `usage html` 可能按上文规则刷新 Trae credits，`--offline` / `--stateless` 可完全避免联网。
所有 Agent 共用一处多选与同一页报告：

- **Agent 多选**（页面顶部唯一选择区）：claude、codex、opencode、kilo、cline、codebuddy（精确 token）、qoder、trae-cn（精确 credits），标签上带各自汇总值；可同时勾选 token 计费与 credits 计费 Agent，至少保留一个；Trae credits 未同步时 chip 显示 `—` 而不是伪造 0
- **点击语义**：单击只看该 Agent，再次单击恢复全选；⌘/Ctrl/Shift+单击增减成员；另有“全选”按钮
- **同一页、按单位分行展示**：tokens、credits、est 单位不同，各自独立汇总，**不跨单位相加**；选择多个单位时，KPI、图表、Top 8、明细都并列展示
- **KPI 按单位分组**：`精确 Token（tokens）`、`精确 Credits（credits）`（Qoder 与 Trae CN 共用四卡：区间 credits / 免费 credits / 区间日均 / 最新额度余额，Trae 不提供的免费额度与额度快照显示 `—` 并说明原因）、`估算`；每组卡片连续排列，全页只有一张主卡，空单位合并为一张“无数据”卡；Trae 无缓存时显示“未同步”或“刷新失败”卡片与刷新命令
- **每日用量**：每个单位一块图——Token 按 Agent 堆叠；credits 单选时使用同一图表结构，Qoder 为 billable / 免费双序列，Trae 为 billable 单序列（不伪造免费序列），Qoder + Trae 同时选中时改为**分组柱状图**，不堆叠成一个总数；Qoder 影子估算 / Trae 弱估算默认隐藏，打开“估算”开关后分别显示；控件位于各自面板，影子轴有标题
- **模型 Top 8 / 项目 Top 8**：按主单位（优先 tokens → credits → 估算）排序；Qoder + Trae 同时选中时按 Agent 分组排名，不做跨厂商合计；条形与百分比统一“相对第一”口径并明示，总计为 0 时显示 `—`
- **明细**：统一一张表，`Agent` 与 `单位` 列区分来源和口径，不适用该单位的列显示 `—`；默认只显示 token / credits 行，打开“估算”开关后才追加 Qoder 影子估算 / Trae 弱估算行；Token / Credits / 估算列使用分组表头，宽表冻结日期 / Agent（>640px 再冻结模型 / 项目），隐藏当前筛选下全空的列；列宽小于卡片时把剩余宽度分给非冻结数据列，冻结列宽与偏移不变，窄屏仍横向滚动；按天 × Agent × 模型 × 项目聚合，按单位和厂商分列合计（Qoder / Trae credits 不合并，来源专用列在对方合计行显示 `—`），分页支持页大小与跳转，1440px 下无表内纵向滚动
- **估算开关**：Qoder 影子估算与 Trae 弱估算共用一个“估算”开关，默认关闭；仅选中对应 Agent 且存在估算数据时显示，开关文案与 `aria-label` 随选中 Agent 生成。关闭时估算不进入 KPI、图表、Top 8、明细表和页脚计数；打开后分别显示并始终注明不可与 credits 相加
- **Trae CN 弱估算**：固定标注「弱估算（hook 可见内容，不含系统提示/工具定义）」与「不可与任何真值或额度相加」；默认隐藏，需打开“估算”开关查看
- **口径与数据覆盖**：覆盖说明、Trae credits 状态、生成时间与行数口径不再单独占卡片，统一收进页首 `?` 按钮打开的帮助层；默认关闭，点击 / Esc / 点击外部关闭并同步 `aria-expanded`；Trae 状态仅在选中 Trae 时显示，warn/error 时问号按钮带提醒点，页脚区分“库内 / 本页”并随筛选刷新
- **活动指标**（会话/提示/工具调用/时长）：仅选中 qoder 时显示，折叠在页面底部，不参与任何用量计算；展开后分页并冻结日期/项目，折叠时跳过重绘
- **日期范围**：默认取截至数据日的近 7 天；「全部」为全量，避免把单日/短周期 Agent 的图压成一条线；可选“聚焦有数据区间”，默认关闭，关闭时恢复近 7 天
- **交互**：图表 tooltip 支持鼠标、触控与键盘，点击可固定、Escape / 空白处关闭；向下滚动保留紧凑粘性筛选条与回到顶部，≤640px 折叠为“筛选”抽屉；筛选 / 排序 / 页码写入 URL hash 与 `localStorage`（URL 优先），布尔开关接受 `true` / `"1"`，无效状态丢弃或夹紧；Top 8 选择模型 / 项目与下拉筛选走同一刷新顺序；主题单独持久化
- 缺失日期以覆盖率（“数据覆盖 N/M 天”）汇总，图表按 0 显示；筛选行固定宽度，切换 Agent 不改变模型 / 项目 / 搜索控件尺寸
- 页首覆盖块说明 token 真值 / credits / 估算 / 活动的口径边界，Qoder 历史 token 真值（2026-06-01 ~ 09-16）只在说明中披露，不并入本页

数据来自与 `report` 相同的聚合链路（天 × 来源 × 模型 × 项目），所以页面数字与 CLI 报表一致。

---

## 技术选型

Python ≥3.11，**标准库 only**（`sqlite3` / `json` / `argparse` / `plistlib`），零第三方包；通过 `pyproject.toml` 安装为 `usage` CLI；SQLite（WAL）存储；launchd 调度。

---

## 测试与门禁

快速套件（离线；不读取真实源、不访问网络、不加载真实 launchd）：

```bash
python3 -m unittest discover -s tests -t .
```

前置：Python ≥3.11；Node 24（HTML/JS 行为测试需要）。Node 缺失时测试会 skip，且 `check_test_policy.py` 会把未授权 skip 判为失败，不会静默变绿。

覆盖率与测试策略门禁：

```bash
uv run --with coverage python -m coverage run --branch --source=src/usage_ledger \
  -m unittest discover -s tests -t .
uv run --with coverage python -m coverage json -o coverage.json
python3 scripts/check_coverage.py coverage.json
python3 scripts/check_test_policy.py
python3 scripts/check_ac_map.py
```

CI 配置在 `.github/workflows/test.yml`：PR、`main`、`sit` 上跑 Python 3.11–3.14 + Node 24 矩阵，并执行上述覆盖率、skip/时长和 AC 映射检查。`main` 已启用 5 个 required checks（strict + enforce_admins），失败 PR 不可合并。

---

## 下一步

1. 安装 launchd：`usage schedule install`（hourly sync / 00:15 full rescan / 00:20 prune）
2. Trae CN credits 验收：登录 Trae CN 后确认 `usage doctor --probe trae-cn` 显示
   `source=storage.json readable=True`，运行
   `usage sync --source trae-cn --remote --days 7`，再运行 `usage credits --source trae-cn` 与
   `usage html --source trae-cn --open`，核对会话数、credits 与 Trae 控制台一致
3. Trae CN H0 hook 真实捕获验收：`usage hooks install trae-cn --scope global` 后，在 Trae CN 设置 > Hooks 确认已加载，
   发一条带工具调用的 prompt，再运行 `usage hooks status trae-cn` / `usage sync --source trae-cn` /
   `usage est --source trae-cn` 核对事件字段与估算结果
4. 计价（可选）：价格表目前为空，`cost_equiv_usd` 恒为 `unknown`——PROBE 证明本机 18/21 个模型是 free/别名，成本列价值低
5. WorkBuddy collector（需先安装 WorkBuddy 采集样本）
6. v2 可选项：`NullStore`、zstd 归档、L3 FSEvents daemon；Qoder 估算系数用新样本定期校准

> 完整快照随时可复现：`python3 scripts/probe.py`
> 测试与门禁命令见上文「测试与门禁」。
