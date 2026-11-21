# CHG-0001 需求 / 变更文档体系对齐

| 项 | 内容 |
|---|---|
| ID | CHG-0001 |
| 类型 | 变更文档 |
| 状态 | 已验证 |
| Owner | wayne |
| 所属模块 / 入口 | `docs/`、`README.md`、`AGENTS.md` |
| 功能卡 | [usage-ledger.md](../../product-specs/usage-ledger.md) |
| 关联 | [ADR-0001](../../design-docs/adr/ADR-0001-source-of-truth-db-as-archive.md)、[ADR-0002](../../design-docs/adr/ADR-0002-pull-collection-no-daemon.md)、[ARCHITECTURE.md](../../../ARCHITECTURE.md) §11、commit `02e8473`（评审修订见后续 CHG-0001 提交） |

> 说明：本变更已通过 [PR #2](https://github.com/sbwkl/usage-ledger/pull/2) 合并 `main`（`5b5f987`，2026-11-15）。文档变更没有部署产物，状态保持“已验证”，不标“已发布”。

> 2026-11-16 后续：项目级 `AGENTS.md` 已合并到 [README.md](../../../README.md#开发约定)；本文保留当时的历史描述与模块范围。

## 摘要

本变更按工作区轻量需求规范建立 usage-ledger 的固定文档体系：新增功能卡 usage-ledger.md、变更记录 CHG-0001、两项 ADR 和文档索引，并把 README / ARCHITECTURE / DESIGN / QODER-DESIGN 对齐到 v0.6.0 当前事实。运行时代码、CLI 行为、数据库 schema 与 HTML 报表均无变化；本次只修正文档事实源和既有漂移。验证证据为全量测试、相对链接检查和文档首部 / 目录核对。

---

## 1. 变更理由与证据

- 工作区规范要求固定目录 `docs/product-specs/`、`docs/exec-plans/completed/`、`docs/design-docs/rfcs/`、`docs/design-docs/`；当前 `docs/` 下没有这些目录，也没有功能卡 / 变更文档。
- [DESIGN.md](../../design-docs/history/v0.4-design-review.md) 仍是 v0.4「待审核」方案稿，其中 `NullStore`、计价、预算告警、WorkBuddy、zstd 等未实现；直接把它当需求事实源会持续误导。
- [README.md](../../../README.md) 的覆盖表把 WorkBuddy 标为已支持，但 `collectors.py` 实际只有 7 个源，README「下一步」也写明需要先安装 WorkBuddy 采集样本。
- [ARCHITECTURE.md](../../../ARCHITECTURE.md) §0 把“设计文档与实现漂移”列为需要审核的现状问题。

---

## 2. 行为 / AC delta

- **运行时代码与 CLI 行为：无变化。** 本变更只整理文档结构、补当前需求事实源，并修正文档漂移。
- 新增文档工件：
  - [usage-ledger.md](../../product-specs/usage-ledger.md)：当前功能卡，含问题 / 证据、目标 / 非目标、As-Built 功能说明（数据源契约 / CLI 命令 / 报表字段 / 存储 / HTML / 调度 / 隐私）、成功指标、R1–R18 EARS 验收、风险与变更索引。
  - [CHG-0001](./CHG-0001-docs-alignment.md)：本变更记录。
  - [ADR-0001](../../design-docs/adr/ADR-0001-source-of-truth-db-as-archive.md)、[ADR-0002](../../design-docs/adr/ADR-0002-pull-collection-no-daemon.md)：两项已做出的架构决策。
  - [docs/design-docs/index.md](../../../README.md)：文档索引与阅读顺序。
  - 项目级 [开发约定](../../../README.md#开发约定)（原 `AGENTS.md`）：把规范落到本项目的文档路径、测试命令、分支流程与下一批 ID。
- 文档修正：
  - README 将 WorkBuddy 改为“未接入（缺样本）”，把“零 UI”改为“零常驻 UI（HTML 为单文件静态报表）”，并修正 `NullStore` 已实现的误导性表述。
  - DESIGN 标注为历史设计稿，指向 usage-ledger.md 与 ARCHITECTURE。
  - ARCHITECTURE 更新代码基线到 main `820a6f2`；在 §0 记录文档漂移已处理，在 §12 记录 #1（DESIGN 历史化）与 #6（未实现项当前不做）已定。
  - QODER-DESIGN 标注 token / activity 已实现，credits / est 以 QODER-CREDITS-DESIGN 为准。
- **AC delta：无新增或删除功能需求。** usage-ledger.md 是 v0.6.0 当前事实的基线，不是新功能。

---

## 3. 影响范围与非目标

### 影响范围

- 仅文档：`docs/product-specs/`、`docs/exec-plans/completed/`、`docs/design-docs/`、`docs/design-docs/rfcs/`、`docs/design-docs/index.md`、`README.md`、`AGENTS.md`，以及 DESIGN / ARCHITECTURE / QODER-DESIGN 的说明性修订。
- 不影响已安装的 `usage` / `usage-ledger` 命令、数据库 schema、采集逻辑或 HTML 报表。

### 非目标

- 不修复 [ARCHITECTURE.md](../../../ARCHITECTURE.md) §11 的 P0-1 / P1-1 / P1-2 / P1-3 / P2 问题。
- 不补写 v0.6.0 之前的历史 CHG；历史以 git log、设计文档和 usage-ledger.md 的测试基线为证据。
- 不搬移现有设计文档；它们继续作为 `docs/` 根目录下的支撑文档。
- 不实现 WorkBuddy、计价、预算告警、`NullStore`、zstd、daemon 或路径哈希。

---

## 4. 验证方式

| 检查 | 命令 / 方法 | 结果 |
|---|---|---|
| 回归测试 | `python3 -m unittest discover -s tests -t .` | **159 tests OK**（2026-11-15） |
| 目录结构 | 检查 `docs/product-specs/`、`docs/exec-plans/completed/`、`docs/design-docs/`、`docs/design-docs/rfcs/` 均存在 | 通过 |
| 文档链接 | 逐项检查新增 / 修改文档中的相对链接目标存在 | 通过 |
| 文档首部 | REQ / CHG / ADR 均含 ID、类型、状态、Owner、关联 | 通过 |
| 功能描述 | usage-ledger.md §3 的源路径 / 命令 / 字段 / 表结构与 v0.6.0 源码逐项核对 | 通过 |
| 运行时回归 | 无代码变更；未重复执行安装 / UI 验收 | 不适用 |

> 说明：本变更没有功能代码，因此“可上线 / 可回滚”主要体现为文档可安全合并与回退；未在真实 CLI / 浏览器上做功能回归。

---

## 5. 回滚方式

- 若已提交：`git revert <commit>`；若未提交：删除新增文档，并还原 README / DESIGN / ARCHITECTURE / QODER-DESIGN 的修订。
- 无数据库迁移、无配置变更、无运行时副作用；回滚不影响已安装 CLI 或历史数据。

---

## 6. 关联

- 功能卡：[usage-ledger.md](../../product-specs/usage-ledger.md)
- 决策：[ADR-0001](../../design-docs/adr/ADR-0001-source-of-truth-db-as-archive.md)、[ADR-0002](../../design-docs/adr/ADR-0002-pull-collection-no-daemon.md)
- 现状问题：[ARCHITECTURE.md](../../../ARCHITECTURE.md) §11
- 使用说明：[README.md](../../../README.md)
- 分支：`feat/req-docs`（从 main 切出）

---

## 7. 变更记录

| 日期 | 状态 | 操作人 | 证据 |
|---|---|---|---|
| 2026-11-15 | 提议 → 就绪 → 开发中 | wayne | 本文件；usage-ledger.md 建立 |
| 2026-11-15 | 开发中 → 已验证 | wayne | 159 tests OK；目录 / 链接 / 首部检查通过；待合并 main |
| 2026-11-15 | 已验证（补充） | wayne | usage-ledger.md §3 补齐 As-Built 功能说明（源契约 / 命令 / 字段 / 存储 / HTML / 调度 / 隐私），与 v0.6.0 源码逐项核对；159 tests OK、117 个相对链接全部可达 |
| 2026-11-15 | 已验证（待 code review） | wayne | 提交 `02e8473` 到 `feat/req-docs` 并合入 `sit`；尚未合并 `main` |
| 2026-11-15 | 已验证（评审修订） | wayne | 补齐 REQ / CHG 摘要、修正 group/world-writable 措辞、登记 commit `02e8473`；159 tests OK，117 links OK；本修订提交见 PR 提交列表 |
