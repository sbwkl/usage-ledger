# usage-ledger 实现方案（设计评审稿）

| 项 | 内容 |
|---|---|
| 文档状态 | **待审核**（v0.4，2026-10-22） |
| v0.4 变更 | 依"既然能直读源，为什么还要数据库"提问修订：① 新增 §4.3 逐条核算 DB 的价值（抗删除 / 抗格式变更 / 聚合索引 / 状态），并明确 **DB 不该当"权威副本"**；② 确立"**源是唯一事实来源，DB 是可插拔的归档+索引层**"；③ 存储层抽象为 `NullStore`（无状态：零 DB、零定时任务）/ `SqliteStore`（归档+索引）两个实现，查询路径分三档新鲜度（§8）；④ 新增 `archived` 标记与归档判定机制（§6/§7.5）—— 每日全量重扫推导"源是否还能重建这条记录"，`archived=1` 的行永久保留，**这是 DB 唯一不可替代的部分**，也是相对 ccusage/tokscale 的核心差异点；⑤ `prune` 规则按 `archived` 分流；⑥ 新增验收项（读写一致、合并差异、归档判定、无副作用）与 Q13 |
| v0.3 变更 | 依"定时采集是否还能看实时"提问修订：① 实测写盘延迟（OpenCode/Kilo 亚秒级、Claude Code turn 结束才落盘、无中间态记录）→ 新增 §10.1.1 可见性延迟模型；② 新增 §10.1.2 实时性三档（L1 按需直读 / L2 高频轮询 / L3 daemon），**L1 让实时不需要常驻进程**；③ 新增 `usage live` 命令与输出契约（直读源、不落库）；④ 修正增量策略：mtime 只能当快速过滤，最终正确性靠行级去重键 + 内容水位（实测 mtime 可领先内容 13 天）；⑤ 新增 G12、R14、Q12；⑥ 工时 6 → 6.5 人日 |
| v0.2 变更 | 依评审提问修订：① 明确"不需要常驻进程"（拉取式 vs 推送式，§10.1）；② 实测发现日志会被归档/迁移/清理 → 采集频率由"每日一次"改为"每小时增量 + 每日全量重扫"，路径全覆盖（§10.2/§10.3）；③ 新增 `usage backfill` 历史回填（§10.5）；④ 补充 Codex `archived_sessions`/`.zst`、OpenCode 双存储、Claude `subagents/` 的坑位（§5.1–5.3）；⑤ 新增 G10/G11、R12/R13、Q9–Q11；⑥ §6 补充"为什么必须是数据库" |
| 目标平台 | macOS（Apple Silicon），单机、单用户、本地 |
| 目标 | 极轻量、零 UI、零社交、零云同步的跨平台 AI 编码工具 **token 用量台账** |
| 明确不做 | TUI / 菜单栏 / 桌面宠物 / 排行榜 / 云同步 / 遥测 / 任何网络上传 |
| 一句话定位 | "一个只读本地日志、只写本地 SQLite、能算出「我今天每个平台每个模型花了多少 token」的离线工具" |

---

## 1. 背景

现有工具的调研结论（详见附录 A）：

- `ccusage`（19.1k⭐）—— 形态最接近诉求（Rust 单二进制、纯表格/JSON、无社交），但**只覆盖 18 类明文写 usage 的 CLI**，不含 WorkBuddy / Qoder / Trae CN。
- `tokscale`（5.7k⭐）—— 覆盖 60 个 client，但**默认带 TUI**，社交/排行榜虽是独立子命令（不执行即无副作用），整体仍是"产品"而非"库"。
- `TokenTracker` / `Token Monitor` / `codeburn` —— 覆盖广但**是完整桌面应用**（宠物、成就、widget、多设备同步），与"极轻量"相悖。

结论：**采集层不值得重写（格式漂移是长期维护成本），但报表层没人做得合口味。**
本方案因此采取"薄采集 + 自定义报表"路线：采集器自己写但只写最必要的 4–5 个（每个都是简单格式），换来 100% 干净、100% 按需 schema、零外部依赖的最终产物。

**这是一个"够用就停"的工具**：目标是把 6 个平台每个模型每天的 token 数和等价成本，用一条命令算出来并存进自己的库。它不追求成为新的 ccusage。

---

## 2. 目标与非目标

### 2.1 目标（In scope）

| G# | 目标 | 验收标准 |
|---|---|---|
| G1 | 汇总 6 个平台的 token 用量 | `usage report` 一张表内含 Claude Code / OpenCode / Kilo / Codex / WorkBuddy / Cline（可选） |
| G2 | 按 **平台 × 模型 × 天** 维度出数 | 表头固定：`date, source, model, input, output, cache_read, cache_write, reasoning, cost_equiv_usd, cost_source` |
| G3 | 极轻量 | 单文件可执行，**零第三方依赖**，冷启动 < 1s，常驻内存 0，无守护进程 |
| G4 | 完全离线 | 除"可选的定价表更新"外无任何网络请求；无遥测 |
| G5 | 只读、隐私 | 对源目录只读打开；**不写入正文/提示词**；项目路径可配置为仅存 basename 或哈希 |
| G6 | 长期留存 | 逐年数据可查，DB 可控（turn 级明细 90 天 + 日聚合永久） |
| G7 | 预算告警 | 月度/日度阈值触发 macOS 通知 |
| G8 | 可诊断 | `usage doctor` 一眼看出每个源是否可用、是否有 token、是否已损坏 |
| G9 | 可交叉校验 | 与 `ccusage` / `tokscale` 同源数据误差 < 2% |
| G10 | 采集完整性 | 覆盖所有会被移动/删除/压缩的日志路径；**丢失窗口 ≤ 1 小时**（采集频率 + 路径枚举共同保证，见 §10.2） |
| G11 | 历史可回填 | 安装当天即可通过 `usage backfill` 一次性导入既有日志，之后靠定时增量积累 |
| G12 | 可看实时 | `usage live` 直读源，**延迟 < 0.3s 且无常驻进程**（L1 档）；更高实时性由 L2/L3 可选提供 |

### 2.2 非目标（Out of scope）

- ❌ 任何 GUI / TUI / 菜单栏 / 状态栏
- ❌ 社交、排行榜、成就、宠物、连续打卡
- ❌ 云同步、账号体系、遥测
- ❌ 逆向厂商私有 API、破解加密数据库（这是 ccusage 明确拒绝、也是维护成本的来源）
- ❌ 对 **无 token 数据** 的平台做估算（Qoder 订阅套餐恒为 0、ChatGPT 桌面端无本地数据 —— 见 §3.2）
- ❌ 多用户 / 团队 / 权限模型
- ❌ 实时（秒级）采集 —— 目标是**日级台账**，不是实时监控

---

## 3. 关键约束（实测事实，非推测）

### 3.1 数据可得性矩阵（本机 2026-10-22 实测）

| 平台 | 本机路径 | 结构 | per-model token | 采集难度 | 决策 |
|---|---|---|---|---|---|
| Claude Code | `~/.claude/projects/<slug>/<sid>.jsonl` | JSONL，每条 assistant 消息带 `message.usage` | ✅ 完整（含 cache read/write） | 低 | **P0** |
| Codex CLI | `~/.codex/sessions/**/*.jsonl` | JSONL，turn 级 `token_count` 事件 | ✅ | 低 | **P0** |
| OpenCode（CLI+桌面） | `~/.local/share/opencode/opencode.db` | SQLite `message` 表，`data` JSON 内含 `tokens` | ✅ | 低 | **P0** |
| Kilo（CLI+桌面） | `~/.local/share/kilo/kilo.db` | SQLite `message` 表，**与 OpenCode 同构** | ✅ | 低 | **P0**（复用同一 adapter） |
| WorkBuddy | `~/.workbuddy/projects/**/*.jsonl`（5.5+ 在 `~/.workbuddy-ai/`） | JSONL（推测同 Claude，**待安装后核实**） | ✅ | 低（推测） | **P1** |
| Cline | `~/.cline/data/sessions/**` | JSONL transcript | ✅ | 中 | P2（可选） |
| **Qoder** | IDE：`~/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db`；桌面端：`~/Library/Application Support/com.qoder.app.stable/main.sqlite` | IDE `chat_message.token_info` 有真实历史 token（19,963 行，截至 2026-09-16）；桌面端 `chat_session_messages` 提供活动元数据 | ✅ 历史 token + ✅ 活动指标（不可相加） | 低 | **P0**（见 §3.3） |
| **Trae CN** | `~/Library/Application Support/Trae CN/User/globalStorage/state.vscdb` | 仅 `credits.monthlyGranted` / `cn.fast_request.lock_map` 等额度键 | ❌ 无 token 字段 | — | **不采集 token**（额度见 §3.4） |
| **ChatGPT 桌面 App** | 无 `com.openai.chat` 本地目录；`~/Library/Application Support/OpenAI` 下仅 Codex | — | ❌ | — | **不采集** |

### 3.2 两条数据轴必须分开

用户诉求里混着两种**语义不同**的数据，强行并表是大多数"全能工具"翻车的地方：

| 数据轴 | 含义 | 来源 | 维度 | 更新频率 |
|---|---|---|---|---|
| **A. token 台账** | 实际消耗的 token 数 + 按 API 价折算的等价成本 | 本地 JSONL / SQLite | 时间 × 平台 × 模型 × 项目 × session | 每次同步（增量） |
| **B. 额度快照** | 套餐剩余百分比 / 重置时间 | 各厂商账号 API（需凭证） | 平台 × 额度类型 | 定时轮询 |

本方案 **v1 只做 A**。B 属于"另一个维度"（百分比不是 token），单独一张表、单独命令，不与 A 混排。

### 3.3 关于 Qoder：v0.4 起双轨采集（token + 活动）

早期探针只看了 `~/.qoder/projects/**/*.jsonl`（订阅套餐全 0），因此 v1 决定不采集。v0.4 复核发现真实数据在别处：

- **token 轴**：IDE 的 `local.db` → `chat_message.token_info` 有完整 `prompt_tokens/completion_tokens/cached_tokens`，共 19,963 行、2,700,982,026 tokens，覆盖 2026-06-01 ~ 2026-09-16；新版客户端已不再写入，属于**历史真值**。
- **活动轴**：桌面端 `main.sqlite` → `chat_session_messages` 持续更新，可提取会话数、提示数、assistant 调用、`turnMetrics`（turns/时长）与工具调用数；**没有 token**。

→ 决策：两条轴独立入库、独立命令展示，**不可相加、活动不参与成本**；`usage report` 在区间内无 Qoder token 但存在活动时显式提示。完整设计、DDL、增量游标与测试见 [QODER-DESIGN.md](QODER-DESIGN.md)。

### 3.4 关于 B 轴（额度）—— 作为 v2 备选，v1 不做

技术上可行但成本高、脆性大：
- Trae CN：需从本地 JWT 取 access token 调 `trae.cn` 账号接口（Token Monitor 用的就是这个思路），**内部 API 随时会变**。
- ChatGPT 配额：需 `chatgpt.com/backend-api/wham/usage`（OpenUsage 标注"cookie auth 进行中"，需补抓 HAR）。
→ 若将来要做，按"独立命令 + 独立表 + 失败不影响 A 轴"的原则增量实现。

---

## 4. 总体架构

### 4.1 组件

```
┌──────────────────────────────────────────────────────────────────────┐
│ CLI 层 (argparse)                                                      │
│   sync | report | top | budget | export | doctor | quota(v2)           │
└───────────────┬──────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────┐
│ Collector 层（只读，插件式）                                            │
│  claude_jsonl   codex_jsonl   opencode_sqlite   kilo_sqlite            │
│  workbuddy_jsonl   cline_jsonl(v2)                                     │
│  每个 collector:  discover() → parse() → yield[UsageRecord]           │
└───────────────┬──────────────────────────────────────────────────────┘
                │  UsageRecord（统一行模型）
┌───────────────▼──────────────────────────────────────────────────────┐
│ Normalize + Dedupe + Price                                            │
│  · 模型名归一（model_alias）   · 幂等去重键   · 定价表匹配              │
└───────────────┬──────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────┐
│ Store 层 (SQLite)  ~/.local/share/usage-ledger/usage.db                │
│  usage_turn(明细) · usage_daily(聚合) · source_state(游标) · meta      │
└───────────────┬──────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────┐
│ Report / Alert 层                                                     │
│  表格式 / CSV / JSON · 预算阈值判定 · macOS 通知                        │
└──────────────────────────────────────────────────────────────────────┘

        ▲ 定时触发（launchd，非常驻）           ▲ 可选：FSEvents daemon
        │  每小时增量 + 每日全量重扫              │  仅在需要"当前 session 实时"时
   ┌────┴─────┐                            ┌───┴────┐
   │ Scheduler │                            │  Daemon │ (v2, 可选)
   └──────────┘                            └────────┘
```

### 4.2 技术选型

| 维度 | 选择 | 理由 |
|---|---|---|
| 语言 | **Python ≥3.11，标准库 only** | 本机实测 Python 3.12.13 / Node 24.16 均可用。Python 有 `sqlite3`、`zoneinfo` 内置；单文件、零安装、跨 macOS 版本稳。Node 备选（若你更熟 TS） |
| 依赖 | **0 个第三方包** | 满足 G3/G4；`argparse` 足够做子命令；`urllib` 仅用于可选的定价表更新 |
| 存储 | SQLite（WAL 模式），**可插拔**（`NullStore` / `SqliteStore`） | 单文件、并发读安全、`sqlite3` 内置；DB 预估 < 30MB/年。且 DB 是**可选**的（见 §4.3） |
| 分发 | v1 直接跑源码（`python3 usage_ledger.py`）；v2 可 `uv tool install` 或 PyInstaller 打成单二进制 | v1 不做打包，避免过早优化 |
| 调度 | **launchd**（`~/Library/LaunchAgents/`），非 cron | macOS 原生、开机自启、错过可补跑（`StartCalendarInterval` + `RunAtLoad`） |
| 告警 | `osascript -e 'display notification'` | 无第三方依赖；可选 terminal-notifier |
| 定价 | 离线 JSON 快照（LiteLLM 派生，随仓库分发）+ 本地 `custom-pricing.json` 覆盖 | 离线可复现；不自动联网 |

### 4.3 存储层可插拔：DB 是"保险"，不是"镜像"

**设问**：既然能直读 agent 写盘，为什么还需要数据库？是不是没用了？

**回答**：DB 提供的价值**不在"现在有什么"**（那永远以源为准），而在**"源已经没有的东西"**。逐条算账：

| # | 价值 | 具体场景（本机实证） | 没有 DB 的后果 |
|---|---|---|---|
| V1 | **抗删除** | agent 会清理/轮转/迁移旧日志：Codex 归档 18 个 rollout、生态存在自动清理作业（`~/.cursor/projects/.agent-data-cleanup-*`） | 那段历史**永久消失**，无法回溯 |
| V2 | **抗格式变更** | 某天 Claude Code 改了 JSONL schema，新 parser 读不出旧格式 | 旧历史随之失效。**ccusage / tokscale 都不存历史，因此同样受此影响** —— 这正是它们"今天能用、半年后可能对不上账"的原因 |
| V3 | **聚合索引** | 5 源 × 多年 × (日/模型/项目/session) 多维查询 | 每次查询扫全盘。实测全量扫描 ~1.5s，**可接受但不理想**（DB 中 < 0.1s） |
| V4 | **状态** | 同步水位、告警去重、预算累计、归档标记 | 需另找地方放状态（多一个状态文件） |

**反过来说，DB 不该做的事**（这决定了架构）：

- ❌ 不该当"当前数据的权威副本" —— 那会制造 DB 与源的双写不一致
- ❌ 不该存 prompt / 正文 —— 源里有，DB 里没必要，还会放大隐私面
- ❌ 不该成为查询路径的**唯一**入口 —— 否则实时性被同步周期绑架

**结论：源是唯一事实来源（source of truth），DB 是可插拔的"归档 + 索引"层。**

因此存储层抽象为统一接口，**两个实现**：

| 实现 | 行为 | 适用 | 代价 |
|---|---|---|---|
| `NullStore`（无状态模式） | 每次查询直读源 + 内存去重，**不落盘、不需要任何定时任务** | 只关心"现在/最近"；接受查询 ~1.5s 与历史丢失 | 几乎零复杂度 |
| `SqliteStore`（归档模式，默认） | 定时把解析结果 upsert 入库；查询读库，可选合并直读源 | 要长期历史 + 秒级查询 + 抗删除 | 多一套 schema/同步状态 |

**查询路径由这两个实现组合出三档新鲜度**：

```
usage report              → 读 SqliteStore            快（<0.1s），新鲜度 = 同步周期（≤1h）
usage report --live       → 读源 ∪ 库（按 key 去重合并） 实时，~1.5s
usage live                → 只读源，不落库              实时，<0.3s
usage --stateless report  → 强制走 NullStore（临时验证用） 实时，无副作用
```

**这让"要不要数据库"变成一个可配置的选择，而不是架构前提。** 若你最终只关心"当下花了多少"，整个工具可以是纯无状态的（~200 行、无 schema、无同步任务）；若你要"一年前的用量还在"，DB 就是必需品。

### 4.4 与开源的关系（复用边界）


| 组件 | 策略 | 理由 |
|---|---|---|
| **数据解析** | 自写（4 个 collector，共约 400 行） | 格式简单（JSONL / SQLite JSON blob）；自写换来零依赖与完全可控的 schema |
| **定价表** | 复用 LiteLLM 的价格数据（离线快照，手动更新） | 不自己维护 2200 个模型价格 |
| **模型名归一** | 自写小表（`model_alias`） | 只需覆盖你实际在用的十几个模型 |
| **ccusage / tokscale** | **仅在开发期做交叉校验**，不作为运行时依赖 | 它们是验证基线，不是依赖；避免版本升级互相拖累 |
| 官方文档 | 抄各格式的字段语义，不抄代码 | 避免许可/维护耦合 |

---

## 5. 数据源契约（逐个 collector 的精确规格）

> 下列字段名均为**本机实测**结果，非文档推测。

### 5.1 claude_jsonl — Claude Code

- **路径**：`~/.claude/projects/**/*.jsonl`（会话目录名为 cwd 的 slug）
- **记录**：每行一个 JSON 对象；assistant 消息形如
  ```json
  {"type":"assistant","timestamp":"...","sessionId":"...","cwd":"/Users/.../material-hub",
   "version":"2.1.153","isSidechain":false,
   "message":{"model":"kimi-for-coding",
     "usage":{"input_tokens":10965,"output_tokens":213,
              "cache_creation_input_tokens":0,"cache_read_input_tokens":14848,
              "service_tier":"standard","cache_creation":{...},"iterations":[]}}}
  ```
- **字段映射**：`input ← usage.input_tokens`；`output ← usage.output_tokens`；`cache_read ← usage.cache_read_input_tokens`；`cache_write ← usage.cache_creation_input_tokens`（含 `cache_creation.ephemeral_1h/5m` 时记入 cache_write 并标 `cache_ttl`）
- **元数据**：`model ← message.model`；`project ← cwd`；`session ← sessionId`；`agent ← "claude-code"`；`sidechain ← isSidechain`
- **坑**：
  1. `isSidechain=true` 是 subagent 的 turn —— **默认计入**（真实消耗），但单独出列以便剔除
  2. `usage.iterations` 非空（服务端多轮推理）时可能重复计数 → 以 `usage` 顶层字段为准，`iterations` 不参与求和
  3. 同一 session 的 assistant 消息有 `message.id` 与 `requestId` → 去重键优先用 `requestId`（跨 compaction 稳定），缺失时退回 `message.id`
  4. `type != assistant` 的行（hook/mode/user）跳过
  5. 存在 `type:"last-prompt"`、`"mode"` 等控制行 —— 一律跳过
  6. **必须递归扫 `subagents/` 子目录**：`~/.claude/projects/<slug>/<sid>/subagents/*.jsonl` 是子代理的独立 transcript（非 `isSidechain` 的另一种形态），漏扫即漏计子代理消耗
  7. 同一文件在会话过程中会被**追加/重写** → 增量判定不能只看文件 mtime，必须叠加"行级去重键"（见 §7.1），否则重写会漏掉新增行
  8. 目录结构按 cwd  slug 划分，**同一项目的历史可能散在多个 slug 目录** → 项目归一按 `cwd` 字段而非路径前缀
- **实测规模**：103 个 jsonl / 13,818 行

### 5.2 codex_jsonl — OpenAI Codex CLI

- **路径**：`~/.codex/sessions/**/*.jsonl`（`${CODEX_HOME:-~/.codex}`）
- **记录**：turn 级事件；token 计数在 `token_count` 事件中，形如
  `{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{...},"last_token_usage":{"input_tokens":N,"cached_input_tokens":N,"output_tokens":N,"reasoning_output_tokens":N,"total_tokens":N},"model_context_window":N}}}`
- **字段映射**：`input ← input_tokens - cached_input_tokens`（缓存部分单列）；`cache_read ← cached_input_tokens`；`output ← output_tokens`；`reasoning ← reasoning_output_tokens`
- **去重键**：rollout 文件名 + `turn` 序号 / `info.last_token_usage` 时间戳
- **坑**：
  1. **`total_token_usage` 是累计值，`last_token_usage` 是增量** —— 必须用增量，累加会二次计数（这是 Codex 统计最常见的错法）
  2. **必须同时扫 `archived_sessions/`** —— 本机实测 `~/.codex/archived_sessions/` 有 **18 个**被移出的 rollout；只扫 `sessions/` 会永久漏掉这批数据
  3. 归档 rollout 为 `.jsonl.zst` 压缩 → v1 跳过压缩文件并在 `doctor` 标注"存在 N 个未解析的压缩归档"，v2 接入 zstd 解压（Python 3.14 自带 `compression.zstd`，或用 `zstd` CLI）
  4. 模型名在同文件内可能变化 → 以事件内的 model 字段为准
  5. `archived_sessions` 中的文件是 `sessions/` 里同一次会话的**副本**（ccusage/tokscale 都有"副本只算一次"的处理）→ 必须用 rollout 内嵌 ID 而非文件路径做去重键
- **实测规模**：50 个 jsonl / 28,231 行

### 5.3 opencode_sqlite / kilo_sqlite — OpenCode & Kilo（同一 adapter）

- **路径**：
  - OpenCode：`${OPENCODE_DATA_DIR:-~/.local/share/opencode}/opencode.db`（旧版 `opencode-stable.db` 或 `storage/message/`）
  - Kilo：`${KILO_DATA_DIR:-~/.local/share/kilo}/kilo.db`
- **表**：`message(id, session_id, time_created, time_updated, data)`，`data` 为 JSON：
  ```json
  {"role":"assistant","agent":"build","variant":"high",
   "path":{"cwd":"/Users/wayne/workspace/article-backup","root":"..."},
   "cost":0,
   "tokens":{"total":39440,"input":1599,"output":1430,"reasoning":1979,
             "cache":{"write":0,"read":34432}},
   "modelID":"deepseek-v4.1-flash-free","providerID":"opencode",
   "time":{"created":1792551104490,"completed":1792551133491},"finish":"stop"}
  ```
- **字段映射**：`input ← tokens.input`；`output ← tokens.output`；`reasoning ← tokens.reasoning`；`cache_read ← tokens.cache.read`；`cache_write ← tokens.cache.write`；`model ← modelID`；`provider ← providerID`；`project ← path.cwd`
- **坑**：
  1. **桌面版与 CLI 共用同一个 DB**（OpenCode.app / opencode CLI 都写 `opencode.db`）→ **天然去重，无需额外处理**（需在验收时验证）
  2. `cost` 字段常为 0（免费模型）→ 不能当成本源，仍用定价表
  3. `tokens.total` = input+output+reasoning+cache.read+cache.write 的某种组合 → **不直接使用 total，自己加总**，避免口径不明
  4. 读 SQLite 时必须**只读打开**：`file:...?mode=ro&immutable=0`（`immutable=1` 会漏掉 WAL 中的新数据）
  5. 同一 message id 可能被多次更新（流式续写）→ 以 `time_updated` 最大者为最新，取增量语义（若 tokens 字段是累计值则取差值）
  6. **双存储并存**：本机 `~/.local/share/opencode/` 下同时存在 `opencode.db` 与 `storage/`（旧版 `storage/message/`）→ 必须两个源都读，并用 message id 去重（schema 迁移期同一会话可能两边都有）
  7. **迁移/重装会产生副本**（tokscale/TokenTracker 均为此专门做了 reinstall-copy dedup）→ 去重键必须跨库稳定，不能包含库名
  8. 桌面版（OpenCode.app / Kilo.app）与 CLI 共写同一个 DB（本机已确认：仅 `kilo.db` + `kilo.db-wal`，无独立 desktop 库）→ 天然去重，但需在验收中专项验证
- **实测规模**：OpenCode 8,543 message（7,870 条含 token）/ 107 session；Kilo 579 message / 8 session / 10,887 event

### 5.4 workbuddy_jsonl — WorkBuddy（腾讯）

- **路径**：`~/.workbuddy/projects/**/*.jsonl`（5.5+ 在 `~/.workbuddy-ai/`）
- **状态**：**本机未安装，字段形状待安装后核实**（TokenTracker/tokscale 均标注为 JSONL，推测与 Claude 同形）
- **计划**：安装后先做一次 `doctor --probe workbuddy` 探测，输出样本键名，再据此实现 parser；**不照抄推测**

### 5.5 cline_jsonl — Cline（可选，P2）

- **路径**：`~/.cline/data/sessions/**`（本机 345MB）
- **状态**：可选，不进 v1 验收标准

---

## 6. 数据模型（SQLite DDL）

**为什么必须是数据库而不是 JSON/CSV 文件**：① 4 个源 × 多维度（天/源/模型/项目/session）的聚合查询；② 增量游标与断点续传；③ 行级去重（幂等 upsert）；④ 长期留存 + 明细压缩后的历史查询。这些用文件做会迅速失控。
**为什么是 SQLite 而不是 Postgres/MySQL**：单机单用户、零服务、零依赖、单文件备份，`sqlite3` 在 Python 标准库里，WAL 模式下读写并发足够。

**位置**：`~/.local/share/usage-ledger/usage.db`（可用 `USAGE_LEDGER_HOME` 覆盖；同目录放 `usage.db-wal`/`-shm`）

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- 源游标：增量同步 + 断点续传
CREATE TABLE source_state (
  source        TEXT PRIMARY KEY,      -- claude|codex|opencode|kilo|workbuddy|cline
  parser_version INTEGER NOT NULL,    -- parser 语义版本，升级时触发全量重扫
  last_sync_at  TEXT,                 -- ISO8601
  last_event_ts INTEGER,              -- 增量水位（epoch ms）
  last_file_mtime INTEGER,
  files_seen    INTEGER DEFAULT 0,
  records_total INTEGER DEFAULT 0,
  status        TEXT,                 -- ok|empty|unsupported|error
  last_error    TEXT
);

-- turn 级明细（只存 token 数与元数据，绝不存正文）
CREATE TABLE usage_turn (
  id            TEXT PRIMARY KEY,      -- dedupe key（见 §7.1）
  source        TEXT NOT NULL,
  event_ts      INTEGER NOT NULL,      -- epoch ms, UTC
  day           TEXT NOT NULL,         -- YYYY-MM-DD (本地时区)
  project       TEXT,                  -- cwd，可配置为 basename/hash
  session_id    TEXT,
  agent         TEXT,                  -- build|code|subagent...；Claude 用 sidechain 标记
  provider      TEXT,                  -- anthropic|openai|opencode|...
  model         TEXT,                  -- 归一后的模型名
  model_raw     TEXT,                  -- 原始模型 ID
  input_tokens  INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read    INTEGER NOT NULL DEFAULT 0,
  cache_write   INTEGER NOT NULL DEFAULT 0,
  reasoning     INTEGER NOT NULL DEFAULT 0,
  cost_equiv_usd REAL,                 -- 等价 API 价；无法计价时 NULL
  cost_source   TEXT,                  -- recorded|pricing-table|manual|unknown
  archived      INTEGER NOT NULL DEFAULT 0,  -- 1 = 源里已不存在（不可重建，必须保留）
  first_seen    TEXT NOT NULL
);
CREATE INDEX idx_turn_day_source ON usage_turn(day, source);
CREATE INDEX idx_turn_model ON usage_turn(model);
CREATE INDEX idx_turn_project ON usage_turn(project);
CREATE INDEX idx_turn_seen ON usage_turn(first_seen);
CREATE INDEX idx_turn_archived ON usage_turn(archived);
```

**`archived` 标记是"源是否还能重建这条记录"的唯一判据**（详见 §7.5）：
- `archived = 0` → 源里还在（或昨天还在）→ 明细可在 90 天后压缩/删除，**因为随时能从源重建**
- `archived = 1` → 源里已经没有了 → **必须永久保留**（哪怕压成日聚合），否则这段历史永久丢失

-- 日聚合（永久保留，明细压缩后以此为准）
CREATE TABLE usage_daily (
  day TEXT NOT NULL, source TEXT NOT NULL, model TEXT NOT NULL,
  project TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL DEFAULT '',
  input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read INTEGER NOT NULL DEFAULT 0, cache_write INTEGER NOT NULL DEFAULT 0,
  reasoning INTEGER NOT NULL DEFAULT 0, cost_equiv_usd REAL,
  cost_source TEXT, turn_count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, source, model, project, session_id)
);

-- 定价表（本地覆盖，优先级最高）
CREATE TABLE price_override (
  model_pattern TEXT PRIMARY KEY, input REAL, output REAL,
  cache_read REAL, cache_write REAL, reasoning REAL, currency TEXT DEFAULT 'USD',
  note TEXT, updated_at TEXT
);

-- v2：额度快照（与 token 台账分离）
CREATE TABLE quota_snapshot (
  source TEXT NOT NULL, captured_at TEXT NOT NULL, metric TEXT NOT NULL,
  used REAL, limit_value REAL, unit TEXT, reset_at TEXT, raw_json TEXT,
  PRIMARY KEY (source, captured_at, metric)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
```

**为什么同时有 turn 表和 daily 表**：turn 表保证可追溯与重算（定价表更新后可重算成本），daily 表保证长期体量可控。保留策略：turn 明细保留 **90 天**，之后压成 daily 并删除明细（可配置）。

**体积估算**：本机半年实测约 Claude 13.8k + Codex 28.2k + OpenCode 8.5k + Kilo 0.6k ≈ **5.1 万 turn**，每行约 300B → 明细约 15MB/年，日聚合表 < 2MB/年。

---

## 7. 可靠性、去重与增量

### 7.1 去重键（每源唯一）

| 源 | dedupe key |
|---|---|
| Claude Code | `claude:{sessionId}:{requestId 或 message.id}` |
| Codex | `codex:{rollout文件ID}:{turn_seq}` |
| OpenCode | `opencode:{message.id}` |
| Kilo | `kilo:{message.id}` |
| WorkBuddy | `workbuddy:{sessionId}:{messageId}` |

`INSERT ... ON CONFLICT DO UPDATE`（upsert）保证重跑幂等。

### 7.2 增量策略

1. 维护 `source_state.last_event_ts` 与 `last_file_mtime`（**每个源路径组一套水位**，如 Codex 的 `sessions/` 与 `archived_sessions/` 各自独立）
2. 每次 sync：枚举源目录 → 跳过 `mtime < last_file_mtime` 的文件 → 解析新文件 → 写库（行级去重键兜底，文件被重写也不漏）
3. **每个源的路径清单是显式配置**，不是"扫全盘"：
   - Codex：`sessions/**/*.jsonl` + `archived_sessions/**/*.jsonl`（+ `*.zst` 待 v2）
   - OpenCode：`opencode.db` + `opencode-stable.db` + `storage/message/`
   - Kilo：`kilo.db`
   - Claude Code：`projects/**/*.jsonl`（含 `subagents/`）
4. **安全阀**：每日 00:15 做一次全量重扫（忽略游标），用于修复漏记；全量重扫后 upsert 保证不重复
5. 源文件被删除/轮转不删历史数据，只是不再更新 —— 但**被删除前的数据若没被抓到就永久丢失**（见 §10.2）
6. **mtime 只能当"快速过滤"用，不能当"新鲜度"判据**（实测：某 Claude 会话文件 mtime 比其最后一条记录晚 **13 天**，因压缩/同目录其他写入会刷新 mtime）→ 最终正确性由**行级去重键 + 内容水位**保证，mtime 命中即重扫该文件、mtime 未命中但水位未推进的文件在每日全量重扫时兜底

### 7.3 归档判定与保留策略（DB 作为"保险"的核心机制）

`archived` 标记由**每日全量重扫**推导，逻辑如下：

```
每日 00:15 全量重扫：
  1. 解析全部源，得到本轮的 key 集合 S
  2. 对 DB 中该源的行：
       key ∈ S        → archived = 0   （源里还在，可重建）
       key ∉ S        → archived = 1   （源里没了，不可重建 → 永久保留）
  3. upsert 本轮新行（archived = 0）
```

由此得到两条不同的保留规则：

| 行类型 | 90 天后 | 理由 |
|---|---|---|
| `archived = 0`（源还在） | 明细可压成日聚合并删除 | 随时能从源重建，DB 里留副本没有价值 |
| `archived = 1`（源已删） | **压成日聚合后永久保留** | 这是 DB 唯一不可替代的部分 —— 唯一的"保险" |

**边界情况**：
- 某源当天**解析失败**（格式漂移、库锁）→ **不得**把该源的所有行标记为 archived（否则一次故障就会误判"源没了"，进而永久锁定大量行）→ 规则：**仅当该源本轮解析成功（exit code 0）时，才做 archived 标记**
- 源目录被临时移走/挂载未就绪 → 同上，视为"解析失败"，跳过标记
- 建议保留"最近一次成功全量重扫"的 key 快照（临时表），以便增量判断

**这条机制让 DB 的存在有了精确的、可验证的理由**：库里每一条 `archived = 1` 的记录，都对应一段"源已经删了、只有我们还留着"的数据 —— `usage doctor` 应单独报告这个数字（"已保全 N 条源已删除的历史记录"），它是本工具相对 ccusage/tokscale 的**核心差异点**。

### 7.4 失败隔离

- 单个 collector 失败**不影响**其他 collector；错误写入 `source_state.last_error`，`doctor` 显示
- SQLite 读失败（库被锁）→ 退避重试 3 次（0.5s/1s/2s）→ 记录错误，本轮跳过
- 源文件行解析失败 → 计数跳过并记入 `source_state`，不中断整轮

### 7.5 数据完整性自检（`doctor`）

- 每个源报告：文件数、记录数、**最近 7 天是否有新记录**、token 是否恒为 0、模型分布
- 与上次的记录数做差，异常下跌（>50%）提示可能漂移
- 检查 DB 是否有 WAL 未 checkpoint
- **报告"已保全的归档记录数"**（`archived = 1` 的行数）—— 这是 DB 不可替代价值的量化体现
- 报告"上次成功全量重扫时间"（超过 26h 未成功 → 告警，说明归档判定已停摆）

---

## 8. CLI 规格

```
usage sync [--source <name>]... [--since <date>] [--full] [--dry-run]
usage backfill [--since <date>] [--source <name>]...          # 一次性导入历史（幂等，可重复跑）
usage live [--source <name>] [--session <id>] [--watch [secs]] # 直读源的实时视图（不落库）
usage report [--daily|--weekly|--monthly|--range <a>..<b>] [--group-by source,model,project]
              [--filter source=X,model=Y] [--format table|json|csv] [--project <p>] [--live]
usage top <models|sources|projects|sessions> [--since 30d] [--limit 20] [--format table|json]
usage budget --monthly 200 [--warn 0.8] [--daily 50]      # 阈值告警判定
usage export --format csv --since 2026-01-01 > out.csv
usage doctor [--probe <source>]                            # 源健康检查 / 样本探测
usage pricing <model>                                      # 查价格来源与匹配规则
usage prune --keep-days 90 --dry-run                       # 明细压缩（仅 archived=0 可清）
usage schedule install|uninstall|status                    # launchd 任务管理
usage quota                                                 # v2

# 全局开关
usage [--stateless] <subcommand>     # 强制 NullStore（不读库、不落库），用于验证与临时使用
```

**存储层选择**（默认 `SqliteStore`；`--stateless` 或未安装归档任务时自动降级为 `NullStore`）：

| 命令 | 读取路径 | 新鲜度 | 典型耗时 |
|---|---|---|---|
| `usage live` | 源 | 实时 | < 0.3s |
| `usage report --live` | 源 ∪ 库（按 key 去重合并） | 实时 | ~1.5s |
| `usage report` | 库 | ≤ 同步周期（默认 1h） | < 0.1s |
| `usage --stateless report` | 仅源 | 实时 | ~1.5s |

**输出契约**：
- `table`：纯文本对齐表，无 ANSI 颜色（除非 `NO_COLOR` 未设置且是 TTY）
- `json`：`--format json` 输出稳定 schema（键名固定），供下游脚本消费
- `csv`：RFC4180，UTF-8 BOM 可选（Excel 兼容开关）
- 退出码：0 正常；1 数据错误；2 参数错误；3 源不可用（不影响其余源时仍为 0 并在 stderr 提示）

**`report` 默认表头**（G2 的固定契约）：
```
date  source  model  input  output  cache_read  cache_write  reasoning  cost_equiv_usd  cost_source
```

**`live` 输出契约**（L1 档，实时视图）：

```
$ usage live
source     session                 model              tokens    cost_equiv  updated
kilo       1a2b3c…                minimax/m3.1-flash   18,402   $0.0312     2s ago
opencode   4d5e6f…                deepseek-v4.1-flash  9,331    $0.0000     1m ago

today: 41,204 tokens  (kilo 18,402 · opencode 22,802)  ≈ $0.061
```

- **直读源、不落库**（不写 `usage_turn`），所以可以随时执行、零副作用
- `--watch [secs]`：前台循环刷新（默认 2s，Ctrl-C 退出），仍不落库
- 活跃判定：各源"最近一条记录的时间"在 N 分钟内（N 默认 10）→ 视为活跃 session
- 只显示有 token 的源；Qoder 仅在 token 覆盖区间内出现，Trae CN/ChatGPT 不会出现在这里（无数据），页脚注明原因与 Qoder 活动入口

---

## 9. 计价模型

### 9.1 价格来源优先级

1. **`recorded`**：日志里厂商直接记录的成本（目前本机各源基本没有 → 极少命中）
2. **`manual`**：本地 `price_override` 表 / `custom-pricing.json` 显式配置（优先级最高的用户覆盖）
3. **`pricing-table`**：随包分发的离线价格表（LiteLLM 派生，2026-10 快照）
4. **`unknown`**：无匹配 → `cost_equiv_usd = NULL`，**不猜、不填 0**

### 9.2 关键规则

- **缓存 token 独立计价**：cache_read 通常 0.1×、cache_write 通常 1.25×，必须分开匹配，不能按 input 价
- **归一化后再计价**：`model_raw`（如 `kimi-for-coding`、`deepseek-v4.1-flash-free`）先经 `model_alias` 映射到计价 ID；映射表可本地增补
- **订阅制下成本是"等价成本"**：`cost_equiv_usd` 命名明确表示"按 API 价折算的等价值"，**不等于实付**；订阅额度型平台（Claude Code 订阅、Kilo 免费模型）的等价成本不代表你的账单。报告中固定加脚注
- **免费模型**：`deepseek-v4.1-flash-free` 等明确标注 free → 成本 0 且 `cost_source='pricing-table'`（不参与预算告警）

### 9.3 重算

定价表更新后，`usage pricing-recalc --since <date>` 重算区间内 `cost_equiv_usd`（明细表存在则重算并回写 daily；已压缩的历史段重算失败 → 记 warning）

---

## 10. 采集模型、调度与告警

### 10.1 为什么不需要"常驻进程"才能采集

**核心事实：数据是各 agent 自己落盘的，我们的模型是 pull（读文件/读库），不是 push（订阅事件流）。**

| | 推送式（需要常驻） | 拉取式（本设计） |
|---|---|---|
| 数据产生方 | 需要暴露事件流 / 回调 / socket | agent 自己写 JSONL / SQLite |
| 采集方不在线时 | **丢事件** | 任意时刻读盘都能拿到**至今为止已落盘的全部数据** |
| 常驻的独有价值 | 实时性 | **无** |

结论：常驻进程**不会多拿到任何数据**，只会更早拿到同一份数据。
真正决定"能不能收全"的不是"是否常驻"，而是 **① 采集频率 ② 采集路径是否覆盖了会被移动/删除的位置**。

### 10.1.1 可见性延迟 = 写盘延迟 + 读取时机（实测）

"能不能看到实时数据"这个问题要先拆成两段：

```
agent 产生 token ──► agent 写盘（写盘延迟）──► 我们读取（读取时机）──► 你看到
                      ↑ 厂商决定，我们改不了            ↑ 我们决定
```

**本机实测的写盘延迟**：

| 源 | 观测 | 写盘延迟 |
|---|---|---|
| OpenCode / Kilo（SQLite WAL） | 消息行 `created 16:46:30.685 → updated 16:46:32.975`，只读连接在 16:46:35 已读到 | **亚秒级**（turn 结束即提交，WAL 直读，无需 checkpoint） |
| Claude Code（JSONL） | 6,492 行中 type 仅 `assistant/user/system/...`，**无任何 partial/stream/delta 中间态记录**；`assistant` 行携带完整 usage | **turn 结束那一刻**写入（与前一条 `user` 行同批追加） |

结论：**我们的轮询间隔只是加在厂商写盘延迟之上的一个可选项**。源数据本身一直是"活的"。

**一个必须说清的硬边界**：在一个 turn 正在流式生成时，**磁盘上任何地方都不存在这个 turn 的 token 数**（实测无中间态记录）。所以"实时看到 token 正在爬升"在文件采集模型下**不可能**——只有 agent 自己的 statusline（它直连 API 才有实时数）或流量代理（需改路由，对订阅账号不适用）才能做到。这不是本工具的实现取舍，是数据源头就没有。

### 10.1.2 由此得到实时性的三档实现

| 档 | 需求 | 实现 | 延迟 | 常驻进程 | 复杂度 |
|---|---|---|---|---|---|
| **L1 按需直读** | "我现在这个 session 花了多少" | `usage live` 命令**直接读源**（不经过 DB、不写库） | **< 0.3s**（读盘耗时本身） | ❌ 无 | 低（复用现有 collector，多一个"不落库"输出模式） |
| **L2 高频轮询** | "每分钟自动更新的数字/日志" | launchd `StartInterval=60`（秒级间隔） | ≤ 60s | ❌ 无 | 极低（改 plist 一个字段） |
| **L3 事件驱动** | "< 5s 实时"、持续刷新 | 常驻 daemon：FSEvents 监听源目录 + 轮询兜底 | < 5s | ✅ 有 | 中（FSEvents 需处理 SQLite WAL、JSONL 追加、编辑器的原子 rename 替换） |

**推荐**：把 L1 放进 v1（成本极低、直接解决"看不到实时"），L2 作为可配置项（默认 hourly，需要时改 60s），L3 留作 v2 选项。
**关键点**：L1 让"实时"这件事**根本不需要常驻进程** —— 因为源数据本来就是实时落盘的，你想看的时候去看一眼即可。定时采集只负责**历史台账**（为了不被清理、为了长期统计），与实时性无关。

### 10.2 真正的风险是"丢失窗口"（本机实测）

各 agent 的日志**不是只增不减**的：

| 现象 | 本机证据 | 后果 |
|---|---|---|
| Codex 把旧 rollout 移出 `sessions/` | `~/.codex/archived_sessions/` 实存 **18 个** | 只扫 `sessions/` → **永久漏掉**这批数据 |
| Codex 归档为压缩文件 | `~/.codex/sessions/**/*.jsonl.zst` | 不解压 → 漏 |
| OpenCode 新旧双存储并存 | `opencode.db` **与** `storage/` 同时存在 | 迁移期数据可能只落一处；迁移/重装会**复制**一份 → 重复计数 |
| Claude Code 的 subagent 独立子目录 | `~/.claude/projects/<slug>/<sid>/subagents/*.jsonl`（最早已到 2026-06-11） | 漏扫 `subagents/` → 漏计子代理消耗 |
| 生态内存在自动清理作业 | `~/.cursor/projects/.agent-data-cleanup-2026-10-2*` | 历史会被删除 |

→ **丢失窗口 = 采集间隔 + 日志保留期**。由此得两条硬性设计约束：

1. **采集路径必须显式枚举**，含 `sessions/` + `archived_sessions/`、`.jsonl` + `.jsonl.zst`、`opencode.db` + `storage/message/`、`projects/**` + `projects/**/subagents/`
2. **采集频率越高，删除前被抓到的概率越高** → 从"每日一次"改为"每小时增量"

### 10.3 推荐方案：每小时增量 + 每日全量重扫（无常驻进程）

| 任务 | 频率 | 动作 | 预计耗时 |
|---|---|---|---|
| 增量同步 | **每小时**（整点后错开 7 分钟） | 只处理 mtime/水位有变化的源 → upsert 写库 | < 0.3s |
| 全量重扫 | **每日 00:15** | 忽略游标重扫全部源（幂等 upsert） | < 1.5s |
| prune | 每日 00:20 | 明细压缩 + 容量报告 | < 1s |

```xml
<!-- ~/Library/LaunchAgents/local.usage-ledger.sync.plist -->
<key>StartCalendarInterval</key>
<dict><key>Hour</key><integer>*</integer><key>Minute</key><integer>7</integer></dict>
<key>RunAtLoad</key><false/>
<key>StandardOutPath</key><string>~/.local/state/usage-ledger/sync.log</string>
<key>StandardErrorPath</key><string>~/.local/state/usage-ledger/sync.err</string>
```

- **无常驻进程、无网络、无内存驻留**；错过的时间点在下次运行补上（launchd 的 `StartCalendarInterval` 会补跑）
- 手动触发：`launchctl kickstart -k gui/$UID/local.usage-ledger.sync`
- 安装/卸载：`usage schedule install|uninstall|status`（只生成/删除自己的 plist，不动系统其它状态）
- 相比"每日一次"多花约 1s/天，**把丢失窗口从 24h 压到 1h**

### 10.4 可选：常驻 daemon 模式（v2，L3 档，仅当你要 < 5s 实时）

只有一种需求需要常驻：**不主动问、但希望数字持续自动刷新**（如挂一个终端窗口看它跳）。
因为那需要"事件到达即读取"，而不是"到点去读一次"。

| 项 | 说明 |
|---|---|
| 触发 | FSEvents 监听源目录（`~/.claude/projects/**`、`~/.codex/sessions/**`、`~/.local/share/opencode/`、`~/.local/share/kilo/`） |
| 必须处理的细节 | ① SQLite WAL：新数据在 `-wal` 里，要监听 `-wal` 而非只监听主库；② JSONL 追加：读到**最后一行不完整**时要容忍（半行 JSON 跳过，等下次）；③ 编辑器式原子替换：文件被 rename 替换，事件指向旧 inode → 以路径而非 inode 为准 |
| 兜底 | 每小时强制全量重扫一次（应对丢失的 FSEvents 事件） |
| 落库 | 写同一张 `usage_turn` 表（幂等 upsert），额外维护 `usage_live`（仅当前活跃 session，进程退出即清理） |
| 约束 | 仍不碰网络、不做 UI；RSS 约 30–40MB，空闲 CPU < 0.1% |

L1/L2 已能满足绝大多数场景，**L3 是可选增强，不是 v1 必需**。

### 10.5 backfill：历史只能回填一次，之后靠积累

**重要事实**：台账只能从你开始装它的那天起自动积累；**被删除的历史无法回溯**。
但现有日志里有可回填的历史（本机 Claude Code 最早到 **2026-06-11**，约 4 个月；Codex 另有 18 个归档 rollout）→ 提供一次性命令：

```bash
usage backfill --since 2026-06-01     # 全量导入历史，只跑一次
```

backfill 与常规 sync **共用同一套 collector 与去重键**，跑多少次结果都一样（幂等）。
建议：**尽早安装 + 立刻 backfill 一次** —— 这是把"过去 4 个月"和"未来无限"同时拿到的唯一办法；晚一天装，就少一天回溯。

### 10.6 告警规则

| 规则 | 触发 | 动作 |
|---|---|---|
| 月度预算 | 当月等价成本 > 阈值×月预算 | macOS 通知（每日最多 1 次，去重） |
| 日预算 | 单日 > 日阈值 | 通知 |
| 异常尖峰 | 单日 > 近 30 日均值 + 3σ | 通知（提示可能有一次失控的长上下文） |
| 源异常 | 连续 3 天某源 0 新记录（而该源近 30 天有记录） | 通知（提示格式漂移或目录变更） |
| Top 模型变更 | 当月 Top3 模型与上月不同 | 不通知，仅报告 |

通知用 `osascript -e 'display notification "..." with title "usage-ledger"'`；通知去重状态存 `meta` 表。

---

## 11. 隐私与安全

| 原则 | 实现 |
|---|---|
| 只读 | 所有源目录以只读模式打开；SQLite 用 `mode=ro` URI；**代码层不写任何源目录** |
| 不存正文 | 只落 token 数 / 模型 / 时间 / session id / 项目路径；**不落 prompt、completion、diff、工具入参** |
| 项目路径可脱敏 | 配置 `paths.mode = full | basename | hash`（默认 `basename`）；`hash` 用 salted SHA-256 |
| 无网络 | 默认零网络；仅 `usage pricing update` 显式联网，且可指向本地文件 |
| 无遥测 | 无崩溃上报、无匿名统计；`doctor` 输出仅本地 |
| 凭证 | v1 不采集任何厂商账号凭证（故 B 轴额度采集 v2 需单独评审凭证处理） |
| 最小权限 | 建议对源目录授予只读即可；launchd 以用户身份运行 |

---

## 12. 验证计划

### 12.1 单元测试

- 每个 collector 一组**脱敏 fixture**（`tests/fixtures/<source>/*.jsonl` 与最小 sqlite 库），覆盖：正常记录、空文件、字段缺失、缓存 token 非零、模型名变体、重复行
- 断言：字段映射正确、去重幂等（同文件跑两次结果不变）、增量不漏不重

### 12.2 交叉校验（开发期 + 可选 cron）

同一时间窗内与开源工具对账：

```bash
ccusage daily --json > /tmp/cc.json
tokscale models --json > /tmp/ts.json
usage report --daily --format json > /tmp/mine.json
```

- 校验维度：按 source × day 的 token 总量、最大相对偏差
- **通过标准**：≤ 2%（差异主要来自缓存 token 口径与 CLI/桌面共用源的归属）
- 差异定位流程：先比 source 覆盖 → 再比 cache_read/cache_write → 再比 Codex 增量 vs 累计口径

### 12.3 端到端验收

- 首次 `sync` 在本机跑通，DB 中 5 个源（Claude/Codex/OpenCode/Kilo/Qoder）均有非零 token；Qoder 为 IDE 历史库（截至 2026-09-16）
- `report` 输出的总量与 `ccusage` 同日数值一致（±2%）
- `doctor` 正确标出 Trae CN/ChatGPT 为"无 token 数据"，并同时输出 Qoder token 截止日与活动覆盖范围
- `usage activity` 输出 Qoder 活动指标，与 token 报表分开展示且注明不可相加
- launchd 任务触发后 1 分钟内 DB 更新
- 重跑 `sync` 两次，DB 行数与总量不变（幂等）
- **`backfill --since 2026-06-01` 能导入 Claude Code 的历史记录**（本机最早 2026-06-11），且连续跑两次结果不变
- **丢失窗口验证**：人为把一个源的水位回退 3 天，`sync` 能补回该区间的数据（证明路径枚举 + 幂等 upsert 无遗漏）
- **归档覆盖验证**：`doctor` 能报告 `archived_sessions/` 中已解析的记录数（对照本机 18 个归档 rollout）
- **副本去重验证**：Codex 的 `sessions/` 与 `archived_sessions/` 同时存在同一 rollout 时，只计一次
- **存储层一致性验证**：`usage report`（读库）与 `usage --stateless report`（读源）输出**完全一致**（同一时间窗，同一 schema）
- **`--live` 合并验证**：`report --live` 与 `report` 的差异仅等于"上次同步后新增的记录"
- **归档判定验证**：人为删除某个源的一个历史文件 → 下一次全量重扫后该文件的行 `archived=1`；若该源解析失败则**不得**标记（构造一次解析失败验证）
- **无状态模式验证**：`--stateless` 下不产生任何 DB 写入（对比 DB mtime 不变）

---

## 13. 里程碑与工时

| 里程碑 | 内容 | 产出 | 工时 |
|---|---|---|---|
| **M0** | 项目骨架、CLI 框架、DB schema、`doctor` 骨架、配置加载 | 可运行的空壳 | 0.5d |
| **M1** | Claude Code + Codex collector + 单测 | 2 源可用 | 1d |
| **M2** | OpenCode + Kilo（同构 adapter）+ 单测 | 4 源可用 | 0.5d |
| **M3** | 定价表、`model_alias`、`report`/`top`/`export` | 出表可用 | 1d |
| **M3b** | 存储层可插拔（`NullStore` / `SqliteStore` 同一接口）+ `usage live`（直读源、不落库）+ `report --live` 合并去重 | 实时可用、可无状态运行 | 0.5d |
| **M4** | 增量游标、去重、`prune`、launchd（hourly）、告警 | 可长期无人值守 | 1d |
| **M4b** | 丢失窗口加固：路径全覆盖（`archived_sessions`/`zst`/`storage`/`subagents`）+ `backfill` 命令 + 幂等验证 + **归档判定（`archived` 标记）** | 数据完整性达标、DB 的"保险"职责可验证 | 0.5d |
| **M5** | 交叉校验、与 ccusage/tokscale 对账、修正 | 验收通过 | 0.5d |
| **M6** | WorkBuddy collector（需先安装 WorkBuddy 采集样本） | 5 源可用 | 0.5d |
| **M7**(可选) | Cline collector / v2 额度轴 / v2 daemon 实时模式（L3） | — | 各 0.5d+ |
| **合计** | | | **≈ 6.5 人日** |

**风险缓冲**：+1 人日（源格式与预期不符时的返工）。若 M6 因 WorkBuddy 未安装而阻塞，则 v1 以 4 源交付，M6 顺延。

---

## 14. 风险登记册

| ID | 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|---|
| R1 | 上游日志格式漂移（Claude/Codex 升级） | 高 | 中 | `parser_version` + 每次升级跑 `doctor` 探针；7 天一次全量重扫兜底；解析失败的行**跳过不中断**并计数 |
| R2 | Codex 增量/累计口径用错导致数量级错误 | 中 | 高 | 专门单测 + 与 ccusage 交叉校验；`usage doctor` 校验日环比 |
| R3 | OpenCode/Kilo 的 `tokens.total` 口径不明 | 中 | 中 | 不用 total，自行加总；在脚注注明口径定义 |
| R4 | 桌面版与 CLI 双写导致重复计数 | 低 | 高 | 实测二者共用同一 DB（天然去重），验收时专项验证；若将来分库则加 `instance` 维度 |
| R5 | 缓存 token 未单独计价导致成本高估 3–10 倍 | 中 | 高 | 计价器强制 cache_read/cache_write 独立价格；`pricing explain` 可解释 |
| R6 | 订阅制下"等价成本"被误读为账单 | 高 | 中 | 字段命名为 `cost_equiv_usd`；报告页脚固定免责声明；预算告警文案措辞审慎 |
| R7 | 用户期待"全平台"但 Trae CN/ChatGPT 无数据、Qoder 新版无 token | **确定发生** | 中 | 需求阶段即已明示（§3.3）；Qoder 提供历史 token + 活动双轨；`doctor` 与报告页脚持续提示，不产生"数据缺失"的误解 |
| R8 | 定价表过期导致成本偏差 | 中 | 低 | 快照带版本日期；`usage pricing <model>` 显示匹配来源与价格生效时间；支持手动覆盖 |
| R9 | 隐私顾虑（项目路径、session id） | 中 | 中 | `paths.mode` 可配置为 hash；不存正文；文档明示字段清单 |
| R10 | DB 膨胀 | 低 | 低 | 90 天明细压缩；预计 < 30MB/年；提供 `prune` 与容量报告 |
| R11 | 上游 schema 迁移（SQLite 重建）丢数据 | 低 | 高 | 全量重扫机制可从源重建；`source_state` 记录 parser 版本，schema 变化触发重扫 |
| R12 | **日志被上游轮转/清理/归档，未被抓到即永久丢失** | **高** | 中 | 路径全覆盖（§10.2）+ 每小时采集把窗口压到 1h + 每日全量重扫兜底 + `backfill` 补历史 + `doctor` 报告"上次成功同步时间"与"未解析的压缩归档数" |
| R13 | 多机/多库副本导致重复计数（Codex 归档副本、OpenCode 迁移副本） | 中 | 高 | 去重键不含库名/路径；`sessions/` 与 `archived_sessions/` 用同一 rollout 内嵌 ID；验收专项覆盖 |
| R14 | 误以为"实时"= 能看到 turn 流式生成过程中的 token | 高 | 低 | §10.1.1 已写明硬边界（源端不落中间态）；`usage live` 明确标注"上一个已完成 turn 的累计值"；如需 in-flight 数值只能靠 agent 自己的 statusline |

---

## 15. 待你拍板的开放问题

| # | 问题 | 我的建议 |
|---|---|---|
| **Q1** | 项目路径存储粒度？ | 默认 `basename`（如 `material-hub`），可切 `full` / `hash` |
| **Q2** | 是否把"等价成本"作为主指标？ | 是，但字段名固定为 `cost_equiv_usd`，报告页脚标注"非实付" |
| **Q3** | v1 是否要碰 ChatGPT 桌面端 / Trae CN 的**额度**（B 轴）？ | **不碰**。需要凭证 + 非公开 API，维护成本与脆性高，且语义与 token 不同轴 |
| **Q4** | 明细保留 90 天够吗？ | 够。90 天后只保留日聚合；若要追某次会话，可回源日志重放（工具提供 `--replay <session_id>` 从源重算） |
| **Q5** | 运行时是否依赖 ccusage / tokscale？ | **不依赖**，仅开发期人工对账。可另开一个可选 `verify` 子命令，检测到这两个工具时自动对账（默认关闭） |
| **Q6** | 语言：Python 还是 TypeScript？ | Python（标准库 sqlite3 免依赖、单文件）。若你更看重 TS 生态可换 Node ≥20，架构不变 |
| **Q7** | 是否需要"多设备"（如未来 MacBook + Mac Studio 汇总）？ | v1 不做。本地单库；如需，多机各跑一份再合并 `usage export/import` 即可，设计上不冲突 |
| **Q8** | 预算告警的阈值与金额基数？ | 等你给具体数值；先用等价成本，阈值可随时改配置 |
| **Q9** | **采集频率选哪档？** | 建议 **A：每小时增量 + 每日全量重扫**（无常驻进程，丢失窗口 1h）。若你要"当前 session 实时"则选 B（常驻 daemon + FSEvents，v2） |
| **Q10** | **要不要 backfill 历史？** | **要**，且建议安装当天就跑一次 `usage backfill --since 2026-06-01`（本机 Claude Code 最早 2026-06-11，约 4 个月可捞）。晚装一天就少一天回溯 |
| **Q11** | 日志被清理导致的历史空洞要不要标注？ | 要：缺失日期在 `report` 中显式标 `—(no data)` 而不是当作 0，避免"看起来没花"与"没采到"混淆 |
| **Q12** | **实时性要做到哪一档？** | 建议 **L1（`usage live` 直读源，<0.3s，无常驻）**进 v1；轮询频率默认 hourly，若你要"自动更新的数字"就配 L2（`StartInterval=60`）；只有需要 <5s 才考虑 L3 daemon。**注意：turn 流式生成过程中的 token 爬升在任何文件采集方案下都看不到**（源端不落中间态） |
| **Q13** | **要不要数据库？（决定要不要装定时任务）** | 决定性问题是：**你要不要"源删掉之后还能查到"**。<br>· **要** → 用 `SqliteStore` + 每小时归档（默认方案，DB 是保险）<br>· **不要**（只关心当下/最近）→ 用 `NullStore`，**零 DB、零定时任务、零状态**，`report` 每次扫源约 1.5s<br>实现上两者同一接口、可随时切换，**建议先按默认装上，之后想简化随时 `--stateless`** |

---

## 附录 A：调研结论摘要（决策依据）

| 项目 | ⭐ | 形态 | 覆盖 | 为什么不选 |
|---|---|---|---|---|
| ccusage | 19.1k | Rust CLI，纯统计 | 18 源（明文 usage 的 CLI） | **形态最优但缺 WorkBuddy/Qoder/Trae CN**；不满足"全平台" |
| tokscale | 5.7k | Rust core + TUI + Web + 社交 | 60 client | 默认 TUI；社交/排行榜虽是独立子命令但属产品面；core 未发布 crates.io（仅 git 依赖） |
| TokenTracker | 2.1k | JS + 本地面板 + 宠物/成就/排行榜 | 46 工具 | 桌面宠物、排行榜、widget —— 与诉求冲突 |
| Token Monitor | — | macOS widget + 多设备同步 | 41+ 工具 | widget 形态、跨设备同步 —— 与诉求冲突 |
| codeburn | 11.5k | TS + 桌面/菜单栏/VSCode 扩展 | 42 工具 | 同上，且含"优化/修复"等重型功能 |
| OpenUsage | 4.4k | Swift 菜单栏 | 偏**额度**而非 token 历史 | 语义不对口 |
| Claude Tracker / CodexBar / ClaudeUsageBar 等 | — | 单 provider 菜单栏 | 单一 provider | 覆盖不足 |

**借鉴而不复用的两点**：
1. ccusage 的**准入哲学**（无 token 不估算、不爬私有 API）→ 直接采纳为本项目的原则（R7 的处置）
2. tokscale 的**多端共用 DB 天然去重**观察 → 已验证并写入 §5.3 坑位 1

---

## 附录 B：本机环境实测证据（2026-10-22）

| 事实 | 取证方式 |
|---|---|
| Claude Code JSONL 含完整 usage 字段 | 读取最新 jsonl 的 assistant 记录，打印 `message.usage` 全字段 |
| Codex 28,231 行 / 50 文件 | `find ~/.codex/sessions -name '*.jsonl'` + 行数统计 |
| OpenCode `message` 表 8,543 行，7,870 条含 token | `sqlite3 ~/.local/share/opencode/opencode.db` 查询 |
| OpenCode/Kilo `message.data` 结构完全同构 | 分别 dump 最新一条 `data` JSON 对比 |
| Kilo 桌面与 CLI 同写 `~/.local/share/kilo/kilo.db` | 目录内存在 `kilo.db` + `kilo.db-wal`，无独立 desktop 库 |
| **Codex 存在 `archived_sessions/`，实存 18 个归档 rollout** | `ls ~/.codex/archived_sessions` → 18 个；说明旧会话被移出 `sessions/` → 只扫 `sessions/` 会永久漏数据 |
| **OpenCode 新旧双存储并存** | `~/.local/share/opencode/` 下同时有 `opencode.db` 与 `storage/`（含 `storage/session_diff`）→ 迁移期数据可能只落一处，且迁移/重装会复制副本 |
| **Claude Code 的 subagent 独立子目录** | `~/.claude/projects/<slug>/<sid>/subagents/agent-*.jsonl`，最早 2026-06-11 → 递归扫描必须覆盖 |
| **生态内存在自动清理作业** | `~/.cursor/projects/.agent-data-cleanup-2026-10-20`、`-2026-10-21` → 历史会被删除，采集频率直接决定丢失量 |
| 桌面版 agent 正在运行并与 CLI 共写同一库 | `ps aux` 见 `OpenCode.app`、`Kilo.app`、`ChatGPT.app/.../Codex` 进程 → 验证共享 DB 去重假设 |
| **写盘延迟：OpenCode/Kilo 亚秒级** | 消息行 `time_created 16:46:30.685 → time_updated 16:46:32.975`；`mode=ro` 只读连接在 16:46:35 即读到该行（说明 WAL 直读有效，无需 checkpoint） |
| **Claude Code 无中间态记录** | 6,492 行 type 分布：`assistant 2603 / user 1512 / mode 447 / last-prompt 433 / attachment 190 / file-history-snapshot 190 / system 169 / agent-name 105 / ai-title 368 / custom-title 87 / queue-operation 20`；`grep -E '"is_partial"|"partial"|"stream_delta"'` **零命中** → usage 在 turn 结束时一次性落盘 |
| **mtime 不可作新鲜度判据** | 某 Claude 会话文件 mtime 比其最后一条记录晚 **1,148,196s（13 天）**（压缩 / 同目录其他写入刷新 mtime） |
| 本机 Claude Code 最近一次会话 | 最新 `~/.claude/projects/*/*.jsonl` 的 mtime 为 **2026-07-27** → 近期主力已是 Kilo / OpenCode / Codex（实现优先级建议相应调整） |
| Qoder token 字段恒为 0 | `grep -ohE '"(input\|output\|cache_read_input\|cache_creation_input\|reasoning)_tokens":[0-9]+' ~/.qoder/projects/*/*.jsonl` → 全部命中 `:0`，非零计数 **0** |
| Qoder SQLite 无 token 列 | `PRAGMA table_info(chat_sessions)` → 仅 `model` 等，无 token |
| Trae CN 无 token 字段 | `strings state.vscdb` → 仅 `credits.monthlyGranted` / `cn.fast_request.lock_map` |
| ChatGPT 桌面端无本地数据 | `ls ~/Library/Application Support/` 无 `com.openai.chat`；`OpenAI/` 下仅 `Codex` |
| 本机 Python / Node | `python3 -V` → 3.12.13；`node -v` → v24.16.0；macOS 27.0.1 |
| 各源数据体积 | `.claude` 110M / `.codex` 809M / opencode 1.0G / `.qoder` 1.1G / `.hermes` 1.8G（后两者不在范围内） |

---

**评审要点**：请重点看 §3（数据可得性的现实边界）、**§4.3（要不要 DB —— 本次的核心争议）**、§10.1–10.2（采集模型：为什么无常驻、可见性延迟、丢失窗口）、§7.5（归档判定）、§13（工时）、§15（13 个待拍板问题）。确认后我再进入 M0。
