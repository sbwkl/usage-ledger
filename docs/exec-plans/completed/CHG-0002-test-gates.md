# CHG-0002 测试门禁与覆盖率基线

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`tests/`、`scripts/`、`.github/workflows/`、`pyproject.toml`
功能卡：[ARCHITECTURE.md §9 测试体系完善](../../../ARCHITECTURE.md#9-测试体系)
关联：[usage-ledger.md](../../product-specs/usage-ledger.md)、[ARCHITECTURE.md §9/§11](../../../ARCHITECTURE.md)

> 2026-11-16 后续：项目级 `AGENTS.md` 已合并到 [README.md](../../../README.md#开发约定)；本文中的 `AGENTS.md` 均为当时的历史记录。

## 1. 摘要

为 usage-ledger 建立可执行的合并门禁：GitHub Actions 在 Python 3.11–3.14 + Node 24 上跑快速套件，强制 coverage 分支阈值、skip/expectedFailure 白名单和 AC→测试映射校验，并把快速套件时长锁在 5 秒内。本次同时补齐达到阈值所需的测试；不改变任何产品行为。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：ARCHITECTURE.md §9 G2（合并前自动门禁）、G3（风险分层覆盖）、G5（可持续执行）；R2–R6。
- 触发原因：当前没有 CI，PR #2 的 `statusCheckRollup` 为空；“159 tests OK”只是本地事实，评审人无法独立验证。
- 证据（v0.6.0，main `5b5f987`，2026-11-15 实测）：
  - 快速套件 159 tests / 0.90s；coverage.py `--branch` 总覆盖 81%。
  - 模块覆盖：store 88%、collectors 83%、CLI 77%、scheduler 45%、aggregation 65%、`__main__` 0%。
  - 4 个 HTML/JS 测试在 Node 缺失时 `skipUnless` 静默跳过；没有 skip 白名单或到期检查。
  - 没有 AC→测试映射文件；usage-ledger.md §5 的 60 个测试名只存在于文档表格，无法机械校验。
- 不做的后果：PR 合并前没有统一反馈；覆盖率继续被当作数字而不是门禁；关键模块可以在“全绿”下退化；Node 缺失时套件仍显示 OK。

## 3. 行为 / AC delta

本次实现 ARCHITECTURE.md §9 的以下需求：

- **R2**：`.github/workflows/test.yml` 在 PR、`main`、`sit` 上运行；矩阵 Python 3.11/3.12/3.13/3.14，Node 24；任一检查失败即 job 失败。`main` 已启用 5 个 required checks（`tests (py3.11)`–`(py3.14)`、`test policy`），strict + enforce_admins；PR #3 5/5 通过，故意失败 PR #5 被 BLOCKED（见 §5.4）。
- **R3**：`scripts/check_test_policy.py` 运行完整套件并检查 skip / expectedFailure 是否有白名单条目（owner、reason、expires）；无条目、条目过期、条目未被使用、重复条目或零测试均失败。白名单文件 `tests/skip_allowlist.json`，当前为空。
- **R4（Python 覆盖率部分）**：`coverage.py --branch` + `scripts/check_coverage.py`；总覆盖 ≥85%，store/collectors ≥85%，CLI ≥80%，scheduler ≥80%；任一关键模块较 v0.6.0 基线下降超过 1 个百分点即失败。浏览器/JS 关键旅程覆盖率不在本 CHG，见 §7。
- **R5（usage-ledger.md 映射部分）**：`tests/ac_map.json` + `scripts/check_ac_map.py`；解析 usage-ledger.md §5 的 R1–R18，校验每条 AC 至少映射一个真实存在的测试标识，缺失或孤立映射即失败。ARCHITECTURE.md §9 自身 R1–R20 的映射不在本 CHG，见 §7。
- **R6**：在 `AGENTS.md` 增加 CHG 验证证据清单（命令、环境、通过/失败数、覆盖率变化、产物链接）；`CHG` 标记“已验证”前必须写全。
- **R17（快速套件部分）**：`check_test_policy.py` 对快速套件计时，超过 5 秒失败。
- **R18（快速套件部分）**：README 与 AGENTS 写明一条快速测试命令及 Node 前置条件。

本次明确不实现：R1（P0/P1 回归测试）、R7（浏览器 E2E）、R8–R10（CLI golden / 调度 / E2E）、R11–R16、R19–R20。它们按“可独立验收、可独立回滚”拆到后续 CHG：

| 后续切片 | 覆盖需求 | 说明 |
|---|---|---|
| 数据正确性回归 | R1、R11、R13 | P0-1 先红后绿；并发；跨轨不相加不变式 |
| CLI 用户旅程 E2E | R8、R9、R10、R19、R20 | 干净安装 + 子进程 J1–J16；scheduler mock |
| 浏览器 E2E | R7 | Playwright B1–B11 |
| 鲁棒性 / 性能 / 契约 | R12、R14、R15、R16、R17（E2E）、R18（E2E） | benchmark、模糊、TZ 矩阵、fixture 契约 |

## 4. 影响范围与非目标

- 受影响：
  - 新增 `.github/workflows/test.yml`、`scripts/check_test_policy.py`、`scripts/check_coverage.py`、`scripts/check_ac_map.py`、`tests/skip_allowlist.json`、`tests/ac_map.json`、`tests/coverage_policy.json`。
  - `pyproject.toml` 增加 `dev` optional extra（coverage）与 `[tool.coverage]` 配置；运行时 `dependencies` 保持为空。
  - 新增/扩展测试：scheduler 安装/卸载/状态、CLI 输出与命令分支、aggregation、store 查询、collectors 边界、`__main__` 入口、pricing/models 末尾分支。
  - 文档：`README.md`、`AGENTS.md` 测试命令与 CHG 证据清单。
- 本次明确不做：
  - 不修改任何产品命令、数据结构、输出格式或调度行为；新增测试只锁定当前行为。
  - 不修复 P0-1/P1-1/P1-2/P1-3；不引入 Playwright/Hypothesis/mutmut。
  - 不引入运行时第三方依赖；coverage 只作为 dev-only 工具，不写入 `dependencies`。
  - 不做浏览器下载、真实 launchd 加载、真实网络或凭证读取。
- 兼容性与迁移：无数据/配置迁移；回滚即删除新增文件并还原文档。

## 5. 验证与观测

### 5.1 快速套件与覆盖率

```bash
python3 -m unittest discover -s tests -t .
uv run --with coverage python -m coverage run --branch --source=src/usage_ledger \
  -m unittest discover -s tests -t .
uv run --with coverage python -m coverage json -o coverage.json
python3 scripts/check_coverage.py coverage.json
```

目标：总覆盖 ≥85%；store ≥85%；collectors ≥85%；CLI ≥80%；scheduler ≥80%；套件 <5s。

为达标新增的测试重点：

- `tests/test_scheduler.py`：`install` 写盘/`load=False`/`bootstrap` 失败回退、`uninstall` bootout+unload+删除、`status` 安装/加载状态、`_launch_command` 的 `usage` 与 `python -m` 两条路径、`render` 为合法 plist。
- `tests/test_cli_output.py`（新）：`live`、`pricing`、`export`、`prune`、`schedule`、`hooks` 的正常与异常路径；`report`/`activity`/`credits`/`est` 的 table 输出分支；`--format json/csv` 与 stderr 提示。
- `tests/test_aggregation.py`（新）：week/month 标签、未知维度、cost unknown/partial/known、project/session 缺失、过滤与 `merge_records`、`missing_days`。
- `tests/test_store.py`：`fetch_records` 过滤/边界、credits/est 查询边界、source_state/meta、prune dry-run。
- `tests/test_collectors_edges.py`（新）：缺失根、坏形状、坏时间戳、未知模型、去重与 SQLite 边界。
- 入口与零散分支：`python -m usage_ledger --version` 子进程；`pricing` 未知模型；`models` 末尾字段。

### 5.2 门禁策略

```bash
python3 scripts/check_test_policy.py
python3 scripts/check_ac_map.py
```

- `check_test_policy.py`：运行完整套件，记录 skip / expectedFailure / unexpected success；校验 `tests/skip_allowlist.json`；零测试、重复白名单条目或套件计时 >5s 均失败。
- `check_ac_map.py`：从 usage-ledger.md §5 解析 AC ID，校验 `tests/ac_map.json` 的覆盖与测试标识存在性。
- CI 上传 `coverage.json` 与 `test.log` 作为 artifact；测试失败时仍上传 `test.log`。

### 5.3 手工验证

- 在 Node 缺失的环境运行 `check_test_policy.py`，确认 4 个 JS 测试被视为未授权 skip 并失败（验证 R3 不是形式主义）。
- 故意删除/拼错 `ac_map.json` 中一个测试名，确认 `check_ac_map.py` 失败。
- 在本地把 `tests/coverage_policy.json` 的 total 临时调到 99，确认 `check_coverage.py` 失败。

### 5.4 结果与证据

本地实现验证（2026-11-15，macOS 27.0 arm64，Node v24.16.0；worktree `feat/test-system`，基线 commit `5b5f987`）：

- 快速套件：`python3 -m unittest discover -s tests -t .` → 244 tests，OK，1.09s；0 skip / 0 expectedFailure。
- 覆盖率：`uv run --with 'coverage>=7.4' python -m coverage run --branch --source=src/usage_ledger -m unittest discover -s tests -t .` + `coverage json`（Python 3.13.13 / coverage 7.17.3）：
  - 总 **93.57%**（基线 80.87%，阈值 85%）；store **97.07%**、collectors **96.32%**、CLI **93.47%**、scheduler **98.23%**、aggregation **100%**。
  - `python3 scripts/check_coverage.py coverage.json` → passed。
- 测试策略：`python3 scripts/check_test_policy.py` → 244 tests / 1.229s（预算 5s），0 skip，passed。
- AC 映射：`python3 scripts/check_ac_map.py` → usage-ledger.md 18 条 AC、65 个测试标识，passed。
- 反向验证：
  - PATH 去掉 node 后运行策略脚本 → exit 1，4 个 HTML/JS 测试报 unauthorized skip。
  - 临时把 total 阈值调到 99% → `check_coverage.py` exit 1（`TOTAL 93.6% < threshold 99.0%`）。
  - `tests/ac_map.json` 曾引用不存在的 `test_trae_collector...test_capture_replays_through_collector`；门禁报 unknown identifier，修正为 `tests.test_trae_hooks.HookScriptTest...` 后通过。
  - 重复白名单条目与零测试套件均验证为 exit 1（`duplicate allowlist entry` / `no tests were run`）。
- review 后续修复：workflow 上传 `coverage.json` + `test.log`，增加 `permissions: contents: read`、job timeout 与 `pipefail`；策略脚本增加零测试、重复白名单检查；YAML 通过解析校验；CHG 的 R4/R5/R2 范围已标注为部分实现。
- 首次远程运行（commit `b81f9d7`，run [43775884697](https://github.com/sbwkl/usage-ledger/actions/runs/43775884697)）：5 个 job 在排队阶段被取消，注解为 `The configuration 'macos-14-arm64-us-default' is not supported`；GitHub 已于 2026-11-07 退役 `macos-14`，改用 `macos-15` 后重跑。
- 远程门禁通过（2026-11-16，commit `f748a32`，run [43776180116](https://github.com/sbwkl/usage-ledger/actions/runs/43776180116)，GitHub-hosted `macos-15` arm64）：
  - 5/5 checks 通过：`tests (py3.11)` 20s、`py3.12` 22s、`py3.13` 18s、`py3.14` 23s、`test policy` 12s。
  - 每个 Python 版本均 `Ran 244 tests ... OK`；Python 3.11/3.12/3.13 覆盖率 93.54%，3.14 为 93.56%；store 97.07%、collectors 96.32%、CLI 93.33%、scheduler 98.23%、aggregation 100%。
  - artifacts `test-report-py3.11`–`test-report-py3.14` 各含 `coverage.json` 与 `test.log`（与 run 同页）。
- 分支保护已启用（2026-11-16）：`main` required checks 为上述 5 个上下文，`strict=true`、`enforce_admins=true`，禁止 force push 与删除；PR #3 状态 `CLEAN`。
- 门禁反向验证：临时 PR #5 只增加一个失败测试，5/5 checks 均为 `FAILURE`，`mergeStateStatus=BLOCKED` 且 `mergeable=MERGEABLE`；验证后关闭 PR 并删除探针分支。
- 未合并 `main`：PR #3 保持 open，等待用户批准；因此本 CHG 标“已验证”，不标“已发布”。

## 6. 回滚方案

- 回滚方式：还原 `pyproject.toml`、`README.md`、`AGENTS.md`，删除 `.github/workflows/test.yml`、`scripts/check_*.py`、`tests/skip_allowlist.json`、`tests/ac_map.json`、`tests/coverage_policy.json` 与本次新增测试文件；GitHub 上关闭 required checks。
- 数据/配置兼容：无数据库、无用户配置、无发布产物变化。
- 回滚验证：`python3 -m unittest discover -s tests -t .` 恢复 159 个测试且 OK；不残留 CI 必过检查。

## 7. 风险与未决问题

- **分支保护已启用**：`main` 已配置 5 个 required checks、`strict=true`、`enforce_admins=true`；需要回滚时在 GitHub 仓库设置中关闭对应保护。注意 enforce_admins=true 时管理员也不能在 checks 失败时合并。
- **CI runner 选择**：按 REQ 的 macOS 平台边界使用 macOS runner。`macos-14` 已于 2026-11-07 被 GitHub 退役，首次触发报 `The configuration 'macos-14-arm64-us-default' is not supported`；现改用 `macos-15`，不改成 Linux。若镜像再次退役，按同一原则换当前受支持的 macOS 镜像并在此记录。
- **覆盖率门槛可达性**：本地已达标（总 93.57%，最低关键模块 store 97.07%）。后续若因新代码下降超过基线 1pp，门禁会失败；不得通过排除文件掩盖。
- **Node 缺失时的本地体验**：4 个 JS 测试会变成未授权 skip，`check_test_policy.py` 会失败；README 明确要求 Node 24，跳过需白名单 + 到期日。
- **CI 时长**：4 个 Python 版本 × 完整套件 + policy 重跑；快速套件当前 <1.5s，预计可接受。
- **PR #4 暂无 checks**：`feat/docs-status` 基于 `main` `5b5f987`，该基线尚无 `.github/workflows/test.yml`，因此 PR #4 要等 PR #3 合并 `main` 后重新触发才有检查；CHG-0003 为纯文档变更，验证不依赖 CI。
- **Actions Node 20 弃用告警**：`actions/checkout@v4`、`actions/setup-python@v5`、`actions/setup-node@v4` 被 GitHub 强制以 Node 24 运行并产生 warning；不影响 5/5 通过，升级 action 主版本留给独立 CHG。
- **R4/R5 仍是部分实现**：本 CHG 只发布 Python 覆盖率，不含浏览器/JS 覆盖率；AC 映射只覆盖 usage-ledger.md，未覆盖 ARCHITECTURE.md §9 自身 R1–R20。完整验收留给后续 CHG，不得用本 CHG 宣称 R4/R5 全部完成。
- **CI 硬化**：workflow 已限制 `permissions: contents: read` 并设置 job timeout；actions 仍按 major tag 引用，未按 commit SHA 固定，后续可按供应链要求收紧。
- **未决**：ARCHITECTURE.md §9 §5.1 的“20/20 条 R”与 usage-ledger.md 的 R1–R18 数量口径不一致；本次按 usage-ledger.md 的 18 条 AC 建映射，待 ARCHITECTURE.md §9 自身 AC 的实施 CHG 落地后追加映射。

## 8. 关联与证据

- RFC/ADR：无（工具选型已在 ARCHITECTURE.md §9 §9 决策）。
- issue/PR：[PR #3](https://github.com/sbwkl/usage-ledger/pull/3)（本 CHG）、[PR #4](https://github.com/sbwkl/usage-ledger/pull/4)（CHG-0003 文档）、[PR #5](https://github.com/sbwkl/usage-ledger/pull/5)（失败门禁演练，已关闭）。
- commit：`c3902ad`、`fcc974a`、`b81f9d7`、`f748a32`（`feat/test-system`，基于 `5b5f987`）。
- release：不涉及；尚未合并 `main`。
- 日志：CI run [43776180116](https://github.com/sbwkl/usage-ledger/actions/runs/43776180116)（5/5 通过，artifacts 同页）；首次取消 run [43775884697](https://github.com/sbwkl/usage-ledger/actions/runs/43775884697)；失败门禁演练 run [43776333098](https://github.com/sbwkl/usage-ledger/actions/runs/43776333098)。
- 分支保护：`main` required checks + strict + enforce_admins（2026-11-16）。

## 9. 变更记录

| 状态 | 操作人 | 证据/链接 |
|---|---|---|
| 提议 | wayne | 2026-11-15 用户指示开发 ARCHITECTURE.md §9；本 CHG 为第一个可独立验收切片 |
| 就绪 | wayne | 待用户确认 CHG 后进入开发 |
| 开发中 | wayne | 2026-11-15 本地实现：244 tests OK、coverage 93.57%、三项门禁通过、反向验证通过；CI 与分支保护待远程验证 |
| 开发中 | wayne | 2026-11-15 按 code review 修复：artifact 增加 test.log、workflow 权限/timeout/pipefail、策略脚本零测试与重复白名单检查、收窄 R2/R4/R5 范围；远程门禁待验证 |
| 已验证 | wayne | 2026-11-16 远程 CI 5/5 通过（4×244 tests，coverage 93.54–93.56%，artifacts 完整）；`main` required checks + strict + enforce_admins 已启用；失败 PR #5 被 BLOCKED；PR #3 待用户批准合并，未发布 |
