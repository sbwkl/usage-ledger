# AGENTS.md — 项目工作区地图

本目录是 `usage-ledger`——macOS 上极轻量的跨 AI 编码工具 **token / credits 用量台账**：默认离线、只读源日志、只写本地 SQLite、零第三方依赖。**本文件只是地图**：目录结构、硬性规则摘要、文档指针。架构基线在根目录 `ARCHITECTURE.md`，需求事实源在 `docs/product-specs/REQ-0001-usage-ledger.md`，变更事实源在 `docs/exec-plans/completed/CHG-0001-docs-alignment.md`，决策事实源在 `docs/design-docs/ADR-0001-source-of-truth-db-as-archive.md`，RFC 占位在 `docs/design-docs/rfcs/README.md`，开发约定与门禁在 `README.md`；动手前按「文档地图」按需读取，聊天 / issue / PR 只做同步。

## 目录结构

- `src/usage_ledger/` — Python 源码（标准库 only）：`collectors.py`（多源采集规则）、`store.py`（SQLite 归档 / 索引）、`aggregation.py`（统一聚合口径）、`cli.py`（所有命令入口）、`html_report.py`（单文件 HTML 报表）、`trae_auth.py` / `trae_credits.py` / `trae_hooks.py`（Trae CN 定向联网与弱估算）、`models.py` / `pricing.py` / `qoder_models.py` / `scheduler.py` 等。
- `tests/` — unittest 单测（Python ≥3.11 + Node 24）；`ac_map.json`（AC→测试映射）、`coverage_policy.json`（覆盖率基线）、`skip_allowlist.json`（skip 白名单）、`fixtures/`（源数据样本）。
- `docs/` — 系统记录：REQ / CHG / ADR / RFC、设计文档、As-Built 架构、调研与本机实测探针；权威事实源在这里，按 `docs/design-docs/index.md` 索引阅读。
- `scripts/` — 门禁检查（`check_coverage.py` / `check_test_policy.py` / `check_ac_map.py`）与本机数据探针（`probe.py` 及 `probe_*.py`）。
- `.github/workflows/test.yml` — CI：PR / `main` / `sit` 上跑 Python 3.11–3.14 × Node 24 矩阵，执行覆盖率、skip / 时长与 AC 映射门禁；`main` 已启用 5 个 required checks。
- 根目录生成物：`usage-report.html`、`coverage.json`、`.coverage`、`build/`、`*.egg-info/` 均已 gitignore，不要手改或提交。

## 硬性规则（永远生效）

1. **默认离线**：只读本地日志、只写本地 SQLite。唯一联网例外是 Trae CN credits 的两条显式前台刷新路径（`usage sync --source trae-cn --remote` 与含 Trae 的 `usage html`）；`report` / `credits` / `doctor` / `live` / 自动同步 / `html --offline` 全部离线。
2. **口径不可混加**：token 真值 / 活动指标 / credits 额度 / est 估算四轨分表分示，任何两轨都不相加；缺失数据不伪造 0、估算永不冒充真值。
3. **隐私与只读**：不写源目录、不存 prompt / 正文；Trae JWT 只在刷新进程内使用，不落库、不写日志、不进 HTML；不读 Keychain / 浏览器 Cookie，不解密 Trae CN SQLCipher 库，不逆向厂商私有 API。
4. `main` 是保护分支，只接受合并，不直接提交；**任何分支合并进 main 都必须先征得用户同意**，未经明确同意禁止合并。新特性走 `feat/<特性名>` 分支；集成测试用临时分支，测完即删，不保留长期集成分支；有未提交改动时用 `git worktree` 并行开发。完整流程见下文「开发流程」。
5. **需求先行**：新特性先满足 DoR（REQ / CHG 已更新、AC delta 覆盖正常 / 异常 / 边界、依赖已链接），再写代码；实现中不得扩大 CHG 范围。新功能 / 跨模块行为变更先建 CHG 并登记 REQ 变更索引；一次性小修也要有极简 CHG 并回链入口。
6. **测试门禁**：快速套件、覆盖率、skip / expectedFailure 白名单与 5 秒预算、REQ-0001 §5 AC→测试映射全部通过才算完成；Node 24 缺失导致的 skip 会被 `check_test_policy.py` 判失败，不得当环境问题忽略。
7. 提交信息引用 CHG ID；PR 标题 / 描述引用 CHG 和 REQ。CHG 标「已验证」前证据必须写全：精确命令、环境（OS / Python / Node / commit）、通过 / 失败 / 跳过数、覆盖率与基线变化、日志或 artifact 链接；缺任一项保持「开发中」。没有部署 / 监控证据不得标「已发布」。
8. 对话与文档用中文。

## 开发流程（每个新特性都必须遵守）

分支模型：`main` 是保护分支，只接受合并，不直接提交；新特性一律走 `feat/<特性名>`；集成测试用临时分支，测完即删，不保留长期集成分支。

1. **从最新 main 切分支**
   先同步 main（有远程时 `git pull`），再 `git checkout -b feat/<特性名>`。

2. **本地有未提交改动时用 worktree**
   不要 stash，也不要带着脏工作区切分支；用 worktree 在独立目录并行开发：
   `git worktree add ../usage-ledger-<特性名> -b feat/<特性名> main`，完成后 `git worktree remove ../usage-ledger-<特性名>`。

3. **TDD 开发**
   先写失败的测试，再写实现，最后重构。完成标准：该子项目的测试命令全部通过。
   单元测试写在 `tests/`；CLI 集成测试放在 `tests/test_cli*.py`，以黑盒方式运行 `usage` / `usage-ledger`，并用 `tempfile` 隔离 HOME / DB / 配置路径，不污染真实配置。

4. **提交前静态检查（强制）**
   每次编码完成后必须运行本项目的编译 / 类型检查和 lint 命令，必须零错误、零警告才能提交；有告警时先修复，不要用跳过检查、局部禁用规则之类的方式压掉。
   本项目当前命令：语法 / 编译检查 `python3 -m compileall -q src tests scripts`（输出为空为通过）；静态策略门禁 `python3 scripts/check_test_policy.py`、`python3 scripts/check_ac_map.py`；覆盖率门禁按「常用命令」执行。当前未配置 mypy / ruff / flake8；若后续引入，必须同步本节并纳入提交前检查，仍不得压制告警。

5. **用临时分支做集成测试**
   从最新 main 切临时分支并合入特性分支：`git checkout -b tmp/integration-<特性名> main && git merge --no-ff feat/<特性名>`；集成测试用例与全项目单元测试必须全部通过。测完删除临时分支：`git checkout main && git branch -D tmp/integration-<特性名>`；临时分支不推送远程。

6. **需求补充 / 修改的处理**
   集成测试通过后若用户提出新的需求补充或修改，先判断它与当前特性分支主题的相关性：

   - **关联大**（同一特性的完善、修 bug、延伸）：回到原 `feat/<特性名>` 分支继续开发，走完步骤 3–5。
   - **关联不大**（新话题）：从最新 main 切新的 `feat/<特性名>` 分支开发；工作区有未提交改动时按步骤 2 用 worktree。
   - **无法判断**：向用户确认后再动手，不要自行归类。

7. **创建 PR 供人工审核**
   推送特性分支并向 `main` 发起 PR。若仓库没有远程（纯本地仓库），跳过 PR，改为保留清晰的提交记录，并向用户说明变更内容与验证结果。
   **任何分支合并进 main 都必须先征得用户同意**；未经用户明确同意，禁止执行合并到 main 的操作。

## 核心设计要点（已定，勿反复）

- **源是唯一事实来源**：DB 是可插拔的「归档 + 索引」层，不是权威副本。`usage report`（读库）与 `usage --stateless report`（读源）输出必须完全一致；`NullStore` 尚未实现。
- **拉取式采集，无常驻进程**：数据由 agent 自己落盘，任何时刻读盘都能拿到已落盘的全部数据；查看命令自动比对源文件 mtime 增量 sync，历史用 `backfill` 回填。
- **实时性三档**：`usage live`（直读源，<0.3s）→ `--live` 合并 → 读库（自动检测新数据）。
- **Qoder 四轨**：token 真值（旧库 2026-06-01 ~ 09-16）、活动指标、credits 额度（转录逐请求 + 桌面端 `turn_credits` 合并去重）、est 估算 token——口径不同、永不互加。
- **Trae CN 双轨**：credits（服务端会话级真值，定向联网）+ hook 弱估算（离线 token 影子），二者不可相加。
- **覆盖 11 个源**：Claude Code / OpenCode / Kilo / Cline / Codex CLI / Qoder / Antigravity / CodeArts / MiniMax Code / CodeBuddy CN / Trae CN；WorkBuddy 未接入，计价按 `PROBE.md` 建议推后。
- **当前版本 v0.10.0**；`ARCHITECTURE.md` §11 的 P0 / P1 / P2 问题需要独立 CHG，不要顺手修。

## 文档地图（真相在这里）

| 文档 | 内容 | 何时读 |
|---|---|---|
| ARCHITECTURE.md | As-Built 架构总览，含 §11 已知问题清单 | 了解整体结构、排障、审计时 |
| docs/DESIGN.md / FRONTEND.md / PLANS.md / PRODUCT_SENSE.md / QUALITY_SCORE.md / RELIABILITY.md / SECURITY.md | 领域宪章：设计、前端、计划、产品感知、质量评分、可靠性、安全 | 对应领域沉淀与评审时 |
| docs/design-docs/index.md / core-beliefs.md | 设计文档索引与核心工程信念 | 沉淀 / 回顾工程价值观时 |
| docs/design-docs/ | 设计文档、讨论纪要、ADR 与 RFC（`design-docs/rfcs/`） | 动采集、变更核心设计或需要 RFC 时 |
| docs/product-specs/ | 产品功能卡与规格：`REQ-0001-usage-ledger.md`、`REQ-0002-testing.md`、`index.md` | 产品 / 需求、评审、开始新特性前 |
| docs/exec-plans/completed/ | 已验证 CHG：`CHG-0001-docs-alignment.md` ~ `CHG-0020-docs-structure-and-dev-process.md` | 开发 / 评审时读本次 CHG |
| docs/exec-plans/active/ | 进行中阶段 spec | 推进阶段实现时 |
| docs/exec-plans/tech-debt-tracker.md | 技术债账本索引；权威清单见 ARCHITECTURE.md §11 | 评审、重构、排期时 |
| docs/references/ | RESEARCH.md / PROBE.md 调研与实测证据 | 查选型证据 / 数据边界时 |
| docs/generated/db-schema.md | SQLite schema 快照（源自 store.py，勿手改） | 查看 / 核对数据库结构时 |
| README.md | 项目定位、覆盖能力、开发约定与门禁 | 首次了解项目、开发前核对约定 |

## 常用命令

```bash
# 快速测试（离线；需 Python ≥3.11 + Node 24）
python3 -m unittest discover -s tests -t .

# 提交前静态检查（强制；零错误、零警告）
python3 -m compileall -q src tests scripts
python3 scripts/check_test_policy.py
python3 scripts/check_ac_map.py

# 覆盖率与门禁
uv run --with coverage python -m coverage run --branch --source=src/usage_ledger \
  -m unittest discover -s tests -t .
uv run --with coverage python -m coverage json -o coverage.json
python3 scripts/check_coverage.py coverage.json
python3 scripts/check_test_policy.py
python3 scripts/check_ac_map.py

# 直接运行 CLI / 本地重装
PYTHONPATH=src python3 -m usage_ledger <cmd>
uv tool install --force --no-cache .

# 本机数据快照复现
python3 scripts/probe.py
```
