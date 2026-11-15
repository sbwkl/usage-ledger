# REQ-0002 测试体系完善

| 项 | 内容 |
|---|---|
| ID | REQ-0002 |
| 类型 | 功能卡 |
| 状态 | 探索 |
| Owner | wayne |
| 关联 | [REQ-0001](REQ-0001-usage-ledger.md)、[CHG-0001](../changes/CHG-0001-docs-alignment.md)、[ARCHITECTURE.md §11](../ARCHITECTURE.md)、`tests/` |
| 代码基线 | usage-ledger v0.6.0（main `5b5f987`，2026-11-15） |
| 平台 | macOS（Apple Silicon）；Python ≥3.11；Node 24（仅测试用） |
| 最后更新 | 2026-11-15 |

> 本卡是“测试体系”这一能力的当前事实源，不替代 [REQ-0001](REQ-0001-usage-ledger.md) 的产品功能需求。两者关系：REQ-0001 定义产品行为与 AC；本卡定义如何证明这些行为、如何防止回归、如何在合并前自动发现风险。

## 1. 摘要

usage-ledger 已有 159 个测试、0.8 秒内可跑完、AC 与测试名有映射，数据层和安全隐私测试明显优于同类个人项目。但测试分布与风险不匹配：已知 P0 数据一致性缺陷没有回归测试；HTML/JS、CLI 展示层、调度安装与打包入口缺少验证；没有 CI 门禁，覆盖率数字掩盖了内联前端代码和低覆盖模块。本卡的目标不是继续增加测试数量，而是建立“风险驱动、分层覆盖、可持续执行”的测试体系：让高风险行为在合并前失败，让每条 AC 有行为级证据，让测试证据可复现、可审计；E2E 以真实用户旅程为覆盖单位，覆盖全部用户可见能力与生命周期，而不是只保留一条冒烟链路。

## 2. 问题与证据

### 2.1 谁、什么场景、现在怎么做

- 主要用户：项目维护者、未来贡献者、代码评审人。
- 触发情境：提交 PR、修复 P0/P1 缺陷、上游日志 schema 变化、生成 HTML 报表、安装/卸载 launchd 任务、发布新版本。
- 现状：测试主要覆盖 store、collectors、Trae 凭证与部分 CLI JSON 输出；执行依赖维护者在本机运行 `python3 -m unittest discover -s tests -t .`。没有 CI、没有覆盖率门禁、没有前端端到端测试、没有缺陷回归清单。
- 结果：数据层测试较扎实，但用户可见的 HTML 交互、默认表格输出、launchd 安装、打包入口和性能边界缺少自动验证；已知问题可以长期与“全绿”共存。

### 2.2 代价

- **数据错误**：P0-1 在 `prune → sync → prune` 后把同一段数据重复累计，报表数字会翻倍；当前测试全绿，无法阻止回归。
- **用户可见回归**：HTML 的 Agent 多选、credits/est 分单位展示、表格排序分页、主题持久化等交互没有浏览器级验证；改样式或脚本时只能靠人工发现。
- **运维失败**：`schedule install/uninstall/status` 与打包入口未测；launchd 装错、卸不掉或安装后命令找不到，只能在真实机器上暴露。
- **质量证据不可复现**：没有 CI，PR 合并时没有自动检查；“159 tests OK”只是本地事实，评审人无法独立验证。
- **覆盖率误判**：81% 分支覆盖看似不错，但 `scheduler` 只有 45%，`html_report.py` 的 2,828 行模板只有 31 条 Python 语句被计入覆盖率，内联 JS 基本未测。

### 2.3 证据

以下数据在 v0.6.0（main `5b5f987`，2026-11-15）上实测：

| 证据 | 当前值 | 说明 |
|---|---|---|
| 测试规模 | 159 tests；0.74–0.88s；Python 3.11/3.12/3.14 OK | 速度快、隔离好，是强项 |
| 分支覆盖 | 总体 81% | store 88%、collectors 83%、Trae 模块 85–89%、CLI 77%、aggregation 65%、scheduler 45%、`__main__` 0% |
| AC 映射 | R1–R18 → 60 个测试名，60/60 存在 | 名字可追溯；但 R1、R5、R16 的测试深度不足 |
| P0 回归 | 0 个针对性测试 | [ARCHITECTURE.md §11](../ARCHITECTURE.md) P0-1；我复现 `usage_daily` input 10 → 20 |
| P1 回归 | 0 个针对性测试 | P1-1 性能、P1-2 建库行为、P1-3 `--live` 合并范围均无自动护栏 |
| HTML/JS | 2,828 行；276 行含 `function`；4 个 Node 行为测试 | 无 DOM/浏览器 E2E；图表、排序、分页、日期范围、主题、影子 est 未验证 |
| CLI 展示层 | `live`/`pricing`/`schedule`/`export` 无直接 CLI 用例；`prune` 仅 store 级用例 | `_write_rows`、`_write_activity`、`_write_est_rows` 的表格分支大量未覆盖 |
| 调度/打包 | scheduler 45%；`__main__` 0% | `install`/`uninstall`/`status` 未测；入口点与干净安装未测 |
| CI | 无 workflow；PR #2 `statusCheckRollup` 为空 | 无必过检查、无覆盖率产物、无跨版本矩阵 |
| 静默跳过 | Node 缺失时 4 个 JS 测试 `skipUnless` | 绿色套件可以在前端测试未执行时成立 |
| 时间确定性 | 测试使用 `date.today()` / `datetime.now()`；未固定 TZ | 跨时区、午夜、DST、月末边界可能漂移 |

### 2.4 不做的后果

- P0-1 修复后仍可能被后续重构重新引入；下一次数据错误仍然只能靠用户发现。
- 前端或 launchd 行为回归时，测试继续全绿，发布证据失真。
- 贡献者无法在提交前获得统一反馈，评审成本转移给维护者。
- 覆盖率继续被当作质量指标，而不是“风险是否被验证”的辅助工具。

## 3. 用户与场景

- **主要用户**：维护者（wayne）、贡献者、评审人。
- **触发情境（When）**：提交 PR；修复 P0/P1；上游源格式变化；生成 HTML；安装/卸载 launchd；发布新版本。
- **期望结果（so I can）**：在合并前看到真实失败；在 CHG 中拿到可复现证据；在不牺牲离线、隐私和零运行时依赖的前提下提高交付信心。
- **关键用例**：
  1. 修复 P0-1 前先看到红色回归测试，修复后变绿。
  2. PR 上自动跑 Python 3.11–3.14 和 Node 测试，失败则不能合并。
  3. 改 HTML 脚本后，浏览器测试能发现 Agent 选择、表格或网络请求回归。
  4. 改 scheduler 后，mock `launchctl` 测试能发现安装幂等、dry-run 或状态报告问题。
  5. 上游 JSONL 字段变化时，契约 fixture 能发现并定位到具体源。
  6. 干净安装后，按真实用户旅程跑 CLI E2E：首次导入、增量同步、报表/导出、HTML、保留策略、调度、hooks、诊断、升级。
  7. 打开生成的 HTML，按真实交互跑浏览器 E2E：Agent 选择、日期/模型/项目/搜索、排序分页、口径切换、影子 est、主题和 Trae 状态。

## 4. 目标与非目标

### 4.1 目标

- **G1 缺陷回归护栏**：已知 P0/P1 缺陷 100% 有“先失败、后通过”的自动化回归测试；修复后不再依赖人工记忆。
- **G2 合并前自动门禁**：PR 与 `main` 有必过 CI；覆盖 Python 3.11–3.14、Node 24；不允许静默 skip。
- **G3 风险分层覆盖**：Python 分支覆盖、前端关键旅程、AC 行为映射、变异得分分开度量；关键模块达到各自阈值。
- **G4 边界层可验证**：HTML 交互、CLI 全部用户旅程、launchd/hooks 生命周期、打包入口、并发、升级与性能边界有自动化测试或明确的手工验收。
- **G5 可持续执行**：快速套件 <5 秒；CLI E2E <90 秒、浏览器 E2E <2 分钟（并行）、全量 E2E <3 分钟；零真实网络/凭证；连续 20 次运行零 flake。

### 4.2 非目标

- 不追求 100% 行覆盖，不把覆盖率数字本身当作发布标准。
- 不把 HTML 做像素级视觉回归；只验证关键语义、交互和“无外部请求”。
- 不引入运行时第三方依赖；测试工具只作为 dev-only 可选依赖。
- 不在本卡修复 P0-1/P1-1/P1-2/P1-3 等产品缺陷；修复走独立 CHG，但必须先有本卡要求的失败测试。
- 不在 CI 中真实调用 Trae CN API、读取真实凭证、解密 SQLCipher 或访问用户主目录。
- 不重建采集层，不重写全部前端；E2E 不做 flag 组合矩阵、不做像素快照，但覆盖全部用户可见能力与生命周期。

### 4.3 当前不做（后续 opt-in）

- 非 macOS 平台测试（当前产品边界）。
- 云端测试报告服务、测试数据平台、性能压测平台。
- 视觉像素级回归、跨浏览器矩阵（当前只保证默认浏览器/WebKit 或 Chromium 其一）。
- 运行时第三方依赖、遥测或测试数据上传。

> 以上“当前不做”不是永久非目标；出现真实需求时按新 CHG 追加。

## 5. 成功指标

### 5.1 主指标

| 指标 | 基线（v0.6.0） | 目标 | 统计口径 / 证据 |
|---|---|---|---|
| 已知 P0/P1 回归覆盖 | 0/4 | 100% | 每个缺陷有“基线失败、修复后通过”的自动化测试；CHG 链接两次运行 |
| AC 行为级覆盖 | 60/60 测试名存在，但深度不足 | 20/20 条 R 至少 1 个行为级自动化测试 | REQ 映射 + CI 校验；不是只检查名字存在 |
| CI 必过检查 | 0 | PR / `main` 100% | GitHub required checks；失败不可合并 |
| Python 分支覆盖 | 81% | 总体 ≥85%；store/collectors ≥85%；CLI ≥80%；scheduler ≥80% | `coverage.py --branch`，按模块阈值 |
| 前端关键旅程 | 4 个函数级测试 | 11 条浏览器 E2E 旅程（B1–B11）全部通过 | Playwright；选择、过滤、表格、口径、影子 est、主题、状态、活动、空态 |
| CLI E2E 用户旅程 | 0 | 16 条安装后 CLI 旅程（J1–J16）全部通过 | 子进程调用入口点；校验 DB/HTML/退出码；不调用 `main()` |
| E2E 旅程覆盖完整性 | 0 | 每个用户可见命令与有状态生命周期至少 1 条 E2E | 旅程矩阵（J1–J16、B1–B11）与 CLI/UI 功能清单逐项对照 |
| 变异得分 | 未测 | ≥60%（首版基线） | `mutmut` 或等价工具；按关键模块统计 |
| Flake | 未知 | 连续 20 次 0 flake | CI 定时重复运行 + 隔离记录 |
| 快速套件时长 | 0.74–0.88s | <5s | 单元 + 进程内集成 |
| E2E 套件时长 | 无 | CLI <90s；浏览器 <2min（2 worker）；总计 <3min | 独立 job，按旅程分片并行 |
| 静默 skip | 可能 | 0（白名单需 owner + 到期日） | CI 检查 skip 数量与原因 |

### 5.2 护栏指标

- 运行时依赖保持 0；`pyproject.toml` 的 `dependencies` 不得因测试工具增加。
- 测试只写临时目录；不得写真实 `~/.claude`、`~/.codex`、`~/.trae-cn`、用户 LaunchAgents 或生产 DB。
- 任何测试不得发起真实网络请求或读取真实凭证；失败路径必须用注入/替身。
- 任一关键模块覆盖率较基线下降超过 1 个百分点即失败；不得用排除文件掩盖下降。
- 不允许永久 `expectedFailure` / `skip`；白名单必须有过期日和负责人。
- 不得把 `est`、credits、token 真值或 activity 任意两轨相加来“简化”断言。

## 6. 方案概述

### 6.1 测试分层

| 层 | 范围 | 运行时机 | 目标时长 |
|---|---|---|---|
| L1 单元 | store、aggregation、pricing、collectors 的纯逻辑 | 每次提交 | 秒级 |
| L2 进程内集成 | `cli.main()` 驱动的 sync/report/credits/est/doctor/html | 每次提交 | 秒级 |
| L3 CLI E2E（黑盒） | 干净安装后的入口点，子进程执行 J1–J16 用户旅程 | PR / 发布前 | <90s |
| L4 浏览器 E2E | 生成的 HTML，执行 B1–B11 用户旅程 | PR / 定时 | <2min（2 worker） |
| L5 运维/打包 | clean-venv 安装、真实 launchd 手工冒烟、发布检查表 | PR / 发布前 | <2min |
| L6 非功能 | 性质/蜕变、模糊、并发、性能、变异 | 定时 / 发布前 | 分钟级 |

### 6.2 E2E 范围：以用户旅程为覆盖单位

E2E 是最接近真实使用的证据层，因此不按“抽样几条边界”设计，而是按**用户旅程**覆盖全部用户可见能力和生命周期。覆盖规则：

- **每个用户可见命令至少一条旅程**：在干净安装、真实子进程、真实 SQLite 文件、fixture HOME 上执行。
- **每条有状态生命周期一条旅程**：prune、schedule、hooks、升级各自覆盖“执行 → 重复执行 → 卸载/回滚”的完整序列。
- **失败与恢复是旅程的一部分**：空环境、坏数据、缺权限、并发、离线、刷新失败都要有真实退出码和输出。
- **不做 flag 组合矩阵**：参数组合与分支边界继续由 L2 进程内集成和 L1 单元测试承担；E2E 只证明“用户在真实边界上能完成这件事”。
- **不做像素回归**：浏览器 E2E 只断言语义、交互结果和网络边界。

#### CLI 用户旅程（安装后子进程，fixture HOME）

| ID | 旅程 | 真实边界与步骤 | 关键断言 |
|---|---|---|---|
| J1 | 安装与入口 | 干净 venv `uv tool install`；分别调用 `usage`、`usage-ledger`、`python -m usage_ledger` | 三个入口 `--version` 成功且版本一致；无 traceback |
| J2 | 首次运行（空环境） | 无源、无库：`sync → report → html --offline` | 自动建库；空状态可读；HTML 可打开；不联网；退出码 0 |
| J3 | 首次历史导入 | 7 源 fixture：`backfill → report --format json → doctor` | 各源计数与 oracle 一致；单位与分轨正确；doctor 全源通过 |
| J4 | 日常增量同步 | `backfill → 追加新事件 → report（触发 mtime 自动同步）→ sync --dry-run → sync → sync` | report 能看到新数据并给出 stderr 同步提示；dry-run 零写入、不联网；后续 sync 0 新增；总量幂等 |
| J5 | 统计报表 | `report` / `top` / `activity` 的 table、json、csv | 行集、合计、字段与 oracle 一致；stderr 提示不污染 stdout |
| J6 | 多轨口径 | `credits`（qoder/trae-cn）、`est`（qoder/trae-cn）、`pricing` | 分厂商分轨展示；不跨轨相加；未知价格不填 0 |
| J7 | 导出与直读 | `export`、`live`、`--stateless report` | CSV 可解析；live 不写库；stateless 不读库不落库 |
| J8 | 过滤与分桶 | `report` 的 `--daily/--weekly/--monthly`、`--source/--model/--project/--filter`、日期范围 | 过滤后行集与合计正确；固定 TZ 下归属确定；空结果不补 0 |
| J9 | HTML 生成 | 非 Trae fixture：`html --output`；含 Trae fixture：`--offline` / `--stateless` 对照 | 文件、CSP、payload 完整；离线零请求；stateless 不写库 |
| J10 | 保留策略生命周期 | `backfill → prune --dry-run → prune → sync → prune` | prune 前后总量不变；re-sync 不重复累计（P0-1）；archived 明细保留；dry-run 零写入 |
| J11 | 调度生命周期 | fake `launchctl` + 临时 LaunchAgents：install / status / 重装 / uninstall / status / dry-run | 3 个任务时间与命令正确；重装幂等；卸载干净；dry-run 不写盘 |
| J12 | Hooks 生命周期 | 临时 HOME 与项目：global/project 的 install / status / 重装 / uninstall / dry-run | 只管理本项目 hook 组；安装前备份；卸载保留他人组；dry-run 不写 |
| J13 | 诊断与坏数据 | 空库、缺源、坏 JSONL、坏 DB、只读目录：`doctor` / `sync` / `report` | 不崩溃；错误被计数并提示；退出码语义正确；无秘密泄漏与部分写入 |
| J14 | Trae credits 刷新 | 本地 127.0.0.1 stub（测试专用 endpoint 覆盖，不改变默认生产 URL）承载 `sync --source trae-cn --remote` 与 `html` 两条前台刷新路径；`--offline`/`--stateless` 对照；stub 失败 + `--strict-refresh` | 真实 HTTP 客户端路径；缓存写入；离线不请求；strict 失败非 0；不碰真实凭证 |
| J15 | 并发同步 | 同一 DB 同时启动两个 `sync` 进程 | 无 lock error；总量确定；重复运行稳定 |
| J16 | 升级兼容 | 构造 v0.5 旧 schema DB（无 `source` 列）→ 新 CLI `report` / `html` | 自动迁移；旧行落到默认源；数据不丢；无需手工步骤 |

#### 浏览器用户旅程（Playwright，生成后的单文件 HTML）

| ID | 旅程 | 关键断言 |
|---|---|---|
| B1 | 默认加载 | KPI、Agent chip、首屏表格与 fixture 合计一致；仅本地请求 |
| B2 | Agent 多选 | 单击隔离/恢复、⌘/Ctrl/Shift 增减、至少保留一个；KPI/图表/表格同步 |
| B3 | 日期范围与预设 | 起止、预设、重置；默认全量；非法区间有可读处理 |
| B4 | 模型/项目/搜索 | 单选与组合过滤；搜索命中；重置恢复 |
| B5 | 明细表 | 各列升降序、分页、行数；不适用列显示 `—`；无跨轨合计 |
| B6 | 图表与口径 | token/credits/est 切换；Qoder+Trae credits 分组不堆叠；Top 8 按 Agent 分组；tooltip |
| B7 | Qoder 影子 est | 默认关闭且仅 qoder 可用；右轴虚线、KPI/表格影子行、“不可相加”说明 |
| B8 | 主题持久化 | 切换深色 → 刷新 → 保持；localStorage 生效 |
| B9 | Trae 状态与弱估算 | 已刷新/离线缓存/刷新失败/未同步四态；刷新命令；弱估算标注 |
| B10 | 活动指标 | 仅 qoder 显示；折叠不参与用量；切换活动口径不影响总量 |
| B11 | 空状态与单 Agent | 空数据无 JS 错误；单 Agent 布局与合计正确；零外部请求 |

覆盖规模：16 条 CLI 旅程 + 11 条浏览器旅程。CLI 旅程共用一次干净安装、按旅程重建 fixture HOME；浏览器旅程共用生成的静态 HTML，按测试隔离浏览器上下文。预算：CLI <90s、浏览器 <2min（2 worker）、全量 <3min。

### 6.3 关键设计取向

- **风险优先**：数据正确性 > 安全隐私 > 用户可见交互 > 运维/打包 > 纯格式。
- **E2E 覆盖用户旅程**：CLI 16 条、浏览器 11 条，覆盖全部用户可见命令、生命周期和失败恢复；参数组合和分支边界交给 L1/L2，不做 flag 矩阵和像素快照。
- **语义 golden**：CLI 输出验证字段、单位、提示和退出码，不对整段文本做脆弱哈希；确需快照时限定稳定片段。
- **确定性优先**：临时 HOME/DB、注入时钟、固定 TZ、离线；测试失败必须可复现。
- **证据可审计**：CI 产物保留覆盖率、测试报告、失败日志；CHG 只链接结果，不复制大段日志。

## 7. 当前需求与验收（EARS）

> 每条 R 至少对应一个自动化测试或明确的手工验收步骤。实施前创建 CHG-0002，并在其中写清 AC delta、影响、验证与回滚；本卡不设阶段门禁。

### 7.1 缺陷回归与门禁

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R1 | When a P0 or P1 defect is confirmed, the project shall add a failing automated test that reproduces the defect before the fix, and the test shall pass after the fix; the CHG shall link both the failing and passing runs. | P0-1 回归：`tests/test_store.py` 新增 `prune → re-sync → prune` 用例；CHG-0002 记录基线失败与修复后通过 |
| R2 | While a pull request is open or `main` receives a commit, CI shall run the full test suite on Python 3.11, 3.12, 3.13, and 3.14 with Node 24 available, and shall block merge when any required check fails. | `.github/workflows/` 测试矩阵；分支保护 required checks；故意失败 PR 演练 |
| R3 | If a required test is skipped, then CI shall fail unless the skip is listed in an allowlist containing owner, reason, and expiry date. | CI 检查步骤；注入一个 skip 验证失败；白名单过期验证 |
| R4 | When CI completes, the project shall publish branch coverage for Python and browser/JS critical journeys separately, and shall fail when a critical module falls below its threshold or total coverage drops by more than 1 percentage point from the recorded baseline. | coverage 产物；模块阈值配置；模拟覆盖率下降 |
| R5 | When a REQ acceptance criterion is added or changed, CI shall verify that at least one existing automated test is mapped to it and that every mapped test identifier exists; missing or orphaned mappings shall fail. | AC→测试映射文件；CI 校验脚本；注入缺失/拼错测试名 |
| R6 | While a CHG is marked `已验证`, its evidence shall include the exact command, environment, pass/fail counts, coverage delta, and artifact link. | CHG 模板检查项；评审记录 |

### 7.2 前端与 CLI 行为

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R7 | When `usage html` generates a report, automated browser tests shall execute the B1–B11 journey matrix against the generated file, covering default load, agent multi-select, date presets, model/project/search filters, table sorting and pagination, token/credits/est switching, Qoder shadow est, theme persistence, Trae status, activity block, empty/single-agent states, and zero external network requests. | `tests/e2e/browser/` 11 条 Playwright 旅程；每旅程独立上下文；网络请求日志断言 |
| R8 | When CLI commands run, semantic golden tests shall verify stdout for table/JSON/CSV, stderr notices, and exit codes for `report`, `top`, `activity`, `credits`, `est`, `doctor`, `live`, `export`, `pricing`, `prune`, `schedule`, and `hooks`. | `tests/test_cli_golden.py` 或等价；每条命令至少正常 + 异常各一例；golden 更新流程 |

### 7.3 E2E、调度、打包、并发与性能

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R9 | When `usage schedule install`, `uninstall`, or `status` runs, tests with a mocked `launchctl` shall verify idempotency, dry-run no-write, bootstrap fallback, and state reporting; a manual macOS smoke shall be recorded for each release. | scheduler 单元测试 + mock；发布检查表；真实 launchd 手工冒烟记录 |
| R10 | When the package is installed into a clean environment, end-to-end tests shall execute the J1–J9 CLI journeys through the installed entry points against fixture HOMEs, covering version/entry points, first run on an empty environment, full backfill of all sources, incremental idempotent sync, report/top/activity output formats, credits/est/pricing separation, export/live/stateless, filters and date bucketing, and HTML generation with offline/stateless guarantees; the tests shall not call `main()` in-process. | `tests/e2e/cli/` J1–J9；干净 venv / `uv tool install`；DB、stdout/exit code、HTML payload 断言 |
| R11 | When sync and report, or prune and sync, run concurrently, tests shall verify no lock errors, no lost or duplicated totals, and a deterministic final state. | SQLite WAL 并发测试；总量与幂等断言；重复执行 |
| R12 | When `usage live` runs on the reference dataset, the benchmark shall record median latency and fail on a >20% regression against the recorded baseline; the <0.3s product target remains tracked separately until P1-1 is fixed. | benchmark 脚本；基线文件；CI 报告；P1-1 修复后切换为 <0.3s 硬阈值 |

### 7.4 性质、鲁棒性与确定性

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R13 | When arbitrary sequences of sync, backfill, and prune are applied, invariant tests shall verify that prune does not change total token counts, repeated sync is idempotent, stateless and DB results match, and token/credits/est/activity are never summed across tracks. | Hypothesis/性质测试；固定种子 + 随机序列；蜕变关系断言 |
| R14 | If source JSONL, SQLite, or credential files are malformed, missing, or permission-restricted, then tests shall verify failure isolation, counted errors, no crash, and no secret leakage. | 模糊/属性测试；损坏语料；日志与 HTML 扫描 |
| R15 | While tests run in any supported timezone or around midnight, DST, month-end, and week boundaries, date attribution shall be deterministic through an injected clock; tests shall not call real `now` or `today`. | 固定 TZ 矩阵（UTC、Asia/Shanghai、America/Los_Angeles、Pacific/Kiritimati）；假时钟；跨日/月末/DST 用例 |

### 7.5 测试数据与维护性

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R16 | While collector tests run, fixtures shall include anonymized real samples per source and version plus synthetic edge cases; contract tests shall detect upstream schema drift; fixtures shall contain no prompt, response body, tool content, or secret. | `tests/fixtures/manifest`；脱敏评审；契约测试；秘密扫描 |
| R17 | When the test suite grows, the fast suite shall stay under 5 seconds, the CLI E2E suite under 90 seconds, the browser E2E suite under 2 minutes with 2 workers, and the full E2E suite under 3 minutes; flaky tests shall be quarantined with owner and expiry, and 20 consecutive CI runs shall report zero flakes. | CI 时长阈值；并行分片；定时重复运行；flake 清单与到期检查 |
| R18 | When a contributor runs tests, the repository shall document one command for fast tests and one for E2E/manual tests, including Python, Node, Playwright prerequisites and offline guarantees. | 更新 `README.md` / `AGENTS.md`；干净机器按文档执行 |

### 7.6 有状态生命周期与韧性 E2E

| ID | 需求（EARS） | 验收 / 测试映射 |
|---|---|---|
| R19 | When stateful lifecycle commands run, end-to-end tests shall execute J10–J12 against a real SQLite file and a temporary HOME, verifying that prune followed by sync and prune preserves totals, that schedule install/status/reinstall/uninstall is idempotent with a fake `launchctl`, and that hooks install/status/reinstall/uninstall touches only managed groups and preserves backups. | `tests/e2e/cli/test_lifecycle.py`；fake launchctl 与临时 LaunchAgents；总量不变与幂等断言 |
| R20 | If the environment contains malformed data, an old-schema database, concurrent writers, or a failing Trae credits endpoint, then end-to-end tests shall execute J13–J16 and verify clear non-zero exits without tracebacks or secret leakage, automatic schema migration, deterministic concurrent sync, and refresh behavior against a localhost stub including `--offline`, `--stateless`, and `--strict-refresh`. | `tests/e2e/cli/test_resilience.py`；旧 schema fixture；本地 127.0.0.1 stub；双进程并发 |

## 8. 风险与兔子洞

| 风险 / 兔子洞 | 影响 | 验证或规避 |
|---|---|---|
| 前端/CLI 快照过于脆弱 | 每次文案改动都红，团队最终忽略测试 | 语义断言优先；golden 只覆盖稳定字段/提示；更新流程写清 |
| E2E 不稳定 | flake 破坏门禁信任 | 27 条旅程按能力组织；CLI 用固定 fixture HOME；浏览器用静态文件 + 固定浏览器版本；2 worker 分片；失败保留 trace/video；20 次零 flake 目标 |
| E2E 时长膨胀 | PR 反馈变慢，开发者绕过 | CLI <90s、浏览器 <2min、总计 <3min 硬预算；超时先拆片或降并行开销量，不删关键旅程 |
| E2E 维护成本 | 功能变化导致旅程频繁失效 | 只断言语义和真实边界；fixture 与 oracle 集中维护；新增用户可见能力必须同步新增旅程 |
| dev 依赖膨胀 | 违背零运行时依赖 | 测试工具放 optional `dev` extra；CI 检查 `dependencies` 仍为空 |
| CI 时间过长 | 开发者绕过检查 | 快速 job 每次提交；E2E 只在 PR/定时；缓存依赖与浏览器 |
| 覆盖率游戏 | 数字好看但缺陷仍在 | 分支 + 变异 + AC 映射 + 评审；不设 100% 目标 |
| P0 测试长期红 | 阻塞其他工作 | 先建独立修复 CHG；允许短期 `expectedFailure`，但必须有过期日，且不得标“已验证” |
| 时钟注入改动行为 | 引入新缺陷 | 先加特征测试锁定当前行为，再做纯测试 seam；单独 CHG |
| launchd 无法在 CI 真实验证 | 安装问题漏到用户 | mock 覆盖逻辑；每次发布保留 macOS 手工冒烟证据 |
| 真实 fixture 隐私 | 泄漏 prompt / 正文 | 只保留元数据与结构；脱敏评审；秘密扫描；不入库原始正文 |
| 上游 schema 漂移 | collector 静默漏数 | 按源/版本维护契约 fixture；`doctor` 继续做运行时兜底 |

## 9. 关键决策

| 决策 | 结论 | 理由 | 记录 |
|---|---|---|---|
| 测试运行器 | 保留标准库 `unittest` | 零运行时依赖、现有 159 测试已稳定；不为测试换生态 | 本卡 |
| CI 平台 | GitHub Actions | 仓库已在 GitHub；矩阵、required checks、artifact 成本低 | 本卡 |
| 覆盖策略 | Python 分支 + 前端关键旅程 + AC 映射 + 变异得分 | 单一覆盖率会误导；四类证据互补 | 本卡 |
| 前端测试 | Playwright，11 条用户旅程（B1–B11），不做像素快照 | 覆盖真实交互与网络边界，维护成本可控 | 本卡 |
| CLI E2E | 干净安装 + 子进程 + fixture HOME，16 条用户旅程（J1–J16），不做 flag 矩阵 | 每个用户可见命令和生命周期都有真实边界证据；组合分支留给 L1/L2 | 本卡 |
| E2E 覆盖单位 | 用户旅程，而不是分支或快照数量 | E2E 最接近真实使用；旅程完整性比用例数量更能代表用户风险 | 本卡 |
| CLI golden | 语义快照，只锁定字段/单位/提示/退出码 | 避免文案微调造成大面积红 | 本卡 |
| 测试数据 | 合成边界样本 + 脱敏真实样本，按源/版本管理 | 同时覆盖异常路径和上游漂移 | 本卡 |
| 确定性 | 注入时钟、固定 TZ、临时 HOME、默认离线 | 消除 flake 和环境泄漏 | 本卡 |
| 缺陷修复顺序 | 先红后绿；修复走独立 CHG | 防止“修了但没护栏” | 本卡 + 各 CHG |
| 运行时依赖 | 保持 0；测试工具仅 dev | 不破坏产品隐私/离线/轻量约束 | 本卡 |

## 10. 变更索引

| CHG ID | 标题 | 状态 | 链接 |
|---|---|---|---|
| CHG-0002 | 测试门禁与覆盖率基线（R2–R6，R17/R18 快速套件部分） | 开发中 | [CHG-0002](../changes/CHG-0002-test-gates.md) |

> 后续按“可独立验收、可独立回滚”继续拆分：数据正确性回归（R1/R11/R13）、CLI 用户旅程 E2E（R8–R10/R19/R20）、浏览器 E2E（R7）、鲁棒性与契约（R12/R14–R17）。

> 本卡不设阶段门禁；如需拆分 CHG，只按“可独立验收、可独立回滚”拆分，不按阶段或时间切分。

## 11. DoR 与实施前置

进入开发前，至少满足：

- [ ] 本卡通过评审，状态从“探索”进入“活跃”。
- [ ] CHG-0002 已创建，AC delta 覆盖 R1–R20 的正常、异常和边界路径；如拆分为多个 CHG，每个 CHG 独立可验收、可回滚，不按阶段切分。
- [ ] CI 平台与分支保护权限已确认；仓库管理员可配置 required checks。
- [ ] 测试工具选型（coverage、Playwright、Hypothesis、mutmut 或等价工具）已批准；运行时 `dependencies` 保持为空。
- [ ] P0-1 修复 CHG 与本卡的先后关系已确认：先有失败测试，再有修复；不得先改实现再补测试。
- [ ] 基线指标已记录：159 tests、81% 分支覆盖、0/4 P0/P1 回归、0 CI、4 个 JS 测试。
- [ ] 至少一位领域评审人看过本卡和 CHG-0002。

## 12. 链接

- 产品功能事实源：[REQ-0001](REQ-0001-usage-ledger.md)
- 文档体系变更：[CHG-0001](../changes/CHG-0001-docs-alignment.md)
- 当前实现与已知问题：[ARCHITECTURE.md](../ARCHITECTURE.md)（§11）
- 测试目录：`../../tests/`
- 运行与分支约定：`../../AGENTS.md`
- 方法论参考（不绑定具体工具）：
  - 风险驱动测试与测试文档：ISTQB、ISO/IEC/IEEE 29119-3
  - 测试只能证明缺陷存在：Dijkstra
  - 覆盖率作为手段而非目标：Martin Fowler《TestCoverage》、Goodhart's law
  - 性质测试 / 蜕变测试：QuickCheck、Hypothesis、Chen et al. 的 metamorphic relations
  - 变异测试：Jia & Harman, mutation testing
  - 测试分层与测试替身：Cohn/Fowler test pyramid、Meszaros《xUnit Test Patterns》
  - 持续交付门禁：Humble & Farley《Continuous Delivery》
  - 探索式测试：Whittaker / Bach session-based testing
