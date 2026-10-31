# QODER-DESIGN.md —— Qoder 用量统计扩展设计（评审稿）

> 日期：2026-10-30 ｜ 状态：**待评审，未写实现代码** ｜ 基线：usage-ledger v0.3.3（d331c31）
> 一句话结论：Qoder 新版桌面端本地**没有 token 真值**；但 Qoder IDE 旧库存在**完整历史 token**（2026-06-01 ~ 2026-09-16），新版客户端存在**当前活动指标**（至今）。建议按“token 台账 + 活动台账”双轨接入，分表、分命令、分提示，**绝不相加**。

---

## 1. 背景与目标

### 1.1 现状

- 现有 4 个 token 源：`claude` / `codex` / `opencode` / `kilo`。
- DESIGN §3.3 曾判定 Qoder “不采集”，依据是 `~/.qoder/projects/**/*.jsonl` 的 6,898 条 assistant 记录 token 字段全为 0。
- 本次重新探针发现：token 真值不在 JSONL，而在 Qoder IDE 的 `SharedClientCache/cache/db/local.db`；新版桌面端把数据迁到 `com.qoder.app.stable/main.sqlite`，但 token 字段为空/0。
- 用户使用 Qoder 的频率很高（本会话即 Qoder），仅显示 0 会严重低估用量；但也不能用活动指标冒充 token。

### 1.2 目标

1. 把 Qoder IDE 历史 token 纳入现有 token 台账，与其他源同表、同字段、同口径。
2. 把 Qoder 桌面端当前活动纳入**独立**活动台账：会话数、提示数、assistant 调用数、turns、工具调用数、运行时长。
3. 在 `report` / `html` / `doctor` 中显式标注数据覆盖范围，避免把“本地取不到”误读为“没有使用”。
4. 严格只读、本地 SQLite、标准库、无网络、不读取/不落库会话正文。

### 1.3 非目标

- 不估算 token（不用文本长度、上下文百分比、消息条数反推）。
- 不调用 Qoder 云 API，不读取登录凭证，不联网。
- 不把活动指标换算成 token 或成本，不参与 `cost_equiv_usd`。
- 不做 Qoder 额度/credits：本地无真值（详见 §2.3）。
- 不追读 `content` / `text` / `tool_result` 正文。

---

## 2. 实测事实（2026-10-30，只读探针）

### 2.1 数据源 A：Qoder IDE token 库（可用，覆盖历史）

**路径**：`/Users/wayne/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db`

| 项 | 实测值 |
|---|---|
| 文件大小 | 1,775,779,840 B（约 1.65 GiB） |
| 最后写入 | 主库 mtime 2026-09-16 09:13；`-wal` 0 字节 |
| 表 `chat_message` | 48,432 行；assistant 21,654 行 |
| 有效 token 行 | **19,963 行**（`token_info` 含完整四字段）；其中 **7 行全 0** 被采集器跳过，实际入库 **19,956 行**；966 行为 `{}`；725 行为空 |
| token 总量 | prompt **2,690,591,243**；completion **10,390,783**；cached **2,522,926,395** |
| 覆盖日期 | 2026-06-01 ~ 2026-09-16（本地时区） |
| 会话/项目 | 271 个 session；8 个项目 |
| 会话类型 | `quest` 130 + `agent_sub_*` 141 |
| 去重 | `chat_message.id` 全表唯一（48,432 / 48,432） |

**字段结构**：

```json
token_info = {"prompt_tokens":181198,"completion_tokens":656,
              "cached_tokens":179200,"max_input_tokens":200000}
model_info = {"model_key":"gfmodel"}
gmt_create = 1789520778220   // epoch ms
```

**月度分布（有效 token 行）**：

| 月份 | 调用数 | prompt | completion |
|---|---:|---:|---:|
| 2026-06 | 11,041 | 1,965,869,904 | 4,934,354 |
| 2026-07 | 118 | 23,275,555 | 119,447 |
| 2026-08 | 1,829 | 175,334,872 | 1,323,089 |
| 2026-09 | 6,975 | 526,110,912 | 4,013,893 |

**模型别名分布（有效 token 行）**：

| `model_info.model_key` | 行数 |
|---|---:|
| （空） | 5,856 |
| `qmodel_latest` | 4,858 |
| `gfmodel` | 3,762 |
| `gm51model` | 2,633 |
| `qmodel_38max` | 1,579 |
| `lite` | 587 |
| `dmodel` | 442 |
| `dfmodel` | 206 |
| `experts-auto` | 31 |
| `quest-ultimate` | 5 |
| `mmodel` | 4 |

> 别名是 Qoder 内部代号；`aicoding.modelConfigs.cache.*` 只有 Auto/Ultimate/Performance 等产品名，无法可靠映射到别名，因此 v1 原样保留别名，`model_raw` 同值。

**关键语义（实测示例）**：同一 `request_id` 下可有 402 条 assistant 消息（agent loop），每条 `prompt_tokens` 从 103,944 递增到 109,848、`cached_tokens` 同步递增。说明**每条 assistant 消息就是一次真实的模型调用**，应按 `message.id` 逐条计，不能按 `request_id` 合并，也不能只取首条/末条。

**索引情况**：主键 `id`；另有 `(session_id, request_id, gmt_create)` 等联合索引，没有 `gmt_create` 单列索引 → 首次全量扫描，后续靠 mtime 跳过。

### 2.2 数据源 B：Qoder 桌面端活动库（可用，覆盖至今）

**路径**：`/Users/wayne/Library/Application Support/com.qoder.app.stable/main.sqlite`

| 项 | 实测值 |
|---|---|
| 文件大小 | 236,048,384 B |
| 活跃状态 | 主库 mtime 2026-10-30 10:22，`-wal` 持续写入 |
| 表 `chat_session_messages` | 4,001 行（2026-10-30 10:26 快照；库仍在实时写入，行数会随使用增长） |
| 覆盖日期 | 2026-06-01 09:01 ~ 2026-10-30 10:26（本地时区） |
| 会话 | `chat_sessions` 175 行（170 个未归档 + 5 个归档） |

**角色必须回退到 payload**：`role` 列大量为 NULL（导入消息），但 `payload_json` 内有 `"role"` 字段。实测按 `COALESCE(role, json_extract(payload_json,'$.role'))` 统计：

| 月份 | user | assistant | system | 工具调用（parts.type=tool） |
|---|---:|---:|---:|---:|
| 2026-06 | 707 | 695 | 0 | 12,708 |
| 2026-07 | 10 | 10 | 0 | 301 |
| 2026-08 | 170 | 169 | 0 | 2,118 |
| 2026-09 | 859 | 867 | 214 | 10,462 |
| 2026-10 | 132 | 138 | 31 | 2,482 |

**assistant payload 字段**：

```json
{"turnMetrics":{"durationMs":61866,"turnCount":15},
 "parts":[{"type":"tool","tool":{"name":"Bash",...}},{"type":"text",...}]}
```

- `turnCount`：agent 步数（不是用户轮次）。
- `durationMs`：含工具执行的 agent 运行时长（不是墙钟在线时长）。
- 部分历史消息没有 `turnMetrics`（如 2026-10-08~10 的 assistant 行 turns=0、duration=0）→ 必须额外记录“有多少 assistant 行带 metrics”，否则会把“未记录”显示成“0 秒”。

### 2.3 明确不可用的来源（本次复核）

| 来源 | 结论 |
|---|---|
| `~/.qoder/projects/**/*.jsonl` | 6,898 条 assistant 的 4 个 usage 字段**全为 0**（本次复核无一条非 0） |
| `main.sqlite` → `chat_session_context_usage` | 48 行，`totalTokens` 全 0，`tokenCountsAvailable` 全 `false`，`apiUsage` 全空 |
| `chat-session-turn-payload-buffer.sqlite` | 299 条投影中 197 条含 usage 字段但四项全 0，109 条 null |
| `~/.qoder/logs`（478 MB） | 无任何非 0 的 `input_tokens` / `prompt_tokens` / `cache_read` 日志行 |
| `~/.qoder/.models/<account>/catalog-v7` | 加密内容，非 JSON；无可用模型名/价格 |
| `sessionMigration.sqlite` | 仅记录 130 个 quest 会话迁移到 JSONL，无 usage |
| Qoder 云端额度/credits | 本地无真值；不联网、不读凭证 |

### 2.4 结论表

| 需求 | 数据源 | 覆盖 | 可信度 |
|---|---|---|---|
| token 明细 | `local.db` → `chat_message` | 2026-06-01 ~ 2026-09-16 | 高（逐调用） |
| 活动指标 | `main.sqlite` → `chat_session_messages` | 2026-06-01 ~ 今天 | 中（角色需 payload 回退；turnMetrics 有缺失） |
| 当前 token | **无** | 2026-09-16 之后 | 不可得 |
| 额度/credits | **无** | — | 不可得 |

> `local.db` 在 2026-09-16 后停止写入，与 `sessionMigration.sqlite` 的迁移时间（2026-09-16 09:13）吻合：用户从 IDE 迁到了新版桌面端。旧库目前仍在磁盘上，是唯一的历史 token 来源，**设计必须假设它随时可能被清理**（归档机制要覆盖）。

---

## 3. 指标口径

### 3.1 两条轴严格分开

| 轴 | 表 | 命令 | 粒度 | 是否可与 token 相加 |
|---|---|---|---|---|
| token 台账 | `usage_turn`（`source='qoder'`） | `report` / `top` / `html` | 每次调用 | 可与其他源相加（但 Qoder 只覆盖历史） |
| 活动台账 | 新表 `usage_activity` | `activity` / `html` 活动区 | 天 × 项目 | **不可**，不参与成本 |

理由与 DESIGN §3.2 一致：活动指标（会话/提示/工具调用）与 token 不是同一维度；混在一张表会让“总量”失去意义。

### 3.2 Qoder token 口径

行 = `chat_message` 中 `role='assistant'` 且 `token_info` 可解析、`prompt_tokens + completion_tokens > 0`。

| 字段 | 取值 |
|---|---|
| `input` | `max(prompt_tokens - cached_tokens, 0)` |
| `cache_read` | `cached_tokens` |
| `output` | `completion_tokens` |
| `cache_write` | `0`（源无此字段） |
| `reasoning` | `0`（源未拆分） |
| 五项合计 | `prompt_tokens + completion_tokens`（与现有 `Counts.total()` 一致） |
| `model` | `model_info.model_key`；空 → `chat_session.preferred_model_info.preferred_model`；再空 → `unknown` |
| `model_raw` | 同上原始别名 |
| `project` | `chat_session.project_name`；空 → `basename(project_uri)`；再空 → `None` |
| `agent` | `session_type`（`quest` / `agent_sub_*`） |
| `provider` | `qoder` |
| `session` | `session_id` |
| `day` | 本地时区 `date(gmt_create / 1000)` |
| `ts` | `gmt_create / 1000` |
| `key` | `qoder:<message_id>` |
| `turns` | `1`（一条 assistant 消息 = 一次调用） |
| 成本 | `unknown`（订阅制 + 别名无价格；不伪造 0） |

### 3.3 Qoder 活动口径

数据 = `chat_session_messages` LEFT JOIN `chat_sessions`（取 `cwd`）。角色 = `COALESCE(role, payload.role)`。

| 指标 | 定义 |
|---|---|
| `sessions` | 当天有 **user** 消息的 distinct session 数（“活跃会话”） |
| `prompts` | 当天 user 消息数 |
| `assistant_calls` | 当天 assistant 消息数（≈ 模型调用次数；无 token 可证实） |
| `assistant_with_metrics` | 当天带非空 `turnMetrics` 的 assistant 消息数（用于解释 turns/duration 的 0） |
| `turns` | `SUM(payload.turnMetrics.turnCount)`，缺失按 0 |
| `tool_calls` | `payload.parts` 中 `type='tool'` 的个数 |
| `duration_ms` | `SUM(payload.turnMetrics.durationMs)`，缺失按 0 |
| `project` | `basename(chat_sessions.cwd)`；空 → 存 `''`（展示为 `unknown`） |
| `day` | 本地时区 `date(created_at / 1000)` |

v1 **不做** `lines_changed`：只有会话级累计快照（`chat_session_context_usage.sessionStats`），无法按天归属，强行分摊会制造假数据。

### 3.4 覆盖与提示

- 动态计算覆盖率：token 的 `min(day) / max(day)`、活动的 `min(day) / max(day)`。
- 文本报告页脚 / HTML 顶部提示：

  > Qoder：token 覆盖 2026-06-01 ~ 2026-09-16；活动覆盖 2026-06-01 ~ 2026-10-30。活动指标与 token 不可相加；2026-09-16 之后本地无 token 真值。

- 若查询区间内 Qoder token = 0 但有活动：`report` 在 stderr 明确提示“Qoder 本地无 token 数据；活动指标见 usage activity”，不静默显示 0。
- `NO_TOKEN_NOTICE` 中移除 Qoder，只保留 Trae CN / ChatGPT 桌面端；Qoder 用动态提示替代。

---

## 4. 存储设计

### 4.1 token：复用 `usage_turn`（不改表）

- `source='qoder'`，其余字段语义不变。
- 现有 `archived` 机制照常工作：`local.db` 在时 `archived=0`；若旧库被删除/迁移，下一次全量重扫会把历史行标为 `archived=1` 并永久保留。

### 4.2 新增 `usage_activity`（仅日聚合，永久保留）

```sql
CREATE TABLE IF NOT EXISTS usage_activity (
  source                 TEXT NOT NULL,
  day                    TEXT NOT NULL,
  project                TEXT NOT NULL DEFAULT '',
  sessions               INTEGER NOT NULL DEFAULT 0,
  prompts                INTEGER NOT NULL DEFAULT 0,
  assistant_calls        INTEGER NOT NULL DEFAULT 0,
  assistant_with_metrics INTEGER NOT NULL DEFAULT 0,
  turns                  INTEGER NOT NULL DEFAULT 0,
  tool_calls             INTEGER NOT NULL DEFAULT 0,
  duration_ms            INTEGER NOT NULL DEFAULT 0,
  updated_at             REAL NOT NULL,
  PRIMARY KEY (source, day, project)
);
CREATE INDEX IF NOT EXISTS idx_activity_day_source ON usage_activity(day, source);
```

- 与 `usage_daily` 一样是“已聚合数据”，体量极小（365 天 × 项目数），**不参与 `prune`**。
- `project` 用 `''` 而不是 NULL，避免 SQLite 复合主键中 NULL 不唯一的问题；展示时 `''` 映射为 `unknown`。

### 4.3 `source_state` 子源

| 子源 | 含义 | `last_file_mtime` |
|---|---|---|
| `qoder` | token 台账 | `max(mtime(local.db), mtime(local.db-wal))` |
| `qoder.activity` | 活动台账 | `max(mtime(main.sqlite), mtime(main.sqlite-wal))` |

- `source_state` 已按 `source` 主键存储，无需改表；子源名只在本模块内部使用。
- 展示层仍把两者合并为一个 `qoder` 源（报告、chip、覆盖提示）。
- `meta` 增加 `activity_cursor:qoder`（最后处理到的 `updated_at`，epoch ms）。

---

## 5. 采集实现

### 5.1 路径与只读约束

```python
home = source_home()  # 默认 ~，测试用 USAGE_LEDGER_SOURCE_HOME
TOKEN_DB = home + "/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db"
ACTIVITY_DB = home + "/Library/Application Support/com.qoder.app.stable/main.sqlite"
```

- 额外支持 `USAGE_LEDGER_QODER_TOKEN_DB`、`USAGE_LEDGER_QODER_ACTIVITY_DB` 覆盖（测试 / 迁移）。
- 打开方式：`sqlite3.connect("file:<path>?mode=ro", uri=True)`，随后 `PRAGMA query_only=ON`。
- 不复制源库、不写源库、不建临时表。
- 表/列存在性检查失败 → `SourceResult.errors` + `doctor` 提示 schema drift，不崩溃。
- **隐私**：token 查询只 SELECT `id/session_id/gmt_create/model_info/token_info` 与 session 元数据，不碰 `content`；活动查询通过 SQLite JSON 函数在库内提取 `role/turnMetrics/parts.type`，**不把正文取到 Python 内存**，也不写入任何日志。

### 5.2 token 采集算法

```sql
SELECT cm.id, cm.session_id, cm.gmt_create, cm.model_info, cm.token_info,
       cs.project_name, cs.project_uri, cs.session_type, cs.preferred_model_info
FROM chat_message cm
LEFT JOIN chat_session cs ON cs.session_id = cm.session_id
WHERE cm.role = 'assistant'
  AND cm.token_info IS NOT NULL
  AND cm.token_info NOT IN ('', 'null', '{}')
```

1. 逐行 `json.loads`，跳过损坏/全 0 行，计入 `key_kinds["zero-usage"]`。
2. `input = max(prompt - cached, 0)`，`cache_read = cached`，`output = completion`。
3. 模型/项目回退顺序见 §3.2。
4. `result.add(Record(...))`，key = `qoder:<id>`，自动去重。
5. 首次全量（约 19,963 行，预估 1~3s）；之后 mtime 未变直接跳过。mtime 变化时重新全量（48k 行，成本可控，且避免漏掉旧行修订）。
6. 不做时间游标：`gmt_create` 无单列索引，全量比带游标的伪增量更简单、更稳。

### 5.3 活动采集算法（增量定位 + 按天重算）

1. 读游标 `activity_cursor:qoder`（首次为 0）。
2. 增量查询（SQLite JSON1，正文不出库）：

```sql
SELECT m.session_id, m.created_at, m.updated_at,
       COALESCE(m.role, json_extract(m.payload_json, '$.role')) AS role,
       COALESCE(json_extract(m.payload_json, '$.turnMetrics.turnCount'), 0) AS turns,
       COALESCE(json_extract(m.payload_json, '$.turnMetrics.durationMs'), 0) AS duration_ms,
       CASE WHEN json_type(m.payload_json, '$.turnMetrics') IS NOT NULL THEN 1 ELSE 0 END AS has_metrics,
       CASE WHEN json_type(m.payload_json, '$.parts') = 'array'
            THEN (SELECT COUNT(*) FROM json_each(m.payload_json, '$.parts') p
                  WHERE json_extract(p.value, '$.type') = 'tool')
            ELSE 0 END AS tool_calls,
       s.cwd
FROM chat_session_messages m
LEFT JOIN chat_sessions s ON s.session_id = m.session_id
WHERE m.updated_at >= ?          -- cursor - 120000（2 分钟重叠）
```

3. 由命中行得到**受影响的天**，再加上今天与昨天（防止跨天写入/晚到 metrics）。
4. 对受影响天**整天重算**：用一次查询覆盖 `[min(day), max(day)+1)` 区间（单次解析 `payload_json`），Python 按本地日期分桶后按 `(day, project)` 聚合 §3.3 的指标；空白日也纳入删除范围，避免旧行残留。
5. 事务内 `DELETE FROM usage_activity WHERE source='qoder.activity' AND day IN (...)` → `INSERT` 新聚合 → 更新游标，保证幂等。
6. 首次全量：游标 0，一次扫 4,001 行；实测 0.46s（预算 ≤2s），增量 0.13~0.17s（预算 ≤0.5s）。
7. 若 `updated_at` 没有推进但主库 mtime 变了（例如只写了 WAL 元数据），做一次轻量探测：`SELECT MAX(updated_at)`，无变化则不重算。
8. `payload_json` 不保证全部合法：所有 JSON 表达式先用 `json_valid()` 判定；非法行按 `role=unknown / turns=0 / duration=0 / tool_calls=0` 处理，不中断整轮。启动时用 `SELECT json_valid('{}')` 检查 JSON1 是否可用，不可用则活动源标记为 unavailable。

### 5.4 新鲜度与自动刷新

- `source_signatures()` 新增两项：`qoder`、`qoder.activity`（见 §4.3）。
- `_refresh_if_stale()` 按子源判断：只有活动库变化时，只刷新活动，不重扫 1.7GB token 库。
- `--stateless` 同时直读两个库，不写库、不刷新。
- `doctor` 分别显示两个子源的最后 mtime、记录数、覆盖范围。

---

## 6. 展示层

### 6.1 源注册

- `SOURCES` 增加 `qoder`（CLI 的 `--source` 可用）；HTML chip 由数据自动生成。
- 内部子源 `qoder.activity` 不出现在 chip 上，合并进 `qoder`。
- 动态覆盖提示替代原 `NO_TOKEN_NOTICE` 中的 Qoder 文案。

### 6.2 `usage report`（token 台账）

- 行为不变，Qoder 历史 token 正常参与表格、`top`、`export`、`html` 的 token 统计。
- 区间内 Qoder token 为 0 但活动 >0 时，stderr 追加一行：
  `qoder: 本地无该区间 token 数据；活动指标见 usage activity（不可与 token 相加）`
- 页脚动态显示 token/活动覆盖范围（见 §3.4）。

### 6.3 新增 `usage activity`

```
usage activity [--range <a>..<b>] [--since <date>] [--until <date>]
               [--source qoder] [--project <p>]
               [--group-by day,project] [--format table|json|csv]
```

默认列：`day, source, project, sessions, prompts, assistant_calls, turns, tool_calls, duration`
- `duration` 输出为 `HH:MM` 或 `xh ym` 可读格式，JSON 保留 `duration_ms`。
- 页脚提示：活动 ≠ token；`assistant_with_metrics` 覆盖率。
- 该命令只读 `usage_activity`，不触发 token 扫描；但仍走自动刷新（活动库）。

### 6.4 `usage html`

- payload 增加：
  - `activity`: 与 token 行同样按日期/来源/项目过滤后的活动行；
  - `coverage`: `{qoder: {token_since, token_until, activity_since, activity_until}}`。
- 新增“Agent 活动（非 token）”区块，位于 token KPI 下方：
  - 卡片：会话数、提示数、assistant 调用、工具调用、运行时长；
  - 每日柱状图：默认工具调用数（可切换会话/提示）；
  - 表：按天 × 项目。
- 活动区只在当前筛选包含 `qoder` 且区间内有活动数据时显示；不改变现有 token 图表和 chip 交互。
- HTML 的日期上界与“全部”预设取 **token 日与活动日的并集**（活动通常更新到当天），否则活动区会被 token 截止日 2026-09-16 截断；活动区自身仍按所选日期过滤。
- 顶部提示条展示覆盖范围与“不可相加”。

### 6.5 `usage doctor`

新增输出示例：

```
qoder: files=1 records=19956 tokens=2,700,982,026 recent7d=0 status=ok
  note: token 覆盖 2026-06-01..2026-09-16（IDE 旧库，只读）
  note: 活动覆盖 2026-06-01..2026-10-30（桌面端，仅活动指标）
qoder.activity: files=1 days=... sessions=... prompts=... tool_calls=... status=ok
```

- `--probe qoder`：打印模型别名分布（含 `unknown` 占比）、月度活动汇总、`assistant_with_metrics` 覆盖率。
- 警告：
  - token 库不存在；
  - token 库 mtime 距今 >30 天（提示“新版客户端无 token”）；
  - 活动库在更新但连续 3 次无新行（疑似 schema drift）；
  - `usage_activity` 存在但 `assistant_with_metrics = 0`（turnMetrics 全部缺失）。

---

## 7. 改动清单（文件级）

| 文件 | 改动 |
|---|---|
| `src/usage_ledger/models.py` | 新增 `Activity` dataclass；`SourceResult` 增加 `activities` 列表（或独立 `ActivityResult`） |
| `src/usage_ledger/collectors.py` | 新增 `scan_qoder_tokens()`、`scan_qoder_activity()`、路径解析；`source_signatures()` 增加 `qoder` / `qoder.activity`；`collect_all()` 支持子源 |
| `src/usage_ledger/store.py` | `SCHEMA` 增加 `usage_activity`；新增 `upsert_activity()`、`fetch_activity()`、`activity_days()`、`activity_cursor` 读写 |
| `src/usage_ledger/cli.py` | `SOURCES` 增加 `qoder`；新增 `activity` 子命令；`_sync_into` 写入活动；`report` 动态提示；`doctor` 双子源输出；`html` payload 增加 `activity/coverage` |
| `src/usage_ledger/html_report.py` | 活动卡片/柱状图/表格 + 覆盖提示 |
| `tests/test_collectors.py` | token/活动采集单测（临时 SQLite fixture） |
| `tests/test_store.py` | `usage_activity` upsert/重算幂等 |
| `tests/test_cli.py` | `activity` 命令、report 提示、source 过滤 |
| `tests/test_html.py` | payload 含 activity/coverage，页面含提示文案 |
| `tests/fixtures/qoder/`（新增） | 测试用最小 schema 生成器；不提交真实数据 |
| `README.md` | 源表增加 Qoder 双轨说明、命令示例 |
| `pyproject.toml` / `__init__.py` | 版本 0.4.0 |
| `docs/DESIGN.md` §3.3 / `docs/PROBE.md` §1.1 | 更新 Qoder 结论（评审通过后） |

---

## 8. 测试与验收

### 8.1 单元测试（新增约 10 个）

**token**
1. 基础映射：`prompt=1000, cached=800, completion=50` → `input=200, cache_read=800, output=50`，total=1050。
2. `cached > prompt` 时 `input=0`（clamp）。
3. 全 0 / `{}` / 损坏 JSON 跳过，且计入 `zero-usage`。
4. 同 id 重复行只计一次。
5. 模型回退：`model_info` 空 → `preferred_model_info`；再空 → `unknown`。
6. 项目回退：`project_name` 空 → `project_uri` basename。

**活动**
7. 角色回退：`role` 列为 NULL 时从 payload 取 `user/assistant/system`。
8. 一天内 2 个 user、3 个 assistant（其中 2 个带 `turnMetrics`）、4 个 tool part → `sessions=2, prompts=2, assistant_calls=3, assistant_with_metrics=2, tool_calls=4, turns/duration` 正确。
9. 同一天重跑两次 → `usage_activity` 行数不变、数值不翻倍（按天重算幂等）。
10. 只更新一条旧消息的 `updated_at` → 仅对应天被重算。

**signatures / CLI / HTML**
11. `qoder` 与 `qoder.activity` 签名相互独立；只 touch 活动库时只刷新活动。
12. `usage activity --format json` 字段完整；`--source claude` 无活动时不报错（空结果）。
13. `usage html` payload 含 `activity` 与 `coverage`；无活动数据时页面仍正常渲染。
14. `doctor` 输出 token/活动两条覆盖信息。

### 8.2 实测验收（真实库）

- `usage sync --source qoder` → 候选 **19,963** 条，其中 7 条全 0 跳过，入库 **19,956** 条；`SUM(input)+SUM(output)+SUM(cache_read)` = **2,700,982,026**（与独立 SQL 校验一致）。
- `usage activity --since 30d` → 与独立 SQL 的按天聚合逐日一致。
- `usage html` 打开后：Qoder chip 可见；活动区数据与命令输出一致；无 console 错误。
- 连续 sync 两次 → 0 条新增（幂等）。
- 只使用 Qoder 后 touch `main.sqlite` → 只有 `qoder.activity` 刷新；`local.db` 未被重新扫描。

### 8.3 性能预算

| 场景 | 预算 |
|---|---|
| token 首次全量 | ≤3s |
| token mtime 未变 | ~0s（不打开库） |
| 活动增量 | ≤0.5s |
| 活动首次全量 | ≤2s |
| HTML 增量体积 | <20 KB |

---

## 9. 风险与缓解

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | Qoder 内部 schema 变更 | 采集失败/漏数 | 表列存在性检查、错误隔离、doctor 告警、fixture 覆盖；失败不删历史 |
| R2 | `local.db` 被新版清理/迁移 | 失去唯一 token 源 | 首次 sync 立即固化进 `usage_turn`；`archived` 永久保留；doctor 提示 mtime 过旧 |
| R3 | 活动与 token 被误相加 | 总量虚高、口径失真 | 分表、分命令、页面/页脚显式“不可相加”；活动不参与成本 |
| R4 | 读取payload 被视为侵犯隐私 | 信任问题 | 只用 SQLite JSON 函数在库内提取元数据，不取正文到 Python、不落库、不写日志；文档写明 |
| R5 | 模型别名不可读 | 报表模型列难懂 | v1 保留别名 + `unknown` 显式标注；别名映射表作为后续可选项 |
| R6 | `turnMetrics` 缺失 | turns/duration 偏低 | 记录 `assistant_with_metrics` 并展示覆盖率；0 不代表没使用 |
| R7 | 1.65GB 旧库读取慢 | 首次 sync 慢 | 只 SELECT 必要列、mtime 跳过、无内容读取；首次预算 ≤3s |
| R8 | 时区/跨天 | 日期归属错误 | 统一 `datetime.fromtimestamp(ms/1000)` 本地时区，与现有源一致 |
| R9 | 活动库 `updated_at` 不推进 | 活动漏记 | 每天重算今天/昨天；mtime 变化时探测 `MAX(updated_at)` |

---

## 10. 发布与回滚

- 版本：**0.4.0**（新增源 + 新表 + 新命令，向后兼容）。
- 迁移：`CREATE TABLE IF NOT EXISTS`，无破坏性变更；老库打开即自动建表。
- 上线步骤：
  1. `usage sync --source qoder`（首次固化 token 历史 + 活动）；
  2. `usage doctor`（核对覆盖范围）；
  3. `usage html`（人工验收活动区）；
  4. 常规 report 不受影响。
- 回滚：从 `SOURCES` 移除 `qoder` 即可停止采集；已写入数据可保留（不影响其他源），必要时手工
  `DELETE FROM usage_turn WHERE source='qoder'; DELETE FROM usage_activity WHERE source='qoder';`。
- 更新 `README`、`DESIGN.md` §3.3、`PROBE.md` §1.1 的 Qoder 结论。

---

## 11. 待拍板（请审核时确认）

1. **是否接受“双轨”方案**：token 历史（2026-06-01~09-16）+ 活动指标（至今），分表展示？
   - 若只要 token：Qoder 只有 9 月 16 日前的数据，之后仍显示为空。
   - 若不要活动指标：本设计可裁剪掉 `usage_activity` / `activity` 命令 / HTML 活动区，只保留 token 采集。
2. **活动指标是否作为独立 `usage activity` 命令**（推荐），还是并入 `usage report` 文本输出？
3. **HTML 活动区**：先做“卡片 + 表格 + 每日柱状图”（推荐），还是只要卡片/表格？
4. **模型别名**：v1 原样显示 `gfmodel` 等（推荐，无法可靠映射），还是现在补一张手工映射表？
5. **活动采集读取 payload 元数据**：通过 SQLite JSON 函数提取 `role` / `turnMetrics` / `parts.type`，不落正文——是否接受？若要求完全不读 payload，则导入消息的角色和工具调用无法统计，活动指标基本不可用。

> 审核通过后按 §7 的文件清单实施；未通过前不写实现代码。
