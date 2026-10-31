# TRAE-CN-DESIGN.md —— Trae CN 用量统计接入设计（评审稿）

> 日期：2026-10-30 ｜ 状态：**Phase 0 已完成：不通过 → 按 §4.3 走方案 D（未写实现代码）** ｜ 基线：usage-ledger v0.4.0（2ec136e）
> Phase 0 实测：加密库无法在本地只读解密（密钥由运行时 `db_persistence` 配置下发，本地无明文落盘；详见 [PROBE.md](PROBE.md) §6）。§5–§10 保留作记录，不实施。
> 一句话结论：Trae CN 的逐次调用 token 明细**只存在于 SQLCipher 加密的 ai-agent 数据库**中，本地明文侧没有任何 token。接入的前提是先完成一次「经用户授权的密钥读取 + 只读解密」可行性验证（Phase 0）；验证通过才实现采集，否则维持不采集，只把 `doctor` 提示写清楚。

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

- 不估算 token（不用文本长度、上下文百分比、消息条数反推）。
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

## 11. 待拍板（请审核时确认）

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
