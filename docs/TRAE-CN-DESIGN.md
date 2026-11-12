# TRAE-CN-DESIGN.md —— Trae CN 用量统计接入设计（已实现 Plan H）

> 日期：2026-10-30（初测）/ 2026-10-31（竞品复测）/ 2026-11-01（额度、hooks 与估算方案）/ 2026-11-02（Plan H 实现） ｜ 状态：**Phase 0 不通过 → 加密库路径维持 §4.3 方案 D；Plan H（Hooks 弱估算）H1–H3 已实现并通过 86 个单测，H0 真实捕获待用户验收** ｜ 基线：usage-ledger v0.4.0（2ec136e）
> Phase 0 实测：加密库无法在本地只读解密（密钥由运行时 `db_persistence` 配置下发，本地无明文落盘；详见 [PROBE.md](PROBE.md) §6）。§5–§10 保留作记录，不实施。
> 竞品复测（2026-10-31）：竞品的内存扫描取密钥方案已在 macOS 端口端到端自测通过（HMAC + sqlcipher 打开），但对 Trae CN 被 hardened runtime 阻断——全进程 `flags=0x10000` 且无 `com.apple.security.get-task-allow`，`task_for_pid`/lldb/Apple debugserver 均被拒（受控实验证实签名是唯一变量）；备份旁路也关闭且即使开启仍为加密导出。详见 [PROBE.md](PROBE.md) §6.6。
> 额度复测（2026-11-01）：本地没有额度真值可读——用量接口响应不落盘，日志只有 URL + HTTP 200，`storage.json` / localStorage 仅套餐权益与活动配置，无 used/remaining；维持不做额度轴。详见 [PROBE.md](PROBE.md) §6.7。
> Hooks 复测（2026-11-01）：Trae CN 提供项目级 `.trae/hooks.json` 与全局 `~/.trae-cn/hooks.json`（六个官方事件），但 hook stdin 只有会话/工具/文本元数据，没有 token、credits、quota 或 transcript 路径；不能用于真值统计（只能做弱估算，见 §12）。详见 [PROBE.md](PROBE.md) §6.8。
> Plan H（2026-11-01 设计 / 2026-11-02 实现）：按用户决定改用 Hooks 做 **token 估算**，复用 Qoder `est` 轨的呈现方式；只记录字符数与事件元数据，不落正文。因 hook 不可见系统提示/工具定义/上下文比例，该轨是**弱估算/下限**，误差可能数倍（未校准），仅看趋势，永不与真值或额度相加。详见 §12。
> 一句话结论：加密库路径仍不可行；Trae CN 的 token 只能走 Hooks 可见内容的**弱估算**（Plan H），额度仍不可得。

---

## 1. 背景与目标

### 1.1 现状

- README / DESIGN 当前把 Trae CN 标为「不采集」，依据是 `~/Library/Application Support/Trae CN/User/globalStorage/state.vscdb` 里只有额度键，没有 token 字段。
- 本次重新探针发现：Trae CN 3.4.11 的 AI agent（Rust `libai_agent.dylib`）把会话、消息、usage 写入
  `/Users/wayne/Library/Application Support/Trae CN/ModularData/ai-agent/database.db`，该库是 **SQLCipher 加密库**。
- 二进制内嵌的 SQL 与结构体明确包含 `token_usage`、`item_token_usage`、`prompt_tokens`、`completion_tokens`、
  `cache_creation_input_tokens`、`cache_read_input_tokens`、`reasoning_tokens` 等字段。
- 明文侧（state.vscdb、logs、Cache、Local Storage、`~/.trae-cn`）只包含额度、AB 配置和稀疏的 memory 摘要，不含 token。
- 本机未安装 `sqlcipher` CLI；Python 标准库没有 AES，无法直接解密该库。

### 1.2 目标

1. 若 Phase 0 解密成功：把 Trae CN 的历史与增量 token 明细纳入现有 token 台账，
   复用 `usage_turn`，`source='trae-cn'`，与其他源同表、同字段、同口径。
2. 采集严格只读、离线：不写源库、不落正文、不调用 Trae 云 API、不读取登录凭证。
3. 在 `report` / `html` / `doctor` 中显式标注 Trae CN 的数据来源、覆盖范围，以及「需要本机密钥 / `sqlcipher`」的边界。
4. 密钥管理必须显式、可撤销、不影响其他源；自动刷新不得偷偷弹出 macOS 授权框。

### 1.3 非目标

- 不估算 token（加密库路径不做文本反推）。**例外**：Plan H 的 hooks 估算轨（§12），只按 hook 可见内容的字符数估算，显式标注为 `est`，永不与真值/额度相加。
- Plan H 的 hook 进程只在内存中计算 `prompt` / `tool_input` / `tool_response` / `last_assistant_message` 的长度，**不落正文、不落命令参数、不落文件内容**；事件文件只保存长度和事件元数据。
- 不调用 `api.trae.cn` 的 `ide_user_ent_usage` / `web_user_ent_usage` / `query_user_usage_group_by_session` 等私有接口。
- 不读取 `/Users/wayne/.trae-cn/trae-jwt-token`，不接触登录态。
- 不做 Trae CN 的额度 / credits 轴：本地无真值，且与 token 不同轴。
- 不读 `content` / `messages` / `full_prompt` / `code_before` / `code_after` 等正文列；不导出明文数据库副本。
- 不把 Trae CN 的 token 写入 `usage_activity`；活动轴仍只属于 Qoder。
- 不做 UI 自动化、内存扫描、进程注入、网络抓包。

---

## 2. 实测事实（2026-10-30，只读探针）

### 2.1 应用与数据位置

| 项 | 实测值 |
|---|---|
| 应用 | `/Applications/Trae CN.app`，版本 3.4.11（build 3.4.11，安装时间 2026-10-28） |
| AI agent | `/Applications/Trae CN.app/Contents/Resources/app/modules/ai-agent/libai_agent.dylib`（201,393,408 B） |
| 数据库 | `/Users/wayne/Library/Application Support/Trae CN/ModularData/ai-agent/database.db` |
| 主库 | 11,153,408 B（2723 × 4096 页），mtime 2026-10-30 15:47 |
| WAL | `/Users/wayne/Library/Application Support/Trae CN/ModularData/ai-agent/database.db-wal`，4,120,032 B，mtime 2026-10-30 17:27（持续写入） |
| SHM | `/Users/wayne/Library/Application Support/Trae CN/ModularData/ai-agent/database.db-shm`，32,768 B |
| 主库头部 | 前 64 B 为随机字节，不是 `SQLite format 3\0` |
| WAL 头部 | 标准 SQLite WAL magic `0x377f0682`，页大小 4096；帧内容不可读 |
| 明文候选 | `User/globalStorage/state.vscdb`（970,752 B，122 个 key）、`User/workspaceStorage/*/state.vscdb`、`Local Storage/leveldb`、`Cache/Cache_Data`、`logs/`、`~/.trae-cn/memory/` |

> `database.db` 和 `-wal` 在 Trae CN 运行期间持续变化。任何采集都必须假设「库随时在被写」。

### 2.2 加密证据

`libai_agent.dylib` 内含 SQLCipher 字符串：

- `PRAGMA key = `
- `PRAGMA cipher_compatibility = %d`
- `PRAGMA cipher_default_kdf_iter = %d`
- `PRAGMA cipher_default_hmac_algorithm = %s`
- `PRAGMA cipher_default_kdf_algorithm = %s`
- `PRAGMA cipher_default_page_size = %d`
- `PRAGMA cipher_default_plaintext_header_size = %d`
- `PRAGMA cipher_page_size = %d`
- `PRAGMA cipher_hmac_algorithm = %s`
- `PRAGMA cipher_plaintext_header_size = %d`
- `sqlcipher_export(...)`
- SQLx 连接选项 `sqlcipher_key`

结论：ai-agent 使用 SQLCipher，不是普通 SQLite；KDF / 兼容性参数由程序设置，**不能假设默认值**。

本机环境：

- `which sqlcipher` → 未安装。
- Python `sqlcipher3` → 不可用。
- `@vscode/sqlite3` 是普通 SQLite，不能打开该库。
- Trae CN 没有随包提供可用的 `sqlite3` / `sqlcipher` 独立可执行文件。

### 2.3 token 字段证据与不确定性

从二进制内嵌 SQL、SeaORM 迁移文件路径和结构体字符串可以确认以下表和列存在（列名按字符串顺序还原，实际 schema 以 Phase 0 解密结果为准）：

| 表 | 已见列 | 用途判断 |
|---|---|---|
| `chat_session` | `session_id`、`project_id`、`session_type`、`hidden_status`、`is_pinned` 等 | 会话元数据 |
| `project` | `id`、`absolute_path`、`workspace_type`、`domain_version` 等 | 项目路径 |
| `chat_message` | `message_id`、`session_id`、`message_type`、`message_role`、`message_index`、`is_archived`、`reply_to_message_id`、`user_message_context`、`revertible`、`created_at` / `updated_at`（待确认） | 消息索引 / 角色 / 时间 |
| `chat_message_general` | `message_id`、`summary` | 消息摘要 |
| `chat_message_task` | `message_id`、`server_task_id` | 任务关联 |
| `chat_turn` | `turn_id`、`session_id`、`reply_to_message_id`、`response_message_id`、`status`、`requirement_id` 等 | 轮次 |
| `history_v2` | `history_v2_id`、`session_id`、`message_id`、`messages`、`token_usage`、`item_token_usage`、`accumulated_summary`、`compress_token_usage`、`micro_compacted`、`truncated_above` 等 | 历史 / 恢复快照；**token 字段主要在这里** |
| `chat_session_goal` | `goal_id`、`objective`、`tokens_used`、`time_used_seconds`、`rounds_used` | 目标级累计 |
| `migration_sql_store` | 迁移记录 | SeaORM 迁移 |

上游 usage JSON 形状（来自 LLM client 结构体）：

- OpenAI 风格：`prompt_tokens`、`completion_tokens`、`total_tokens`；可选 `reasoning_tokens`
- Anthropic 风格：`input_tokens`、`output_tokens`、`cache_creation_input_tokens`、`cache_read_input_tokens`

**必须由 Phase 0 回答的不确定点**：

1. 逐次调用的真值在 `history_v2.token_usage`、`chat_turn` 还是 `chat_message`？
2. `history_v2.token_usage` 是「本次调用」还是「会话累计 / 压缩后累计」？`accumulated_summary`、`compress_token_usage` 的存在说明不能直接求和。
3. `item_token_usage` 与 `token_usage` 是否重复记录同一次调用？
4. `history_v2` 是否每条消息一行，还是每次保存整段历史（需要按 `message_id` / `history_v2_id` 去重）？
5. `chat_message` 是否有 `created_at` / `updated_at`；时间单位是秒还是毫秒？
6. 每条 assistant 消息是否一定带 usage；工具调用 / 纯文本回复是否分开计。
7. 模型名存放在哪里：`chat_session`、`chat_turn`、`model_config_cache`，还是 `history_v2.messages` 内部（后者不可读）？
8. 同一 `message_id` 是否可能因编辑 / 重试出现多行，应该取哪一行。

> 在这些问题回答之前，不能写「按行求和」的采集器；否则很容易把累计值当单次值，或把 `item_token_usage` 与 `token_usage` 重复计入。

### 2.4 明文侧复核（全部为负）

| 来源 | 结论 |
|---|---|
| `/Users/wayne/Library/Application Support/Trae CN/User/globalStorage/state.vscdb` | 122 个 key，只有额度 / 横幅 / AB 配置（如 `1888287190424090:cn.fast_request.lock_map`、`commercial-banner-popup:...credits.monthlyGranted`），无 token |
| `User/workspaceStorage/{61021ad90ff7b42f92a620e01944f467,bda8950952c93a549a3a0402edc83a28}/state.vscdb` | 工作区状态；`workspace.json` 指向 `tongxing-air` 与 solo-lite 工作区；无 token |
| `/Users/wayne/.trae-cn/memory/projects/-Users-wayne-workspace-tongxing-air--p2-f88d2c6ed27e56f04fec/` | 仅 3 个会话 × 3 行（2026-10-03 / 10-08），字段为 `intent/actions/outcome/learned/message_summary_time/message_id/compact_summary_meta.created_at_ms`，无 token |
| `/Users/wayne/Library/Application Support/Trae CN/logs/` | 主日志、renderer、cue-server stdout 只有 API URL / 会话活动；`ai_agent-*.alaudalog` 是 `AalG` 压缩/二进制格式，无可读 token |
| `Cache/Cache_Data`、`Local Storage/leveldb` | 只有 JS bundle、AB 配置、`credits-billing-status:v1` 等，无 usage 响应 |
| `/Users/wayne/.trae-cn/trae-jwt-token` | 存在，但属于登录凭证；本设计不读取 |

### 2.5 私有 API（明确排除）

日志 / 前端 JS 中出现：

- `https://api.trae.cn/trae/api/v2/pay/ide_user_ent_usage`
- `https://api.trae.cn/trae/api/v1/pay/web_user_ent_usage`
- `https://api.trae.cn/trae/api/v1/pay/query_user_usage_group_by_session`
- `https://api.trae.cn/trae/api/ug/checkin_credits/status`

这些接口需要登录态、响应体不落盘、随时变更，与项目「无网络、无私有 API」的立场冲突，不采用。

### 2.6 密钥线索与负结果

Keychain（只读取了元数据，未读取 secret）：

- service `Trae CN Safe Storage`，account `Trae CN`（创建 2026-09-28）
- service `Trae CN Safe Storage`，account `Trae CN Key`（创建 2026-10-21）——最可疑的 DB 密钥

候选密钥推导（临时脚本，2026-10-30）：

- 候选：硬件 UUID、machine ID、user id、固定字符串、常见拼接组合。
- KDF：PBKDF2-SHA512 256k、PBKDF2-SHA1 64k、raw SHA-256、raw hex。
- SQLCipher 参数：page 4096 / reserve 80、reserve 48；page 1024 / reserve 48、reserve 36；多个 IV 位置。
- 结果：**全部不匹配**（首块解密后不等于 `SQLite format 3\0`）。
- 结论：密钥不能从常见本机标识直接推导；更可能来自 Keychain、IDE→agent 的运行时传递，或程序内常量。Phase 0 必须先验证 Keychain 项。

### 2.7 结论表

| 需求 | 数据源 | 覆盖 | 可信度 |
|---|---|---|---|
| 逐次 token 明细 | `database.db` → `history_v2` / `chat_turn` 的 usage 字段（SQLCipher） | 待 Phase 0 确认 | 高（若解密成功） |
| 当前明文 token | **无** | — | 不可得 |
| 活动指标 | 明文侧仅 3 个 memory 会话摘要 | 2026-10-03 ~ 10-08 | 极低，不足以做台账 |
| 额度 / credits | 仅云 API | — | 不可得（且不采用） |

---

## 3. 方案选项

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **A. SQLCipher + Keychain 密钥（推荐，带 Phase 0 门槛）** | 用户授权读取 Keychain → 缓存密钥 → 用 `sqlcipher` CLI 只读查询 | 唯一能拿到逐次 token 的本地路径；可复用现有台账 | 需要一次 Keychain 授权；引入 `sqlcipher` 系统依赖；schema 未知 | **推荐，先做 Phase 0** |
| B. 仅活动指标 | 读 `~/.trae-cn/memory` 摘要 | 无依赖 | 只有 3 个会话 / 9 条摘要；不是 token；不可用于用量 | 不采用 |
| C. 云 API + 本地 JWT | 用 `trae-jwt-token` 调私有接口 | 数据最全 | 违反无网络 / 无私有 API；凭证泄露风险；接口易变 | 拒绝 |
| D. 维持不采集 + 改进提示 | 保持「不采集」，`doctor` 说明「加密库无密钥」 | 零风险 | 用户看不到用量 | Phase 0 失败时的兜底 |

推荐路径：**A**，但把「能否拿到密钥并解密」作为 **Phase 0 硬门槛**；Phase 0 不通过就执行 D，不写采集代码。

---

## 4. Phase 0：可行性验证（实现前置）

### 4.1 需要用户授权的动作

1. **一次性读取 Keychain**（service `Trae CN Safe Storage`，account `Trae CN` / `Trae CN Key`）的 secret。
   - 只在本机内存中使用；不打印、不写日志、不写文档。
   - 读取本身可能弹出 macOS 授权框；若希望后续无人值守，需要选择「始终允许」，或改用 §5.2 的 0600 密钥文件。
2. **安装 `sqlcipher` CLI**（`brew install sqlcipher`）。
   - 这是一次性的系统依赖安装；`usage` 本身仍然不联网。
3. **允许在 `/tmp` 下复制加密的 `database.db` + `-wal`** 做解密测试。
   - 副本仍是密文；测试后删除。

> 若用户不接受第 1 或第 2 项，直接走方案 D，本文档停止在 §4。

### 4.2 验证步骤

1. 读取 Keychain secret，不落盘；可选计算 SHA-256 前 8 位仅用于日志标识。
2. 用 `sqlcipher` 打开副本，依次尝试：
   - 原样字符串作为 passphrase（SQLCipher 4 默认：page 4096、PBKDF2-HMAC-SHA512 256k、AES-256-CBC、HMAC-SHA512、reserve 80）
   - base64 解码后的 32 字节作为 raw key（`PRAGMA key = "x'...'"`）
   - hex 解码后的 32 字节作为 raw key
   - `PRAGMA cipher_compatibility = 3`（PBKDF2-SHA1 64k）
   - 若程序自定义 `kdf_iter` / `page_size` / `plaintext_header_size`，按二进制字符串与 schema 再调
3. **成功标准**：`SELECT count(*) FROM sqlite_master` 可执行，且能读到 `chat_message` / `chat_session` / `project` / `history_v2` 等表。
4. 读取 schema 与 3~5 条样本（只取元数据列，不取 `messages` / `content`）：
   - `history_v2.token_usage` / `item_token_usage` 的 JSON 形状与字段名
   - `message_role` / `message_type` 取值；assistant 过滤条件
   - `created_at` / `updated_at` 单位（秒 / 毫秒）与时区
   - `message_id` 唯一性；`is_deleted` / `is_archived` 语义
   - model 字段位置（`chat_session` / `chat_turn` / `model_config_cache` / 其他）
   - project 字段位置（`project.absolute_path` / `chat_session.project_id`）
   - `history_v2` 与 `chat_message` 是否重复；`item_token_usage` 与 `token_usage` 是否重复
   - `token_usage` 是单次值还是累计值（对照同会话相邻消息的数值是否单调递增）
5. 只读性验证：
   - 打开前后源库 `mtime` / 文件大小不变；不产生 `-journal`；WAL 不被 checkpoint。
   - `PRAGMA query_only=ON` + `sqlcipher -readonly`；若 WAL 读锁失败，再退回「复制三件套到临时目录查询副本」。
6. 无人值守验证：
   - 在非交互 shell（模拟 launchd）中再次读取 Keychain；若被拒绝，确认必须使用 0600 密钥文件或「始终允许」。
7. 性能：记录首次打开耗时、全表扫描耗时、增量（mtime 不变）耗时。
8. 产出：把 §4.2 结果追加到 `/Users/wayne/workspace/playground/usage-ledger/docs/PROBE.md`（不含密钥、不含正文），作为是否进入 Phase 1 的依据。

### 4.3 Phase 0 通过 / 不通过标准

| 结果 | 判定 |
|---|---|
| 能解密 + 能定位逐次 usage（非累计、可按 message_id 去重）+ 有非 0 的 prompt/completion/cache 字段 + 能定位 model/project/时间 | **通过**，进入 Phase 1 |
| 能解密但 token 全 0 / 只有会话级汇总 / 无法按调用归属 | **不通过**，走方案 D（不做假数据） |
| 不能解密（密钥不对 / 参数不支持） | **不通过**，走方案 D |
| 能解密但无人值守无法取密钥，且用户不接受 0600 文件 | **降级**：只在手动 `sync` 时采集，不做自动刷新（需评审确认） |

---

## 5. 采集设计（Phase 1，仅在 Phase 0 通过后实施）

### 5.1 路径与只读约束

```python
home = source_home()
TRAE_DB = env("USAGE_LEDGER_TRAE_CN_DB") or (
    home + "/Library/Application Support/Trae CN/ModularData/ai-agent/database.db")
KEY_FILE = env("USAGE_LEDGER_TRAE_CN_KEY_FILE") or (
    home + "/.local/share/usage-ledger/trae-cn.key")
```

- 只读：`sqlcipher -readonly` + `PRAGMA query_only=ON`。
- 优先直接只读打开源库；若 SQLite 需要写 `-shm` 或加锁失败，则复制 `database.db` + `database.db-wal`
  到临时目录（不复制 `-shm`，让 SQLite 重建），查询后删除副本。
- 不读 `messages` / `content` / `full_prompt` / `code_*` 等正文列。
- 源库不存在 / 密钥缺失 / `sqlcipher` 缺失 → `SourceResult.available=False` + `notes`，
  不抛异常、不影响其他源。

### 5.2 密钥解析与缓存

解析顺序：

1. `USAGE_LEDGER_TRAE_CN_KEY`（测试 / 临时；hex 或 base64）
2. `USAGE_LEDGER_TRAE_CN_KEY_FILE`（默认 `/Users/wayne/.local/share/usage-ledger/trae-cn.key`，权限 0600）
3. Keychain（仅显式命令 `usage trae-cn-setup` / `usage sync --source trae-cn` 首次时读取；
   自动刷新**不**弹窗）

密钥只通过 stdin 传给 `sqlcipher`，**不放进 argv**（避免 `ps` 泄露）；不写日志；
异常信息中脱敏。

缓存策略（评审点）：

| 方案 | 安全性 | 无人值守 | 说明 |
|---|---|---|---|
| K1 Keychain +「始终允许」 | 高（不落盘） | 取决于 ACL / launchd | 需要在 Keychain Access 中给 `/usr/bin/security` 授权 |
| K2 0600 文件（推荐） | 中（落盘，权限 0600） | 稳定 | 目录 0700；用户可随时删除；`doctor` 检查权限 |
| K3 每次手动输入 / 环境变量 | 高 | 不可 | 不适合定时任务 |

推荐 K2，并在首次 `usage trae-cn-setup` 时明确告知「密钥将以 0600 保存到 …」。
若用户拒绝落盘，改 K1 并把自动刷新降级为手动。

### 5.3 SQL 与口径（待 Phase 0 固化）

候选查询（只取元数据，**不选 `messages`**）：

```sql
SELECT h.history_v2_id, h.session_id, h.message_id,
       h.token_usage, h.item_token_usage,
       m.message_role, m.message_type, m.created_at, m.updated_at,
       m.is_deleted, m.is_archived,
       s.project_id, s.session_type,
       p.absolute_path
FROM history_v2 h
LEFT JOIN chat_message m ON m.message_id = h.message_id
LEFT JOIN chat_session s ON s.session_id = h.session_id
LEFT JOIN project p ON p.id = s.project_id
WHERE m.message_role = 'assistant'
  AND COALESCE(m.is_deleted, 0) = 0
  AND h.token_usage IS NOT NULL
  AND h.token_usage NOT IN ('', 'null', '{}')
```

> 若 Phase 0 证明 `chat_turn` 才是逐次真值，则改为 `chat_turn` + `chat_message`；
> 若 `token_usage` 是累计值，则必须按会话 / 消息顺序做差分，不能直接求和。

映射规则（与现有源一致）：

- OpenAI 形状：`input = max(prompt_tokens - cached, 0)`、`cache_read = cached`、
  `output = max(completion_tokens - reasoning, 0)`、`reasoning = reasoning`、`cache_write = 0`
- Anthropic 形状：`input = input_tokens`、`output = output_tokens`、
  `cache_read = cache_read_input_tokens`、`cache_write = cache_creation_input_tokens`、`reasoning = 0`
- 全 0 / 损坏 JSON 跳过，计入 `key_kinds["zero-usage"]` / `["bad-json"]`
- 五项合计 = `input + output + cache_read + cache_write + reasoning`，与现有 `Counts.total()` 一致
- `key = "trae-cn:<message_id>"`；`session = session_id`；`turns = 1`
- `model`：Phase 0 确定；回退 `unknown`；`model_raw` 同值
- `project = basename(absolute_path)`；空 → `None`
- `agent = session_type`（若列存在，如 `ide` / `solo`）；否则 `None`
- `provider = "trae-cn"`；`cost = None`，`cost_source = "unknown"`
- `day = local_day(created_at)`；`ts = epoch seconds`

### 5.4 增量、去重、归档

- `source_signatures()` 增加 `trae-cn`：`max(mtime(database.db), mtime(database.db-wal))`；
  `-shm` 不计入（变化频繁且不代表数据）。
- mtime 未变 → 不打开库（零成本）。
- mtime 变 → 全量查询 `history_v2` / `chat_message`（预估 ≤ 数万行，Phase 0 实测）；
  `usage_turn` 主键去重，重复 sync 幂等。
- **去重不能用 `SourceResult.add()` 的「保留较大 Counts」语义**：如果 `history_v2` 存的是累计快照，
  较大值就是累计值，会把总量放大。Phase 0 必须先确定：
  - 若一行就是一次调用 → 按 `message_id` 直接取该行；
  - 若同一 `message_id` 有多行快照 → 取最新 `history_v2_id` / `updated_at`，或按时间顺序差分；
  - 若 `token_usage` 是累计值 → 按会话 / 消息顺序差分，差分为负则跳过并记 `negative-delta`。
- 如果 Phase 0 发现 `updated_at` 有索引且全量偏慢，再改为「游标 + 2 分钟重叠 + 受影响天重算」；
  v1 不做时间游标。
- 归档：沿用现有 `full` / `mark_archived` 机制；Trae CN 库被清理时历史行永久保留。

### 5.5 自动刷新

- `_refresh_if_stale()` 默认会检查所有源；Trae CN 密钥缺失时**静默跳过**
  （打印一行 stderr note，不弹 Keychain）。
- 只有显式 `usage sync --source trae-cn` 或 `usage trae-cn-setup` 才允许触发 Keychain 读取。
- `--stateless` 直读源：需要密钥文件 / 环境变量；无密钥则 `available=False`。

### 5.6 失败处理

| 情况 | 行为 |
|---|---|
| `sqlcipher` 未安装 | `available=False`，note 提示 `brew install sqlcipher`，其他源正常 |
| 密钥文件缺失 / 权限错误 | `available=False`，note 提示运行 `usage trae-cn-setup` |
| 解密失败 | `available=False`，error「密钥不匹配或 SQLCipher 参数变化」，不重试、不删历史 |
| schema drift | error 指出缺失的表 / 列；不中断整轮 sync |
| WAL 读锁失败 | 复制 `db` + `-wal` 到临时目录重试一次；仍失败则记 error |
| JSON 损坏 | 跳过该行，计入 `bad-json`，继续 |

---

## 6. 展示层

### 6.1 源注册

- `SOURCES` 增加 `trae-cn`；CLI `--source trae-cn` 可用；HTML chip 自动生成。
- `NO_TOKEN_NOTICE` 移除 Trae CN，只保留 ChatGPT 桌面端。
- 源显示名 `Trae CN`，内部 id `trae-cn`。

### 6.2 `usage report` / `top` / `export`

- Trae CN 行正常参与天 × 源 × 模型、`top`、`export`；成本列 `unknown`。
- 页脚动态提示：

  > Trae CN：token 覆盖 `<min>..<max>`（SQLCipher 只读，需本机密钥）；与活动指标不可相加。

- 若查询区间内 Trae CN token = 0 且源不可用：
  `trae-cn: 本地加密库未解密（缺少密钥 / sqlcipher），本区间无数据；不代表未使用`

### 6.3 `usage html`

- 无新表 / 新图表；Trae CN 作为普通 source 进入现有 KPI / 柱状图 / 模型 / 项目 / 明细。
- 顶部覆盖提示增加 Trae CN 的 token 覆盖范围与「需密钥」说明。
- 若源不可用，页面显示 0（与现有缺失源一致），但顶部提示说明原因，避免误读。

### 6.4 `usage doctor`

可用时：

```
trae-cn: files=1 records=N tokens=... recent7d=... status=ok
  note: SQLCipher 只读；密钥来源=key-file / Keychain；覆盖 2026-..-.. ~ 2026-..-..
  warning: database.db 已 X 天未更新（Trae CN 可能未使用）
```

不可用时：

- `warning: 缺少 sqlcipher CLI（brew install sqlcipher），Trae CN 跳过`
- `warning: 未配置 Trae CN 密钥；运行 usage trae-cn-setup`
- `warning: Trae CN 解密失败（密钥不匹配或 SQLCipher 参数变化）；已跳过，不影响其他源`
- `warning: chat_message / history_v2 或 token_usage 列缺失，疑似 Trae CN schema 变更`

新增 `usage doctor --probe trae-cn`：打印 token 覆盖范围、月度汇总、模型分布（含 `unknown` 占比），
不打印正文、不打印密钥。

### 6.5 新增 `usage trae-cn-setup`（一次性）

```
usage trae-cn-setup [--keychain-account "Trae CN Key"] [--key-file PATH] [--no-cache]
```

- 读取 Keychain → 用 `sqlcipher` 试解密 → 成功则写 0600 密钥文件（或提示已配置 Keychain）
  → 打印覆盖范围与样本计数（不含正文）。
- 失败时不写任何文件，返回非 0，并提示可能的参数不匹配。
- 该命令是唯一会主动触发 Keychain 弹窗的入口。

---

## 7. 改动清单（文件级）

| 文件 | 改动 |
|---|---|
| `src/usage_ledger/collectors.py` | 新增 `trae_cn_paths()`、`scan_trae_cn_tokens()`、SQLCipher 子进程封装、token JSON 映射；`source_signatures()` 增加 `trae-cn`；`collect_all()` 支持 |
| `src/usage_ledger/models.py` | 复用 `Record` / `Counts` / `SourceResult`；不新增表 |
| `src/usage_ledger/store.py` | 复用 `usage_turn` / `source_state`；无 schema 变更 |
| `src/usage_ledger/cli.py` | `SOURCES` 增加 `trae-cn`；`NO_TOKEN_NOTICE` 移除 Trae CN；新增 `trae-cn-setup` 子命令；`_sync_into` 跳过 / 错误处理；`doctor` 分支；覆盖率提示 |
| `src/usage_ledger/html_report.py` | 仅覆盖提示文案（source 自动进入现有图表） |
| `tests/test_collectors.py` | 新增 token JSON 映射、去重、密钥缺失、sqlcipher 缺失等单测 |
| `tests/test_cli.py` | `--source trae-cn`、setup 失败分支、doctor 文案 |
| `tests/test_store.py` | 复用现有；可加 `trae-cn` 归档用例 |
| `tests/test_html.py` | payload 含 `trae-cn` source；不可用提示 |
| `tests/fixtures/trae_cn/`（新增） | 生成 SQLCipher 测试库的脚本（需 `sqlcipher`，默认跳过）；不提交真实数据 |
| `README.md` | 覆盖表 Trae CN 改为「可用（条件：SQLCipher + 本机密钥）」；命令示例；依赖说明 |
| `docs/DESIGN.md` §3.3 / `docs/PROBE.md` §1.1 | 更新 Trae CN 结论（Phase 0 通过后） |
| `pyproject.toml` / `__init__.py` | 版本 0.5.0 |

---

## 8. 测试与验收

### 8.1 单元测试（不依赖真实库）

1. OpenAI 形状：`prompt=1000, cached=800, completion=50, reasoning=10`
   → `input=200, cache_read=800, output=40, reasoning=10`，total=1050。
2. Anthropic 形状：`input=200, cache_read=800, cache_write=100, output=50` → 原样映射，total=1150。
3. `cached > prompt` clamp；全 0 / `{}` / 损坏 JSON / 非 assistant 行跳过。
4. 同 `message_id` 重复行只计一次；`history_v2` 与 `chat_message` 不重复计。
5. 模型 / project / session / agent 回退。
6. 密钥缺失 → `available=False` + note，不抛异常。
7. `sqlcipher` 缺失 → 同上，note 含安装提示。
8. 密钥解析顺序：env > file > keychain；测试用 fake keychain 函数。
9. `source_signatures` 只随 `database.db` / `-wal` 变化；`-shm` 变化不触发。
10. `trae-cn-setup` 解密失败 → 不写密钥文件、返回非 0。
11. CLI：`sync/report/activity/doctor --source trae-cn` 参数合法；report JSON 含 `trae-cn`。

### 8.2 集成测试（需 `sqlcipher`，默认跳过）

12. 用 `sqlcipher` 生成临时库（已知密钥、2 个会话、3 条 assistant、1 条 user、1 条全 0），
    跑 `scan_trae_cn_tokens`，断言记录 / 字段 / 去重。
13. 连续 sync 两次 → 0 新增（幂等）。
14. 只改 WAL → 签名变化；只改 `-shm` → 签名不变。

### 8.3 真实库验收（Phase 0 通过后）

- `usage trae-cn-setup` → 成功；密钥文件权限 0600；不打印密钥。
- `usage sync --source trae-cn` → 记录数 = 独立 SQL 的 assistant + 非空 usage 行数（去重后）；
  tokens = `SUM(input)+SUM(output)+SUM(cache_read)+SUM(cache_write)+SUM(reasoning)`，与独立 SQL 一致。
- 连续 sync 两次 → 0 新增。
- 源库 mtime 不变；不产生新文件（除 `-shm` 既有）；`database.db` 大小不变。
- `usage report --source trae-cn --format json` 与库内一致。
- `usage html` 中 Trae CN chip / 图表 / 明细可见；无 console 错误。
- `usage doctor` 显示覆盖范围；删除密钥后显示「未配置密钥」且其他源正常。
- 自动刷新（`usage report`）在密钥存在时不弹 Keychain；删除密钥后只打印 note。

### 8.4 性能预算

| 场景 | 预算 |
|---|---|
| mtime 未变 | ~0s（不打开库） |
| 首次解密 + 全量 | ≤3s（含 sqlcipher KDF） |
| 增量（mtime 变） | ≤2s |
| setup 一次 | ≤5s |
| HTML 增量 | <10 KB |

---

## 9. 风险与缓解

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | Keychain 密钥不是 DB key / 无法获取 | 方案 A 失败 | Phase 0 先验证；失败走 D；不写半成品 |
| R2 | `sqlcipher` 参数非默认（compat / kdf_iter / page_size） | 无法解密 | Phase 0 多参数试解；doctor 明确报错；不做无限重试 |
| R3 | schema / JSON 形状变更 | 采集失败 / 漏数 | 列存在性检查、JSON 容错、错误隔离、doctor 告警、fixture |
| R4 | WAL 读取锁 / 一致性 | 读失败或漏最新 | `-readonly` + `query_only`；失败时复制三件套到临时目录查询；不写源库 |
| R5 | 重复计数（`history_v2` / `item_token_usage`） | 总量虚高 | Phase 0 采样确认；只取一张表 / 一个字段；`message_id` 去重 |
| R6 | 累计值被当单次值 | 总量虚高 | Phase 0 对照相邻消息判断单调性；累计则差分；无法判断则不采集 |
| R7 | 密钥落盘 | 本机泄露风险 | 0600 / 0700；用户可选 Keychain；`doctor` 检查权限；可一键删除；不写日志 |
| R8 | Keychain 弹窗 / launchd 无 UI | 自动刷新失败 | 首次 setup 缓存；自动刷新只读缓存；失败静默跳过并提示 |
| R9 | `sqlcipher` 依赖违反「零依赖」 | 部署复杂 | 仅 Trae CN 可选依赖；缺失时跳过；Python 侧仍 stdlib；文档明示 |
| R10 | Trae CN 升级 / 重装导致密钥 / 库变化 | 解密失败 / 历史丢失 | 历史已固化 `usage_turn`；doctor 提示重跑 setup；不自动删除旧行 |
| R11 | 隐私 / 合规 | 信任问题 | 只读元数据列；不读正文；不联网；不导出明文库；文档写明 |
| R12 | 时区 / 时间单位 | 日期错位 | Phase 0 确认秒 / 毫秒；统一 `local_day()`；与现有源一致 |

---

## 10. 发布与回滚

- 版本：**0.5.0**（新增源 + 可选系统依赖，向后兼容）。
- 迁移：无 schema 变更；`source_state` 自动新增 `trae-cn` 行。
- 上线顺序：
  1. Phase 0（评审通过后）；
  2. `usage trae-cn-setup`；
  3. `usage sync --source trae-cn`；
  4. `usage doctor` 核对覆盖；
  5. `usage report` / `usage html` 人工验收。
- 回滚：
  - 从 `SOURCES` 移除 `trae-cn` 停止采集；
  - 删除密钥文件 / Keychain 项；
  - 可选 `DELETE FROM usage_turn WHERE source='trae-cn'; DELETE FROM source_state WHERE source='trae-cn';`
  - 不影响其他源。
- 文档更新：README 覆盖表、DESIGN §3.3、PROBE §1.1、本文件。

---

## 11. 待拍板（Phase 0 路径，已归档）

> 以下问题属于加密库路径；Phase 0 不通过后均不再阻塞。Plan H 的已确认事项见 §13。

1. **是否同意先做 Phase 0**（一次性读取 Keychain + 安装 `sqlcipher` + 临时复制加密库）？
   这是方案 A 的唯一入口。
2. **密钥缓存方式**：0600 文件（推荐，支持 launchd）／Keychain「始终允许」／每次手动输入（不支持自动刷新）？
3. **是否接受 `sqlcipher` 作为可选系统依赖**？
   若不接受，是否接受「Trae CN 永远不采集，只改进 doctor」（方案 D）？
4. **若 Phase 0 只能手动 sync、无法无人值守**：是否接受「只在手动 `usage sync --source trae-cn` 时采集，
   不做自动刷新」？
5. **是否只做 token、不做活动轴**（推荐；明文侧活动数据只有 3 个会话，不足以做台账）？
6. **源命名**：`trae-cn`（推荐）还是 `traecn` / `trae`？
7. **密钥读取入口**：新增 `usage trae-cn-setup`（推荐）还是复用 `usage sync --source trae-cn` 首次提示？

> 审核通过后按 §4 先做 Phase 0；Phase 0 结果确认后再按 §7 实施 Phase 1。
> 未通过前不写采集实现代码。

---

## 12. Plan H：Hooks 估算轨（2026-11-01 设计，2026-11-02 实现）

> 用户决定：既然 Trae CN 有 hooks，就采用与 Qoder `est` 相同的呈现方式做 token 估算。
> 本文只设计**估算轨**，不碰加密库、不调私有 API、不读 JWT、不做额度。
> 前提事实：Trae Hooks 的 stdin **没有** token/credits/quota/transcript 字段（PROBE §6.8），
> 因此只能对 hook 可见的文本做字符级估算；这是弱估算，不是 Qoder 那种带上下文比例的估算。
>
> **实现状态（2026-11-02）**：H1–H3 已完成，`tests/test_trae_hooks.py`、
> `tests/test_trae_collector.py`、`tests/test_cli_trae.py`、`tests/test_store.py` 覆盖安装/卸载、
> 重放、分源存储、CLI 与 HTML；全量 86 个单测通过。H0 真实捕获仍需用户安装 hook 并操作 Trae CN 验收。

### 12.1 边界与口径

| 项 | 决定 |
|---|---|
| 数据来源 | Trae CN Hooks（`SessionStart` / `UserPromptSubmit` / `PreToolUse` / `PostToolUse` / `Stop`） |
| 记录内容 | 仅事件元数据 + 字符数；**不落 prompt、tool_input、tool_response、last_assistant_message 正文** |
| 估算对象 | 每次「模型调用边界」：每个 `PreToolUse` 与每个 `Stop` 各一条 `Estimate` |
| 存储 | 复用 `usage_est`，新增 `source='trae-cn.est'`；与 Qoder 的 `qoder.est` 分源、分示 |
| 可加性 | **不可**与 token 真值、credits、活动指标相加；`report`/`html` 必须标注 |
| 历史 | 只覆盖 hook 安装之后的会话；不回溯加密库历史 |
| 模型 | hook 若提供 `model` 则记录；否则统一记 `trae-cn`（官方文档未列 `model`） |
| 额度 | 不做。额度仍只在服务端响应/加密库中，hook 拿不到（PROBE §6.7） |

### 12.2 数据流

```
Trae CN agent
  ├─ SessionStart       ─┐
  ├─ UserPromptSubmit    │    hook command（绝对路径的 Python + 独立脚本）
  ├─ PreToolUse          ├──► 只算长度，追加一行 JSON
  ├─ PostToolUse         │    /Users/wayne/.local/share/usage-ledger/trae-cn/events-YYYY-MM-DD.jsonl
  └─ Stop               ─┘    （0600；无正文）
                                      │
                         usage sync / usage est --source trae-cn
                                      │
                         重建每个 session 的可见上下文长度
                                      │
                         usage_est.source='trae-cn.est'
                                      │
                    usage est / usage html / usage doctor
```

### 12.3 Hook 配置与安装

官方配置（`https://docs.trae.cn/ide/reference-for-hooks-configuration`）：

- 全局：`/Users/wayne/.trae-cn/hooks.json`（对本机所有工作区生效）
- 项目：`<workspace>/.trae/hooks.json`（只对当前项目生效）
- 顶层：`{"version": 1, "hooks": {"<EventName>": [<group>, ...]}}`
- group：`matcher`（仅 PreToolUse/PostToolUse/Notification）、`loop_limit`（仅 Stop）、`hooks`
- hook item：`type: "command"`、`command`、`timeout`（默认 30s）
- 输入：stdin JSON；输出：stdout + 退出码；非 0/2 的退出码被忽略
- 官方事件字段：`SessionStart{source}`、`UserPromptSubmit{prompt}`、
  `PreToolUse{tool_use_id, tool_name, llm_tool_name, tool_input}`、
  `PostToolUse{..., tool_response}`、`Stop{stop_hook_active, loop_count, last_assistant_message}`、
  `Notification{notification_type, message, tool_use_id}`

安装后的全局配置示例（由 `usage hooks install trae-cn --scope global` 生成/合并）：

```json
{
  "version": 1,
  "hooks": {
    "SessionStart": [
      {"hooks": [{"type": "command", "command": "/opt/homebrew/bin/python3 /Users/wayne/.local/share/usage-ledger/hooks/trae-cn-hook.py", "timeout": 5}]}
    ],
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "/opt/homebrew/bin/python3 /Users/wayne/.local/share/usage-ledger/hooks/trae-cn-hook.py", "timeout": 5}]}
    ],
    "PreToolUse": [
      {"matcher": "*", "hooks": [{"type": "command", "command": "/opt/homebrew/bin/python3 /Users/wayne/.local/share/usage-ledger/hooks/trae-cn-hook.py", "timeout": 5}]}
    ],
    "PostToolUse": [
      {"matcher": "*", "hooks": [{"type": "command", "command": "/opt/homebrew/bin/python3 /Users/wayne/.local/share/usage-ledger/hooks/trae-cn-hook.py", "timeout": 5}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "/opt/homebrew/bin/python3 /Users/wayne/.local/share/usage-ledger/hooks/trae-cn-hook.py", "timeout": 5}]}
    ]
  }
}
```

安装约束：

1. 只合并、不覆盖：保留用户已有事件/组；JSON 解析失败则中止，不写文件。
2. 写前备份 `hooks.json.bak-<timestamp>`，临时文件 + `os.replace` 原子替换。
3. 幂等：通过「command 含 `trae-cn-hook.py` 绝对路径」识别自己的组；重复安装先移除旧组再写入。
4. 命令使用 `sys.executable` + 脚本绝对路径并 `shlex.quote`；Python/venv 搬迁后需重跑安装。
5. Hook 脚本独立、仅标准库；任何异常都 `exit 0`，绝不阻塞 Trae 的 agent。
6. 默认 `timeout: 5` 秒；正常执行 < 100ms。
7. Trae 可能在 Settings > Hooks 里要求确认/启用，或要求在「本地自动运行」模式下运行；
   安装命令打印绝对路径与操作提示，但不替用户点 UI。
8. 默认装全局（覆盖所有工作区）；如用户不接受全局 hook，可 `--scope project --project <abs path>`。

### 12.4 事件记录格式（隐私关键）

每行一个 JSON，建议 < 1 KB，字段固定：

```json
{"v":1,"uid":"<session>:<ts_ns>:<event>:<tool_use_id>","ts":1762000000.123,"event":"PreToolUse","session":"<session_id>","project":"usage-ledger","tool":"Read","tool_use_id":"toolu_xxx","chars_in":0,"chars_out":37}
```

- `chars_in`：进入上下文的字符数（`prompt`、`tool_response`）
- `chars_out`：模型生成的字符数（`tool_input`、`last_assistant_message`）
- `project`：`cwd` 的 basename，不存完整路径
- `tool`：标准化工具名（可选；MCP 工具名可能含 server/tool 名，不含参数）
- **不写**：prompt 文本、tool_input 内容、tool_response 内容、last_assistant_message 文本、命令、文件内容、完整 cwd
- 文件权限 0600，目录 0700；按本地日期切文件；默认保留 180 天（可手工清理，估算结果已在 DB 中）

长度测量规则：

- 字符串：Python `len(s)`（Unicode 字符数）
- 对象/数组：`len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))`
- 无法解析的 stdin / 未知事件：直接 `exit 0`，不写事件

### 12.5 估算算法

对每个 `session_id` 顺序重放事件，维护可见上下文长度 `ctx_chars`：

| 事件 | 动作 |
|---|---|
| `SessionStart` | 仅当该 session 尚未出现任何事件时 `ctx_chars = 0`；记录 project/model（若有）；防止重复 `SessionStart` 清空已累积上下文 |
| `UserPromptSubmit` | `ctx_chars += chars_in` |
| `PreToolUse` | 用**当前** `ctx_chars` 发一条估算；随后 `ctx_chars += chars_out`（tool_input 成为历史） |
| `PostToolUse` | `ctx_chars += chars_in`（工具结果成为历史） |
| `Stop` | 用当前 `ctx_chars` 发一条估算；随后 `ctx_chars += chars_out`（最终回复成为历史） |
| `PreCompact` / `PostCompact` | 官方文档未列；若未来出现，`PostCompact` 后把 `ctx_chars` 重置为摘要长度或 0（前向兼容） |

每条估算：

```text
est_input  = min(round(ctx_chars / factor) + overhead_tokens, window_tokens)
est_output = round(chars_out / factor)
chars_in   = ctx_chars
chars_out  = 本次输出字符数
ratio      = NULL
source     = "trae-cn.est"
request_id = "trae-cn:" + uid
```

默认参数（v1，可用环境变量覆盖，便于校准）：

| 参数 | 默认 | 环境变量 | 说明 |
|---|---|---|---|
| `factor` | 3.8 | `USAGE_LEDGER_TRAE_EST_FACTOR` | 字符/ token；沿用 Qoder 默认值 |
| `overhead_tokens` | 0 | `USAGE_LEDGER_TRAE_EST_OVERHEAD` | 系统提示/工具定义的固定补偿；默认 0 = 纯可见内容下限 |
| `window_tokens` | 200000 | `USAGE_LEDGER_TRAE_EST_WINDOW` | `ctx_chars` 上限；超出按窗口截断 |

示例（仅示意）：

```text
UserPromptSubmit: chars_in=200            ctx=200
PreToolUse:       chars_out=120           emit(input=200)   ctx=320
PostToolUse:      chars_in=8000           ctx=8320
Stop:             chars_out=300           emit(input=8320)  ctx=8620
→ 两个请求：est_input=53 / 2189，est_output=32 / 79（factor=3.8，overhead=0）
```

### 12.6 精度边界（必须在 UI/CLI 明示）

**偏低因素**：

- hook 拿不到系统提示、工具定义、Rules/Skills/Memory、MCP schema；
- 拿不到工具调用之间的 assistant 自然语言/思考内容（`Stop` 只有最终回复）；
- 附件、图片、未以文本形式出现在 `prompt` 里的上下文不可见；
- 官方未提供 token 真值，无法做误差校准。

**偏高因素**：

- 同一轮并行多个工具调用会产生多条 `PreToolUse`，每条都按完整上下文计输入；
- 没有压缩/截断信号时，`ctx_chars` 只增不减，压缩后仍按旧上限估算；
- 工具结果/文件内容在上下文里可能被截断，hook 看到的是完整结果。

**结论**：这是「可见内容下限 + 部分重复」的混合估算，**误差可能数倍且方向不定（未校准）**；
只适合看趋势/占比，不适合对账、计费或与 Qoder 的 est 直接比较。
CLI/HTML 固定标注：`Trae CN 弱估算（hook 可见内容，不含系统提示/工具定义）`。

### 12.7 存储与命令接入

**Schema**（`usage_est`）：

```sql
ALTER TABLE usage_est ADD COLUMN source TEXT NOT NULL DEFAULT 'qoder.est';
CREATE INDEX IF NOT EXISTS idx_est_source_day ON usage_est(source, day);
```

- 新库在 `CREATE TABLE` 里直接带 `source`；旧库启动时检测 `PRAGMA table_info(usage_est)` 后补列。
- `Estimate` 增加 `source: str = "qoder.est"`；Qoder 现有构造不传，行为不变。
- `upsert_estimates` 写入 `source`；`request_id` 已带 `trae-cn:` 前缀，避免冲突。

**新增源**：

- 公开源名：`trae-cn`（`SOURCES` 增加）；子源名：`trae-cn.est`（`source_state` / `usage_est.source`）。
- `scan_trae_cn_est()`：读事件文件 → 重放 → 返回 `SourceResult("trae-cn.est")`。
- `source_signatures`：`trae-cn` → 事件目录最新 mtime；`trae-cn.est` 与 `trae-cn` 同签名。
- `collect_all`：`trae-cn` → `scan_trae_cn_est()`。
- `_sync_into`：`trae-cn.est` 走 `upsert_estimates` + `update_source_state`，不碰 `usage_turn`。
- 不做 `usage_activity`；活动轴仍只属于 Qoder（如后续要加，另立方案）。

**CLI**：

```bash
usage hooks install trae-cn --scope global      # 写/合并 ~/.trae-cn/hooks.json
usage hooks status trae-cn                      # 配置、事件文件、最近事件、条数
usage hooks uninstall trae-cn --scope global    # 只删自己的组
usage sync --source trae-cn                     # 重建并入库（可重复执行）
usage est --source trae-cn --group-by day,session
usage est --source trae-cn --stateless --group-by day,model
usage doctor                                    # 显示 hook 安装状态/覆盖/最近事件
```

- `usage est` 新增 `--source {qoder,trae-cn}`，默认 `qoder`（保持兼容）；
  `trae-cn` 不支持 `ratio`，提示改为「无上下文比例，仅字符估算」。
- `usage report --source trae-cn` 没有 token 真值，只显示提示；
  Trae 估算在 `usage est` 与 `usage html` 中展示（HTML 中作为独立 agent chip）。
- `usage sync`（不带 `--source`）默认包含 `trae-cn`；无 hook 日志时 `available=False`，不报错。

**HTML（Phase H3）**：

- 来源 chip 增加 `trae-cn`：无 token 真值，chip 显示弱估算总量（`est`）；
  单独选中时隐藏 token 主视图，只显示弱估算补充区；
- 「补充口径」区保留来源切换：`Qoder（活动/额度/估算）` 与 `Trae CN（估算）`；
  补充区跟随来源筛选，Qoder 只在 Qoder 选中时出现，Trae 只在 Trae CN 选中时出现；
- Trae 面板复用 est 卡片/表格，固定标注「弱估算、不可相加」；
- 无数据时不显示该来源。

### 12.8 改动清单

| 文件 | 改动 |
|---|---|
| `src/usage_ledger/trae_hooks.py`（新增） | hook 安装/合并/卸载、事件文件路径、hook 脚本生成 |
| `src/usage_ledger/collectors.py` | `scan_trae_cn_est()`、签名、`collect_all` 接入、估算常量 |
| `src/usage_ledger/models.py` | `Estimate.source` 默认值 |
| `src/usage_ledger/store.py` | `usage_est.source` schema + 迁移、upsert、按 source 查询 |
| `src/usage_ledger/cli.py` | `hooks` 子命令、`SOURCES`、`est --source`、`sync`/`doctor` 接入 |
| `src/usage_ledger/html_report.py` | Trae 来源 chip、补充区来源切换与弱估算面板（H3） |
| `tests/fixtures/trae_hooks/`（新增） | 脱敏事件序列 |
| `tests/test_trae_hooks.py`（新增） | 安装合并、长度记录、隐私、重放、幂等 |
| `tests/test_store.py` / `test_cli.py` / `test_html.py` | source 迁移、`est --source`、doctor、HTML |
| `README.md` / `docs/TRAE-CN-DESIGN.md` / `docs/PROBE.md` | 口径、命令、限制 |

### 12.9 测试与验收

**单元测试**：

1. 安装器：空文件、已有其他 hook、已有旧的本项目 hook、损坏 JSON（中止且不覆盖）。
2. 隐私：给定含敏感文本的 stdin，事件文件只含长度/元数据；断言敏感子串不出现。
3. 重放：prompt → Pre → Post → Stop 的 est_input/est_output 与手算一致。
4. 边界：无 tool、多个 tool、并行 tool、Stop 为空、跨天 session、乱序文件、重复事件。
5. 幂等：同一事件日志 sync 两次，`usage_est` 行数不变。
6. 迁移：旧库启动后 `source` 列存在，Qoder 行默认 `qoder.est`，查询不混源。
7. 失败安全：stdin 非法/目录不可写 → 退出码 0，Trae 不受影响。

**真实验收（需用户操作，约 2 分钟）**：

1. 在 Trae CN 中启用 hook（Settings > Hooks 确认）；
2. 打开任意工作区，发一条会触发至少一次工具调用的 prompt；
3. 确认 `/Users/wayne/.local/share/usage-ledger/trae-cn/events-<date>.jsonl` 出现
   `SessionStart` / `UserPromptSubmit` / `PreToolUse` / `PostToolUse` / `Stop`；
4. `usage sync --source trae-cn` 后，`usage est --source trae-cn --group-by day,session`
   出现 ≥ 1 条，且 `chars_in/out` 与文件一致；
5. `usage doctor` 显示 hook 已安装、最近事件时间、估算条数；
6. 抽查事件文件/DB，确认没有 prompt/工具输出正文。

### 12.10 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| hook 未真正启用（手写配置不被识别） | 无数据 | H0 先做一次真实捕获；安装后提示用户在 Settings 确认；失败则回退项目级/UI 创建 |
| hook 运行在沙箱，无法写 `~/.local/share` | 无数据 | 文档要求切「本地自动运行」；doctor 提示；不静默失败 |
| hook 阻塞 agent | 体验受损 | 独立脚本、标准库、`timeout: 5`、所有异常 `exit 0` |
| 估算严重偏低/偏高 | 误导 | 固定标注「弱估算/趋势」；不参与汇总、成本、额度；保留 `chars_*` 供校准 |
| 全局 hook 影响所有工作区 | 安全/隐私顾虑 | 默认推荐全局但需用户批准；支持 project scope；脚本只读 stdin + 写本地元数据 |
| Trae 升级改字段/路径 | 采集中断 | 字段缺失容错为 0；`doctor` 显示最近事件；H0 记录版本 |
| 事件文件增长 | 磁盘 | 按日切分、0600、默认 180 天保留；同步只读元数据 |
| 并行工具调用重复计输入 | 高估 | 文档明示；后续可按 `llm_tool_name`/时间窗聚合（暂不做） |

### 12.11 分期

| 阶段 | 内容 | 状态 |
|---|---|---|
| H0 | 真实 hook 捕获探针：确认启用方式、实际字段（尤其 `model`）、事件顺序；只记字段名+长度 | **待用户验收**（安装 hook 后发一条带工具调用的 prompt） |
| H1 | hook 脚本 + 安装/状态/卸载 + 事件日志 + 重放 + `scan_trae_cn_est` + store source 迁移 | 已实现 |
| H2 | `usage est --source trae-cn` + `sync`/`doctor` + 测试 + 文档 | 已实现 |
| H3 | HTML 补充区来源切换 + Trae 估算面板 | 已实现 |

> 真实 hooks 未由本仓库自动写入；安装命令为
> `usage hooks install trae-cn --scope global`，执行前会展示目标路径并生成带时间戳备份。
> H0 验收步骤见 README「下一步」。

---

## 13. Plan H 已确认事项

1. **作用域**：默认全局 `/Users/wayne/.trae-cn/hooks.json`；同时支持 `--scope project`。
2. **精度预期**：已接受「弱估算/可见内容下限，误差可能数倍且方向不定（未校准），只做趋势」。
3. **隐私**：只保存字符数、session_id、project basename、工具名与事件元数据，不保存正文。
4. **H0**：安装 hook 后由用户在 Trae CN 中发一条带工具调用的 prompt 做真实捕获验收；未通过前不宣称采集成功。
5. **默认参数**：`factor=3.8`、`overhead=0`、`window=200000`；支持环境变量校准。
6. **模型维度**：hook 未提供 `model` 时统一记 `trae-cn`。
7. **HTML**：H1–H3 一次交付；Trae 面板只在有弱估算数据时显示。

> 最终组合：全局 hook + H0 待验收 + 弱估算明示 + 默认参数 + 已实现 H1–H3；不碰加密库、JWT、私有 API、额度。
