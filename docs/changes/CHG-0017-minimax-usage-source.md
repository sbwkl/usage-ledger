# CHG-0017 接入 MiniMax Code 用量（会话 messages.jsonl + 运行库项目映射）

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage report` / `usage html` / `usage doctor` / `src/usage_ledger/collectors.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：探针脚本 [scripts/probe_minimax.py](../../scripts/probe_minimax.py)

## 1. 摘要

把 MiniMax Code 接成第 9 个采集源。MiniMax Code 把每次模型响应落盘在会话目录
`~/.minimax/v2/sessions/<YYYY>/<MM>/<DD>/<session>/messages.jsonl`，assistant 消息自带
`usage`（input / output / cacheRead / cacheWrite / totalTokens）与 `model`；本 CHG 逐条读取
这些字段产出 token 真值，并用运行库 `runtime-state.sqlite` 的 `local_runtime_sessions
.workspace_dir` 补上项目维度。额度（credits）在本地**没有落盘**，不在本次范围内。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：REQ-0001 G1（在一个视图里回答"每个平台、每个模型的用量"）。
- 触发原因：用户 2026-11-20 要求给 usage-ledger 增加 MiniMax 的用量统计。
- 证据：以下全部来自本机实测，可用 `python3 scripts/probe_minimax.py` 复现（只读，不联网）。

### 2.1 用量数据的位置与格式

```
~/.minimax/v2/sessions/2026/11/20/05-47-46-783-session_<base64url(sessionId)>/
├── manifest.json     # sessionId / createdAtMs / layout=v2-final-dated-session
├── messages.jsonl    # 会话消息（含 assistant 的 usage）
└── llm-call.json
```

`messages.jsonl` 每行一个对象，外层是 `{message_id, turn_id, message}`，`message` 里才有
`role` / `model` / `provider` / `usage` / `timestamp`：

```json
{"message_id":"msg-ldaHe2U9dLUgZMMK5uJ3-F90-x6MTvObfDQsdrI1Wbc",
 "turn_id":"f155eb0c-8330-42d6-8d09-b9c8f5a32d11",
 "message":{"role":"assistant","api":"anthropic-messages","provider":"minimax",
   "model":"MiniMax-M3.1-Flash",
   "usage":{"input":31677,"output":131,"cacheRead":1152,"cacheWrite":0,
            "totalTokens":32960,
            "cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0,"total":0}},
   "stopReason":"toolUse","timestamp":1795153668789,
   "responseId":"074f1205d85206fb49e2e9fdf42a20ec"}}
```

### 2.2 探针实测结论（2026-11-20，冻结快照）

> 下表取自**冻结快照**（把 `~/.minimax` 复制到临时目录后再跑探针），
> 避免会话边跑边长导致前后两次取值不可比。

| # | 结论 | 实测值 |
|---|---|---|
| 1 | assistant 消息**全部**带 `usage`，形状完全一致 | 83/83 条均为 `{cacheRead, cacheWrite, cost, input, output, totalTokens}` |
| 2 | **`input` 已排除 cache read**（非重叠口径） | `totalTokens == input + output + cacheRead` 成立 83/83，失败 0 |
| 3 | `cacheWrite` 恒为 0（源未提供写入缓存计数） | 83 条全部为 0 |
| 4 | 模型 / provider 稳定 | `model=MiniMax-M3.1-Flash`、`provider=minimax`（83/83） |
| 5 | `(session_id, message_id)` 唯一，可作去重键 | 重复 0 处 |
| 6 | 会话目录名后缀是 `base64url(session_id)`，与 `manifest.json` 的 `sessionId` 一致 | 1/1 会话一致 |
| 7 | 无解析失败行 | 不可解析行 0 |

汇总口径实测：input 168,684 / output 50,748 / cache_read 9,849,472 / cache_write 0。

### 2.3 与运行库交叉校验（两个独立落盘表示）

运行库 `~/.minimax/v2/sqlite/runtime-state.sqlite` 里另有一份投影
`local_runtime_message_rows`（列 `msg_id` / `data_json`）。它的 `msg_id` 是内部 UUID，
与 `data_json.canonical_message_id` 对应，后者才与会话文件的 `message_id` 相同：

| 交叉校验项 | 实测 |
|---|---|
| 会话文件 assistant 条目 | 83 |
| 运行库投影 assistant 条目 | 82（最新一条尚未落投影） |
| 公共键上 usage 完全一致 | **82/82** |
| 只在文件里 | 1（最新一条） |
| 只在运行库里 | 0 |

结论：会话文件与运行库对用量的记录**逐条一致**，采集口径可交叉验证。

### 2.4 项目维度来源

会话文件本身**不含** cwd。运行库 `local_runtime_sessions` 表提供
`session_id / workspace_dir / project_workspace_dir / title`，实测 1/1 会话可映射到
`workspace_dir=/Users/wayne/workspace/playground`。项目取 `workspace_dir` 的 basename
（缺失回退 `project_workspace_dir`），与 Claude / Cline 等源"cwd basename"口径一致。

### 2.5 额度（credits）本地不存在

会话文件里的 `usage.cost` 六个字段恒为 0（客户端未计价），运行库也没有额度 / 配额表。
本机唯一的额度信息在服务端（订阅制套餐），本地不可得，**本次不采集**。

### 2.6 不做的后果

MiniMax Code 的 token 消耗在报表里完全缺失；用户无法回答"MiniMax 花了多少"。

## 3. 行为 / AC delta

- 新增：**R47**（见下）。
- 修改：**R1** 的源清单由 8 个增至 9 个，增加 `minimax`。
- 删除：无。

**R47**：When MiniMax Code session data is present under `~/.minimax/v2/sessions`, the system shall read each session's `messages.jsonl`, emit one token record per assistant message whose `message.usage` is present, map `usage.input` / `usage.output` / `usage.cacheRead` / `usage.cacheWrite` to `input` / `output` / `cache_read` / `cache_write` with `reasoning = 0`, attribute it to the local day of `message.timestamp` (milliseconds), deduplicate by `message_id` within a session and key records `minimax:<session_id>:<message_id>`, take the model from `message.model`, take the project from the matching `local_runtime_sessions.workspace_dir` basename in the runtime state database (falling back to `project_workspace_dir`, and to no project when that database cannot be read), resolve `session_id` from the session's `manifest.json` and fall back to base64url-decoding the session directory name, skip assistant messages without `usage` or with zero token counts without fabricating 0, skip unparsable lines while counting them instead of failing the run, degrade gracefully when the sessions directory or the runtime database is missing, and expose the rows under the single source `minimax`.

预期行为补充（R47 的可观察结果）：

- `usage report` / `usage html` 把 MiniMax Code 归入 **token 真值轨**（`AGENT_KINDS` 为 `token`），
  与 Qoder / Trae CN 的 credits 轨分开展示，任何两轨都不相加。
- `usage doctor` 报告 `minimax` 源的状态、记录数、token 数与覆盖日期。
- 源签名取所有会话 `messages.jsonl` 的最大 mtime；新会话或追加消息即触发增量同步（R3）。
- 重复跑 `sync` / `backfill` 不产生重复行（R4）；坏行只计数不中断（R17）。
- 项目维度来自运行库；运行库不可读时记录 note 并降级为无项目，**不**让整个源失败。

## 4. 影响范围与非目标

只读契约：会话文件用普通只读打开；运行库走既有 `_open_ro`（`mode=ro` + `query_only=ON` +
2s 超时），与 Antigravity / Qoder 采集器一致，不写回主库。注意 WAL 模式库即使只读打开，
SQLite 仍会在源目录创建空的 `-shm` / `-wal` 边文件；这是既有采集器同样的行为，不算写库。

受影响：

- `src/usage_ledger/collectors.py`：新增 `scan_minimax`，注册进 `collect_all` 与 `source_signatures`。
- `src/usage_ledger/cli.py`：`SOURCES` 增加 `minimax`。
- `src/usage_ledger/html_report.py`：`AGENT_KINDS` 把 `minimax` 归为 token 轨，补颜色 / 顺序 / 显示名。
- `src/usage_ledger/__init__.py` + `pyproject.toml`：版本号 → `0.8.0`（`__version__` 此前停留在 `0.6.0`、
  与 pyproject 的 `0.7.0` 漂移，`usage --version` 会报旧版本；本次随版本升级一并对齐）。
- `README.md` 覆盖能力表与状态行、`ARCHITECTURE.md` 数据源契约、`REQ-0001` §3.2 与 §5.4。
- 测试：`tests/test_collectors.py` / `tests/test_cli.py` / `tests/test_html.py` 新增用例，
  `tests/ac_map.json` 增加 R47 映射，新增夹具 `tests/minimax_helpers.py`。

本次明确不做：

- 额度 / credits 轨（本地无落盘，见 §2.5）。
- 把 `usage.cost` 读成金额（客户端恒为 0，不做任何"看起来像钱"的填充）。
- 子 Agent / 后台任务的独立归属（`Record.sidechain` 在本项目其他源也未使用）。
- 任何联网行为。

## 5. 验证与观测

探针（已完成，只读）：

```bash
python3 scripts/probe_minimax.py
```

自动化测试（已执行）：

- `MiniMaxCollectorTest`（9 例）：字段映射（input/output/cache_read/cache_write/reasoning）、
  `input` 不含 cache read、模型 / provider 提取、无 `usage` 的 assistant 跳过并计数、
  零 token 跳过、坏行只计数不中断、`(session, message_id)` 去重、`session_id` 从 manifest 读取与
  目录名 base64url 回退、项目取 `workspace_dir` basename 与 `project_workspace_dir` 回退、
  运行库缺失 / 损坏时降级、会话目录缺失时源不可用。
- `MiniMaxSignatureTest`（1 例）：会话文件 mtime 变化会推进 `minimax` 签名。
- `MiniMaxCliTest`（4 例）：`backfill` → `report` 与 `--stateless` 一致；重复 `backfill` 幂等；
  新增消息触发自动增量同步；`doctor` 报告该源。
- `HtmlRenderTest.test_minimax_is_classified_as_token`：HTML 侧 `minimax` 归 token 轨。

结果：

- `python3 -m unittest discover -s tests -t .` → **314 tests / 0 failures / 0 errors / 0 skips**（基线 299）。
- `scripts/check_test_policy.py` 通过（314 tests，fast suite 1.8s / 预算 5.0s）。
- `scripts/check_ac_map.py` → **47 criteria / 128 mapped identifiers**（基线 46 / 113）。
- `scripts/check_coverage.py` 通过 → 总覆盖率 **93.4%**（collectors 95.3%、cli 93.6%、
  store 96.7%、scheduler 98.2%），均高于阈值且相对基线 80.9% 只升不降。

手工验证（本机实测，2026-11-20；**冻结快照** = 把 `~/.minimax` 复制到临时目录后采集，
避免会话边跑边长导致两次取值不可比）：

- `usage backfill --source minimax` → `80 records, 9,552,241 tokens, files=1, errors=0, status=ok`
  （该次取的是实时目录，会话仍在增长）。
- 冻结快照下 `usage --stateless report --source minimax` →
  `input 168,684 / output 50,748 / cache_read 9,849,472 / cache_write 0 / turns 83`，
  与探针 §2.2 的汇总**逐项完全一致**。
- `usage report --source minimax`（读库）与 `--stateless report`（直读源）输出**完全一致**。
- `usage report --source minimax --group-by project,model` → 项目列为 `playground`，
  证明运行库项目映射生效。
- `usage doctor` → `minimax: files=1 records=83 tokens=10,068,904 recent7d=83 errors=0 status=ok`。
- `usage html --source minimax --offline` → `rows=1 records=83 tokens=10,068,904`；
  payload 的 `agents` 含 `"minimax":"token"`，与 qoder / trae-cn 的 `credits` 分轨。

## 6. 回滚方案

- 回滚方式：把 `minimax` 从 `SOURCES`、`collect_all`、`source_signatures`、`AGENT_KINDS`
  四处摘除即可；SQLite 里 `source='minimax'` 的历史行保留但不再展示，`prune` 会按既有策略处理。
- 数据 / 配置兼容：无 schema 迁移；`Record` 字段全部是既有列。
- 回滚验证：`usage report` 回到 8 个源；`usage doctor` 不再报告 `minimax`。

## 7. 风险与未决问题

| 风险 / 未决 | 影响 | 处理 |
|---|---|---|
| **本机只有 2026-11-20 起的 1 个会话**（MiniMax Code 当天才安装） | 报表在 2026-11-20 之前为空，容易被误读为"没用过" | CHG 与 README 明确写"接入前的用量本地不可得"；`doctor` 报告覆盖日期区间 |
| 运行库是**运行中应用**的活库 | 只读打开 WAL 库会产生边文件；应用未运行时 WAL 恢复可能失败 | 走既有 `_open_ro`；打开失败降级为"无项目"并记 note，不让源失败 |
| `messages.jsonl` 在写入过程中被读到，末行可能截断 | 整次同步失败 | 坏行只计数不中断（R17），下次增量自动补齐 |
| 会话文件可能被压缩 / 轮转 | 历史丢失 | 每日全量重扫 + `mark_archived` 保留已删源的历史行（既有机制） |
| 模型名是友好名（`MiniMax-M3.1-Flash`） | 价格表无此条目，`cost_equiv_usd` 为 unknown | 与 Antigravity 同类问题；本次不建别名表，`cost_source` 记 `unknown` |
| `usage.cost` 恒为 0 | 不能据此算金额 | 明确不读成金额；额度轨本次不做 |
| 既有测试在部分时区失败（`TZ=America/Los_Angeles` / `Pacific/Kiritimati` 下 Trae CN 的窗口与 HTML 用例） | 与本次改动无关 | 已在 main 上复现同样失败（**既有问题**）；CI 固定 `TZ=UTC` 不受影响，按 AGENTS.md 不在本次顺手修 |

## 8. 关联与证据

- 探针脚本：[scripts/probe_minimax.py](../../scripts/probe_minimax.py)
- 探针输出（本机，2026-11-20，冻结快照）：1 个会话文件；assistant 83 条，全部带 `usage`；
  `totalTokens == input + output + cacheRead` 成立 83/83；重复 `(session, message_id)` 0 处；
  汇总 input 168,684 / output 50,748 / cache_read 9,849,472 / cache_write 0；
  与运行库投影交叉校验公共键 usage 一致 82/82。
- 基线：main `505ef0b`。
- issue / PR：无。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne | 本 CHG + 探针脚本 |
| 就绪 | wayne | 2026-11-20 实现完成：单源 `minimax`、token 真值轨、项目映射走运行库 |
| 已验证 | wayne | 314 tests / 0 failures；覆盖率 93.4%；AC map 47/128；本机冻结快照实测 83 records / 10,068,904 tokens，与探针逐项一致 |
