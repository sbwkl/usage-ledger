# CHG-0019 接入腾讯 CodeBuddy CN 用量（本地日志逐 step token）

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage report` / `usage html` / `usage doctor` / `src/usage_ledger/collectors.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：探针脚本 [scripts/probe_codebuddy.py](../../scripts/probe_codebuddy.py)

> ID 说明：CHG-0017 / R47（MiniMax Code）、CHG-0018 / R48（CodeArts）已占用，
> 本变更按递增取 CHG-0019 / R49。

## 1. 摘要

把腾讯 CodeBuddy CN（macOS IDE）接成第 11 个采集源。CodeBuddy 把每次模型调用的
token 真值写进扩展日志的 `Step execution metrics: ... usage={...}` 行；两处日志目录
镜像同一批事件。本变更只读这两处日志，按 `(traceId, step)` 去重，映射为现有五字段
token 记录，归入 token 真值轨。额度字段 `credit` 实测恒为 0，不作为 credits 真值采集。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：REQ-0001 G1（在一个视图里回答"每个平台、每个模型的用量"）。
- 触发原因：用户 2026-11-20 要求接入腾讯 CodeBuddy 的用量统计。
- 证据：全部来自本机实测，可用 `python3 scripts/probe_codebuddy.py` 复现（只读、不联网）。

### 2.1 用量数据的位置与格式

两处日志目录（同一事件镜像写入，时间戳格式不同）：

```
~/Library/Application Support/CodeBuddy CN/logs/<启动时间>/window<N>/exthost/Tencent-Cloud.coding-copilot/腾讯云代码助手*.log
    2026-11-20 15:28:08.671 [info] [AgentReporter] [a8e5acced6f3fc473ada2289b956dcaa] Step execution metrics: step=1, duration=3997ms, usage={...}

~/Library/Application Support/CodeBuddyExtension/Logs/CodeBuddyIDE/<YYYY-MM-DD>/<workspace>__<hash>.log
    [11/20/2026, 3:28:08 PM.672] [Info] [AgentReporter] [a8e5acced6f3fc473ada2289b956dcaa]  Step execution metrics: step=1, duration=3997ms, usage={...}
```

同一 step 还会再写一行不带 `usage=` 的摘要（`... step=1, duration=3997ms`），必须忽略；
探针只统计带 `usage=` 且带 `[AgentReporter] [traceId]` 前缀的行，避免把终端命令回显误判为坏行。

`usage` JSON 实测字段（36 行，2026-11-20）：

```json
{"inputTokens":15142,"outputTokens":292,"totalTokens":15434,"cacheTokens":4096,
 "cachedWriteTokens":0,"cachedMissTokens":11046,"lastTokens":15434,
 "credit":0,"thinkingTokens":276}
```

### 2.2 探针实测结论（2026-11-20，冻结于本次实现前的快照）

| # | 结论 | 实测值 |
|---|---|---|
| 1 | 两目录镜像同一批事件，`(traceId, step)` 去重后无 usage 不一致 | cn=39 / ide=26 行，唯一键 39 个，冲突 0 |
| 2 | `inputTokens` **含** cache read：`inputTokens == cacheTokens + cachedMissTokens` | 39/39 成立 |
| 3 | `outputTokens` 是**逐 step 独立**值（非累计，会上下波动） | 单调不减 = False；无需差分 |
| 4 | `totalTokens == inputTokens + outputTokens`，已含 cache read，不能直接用 | 39/39 成立 |
| 5 | `thinkingTokens` 未单列进 total，已包含在 outputTokens 中 | 不另计 reasoning，避免重复 |
| 6 | 元数据可得：`onAgentStart` 带 conversationId，`Preparing model: <name> (<id>)` 带 modelId，genie-history 可解码 workspace | 本机 1/1 trace 三项齐备 |
| 7 | `credit` 恒为 0 | 39/39，不作为 credits 采集 |

按非重叠口径合计（当前会话仍在增长，数值仅作口径证据）：
input(=cachedMissTokens) 120,588 / output 22,624 / cache_read 2,934,400 / cache_write 0；
覆盖日期 2026-11-20；项目 `playground`，模型 `hy4flash-free`。

### 2.3 采集口径

- 每个 `(traceId, step)` = 一次模型调用 = 一条 `Record`。
- `input = cachedMissTokens`（等价 `inputTokens − cacheTokens`，与 Claude / Codex 的非重叠口径一致）、
  `cache_read = cacheTokens`、`output = outputTokens`、`cache_write = cachedWriteTokens`、`reasoning = 0`。
- 不采 `inputTokens` / `totalTokens` / `lastTokens`（含 cache read，直接采会重复计）；
  不采 `credit`（实测 0，不代表服务端计费真值）。
- 去重键：`codebuddy:<traceId>:<step>`；两目录镜像行、同一行重复出现均幂等。
- 时间：日志行首时间戳的本地日，兼容 `YYYY-MM-DD HH:MM:SS.mmm` 与 `[MM/DD/YYYY, h:mm:ss AM/PM.mmm]` 两种格式。
- 模型：同 traceId 的 `Preparing model: <显示名> (<modelId>)` 取括号内 id，缺失时 `unknown`。
- 会话：同 traceId 的 `onAgentStart: ... conversationId=<id>`，缺失时回退 traceId。
- 项目：把 `genie-history/<base64url(cwd)>/current.json` 的 `conversationId` 映射到 cwd 的 basename；
  映射不到时无项目，不伪造。
- 厂商命名 quirk（PR #12 评审 #1 修复）：目录名把 base64 padding 的 `=` 写成 `_`，
  部分无 padding 的目录还追加 `__`；解码前先剥尾部 `_` 再补 padding。实测本机 20/20
  目录正确解出（`tongxing-air?` → `tongxing-air`，时间戳目录 `…OQ__` →
  `/Users/wayne/CodeBuddy/20260928133809`），真实扫描 `skipped:bad-genie=0`。
  边界：若真实路径的 base64 数据位本身以 `_` 结尾，厂商编码与 padding 写法不可区分，
  本实现按 padding 解释；需在带该特征的工作区开一次会话验证（见 §7）。

### 2.4 不做的后果

CodeBuddy 的 token 消耗在 `doctor` / 报表 / HTML 中完全缺失，用户无法回答"CodeBuddy 花了多少"。

## 3. 行为 / AC delta

- 新增：**R49**（见下）。
- 修改：**R1** 源清单增至 11 个，增加 `codebuddy`；REQ-0001 §4 覆盖指标同步。
- 删除：无。

**R49**：When CodeBuddy CN logs are present under either
`~/Library/Application Support/CodeBuddy CN/logs/**/Tencent-Cloud.coding-copilot/*.log` or
`~/Library/Application Support/CodeBuddyExtension/Logs/CodeBuddyIDE/**/*.log`, the system shall
read lines carrying `[AgentReporter] [<traceId>] Step execution metrics: step=<n>, duration=<ms>,
usage=<json>` from both roots, ignore the duplicate summary lines without `usage=`, emit one token
record per `(traceId, step)` with key `codebuddy:<traceId>:<step>` (mirrored events deduplicated
across roots), map `cachedMissTokens` (equivalently `inputTokens − cacheTokens`) to `input`,
`cacheTokens` to `cache_read`, `outputTokens` to `output`, `cachedWriteTokens` to `cache_write`,
and `reasoning = 0` without using `inputTokens` / `totalTokens` / `lastTokens` (which include cache
read) or `credit` (measured 0), attribute each record to the local day of the log timestamp in
both supported timestamp formats, take the model from the `Preparing model: <name> (<modelId>)`
line of the same trace (fallback `unknown`), the session from the `onAgentStart`
`conversationId` of the same trace (fallback traceId), and the project from the basename of the
workspace path decoded from the `genie-history` directory whose `current.json` carries that
conversationId, restoring vendor naming where base64 padding `=` is written as `_` and an extra
`__` may be appended (no project when unmapped), skip lines with non-integer step, unparsable `usage`
JSON, or all-zero token counts while counting them instead of failing, degrade gracefully when
either root is missing and mark the source unavailable when neither exists, keep the source
offline with no network calls, and expose the rows under the single source `codebuddy`.

预期行为补充（R49 的可观察结果）：

- `usage report` / `usage html` 把 CodeBuddy 归入 **token 真值轨**（`AGENT_KINDS` 为 `token`），
  显示名 `CodeBuddy`，与 Qoder / Trae CN 的 credits 轨分开展示，任何两轨不相加。
- `usage doctor` 报告 `codebuddy` 源的状态、记录数、token 数与覆盖日期。
- 源签名取两处日志目录中匹配日志的最大 mtime；新 step 落盘即触发增量同步。
- 重复跑 `sync` / `backfill` 不产生重复行；坏行只计数不中断。
- 本机接入前的会话日志不带该字段，报表在接入前日期为空，不伪造 0。

## 4. 影响范围与非目标

只读契约：逐行读日志与 `genie-history/current.json`，不写源目录、不调用厂商 API、不联网。

受影响：

- `src/usage_ledger/collectors.py`：新增日志扫描（两 root、两种时间戳、元数据映射）并注册进
  `collect_all` 与 `source_signatures`。
- `src/usage_ledger/cli.py`：`SOURCES` 增加 `codebuddy`。
- `src/usage_ledger/html_report.py`：`AGENT_KINDS` 增加 `codebuddy`，补颜色 / 顺序 / 显示名。
- `src/usage_ledger/__init__.py` + `pyproject.toml`：版本号 → `0.10.0`。
- `README.md` 覆盖能力表与状态行、`ARCHITECTURE.md` 数据源契约 / 去重键 / 源详解、
  `REQ-0001` §3.2 / §4 / §5.4 / §8、`docs/design-docs/index.md` 可用 ID 行。
- 测试：`tests/test_collectors.py` / `tests/test_cli.py` / `tests/test_html.py` 新增用例，
  `tests/ac_map.json` 增加 R49 映射；新增探针 `scripts/probe_codebuddy.py`。

本次明确不做：

- credits / 余额轨（`usage.credit` 实测 0，不代表服务端计费；订阅信息本地不可得）。
- 解析 prompt / 正文 / 工具参数；不读 Cookies、JWT、Keychain 或私有 API。
- 子 Agent / 后台任务独立归属；任何联网行为。
- 为旧日志补估算（无本地字段可回填）。

## 5. 验证与观测

- 探针（只读）：`python3 scripts/probe_codebuddy.py`。
- 自动化测试：`CodeBuddyCollectorTest`（字段映射、双 root 去重、元数据缺失回退、坏行 / 零值跳过、
  双时间戳、无 root 降级）、`CodeBuddySignatureTest`（mtime 推进签名）、
  `CodeBuddyCliTest`（`backfill` ↔ `--stateless` 一致、幂等、增量、`doctor` 报告）、
  `HtmlRenderTest.test_codebuddy_is_classified_as_token`。
- 自动化门禁：全量单测、`check_test_policy.py`、`check_ac_map.py`、`check_coverage.py`。
- 手工验证：`usage backfill --source codebuddy` → `usage report --source codebuddy` 与
  `usage --stateless report --source codebuddy` 输出一致；`usage doctor` 显示该源；
  `usage html --offline` 的 `agents` 中 `codebuddy=token`。
- 结果与证据（2026-11-20，本机；环境 macOS 27.0.1 / Python 3.12.13 / Node 24.16.0 / 基线 commit `50a73a0`）：
  - `python3 -m unittest discover -s tests -t .` → **340 tests / 0 failures /
    0 errors / 0 skips**（基线 325；PR #12 评审修复新增 2 例）。
  - `scripts/check_test_policy.py` 通过：fast suite 2.209s（预算 5.0s）；
    `scripts/check_ac_map.py` → **49 criteria / 154 mapped identifiers**（基线 48 / 139）。
  - `scripts/check_coverage.py` 通过：总覆盖率 **92.8%**（collectors 92.9%、
    cli 93.6%、store 96.7%、scheduler 98.2%），高于阈值且相对基线 80.9% 只升不降。
  - 临时集成分支 `tmp/integration-codebuddy`（从 `main` 以 `--no-ff` 合入特性分支）
    上重跑全量单测、测试策略、AC 映射与覆盖率门禁均通过；分支已删除、未推送。
    评审修复后新增用例再次按同流程集成验证，结果见 PR #12 更新。
  - PR #12 评审 #1（MAJOR）修复：`_codebuddy_decode_workspace()` 与探针统一先
    `rstrip("_")` 再补 padding；本机 genie-history **20/20 目录正确解码**，
    真实扫描 `skipped:bad-genie=0`（修复前 17/20 失败、1 个解成 `tongxing-air?`）。
    评审 #2（MINOR）同步校准 `ARCHITECTURE.md` 行数 / 签名数与 README 源列表。
  - 探针 `python3 scripts/probe_codebuddy.py`：cn=129 / ide=110 行（镜像），唯一
    `(traceId, step)` 129 个、冲突 0；`inputTokens == cacheTokens + cachedMissTokens`
    129/129；`totalTokens == inputTokens + outputTokens` 129/129；`credit` 全 0；
    model / project 元数据覆盖 1/1。
  - 真实日志实测：`scan_codebuddy()` 88 文件 / 117 条唯一记录 / 16,034,512 tokens /
    dup=110 / errors=0 / 1.709s（会话边跑边长，与探针不同时刻取值不同属正常）。
  - `usage backfill --source codebuddy` → `110 records, 14,660,014 tokens, files=88,
    errors=0, status=ok`；`usage report --source codebuddy --format json` 与
    `usage --stateless report --source codebuddy --format json` **完全一致**；
    `report --group-by day,project` 项目列 `playground`；`usage doctor` 显示
    `codebuddy: files=88 records=111 tokens=14,854,738 ... status=ok`；
    `usage html --offline --source codebuddy` 生成成功，payload 含 `codebuddy=token` 与
    `CodeBuddy` 标签。
  - 未部署 / 未发布：本变更为本地 CLI 功能，无服务端部署；状态为“已验证”而非“已发布”。

## 6. 回滚方案

- 回滚方式：把 `codebuddy` 从 `SOURCES`、`collect_all`、`source_signatures`、`AGENT_KINDS`
  四处摘除即可；SQLite 中 `source='codebuddy'` 的历史行保留但不再展示。
- 数据 / 配置兼容：无 schema 迁移；`Record` 字段全部是既有列，不需要删库。
- 回滚验证：`usage report` 回到 10 个源；`usage doctor` 不再报告 `codebuddy`。

## 7. 风险与未决问题

| 风险 / 未决 | 影响 | 处理 |
|---|---|---|
| **本机只有 2026-11-20 起的日志带 usage 字段** | 接入前日期为空，容易被误读为"没用过" | README / 本 CHG 明确写"接入前的用量本地不可得"；doctor 报告覆盖日期 |
| 两处日志目录镜像同一事件，且日志目录会轮转 | 若不去重会翻倍计数 | 按 `(traceId, step)` 去重；签名取两 root 匹配日志最大 mtime |
| 日志里会回显终端命令（含正则 / `usage=` 字样） | 误判为用量行 | 只接受 `[AgentReporter] [<traceId>] Step execution metrics:` 前缀 + 合法 JSON 的 usage |
| `inputTokens` 含 cache read，`totalTokens` 不是互斥口径 | 误采会重复计 cache | 只采 `cachedMissTokens` / `cacheTokens` / `outputTokens` / `cachedWriteTokens`，reasoning 不另计 |
| `credit` 恒为 0 | 无法判断真实计费 | 不采集，文档说明不是 credits 真值 |
| genie-history 目录名把 padding `=` 写成 `_`，厂商也可能追加 `__` | 项目维度失真（修复前 17/20 解码失败、1 个错解） | 解码前剥尾部 `_` 再补 padding，collector 与探针同修；本机 20/20 验证通过 |
| 真实路径的 base64 数据位本身以 `_` 结尾时与 padding 写法不可区分 | 该路径项目名可能被剥掉一字符 | 按 padding 解释（厂商信息不足以区分）；需在带该特征的工作区开一次会话验证后再调整 |
| CodeBuddy 升级改日志格式 / 换字段 | 采集不到新事件 | 逐行跳过 + 计数；探针与测试覆盖当前两种时间戳；升级后按需新增 CHG |

## 8. 关联与证据

- 探针脚本：[scripts/probe_codebuddy.py](../../scripts/probe_codebuddy.py)
- 开发基线：main `50a73a0`；特性分支 `feat/codebuddy-usage-source`。
- issue / PR：暂无。
- 测试 / 覆盖率证据：见 §5；探针输出保存于 `/tmp/codebuddy-probe-final.txt`（临时文件，不入仓库）。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne | 本 CHG + 只读探针实测（2026-11-20） |
| 就绪 | wayne | REQ-0001 R49 + 正常 / 异常 / 边界 AC 已登记；探针证据已附 |
| 开发中 | wayne | TDD：先写 13 个新增测试（红灯），再实现 `scan_codebuddy` 与四处注册（绿灯） |
| 已验证 | wayne | 340 tests / 0 skip；覆盖率 92.8%；AC map 49/154；真实日志 117 记录 / 16,034,512 tokens，读写一致、doctor / html 均正常 |
| 评审修复 | wayne | PR #12 review #1：genie 目录名 padding 还原 + 探针同修 + 2 例回归；#2：三处文档数字校准 |
