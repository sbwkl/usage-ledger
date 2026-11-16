# usage-ledger 文档索引

本目录按工作区根目录 `AGENTS.md` 的轻量需求规范组织；项目级开发约定见 [README.md](../README.md#开发约定)（原项目 `AGENTS.md` 已合并）。**功能卡是功能事实源，变更文档是变更事实源，ADR 是决策事实源**；聊天、issue、PR 只做同步。

## 固定目录

| 目录 | 只放什么 | 当前文档 |
|---|---|---|
| [requirements/](requirements/) | 功能卡（REQ） | [REQ-0001 本地 AI 编码工具用量台账](requirements/REQ-0001-usage-ledger.md)、[REQ-0002 测试体系完善](requirements/REQ-0002-testing.md) |
| [changes/](changes/) | 变更文档（CHG） | [CHG-0001 需求 / 变更文档体系对齐](changes/CHG-0001-docs-alignment.md)、[CHG-0002 测试门禁与覆盖率基线](changes/CHG-0002-test-gates.md)、[CHG-0003 修正合并状态](changes/CHG-0003-docs-status.md)、[CHG-0004 HTML 报表空状态与筛选联动修复](changes/CHG-0004-html-report-empty-state-and-filters.md)、[CHG-0005 HTML 报表展示与交互优化](changes/CHG-0005-html-report-display-and-interaction.md)、[CHG-0006 补齐 Qoder 桌面端 turn credits](changes/CHG-0006-qoder-turn-credits.md)、[CHG-0007 Trae CN credits 展示结构对齐 Qoder](changes/CHG-0007-trae-report-parity.md)、[CHG-0008 口径说明改为问号帮助层](changes/CHG-0008-coverage-help-popover.md)、[CHG-0009 明细表填满卡片宽度](changes/CHG-0009-detail-table-fill-width.md)、[CHG-0010 Qoder turn credits 增量去重与历史重复清理](changes/CHG-0010-qoder-incremental-turn-dedup.md)、[CHG-0011 HTML 布尔筛选状态恢复](changes/CHG-0011-html-boolean-state.md)、[CHG-0012 HTML 筛选后的页脚与 Top 8 同步](changes/CHG-0012-html-filter-sync.md)、[CHG-0013 明细合计的来源专用列显示](changes/CHG-0013-html-total-source-columns.md) |
| [adr/](adr/) | 已做出、难回退的决策（ADR） | [ADR-0001 源是唯一事实来源](adr/ADR-0001-source-of-truth-db-as-archive.md)、[ADR-0002 拉取式采集，无常驻进程](adr/ADR-0002-pull-collection-no-daemon.md) |
| [rfcs/](rfcs/) | 跨团队、不可逆、技术不确定的方案（RFC） | 暂无；按需创建，见 [rfcs/README.md](rfcs/README.md) |

## 阅读顺序

- **产品 / 需求**：REQ-0001 §3（当前功能）→ 根目录 [README.md](../README.md) → [ARCHITECTURE.md](ARCHITECTURE.md)
- **开发 / 评审**：REQ-0001 §3（功能与数据源契约）→ §5（当前 AC）→ [ARCHITECTURE.md](ARCHITECTURE.md) → 对应源设计文档 → 本次 CHG
- **测试 / 质量**：[REQ-0002 测试体系完善](requirements/REQ-0002-testing.md) → [tests/](../tests/) → [.github/workflows/test.yml](../.github/workflows/test.yml)
- **排障 / 审计**：REQ-0001 §6（风险与已知缺口）→ [ARCHITECTURE.md](ARCHITECTURE.md) §11 → [PROBE.md](PROBE.md)

## 支撑文档（不属于四类工件）

| 文档 | 定位 | 说明 |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | As-Built | 当前实现如何工作；含已知问题清单 |
| [DESIGN.md](DESIGN.md) | 历史设计稿（v0.4） | 设计沿革与动机；**不再作为当前需求 / AC 事实源** |
| [QODER-DESIGN.md](QODER-DESIGN.md) | Qoder 设计沿革 | token / 活动轨已实现；credits / est 见 QODER-CREDITS-DESIGN |
| [QODER-CREDITS-DESIGN.md](QODER-CREDITS-DESIGN.md) | Qoder credits / est 设计 | 已实现（v0.5.0） |
| [TRAE-CN-DESIGN.md](TRAE-CN-DESIGN.md) | Trae CN 接入设计沿革 | hook 弱估算已实现；credits 以 TRAE-CN-CREDITS-DESIGN 为准 |
| [TRAE-CN-CREDITS-DESIGN.md](TRAE-CN-CREDITS-DESIGN.md) | Trae CN credits 设计 | 已实现（v0.6.0） |
| [CLINE-DESIGN.md](CLINE-DESIGN.md) | Cline 采集设计 | As-Built（v1） |
| [RESEARCH.md](RESEARCH.md) | 竞品调研 | 选型证据 |
| [PROBE.md](PROBE.md) | 本机实测探针 | 数据可得性 / 规格偏差证据 |
| [DISCUSSION.md](DISCUSSION.md) | 讨论纪要 | 决策链与文档修订记录 |

> 设计文档继续放在 `docs/` 根目录，作为支撑材料；不复制进 `requirements/` 或 `changes/`。需求变化先回写 REQ-0001，再按需修订设计文档。

## ID 与变更约定

- ID 按类型在仓库内递增，创建后不复用：`REQ-0001`、`CHG-0001`、`ADR-0001`。
- 下一批可用 ID：`REQ-0003`、`CHG-0014`、`ADR-0003`。
- 新功能 / 跨模块行为变更：先建 CHG，更新对应 REQ 的 AC / 变更索引，再写代码。
- 一次性小修：可以只有极简 CHG（问题、改动、验证、回滚），但必须回链所属模块 / 入口。
- 跨团队、不可逆、技术不确定、影响公共接口 / 数据模型：加 RFC。
- 已做出的难回退架构 / 技术选型：加 ADR；被替代时新建 ADR 并链接旧 ADR，不篡改历史。
- 状态以文档首部为准；代码合并但未部署 / 未验证时仍属“开发中”，不得自行标“已发布”。
