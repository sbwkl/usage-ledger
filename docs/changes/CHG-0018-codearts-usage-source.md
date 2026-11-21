# CHG-0018 接入 CodeArts（码道）用量（codearts-data opencode.db，复用 SQLite agent adapter）

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage report` / `usage html` / `usage doctor` / `src/usage_ledger/collectors.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：探针脚本 [scripts/probe_codearts.py](../../scripts/probe_codearts.py)

> ID 说明：CHG-0017 / R47 已由 CHG-0017（MiniMax Code，已合入 main）占用，
> 本变更按递增取 CHG-0018 / R48。分支基于 pre-minimax 的 main（`505ef0b`）开发，
> 2026-11-20 已 merge 最新 main（`07224fd`）并解决全部 12 处冲突（见 §7）。

## 1. 摘要

把 CodeArts（码道，华为云 CodeArts Agent）接成第 10 个采集源。CodeArts 把会话数据落盘在
`~/.codeartsdoer/codearts-data/opencode.db`，是 **OpenCode 旧版（legacy）schema**：
`message` 表的 `data` JSON 里带 `role` / `modelID` / `providerID` / `tokens` / `path.cwd`。
该形状与既有共享 adapter `scan_sqlite_agent` 的 legacy 分支完全一致，因此本 CHG 复用该
adapter，只新增路径与注册，不新增解析逻辑。额度（credits）本地**没有落盘**，不在本次范围内。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：REQ-0001 G1（在一个视图里回答"每个平台、每个模型的用量"）。
- 触发原因：用户 2026-11-20 要求给 usage-ledger 接入 CodeArts（码道）的用量统计。
- 证据：以下全部来自本机实测，可用 `python3 scripts/probe_codearts.py` 复现（只读，不联网）。

### 2.1 用量数据的位置与格式

```
~/.codeartsdoer/codearts-data/opencode.db   # SQLite，WAL 模式
```

`message` 表（legacy OpenCode schema，无 `session_message` 表）：

```sql
CREATE TABLE `message` (
  `id` text PRIMARY KEY,
  `session_id` text NOT NULL,
  `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL,
  `data` text NOT NULL, ...
)
```

`data` JSON 中 assistant 消息的形状（实测样例）：

```json
{"role": "assistant",
 "modelID": "glm-5.3-flash", "providerID": "inferhub-provider",
 "tokens": {"total": 18689, "input": 18052, "output": 334, "reasoning": 303,
            "cache": {"write": 0, "read": 0},
            "context": {"tools": 0, "mcp": 0, "messages": 948,
                        "skills": 0, "system_prompts": 17741}},
 "time": {"created": 1795154953135, "completed": 1795155093770},
 "path": {"cwd": "/Users/wayne/workspace/playground", "root": "/"}}
```

### 2.2 探针实测结论（2026-11-20，冻结快照）

> 下表取自**冻结快照**（用 `sqlite3 .backup` 对活库做一致性快照后探针），
> 避免会话边跑边长导致前后两次取值不可比。快照时刻 28 条 assistant 消息。

| # | 结论 | 实测值 |
|---|---|---|
| 1 | schema 是 legacy `message` 表（`role` 在 `data` JSON 内），无 `session_message` 表 | 30 行 = assistant 28 + user 2 |
| 2 | `input` **不含 cache read**（非重叠口径） | `total == input + output + cache.read + reasoning` 成立 27/27（有完整字段的行） |
| 3 | `cache.write` 恒为 0 | 28 条全部为 0 |
| 4 | 模型 / provider 稳定 | `modelID=glm-5.3-flash`、`providerID=inferhub-provider`（28/28） |
| 5 | `message.id` 全局唯一，可作去重键 | 重复 0 处 |
| 6 | `path.cwd` 全部存在 | 28/28 可取项目 basename（`playground`） |
| 7 | 1 条 assistant 消息 `tokens.total` 缺失、其余全 0 | 属中断/失败响应，字段全 0，采集端按 zero-usage 跳过，不伪造记录 |

汇总口径实测（28 条 assistant，含 1 条全 0）：
input 277,622 / output 6,522 / cache_read 1,329,152 / cache_write 0 / reasoning 5,732 /
total 1,619,028；全部归属 2026-11-20（本机本地日），2 个会话，项目均为 `playground`。

### 2.3 采集口径

- 与 opencode / kilo 同一 adapter `scan_sqlite_agent`：legacy 分支过滤
  `data.role == 'assistant'`，取 `tokens.input / output / cache.read / cache.write /
  reasoning`，`model ← modelID`，`provider ← providerID`，`project ← basename(path.cwd)`，
  `ts ← time_created`（毫秒 → 本地日）。
- 去重键：`codearts:<message.id>`（adapter 既有键格式 `<source>:<message.id>`）。
- **不取 `tokens.total`**：该字段已含 cache read 与 reasoning，与台账的互斥字段口径不同，
  沿用 opencode 的映射规则，不引入第二套口径。

### 2.4 项目维度来源

`message.data.path.cwd` 实测 28/28 存在；adapter 对 legacy 行不 JOIN session 表，
cwd 缺失时记录为无项目（与 opencode legacy 行为一致），本次不改 adapter。

### 2.5 额度（credits）本地不存在

`opencode.db` 没有额度 / 配额 / 计费表；CodeArts 为订阅制，额度在服务端，本地不可得，
**本次不采集**，归入 token 真值轨。

### 2.6 不做的后果

CodeArts 的 token 消耗在报表里完全缺失；用户无法回答"码道花了多少"。

## 3. 行为 / AC delta

- 新增：**R48**（见下）。
- 修改：**R1** 的源清单由 9 个增至 10 个，增加 `codearts`。
- 删除：无。

**R48**：When CodeArts (码道) session data is present under
`~/.codeartsdoer/codearts-data/opencode.db`, the system shall read each `message` row whose
`data.role` is `assistant` via the shared legacy-OpenCode adapter, map `data.tokens.input` /
`output` / `cache.read` / `cache.write` / `reasoning` to `input` / `output` / `cache_read` /
`cache_write` / `reasoning` without reading `tokens.total`, attribute each record to the local
day of `time_created` (milliseconds), deduplicate by `message.id` and key records
`codearts:<message.id>`, take the model from `data.modelID` and the provider from
`data.providerID`, take the project from `data.path.cwd` basename (no project when absent),
skip assistant messages without tokens or with zero token counts without fabricating 0,
skip rows whose `data` JSON is unparsable while counting them instead of failing the run,
degrade gracefully when the database is missing or unreadable, and expose the rows under the
single source `codearts`.

预期行为补充（R48 的可观察结果）：

- `usage report` / `usage html` 把 CodeArts（码道）归入 **token 真值轨**（`AGENT_KINDS` 为
  `token`），显示名 `CodeArts（码道）`，与 Qoder / Trae CN 的 credits 轨分开展示，任何两轨
  不相加。
- `usage doctor` 报告 `codearts` 源的状态、记录数、token 数与覆盖日期。
- 源签名取 `opencode.db` 与 `-wal` 的最大 mtime；新消息落库即触发增量同步（R3）。
- 重复跑 `sync` / `backfill` 不产生重复行（R4）；坏行只计数不中断（R17）。
- WAL 活库走既有 `mode=ro` 只读打开；打开失败降级记 error，不让整个同步失败。

## 4. 影响范围与非目标

只读契约：复用 `scan_sqlite_agent` 的 `file:...?mode=ro` 只读打开；不写回源库或源目录。
与 opencode / kilo 一样，WAL 模式活库在只读打开时 SQLite 可能创建空的 `-shm` / `-wal`
边文件，这是既有采集器同样行为，不算写库。

受影响：

- `src/usage_ledger/collectors.py`：新增 `codearts_db()` 路径 helper 与 `scan_codearts()`，
  注册进 `collect_all` 与 `source_signatures`（与 kilo 同款两行注册）。
- `src/usage_ledger/cli.py`：`SOURCES` 增加 `codearts`。
- `src/usage_ledger/html_report.py`：`AGENT_KINDS` 把 `codearts` 归为 token 轨，补颜色 /
  顺序 / 显示名 `CodeArts（码道）`。
- `src/usage_ledger/__init__.py` + `pyproject.toml`：版本号 → `0.9.0`
  （`0.8.0` 已被已合入 main 的 CHG-0017（minimax）占用；main 上 `pyproject=0.8.0` 与
  `__init__` 的历史漂移随本次一并对齐到 0.9.0）。
- `README.md` 覆盖能力表与状态行、`ARCHITECTURE.md` 数据源契约、`REQ-0001` §3.2 与
  §5.4、`docs/design-docs/index.md` 可用 ID 行。
- 测试：`tests/test_collectors.py` / `tests/test_cli.py` / `tests/test_html.py` 新增用例，
  `tests/ac_map.json` 增加 R48 映射；新增探针 `scripts/probe_codearts.py`。

本次明确不做：

- 额度 / credits 轨（本地无落盘，见 §2.5）。
- 修改共享 adapter（opencode / kilo / codearts 三源共用，行为保持一致）。
- `session.directory` 回退补项目（adapter legacy 分支既有口径，cwd 实测恒在，无必要）。
- 子 Agent / 后台任务独立归属；任何联网行为。

## 5. 验证与观测

探针（只读）：

```bash
python3 scripts/probe_codearts.py
```

自动化测试（计划 / 已执行）：

- `CodeArtsCollectorTest`：字段映射（input/output/cache_read/cache_write/reasoning）、
  模型 / provider 提取、`codearts:<id>` 去重键、无 tokens 的 assistant 跳过、
  零 token 跳过、坏 data JSON 只计数不中断、DB 缺失时源不可用。
- `CodeArtsSignatureTest`：`opencode.db` / `-wal` mtime 变化会推进 `codearts` 签名。
- `CodeArtsCliTest`：`backfill` → `report` 与 `--stateless` 一致；重复 `backfill` 幂等；
  新增消息触发自动增量同步；`doctor` 报告该源。
- `HtmlRenderTest.test_codearts_is_classified_as_token`：HTML 侧 `codearts` 归 token 轨。

结果：

- `python3 -m unittest discover -s tests -t .` → **325 tests / 0 failures / 0 errors / 0 skips**（merge main 后基线 314）。
- `scripts/check_test_policy.py` 通过（325 tests，fast suite 1.91s / 预算 5.0s）。
- `scripts/check_ac_map.py` → **48 criteria / 139 mapped identifiers**（merge main 后基线 47 / 124）。
- `scripts/check_coverage.py` 通过 → 总覆盖率 **93.4%**（collectors 95.3%、cli 93.6%、
  store 96.7%、scheduler 98.2%），均高于阈值且相对基线 80.9% 只升不降。

手工验证（本机实测，2026-11-20；**冻结快照** = 用 `sqlite3 .backup` 对活库做一致性快照
后采集，避免会话边跑边长导致两次取值不可比）：

- 探针 `python3 scripts/probe_codearts.py /tmp/codearts-snap-fixed/opencode.db`（冻结快照）：
  assistant 28 条（1 条中断响应全 0 跳过），27/27 完整字段行满足
  `total == input+output+cache.read+reasoning`，重复 `message.id` 0 处，
  cwd 28/28；汇总 input 277,622 / output 6,522 / cache_read 1,329,152 /
  cache_write 0 / reasoning 5,732，与 §2.2 逐项一致。
- 实时目录（会话仍在增长）：`usage backfill --source codearts`（临时 DB）→
  `80 records, 5,830,738 tokens, files=1, errors=0, status=ok`。
- `usage report --source codearts`（读库）与 `usage --stateless report`（直读源）输出
  **完全一致**（input 358,414 / output 28,600 / cache_read 5,427,840 / turns 80）。
- `usage report --source codearts --group-by project` → 项目列 `playground`，
  证明 `path.cwd` 项目映射生效。
- `usage doctor` → `codearts: files=1 records=81 tokens=5,942,596 recent7d=81
  errors=0 status=ok`（doctor 运行时比 backfill 多了 1 条新消息，属活库正常增长）。
- `usage html --source codearts --offline` → payload 的 `agents` 含
  `"codearts":"token"`，与 qoder / trae-cn 的 `credits` 分轨。

## 6. 回滚方案

- 回滚方式：把 `codearts` 从 `SOURCES`、`collect_all`、`source_signatures`、`AGENT_KINDS`
  四处摘除即可；SQLite 里 `source='codearts'` 的历史行保留但不再展示，`prune` 会按既有
  策略处理。
- 数据 / 配置兼容：无 schema 迁移；`Record` 字段全部是既有列。
- 回滚验证：`usage report` 回到 8 个源；`usage doctor` 不再报告 `codearts`。

## 7. 风险与未决问题

| 风险 / 未决 | 影响 | 处理 |
|---|---|---|
| **本机只有 2026-11-20 起的会话**（CodeArts 当天才开始使用） | 报表在 2026-11-20 之前为空，容易被误读为"没用过" | CHG 与 README 明确写"接入前的用量本地不可得"；`doctor` 报告覆盖日期区间 |
| 源库是**运行中 Agent** 的活 WAL 库 | 只读打开可能产生边文件；写入瞬间快照可能不一致 | 走既有 `mode=ro`；本机探针曾出现裸 `cp` 复制打不开的情况，探针脚本改用 `sqlite3 .backup` 做一致性快照；采集端逐行解析 + 坏行计数，不整跑失败 |
| CodeArts 升级换用新版 `session_message` schema | 采集不到新消息 | adapter 已兼容新版 schema（opencode 同款），升级后无需改代码；跟踪项记录在 ARCHITECTURE 已知问题 |
| `tokens.total` 与互斥字段口径不同 | 若误读 total 会重复计 cache | 明确不读 total（§2.3），沿用 opencode 口径 |
| 模型名 `glm-5.3-flash` 无价格条目 | `cost_equiv_usd` 为 unknown | 与 Antigravity 同类问题；本次不建别名表，`cost_source` 记 `unknown` |
| 与 CHG-0017（minimax）的合并 | **实际发生 12 个文件冲突**（README、ARCHITECTURE、REQ-0001、pyproject、`__init__`、cli、collectors、html_report、ac_map、test_cli、test_collectors、docs/README），本 CHG 初版"纯追加行，机械合并即可"的判断不成立 | 已在特性分支 merge main（`07224fd`）逐一取并集解决（源注册 / KNOWN_ORDER / R47+R48 / 测试类共存 / 版本 0.9.0），并按 post-minimax 世界重算全部计数后重跑四门禁 |

## 8. 关联与证据

- 探针脚本：[scripts/probe_codearts.py](../../scripts/probe_codearts.py)
- 探针输出（本机，2026-11-20，冻结快照）：28 条 assistant；27/27 完整字段行满足
  `total == input + output + cache.read + reasoning`；重复 `message.id` 0 处；
  汇总 input 277,622 / output 6,522 / cache_read 1,329,152 / cache_write 0 /
  reasoning 5,732；项目 `playground`（cwd 28/28）。
- 开发基线：main `505ef0b`；已 merge 最新 main `07224fd`（含 CHG-0017 minimax）。
- issue / PR：无。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne | 本 CHG + 探针脚本 |
| 就绪 | wayne | 2026-11-20 实现完成：单源 `codearts`、token 真值轨、复用 `scan_sqlite_agent` |
| 已验证 | wayne | merge main 后 325 tests / 0 failures；覆盖率 93.4%；AC map 48/139；本机冻结快照实测与探针逐项一致，实时目录 80 records / 5,830,738 tokens，读库与 `--stateless` 输出一致 |