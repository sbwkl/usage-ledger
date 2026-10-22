# 调研报告：macOS 上跨 AI 编码工具的 Token 用量统计

> 调研日期：2026-10-22 ｜ 环境：macOS 27.0.1 (Apple Silicon) ｜ Python 3.12.13 / Node 24.16.0
> 关联文档：[DESIGN.md](./DESIGN.md)（实现方案）、[DISCUSSION.md](./DISCUSSION.md)（讨论纪要）

## 摘要

- **目标**：统计 7 个 AI 编码工具（opencode / qoder / chatgpt / claude code / kilo / trae CN / workbuddy），桌面版与 CLI 都算，每个平台每个模型的 token 用量。
- **结论**：**用开源的采集能力 + 自研报表层**，不自研采集层。但**没有任何现成工具同时满足"极轻量 + 全平台 + 纯统计"**，且其中 3 个平台在本地**根本不存在** per-model token 数据。
- **本机实测结论**：7 个平台中只有 4 个（Claude Code / OpenCode / Kilo / Codex）有真实 token 数据；WorkBuddy 有（本机未装）；Qoder、Trae CN、ChatGPT 桌面端**没有**。

---

## 1. 现有产品横评

| 项目 | 形态 / 语言 | ⭐ | 覆盖 | macOS 形态 | 许可 | 为什么不选 |
|---|---|---|---|---|---|---|
| **ccusage** | Rust CLI，纯统计 | 19.1k | 18 源（仅明文写 usage 的 CLI） | `npx` | MIT | **形态最贴合**（无社交/无 UI/单二进制），但缺 WorkBuddy / Qoder / Trae CN |
| **tokscale** | Rust core + TUI + Web + 社交 | 5.7k | ~60 client | `npx` TUI + 3D 前端 | MIT | 默认 TUI；社交/排行榜是独立子命令（不执行即无副作用）但仍属产品面；`tokscale-core` **未发布到 crates.io**（仅 git 依赖） |
| **codeburn** | TS + 桌面/菜单栏/VSCode 扩展 | 11.5k | 42 工具 | 全平台 app | MIT | 桌面应用形态 + 含"优化/修复"等重型功能 |
| **TokenTracker** | JS + 本地面板 + 宠物/成就/排行榜 | 2.1k | 46 工具 | brew cask 菜单栏 | MIT | **桌面宠物、排行榜、widget** —— 与诉求直接冲突 |
| **Token Monitor** | macOS widget + 多设备同步 | — | 41+ 工具 | macOS 12+ 原生 | MIT | widget 形态、跨设备同步 —— 与诉求冲突 |
| **OpenUsage** | Swift 菜单栏 | 4.4k | 偏**额度**而非 token 历史 | 原生菜单栏 | MIT | 语义不对口（只做配额/重置倒计时） |
| **TokenTelemetry** | Python | 383 | 20 工具（含 Qoder） | localhost 面板 | MIT | 覆盖面与形态尚可，但星数少、活跃度一般 |
| **Claude Tracker / ClaudeUsageBar / CodexBar / AIQuotaBar …** | 单 provider 菜单栏 | — | 单一 provider | 原生菜单栏 | MIT | 覆盖不足 |

### 1.1 为什么 ccusage 星最多、平台反而最少

调研中一个反直觉现象的解释（对选型有直接指导意义）：

1. **时间红利**：ccusage 创建于 2025-05-29（本次调研对象中最早，约 17 个月），是"Claude Code 有没有烧钱"的标准答案；2026 年才进场的项目只能靠"覆盖广度"做差异化。ccusage 目前 19.1k⭐ / 888 fork / 仅 3 个 open issue / ~83 contributors / 2800+ commits。
2. **写死的准入哲学**（`docs/guide/source-support-qa.md` 原文）：
   > ccusage only supports a coding agent when it can read local usage records with **local timestamps, session identity, model identity, and token counts**… If a tool stores only prompts, transcripts, quota percentages, or opaque cloud state, **ccusage does not estimate token usage from text length**.
   > It **does not scrape private cloud services** or depend on undocumented authenticated APIs.

   即：**不估算、不爬私有 API**。而竞品恰好做了这三件它拒绝的事：
   - TokenTracker 用 TRAE 的**共享 SQLCipher app key** 解密库
   - tokscale 解密 `iCubeAuthInfo` blob 拿 JWT，调 `POST /trae/api/v1/pay/query_user_usage_group_by_session`
   - Token Monitor 明写 Command Code "token usage is estimated from the transcript"
3. **单位工作量差一个量级**：加一个明文 JSONL 源 ≈ 半天；加一个加密/私有 API 的 IDE 源 ≈ 数周且一升级就断。ccusage 主动砍掉了后者。
4. **形态定位不同**：ccusage 是"分析工具"（核心资产是稳定 schema 与计价语义）；tokscale/TokenTracker 是"采集平台/产品"（覆盖度本身就是护城河与增长引擎）。Token Monitor 的 README 写明它与 Tokscale 共用环境变量覆盖规则 —— 这类项目**共享/移植解析代码**，tokscale 的 60 client 有相当部分借了邻近仓库的现成活。

> **对本项目的启示**：adopt ccusage 的**准入哲学**（无 token 不估算、不爬私有 API），但补上它没有的**归档层**（见 DESIGN.md §4.3、§7.3）。

---

## 2. 本机数据可得性（实测，非推测）

| 平台 | 本机路径 | 结构 | per-model token | 结论 |
|---|---|---|---|---|
| Claude Code | `~/.claude/projects/**/*.jsonl` | 每条 assistant 消息带 `message.usage` | ✅ 含 cache read/write | 采集 |
| Codex CLI | `~/.codex/sessions/**/*.jsonl` | turn 级 `token_count` 事件 | ✅ | 采集 |
| OpenCode | `~/.local/share/opencode/opencode.db` | SQLite `message` 表，`data` JSON 内含 `tokens` | ✅ | 采集 |
| Kilo | `~/.local/share/kilo/kilo.db` | **与 OpenCode 完全同构** | ✅ | 采集（复用同一 adapter） |
| WorkBuddy | `~/.workbuddy/projects/**/*.jsonl` | JSONL（待安装后核实） | ✅ | P1 |
| **Qoder** | `~/.qoder/projects/**/*.jsonl` | 有 usage 字段但**6898 条实测全为 0**；`main.sqlite` 的 `chat_sessions` 只有 `model` 无 token 列 | ❌ | **不采集** |
| **Trae CN** | `~/Library/Application Support/Trae CN/User/globalStorage/state.vscdb` | 仅 `credits.monthlyGranted` / `cn.fast_request.lock_map` 等额度键 | ❌ | **不采集 token** |
| **ChatGPT 桌面 App** | 无 `com.openai.chat` 本地目录 | — | ❌ | **不采集** |

### 2.1 关键实测细节

**Claude Code** 记录形态：
```json
{"type":"assistant","timestamp":"...","sessionId":"...","cwd":"/Users/wayne/workspace/material-hub",
 "version":"2.1.153","isSidechain":false,
 "message":{"model":"kimi-for-coding",
   "usage":{"input_tokens":10965,"output_tokens":213,
            "cache_creation_input_tokens":0,"cache_read_input_tokens":14848,
            "service_tier":"standard","cache_creation":{...},"iterations":[]}}}
```
- 6,492 行 type 分布：`assistant 2603 / user 1512 / mode 447 / last-prompt 433 / attachment 190 / file-history-snapshot 190 / system 169 / agent-name 105 / ai-title 368 / custom-title 87 / queue-operation 20`
- **无任何 intermediate 记录**（`"is_partial"|"partial"|"stream_delta"` 零命中）→ usage 在 turn 结束那一刻一次性落盘
- `subagents/agent-*.jsonl` 是子代理的独立 transcript，必须递归扫描

**OpenCode / Kilo** 记录形态（两者完全一致）：
```json
{"role":"assistant","agent":"build","variant":"high",
 "path":{"cwd":"/Users/wayne/workspace/article-backup","root":"..."},"cost":0,
 "tokens":{"total":39440,"input":1599,"output":1430,"reasoning":1979,"cache":{"write":0,"read":34432}},
 "modelID":"deepseek-v4.1-flash-free","providerID":"opencode",
 "time":{"created":1792551104490,"completed":1792551133491},"finish":"stop"}
```

**Codex**：`total_token_usage` 是**累计值**、`last_token_usage` 是**增量** —— 必须用后者，否则数量级错误。

### 2.2 日志不是"只增不减"（丢失窗口的根源）

| 现象 | 本机证据 | 后果 |
|---|---|---|
| Codex 把旧 rollout 移出 `sessions/` | `~/.codex/archived_sessions/` 实存 **18 个** | 只扫 `sessions/` 会永久漏数 |
| Codex 归档为压缩文件 | `~/.codex/sessions/**/*.jsonl.zst` | 不解压 → 漏 |
| OpenCode 新旧双存储并存 | `opencode.db` **与** `storage/` 同时存在 | 迁移期数据可能只落一处；迁移/重装会复制副本 → 重复计数 |
| 生态存在自动清理作业 | `~/.cursor/projects/.agent-data-cleanup-2026-10-2*` | 历史会被删除 |
| **mtime 不可作新鲜度判据** | 某 Claude 会话文件 mtime 比最后一条记录晚 **1,148,196s（13 天）** | 按 mtime 增量会漏 |

### 2.3 写盘延迟（决定实时性上界）

| 源 | 观测 | 延迟 |
|---|---|---|
| OpenCode / Kilo | 消息行 `created 16:46:30.685 → updated 16:46:32.975`；`mode=ro` 只读连接在 16:46:35 即读到 | **亚秒级**（WAL 直读，无需 checkpoint） |
| Claude Code | usage 随 assistant 行在 turn 结束时落盘 | turn 结束那一刻 |

> 推论：**实时性瓶颈不在采集侧，在"什么时候去读"**。且 **turn 流式生成过程中的 token 爬升在磁盘上不存在**，任何文件采集方案都做不到（只有 agent 自己的 statusline 直连 API 才有）。

### 2.4 规模与时序

| 项 | 实测 |
|---|---|
| Claude Code | 103 个 jsonl / 13,818 行；`.claude` 110MB；**最新会话 2026-07-27** |
| Codex | 50 个 jsonl / 28,231 行；`.codex` 809MB；另 18 个归档 rollout |
| OpenCode | `message` 表 8,543 行（7,870 含 token）/ 107 session；1.0GB |
| Kilo | `message` 579 行 / 8 session / `event` 10,887；93MB |
| Qoder | `.qoder` 1.1GB（token 全 0）；Trae CN / OpenCode 桌面应用支持目录均存在 |
| 全量扫描预估 | 约 5.1 万 turn → < 1.5s |

---

## 3. 覆盖矩阵

|  | ccusage | tokscale | TokenTracker | Token Monitor | **本项目** |
|---|---|---|---|---|---|
| Claude Code | ✅ | ✅ | ✅ | ✅ | ✅ |
| OpenCode | ✅ | ✅ | ✅ | ✅ | ✅ |
| Kilo | ✅ | ✅ | ✅ | ✅ | ✅ |
| Codex / ChatGPT 订阅侧 | ✅ | ✅ | ✅ | ✅ | ✅ |
| WorkBuddy | ❌ | ✅ | ✅ | ✅ | ✅ (P1) |
| Qoder | ❌ | ❌ | ✅ | ✅ | ❌（无数据，见上） |
| Trae CN | ❌ | ❌（仅国际版） | ✅ | ✅（额度） | ❌（无 token） |
| ChatGPT 桌面 | ❌ | ❌ | ❌ | ❌ | ❌（无数据） |

---

## 4. 可借鉴而不复用的两点

1. **ccusage 的准入哲学**（无 token 不估算、不爬私有 API）→ 直接采纳为本项目原则
2. **tokscale 的多端共用 DB 天然去重**观察 → 已在本机验证（桌面版与 CLI 共写同一 `kilo.db` / `opencode.db`）

**不复用其代码**：两个核心 crate（`ccusage-core`、`tokscale-core`）**均未发布到 crates.io**，仅 git 依赖；且它们的解析逻辑是各自产品的一部分，维护耦合不划算。本项目只**借用格式语义**，自写约 400 行 collector。

---

## 5. 参考链接

- ccusage：https://github.com/ccusage/ccusage ｜ 准入哲学：`docs/guide/source-support-qa.md`
- tokscale：https://github.com/junhoyeo/tokscale
- TokenTracker：https://github.com/xiufengsun/TokenTracker ｜ https://www.tokentracker.cc/
- Token Monitor：https://github.com/Javis603/token-monitor
- codeburn：https://codeburn.app/ ｜ https://github.com/getagentseal/codeburn
- OpenUsage：https://github.com/robinebers/openusage ｜ https://github.com/janekbaraniewski/openusage
- TokenTelemetry：https://github.com/VasiHemanth/tokentelemetry
