# CHG-0016 接入 Google Antigravity 用量（IDE / agy 双目录合并）

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage report` / `usage html` / `src/usage_ledger/collectors.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../../product-specs/REQ-0001-usage-ledger.md)
关联：探针脚本 [scripts/probe_antigravity.py](../../../scripts/probe_antigravity.py)

## 1. 摘要

把 Google Antigravity 接成第 8 个采集源。Antigravity 的 IDE 与 `agy` CLI 是同一个二进制的两种运行方式，但**默认写两个互不复用的 app data dir**；本 CHG 用单个源 `antigravity` 同时扫这两个目录，靠 `(app_data_dir, 会话, step_index)` 去重合并，用 `Record.agent` 保留 IDE / CLI 拆分能力。逐 turn token 存在 `brain/<会话>/.system_generated/logs/transcript_full.jsonl`；额度在本地**没有落盘**，不在本次范围内。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：REQ-0001 G1（在一个视图里回答"每个平台、每个模型的用量"）。
- 触发原因：用户 2026-11-20 要求接入 Antigravity，并先确认 IDE 与 `agy` 的用量是否共用存储。
- 证据：以下全部来自本机实测，可用 `python3 scripts/probe_antigravity.py` 复现（只读，不联网）。

### 2.1 IDE 与 agy 不共用目录

IDE（`/Applications/Antigravity IDE.app`，product 1.107.0 / bundle 2.7.0）自身没有 agent 运行时。它的 `google.google-antigravity` 扩展拉起的是同一个 `agy` 二进制：

```
[LAUNCH] Spawning /Users/wayne/.gemini/bin/agy (v1.5.13) --hub --hub-port=55552 --app_data_dir=antigravity
```

（出处：`~/Library/Application Support/Antigravity IDE/logs/20261120T090124/window1/exthost/output_logging_20261120T090126/2-Antigravity.log`）

| 前端 | 可执行体 | app data dir |
|---|---|---|
| Antigravity IDE（`/Applications/Antigravity IDE.app`，product 1.107.0 / bundle 2.7.0） | 扩展拉起 `agy --hub --app_data_dir=antigravity` | `~/.gemini/antigravity` |
| Antigravity 桌面 hub（`/Applications/Antigravity.app`，2.33.0） | 自带 `language_server --standalone`，进程句柄实测在 `~/.gemini/antigravity` | `~/.gemini/antigravity`（与上同一目录） |
| `agy` CLI（用户在终端直接跑） | `agy` 默认 `--cli_dir_name=antigravity-cli` | `~/.gemini/antigravity-cli` |

`~/.gemini/antigravity-ide/` 是遗留空目录（只有 `.ide_migration` 标记，`brain/`、`conversations/` 全空），**不采集**。

结论：两者**不共用**，但走同一套代码、同一套落盘格式，所以合并成本低。

### 2.2 用量数据的位置与格式

```
<app_data_dir>/brain/<conversationId>/.system_generated/logs/transcript_full.jsonl
```

每个 JSON 对象是一个 step，只有 `source == "MODEL"` 的步骤带 token：

```json
{"step_index":3,"type":"PLANNER_RESPONSE","source":"MODEL","status":"DONE",
 "model":"gemini-3.8-flash-high","input_tokens":2471,"output_tokens":271,
 "cache_read_tokens":13575,"created_at":"2026-11-20T01:02:06Z"}
```

会话标题与项目要从同目录的 `conversation_summaries.db`（表 `conversation_summaries`，字段 `workspace_uris`）取；`conversations/<id>.db` 里只有步骤二进制，**没有 token**。

### 2.3 探针实测结论

| # | 结论 | 实测值 |
|---|---|---|
| 1 | 两个 root 都有数据，格式一致 | ide 129 文件 / 15,480 step；cli 3 文件 / 339 step |
| 2 | 只有 `MODEL` step 可能带 token，且绝大多数没有 | `MODEL` 共 14,468，其中 **14,451 条无 token（99.9%）** |
| 3 | `input_tokens` **不含** `cache_read_tokens`，可直接映射 `input` / `cache_read` | 17 条带 token 的 step 中，13 条 `cache_read > input` |
| 4 | 没有 `cache_write` 字段 | 17/17 无该键 → 只能记 0 |
| 5 | `chunks/transcript_full/*.jsonl` 与 `transcript_full.jsonl` 内容一致 | 一致 5 / 不一致 0 / 无 chunks 目录 127；main+chunks 合并后 `step_index` 冲突 0 |
| 6 | 两个 root 的会话 ID 不重叠；单文件内 `step_index` 唯一 | 重叠 0；重复 0 处 |
| 7 | 转录**不是严格 JSONL**，存在游离片段 | 4 个文件出现独立成行的 `}]}` 之类片段 |

按 `(app_data_dir, 会话, step_index)` 合并后得 17 条，与原始带 token 的 17 条一致——**去重不会丢数据，也不会重复计数**。

### 2.4 额度（quota）本地不存在

翻遍 `antigravity_state.pbtxt`、`jetski_state.pbtxt`、IDE 的 `state.vscdb` / `storage.json`、`app_storage.json`，都没有额度落盘。`agy` 二进制里的 `RetrieveUserQuotaSummary` / `remaining_credits` / `used_percentage` 表明额度是**每次实时向服务端拉**，只在内存。唯一本机入口是语言服务器的 `/exa.language_server_pb.LanguageServerService/GetUserStatus`（需 `X-Codeium-Csrf-Token`，端口随机）。

### 2.5 不做的后果

Antigravity 上的 token 消耗在报表里完全缺失；用户无法回答"Antigravity 花了多少"。

## 3. 行为 / AC delta

- 新增：**R46**（见下）。
- 修改：**R1** 的源清单由 7 个增至 8 个，增加 `antigravity`。
- 删除：无。

**R46**：When Antigravity data is present under `~/.gemini/antigravity` (IDE / hub) or `~/.gemini/antigravity-cli` (CLI), the system shall read `brain/<conversationId>/.system_generated/logs/transcript_full.jsonl` from both roots, emit one token record per step whose `source` is `MODEL` and which carries `input_tokens`, map `input_tokens`/`cache_read_tokens`/`output_tokens` to `input`/`cache_read`/`output` with `cache_write = 0` and `reasoning = 0`, attribute it to the local day of `created_at`, use `antigravity:<app_data_dir>:<conversationId>:<step_index>` as the dedup key, set `Record.agent` to `ide` or `cli`, take the project from the matching root's `conversation_summaries.db` `workspace_uris` basename with `default-cli-project` as fallback, parse transcripts with a streaming JSON decoder that resyncs past orphan fragments and drops objects whose `step_index` is not an integer, silently skip `MODEL` steps without token fields, tolerate missing roots/files without failing the run, and expose the merged rows under the single source `antigravity` while keeping the IDE/CLI split available through `Record.agent`.

预期行为补充（R46 的可观察结果）：

- `usage report` / `usage html` 默认把两个目录合成一个 `antigravity` 行，不按 IDE/CLI 拆两列。
- `Record.agent` 取 `ide` / `cli`，报表侧可按 agent 细分，但默认不拆。
- `usage doctor` 报告 `antigravity` 的两个 root 是否存在、转录文件数、带 token 的 step 数与覆盖日期。
- 源签名取两个 root 下所有 `transcript_full.jsonl` 的最大 mtime；任一目录有新数据即触发增量同步（R3）。
- 重复跑 `sync` / `backfill` 不产生重复行（R4）；坏行只计数不中断（R17）。

## 4. 影响范围与非目标

只读契约：`_antigravity_projects` 走既有 `_open_ro`（`mode=ro` + `query_only=ON` + 2s 超时），与其它 SQLite 采集器一致，不写回主库。注意 WAL 模式库即使只读打开，SQLite 仍会在源目录创建空的 `-shm` / `-wal` 边文件（实测 `-wal` 0 字节、`-shm` 32KB，主库 mtime 不变）；这是既有 Qoder 采集同样的行为，不算写库。

受影响：

- `src/usage_ledger/collectors.py`：新增 `scan_antigravity`，注册进 `collect_all` 与 `source_signatures`。
- `src/usage_ledger/cli.py`：`SOURCES` 增加 `antigravity`。
- `src/usage_ledger/html_report.py`：`agentKind` 把 `antigravity` 归为 token 轨。
- `README.md` 覆盖能力表、`ARCHITECTURE.md` 数据源契约、`REQ-0001` §3.2 与 §5.1。
- 测试：`tests/test_collectors.py` 新增用例，`tests/ac_map.json` 增加 R46 映射。

本次明确不做：

- 额度 / credits 轨（本地无数据，且需要访问随机端口的本机服务，见 §7）。
- 解析 `conversations/<id>.db` 里的步骤二进制。
- 任何联网行为。
- 历史回填——见 §7，本地没有历史 token。

## 5. 验证与观测

探针（已完成，只读）：

```bash
python3 scripts/probe_antigravity.py
```

自动化测试（已执行）：

- `AntigravityTest`（10 例）：字段映射、`input` 不含 cache、无 `cache_write` 记 0、`source != MODEL` 跳过、无 token 的 MODEL step 静默跳过、游离片段后仍能读到后续 step、`step_index` 非整数丢弃、`chunks/` 不重复计数、两个 root 合并去重、缺失 root 降级、零 token 与非法时间戳跳过、摘要库损坏降级。
- `AntigravitySignatureTest`（2 例）：任一 root 的 `transcript_full.jsonl` 或 `chunks/*.jsonl` mtime 变化会推进 `antigravity` 签名。
- `AntigravityCliTest`（4 例）：`backfill` → `report` 与 `--stateless` 一致；重复 `backfill` 幂等；IDE 与 CLI 合成单一 `antigravity` 源；`doctor` 报告该源。

结果：

- `python3 -m unittest discover -s tests -t .` → **299 tests / 0 failures / 0 errors / 0 skips**（基线 284）。
- `scripts/check_test_policy.py` 通过；`scripts/check_ac_map.py` → 46 criteria / 113 mapped identifiers；覆盖率 **93.3%**（collectors 94.7%）。

手工验证（本机实测，2026-11-20）：

- `usage backfill --source antigravity` → `17 records, 308,611 tokens, files=132, errors=0`。
  308,611 = input 87,489 + output 8,737 + cache_read 212,385，**与探针 §4 完全一致**。
- `usage doctor` → `antigravity: files=132 records=17 tokens=308,611 recent7d=17 errors=0 status=ok`。
- `usage html --source antigravity --offline` → `rows=2 records=17 tokens=308,611`；
  payload 的 `agents` 含 `"antigravity":"token"`，与 qoder / trae-cn 的 `credits` 分轨。

## 6. 回滚方案

- 回滚方式：把 `antigravity` 从 `SOURCES`、`collect_all`、`source_signatures`、`agentKind` 四处摘除即可；SQLite 里 `source='antigravity'` 的历史行保留但不再展示，`prune` 会按既有策略处理。
- 数据/配置兼容：无 schema 迁移；`Record.agent` 是既有列。
- 回滚验证：`usage report` 回到 7 个源；`usage doctor` 不再报告 `antigravity`。

## 7. 风险与未决问题

| 风险 / 未决 | 影响 | 处理 |
|---|---|---|
| **本地只有 2026-11-20 起的 17 条记录**（4 个会话），14,451 条 MODEL step 无 token | 报表在 2026-11-20 之前为空，容易被误读为"没用过" | CHG 与 README 明确写"记账上线前的用量本地不可得"；`doctor` 报告覆盖日期区间 |
| 转录存在游离片段，且未来可能出现跨物理行的对象 | 按行解析会丢 step | 流式 `raw_decode` + 失败重同步 + `step_index` 形状校验，已有 4 例实测 |
| 模型名是友好名（`gemini-3.8-flash-high`） | LiteLLM 快照基本查不到，`cost_equiv_usd` 覆盖率低 | 与 PROBE.md §1.2 同类问题；本次不建别名表，`cost_source` 记 `unknown` |
| `chunks/` 与 `transcript_full.jsonl` 当前一致，但若将来轮转 | 只读 `transcript_full.jsonl` 可能漏历史 | 采集器**同时读**两处并按 `step_index` 去重（已实测 0 冲突），代价是每会话多读几个小文件 |
| `agy` 仍在调整目录布局（changelog 提到 `hooks.json` 迁到共享 `~/.gemini/config/`） | 路径可能再变 | 两个 root 写成模块级常量，便于一处修改 |
| 额度只能靠本机随机端口的 `GetUserStatus`，且粒度 20% | 无法做 credits 真值 | **本次不做**，留待单独 CHG；若做，须照 R11 的显式 opt-in 模式 |

已决（2026-11-20 评审）：

1. 采用单源 `antigravity` + `Record.agent` 区分 IDE / CLI。合并展示默认成立，报表不新增卡片。
2. `default-cli-project` 作为项目名兜底，可接受。

剩余风险（不改设计）：

- 本机 2026-11-20 前的用量本地不可得；`agy` 仍在调整目录布局，两个 root 已写成模块级常量 `ANTIGRAVITY_AGENTS`。

## 8. 关联与证据

- 探针脚本：[scripts/probe_antigravity.py](../../../scripts/probe_antigravity.py)
- 探针输出（本机，2026-11-20）：ide 129 文件 / 15,480 step，cli 3 文件 / 339 step；带 token 17 条（ide 15 / cli 2）；合计 input 87,489 / output 8,737 / cache_read 212,385；覆盖 1 天。
- 基线：main `a81870f`。
- issue/PR：无。

## 9. 变更记录

| 状态 | 操作人 | 证据/链接 |
|---|---|---|
| 提议 | wayne | 本 CHG + 探针脚本；等待评审（含 §7 两个未决问题） |
| 就绪 | wayne | 2026-11-20 评审通过：单源 + `Record.agent`，`default-cli-project` 兜底 |
| 已验证 | wayne | 299 tests / 0 failures；覆盖率 93.3%；本机实测 17 records / 308,611 tokens 与探针一致；commit 见 PR |
| 已验证 | wayne | 评审修复：`_antigravity_projects` 改用 `_open_ro`（只读契约）、README 单测数校正、R46 措辞校正、`step_index` 原地补全与 chunks 签名两个缺口；299 tests / 0 failures、覆盖率 93.3%、AC map 46/113 |