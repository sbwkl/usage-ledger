# 设计文档索引

本目录是 `usage-ledger` 的**设计知识库**：收录当前仍有效的源 / 子系统设计、架构决策、RFC、设计历史与核心工程信念。它服务于 agent 的渐进披露：`AGENTS.md` 是地图，根目录 `ARCHITECTURE.md` 是当前实现总图，`docs/product-specs/usage-ledger.md` 是产品行为事实源；本索引负责说明“为什么这样设计、哪些结论仍然有效、哪些已被替代”。

## 状态说明

| 状态 | 含义 |
|---|---|
| current | 当前有效，已与 `usage-ledger.md` / `ARCHITECTURE.md` / 代码核对 |
| partial | 部分有效；必须按 `superseded_by` 指向当前事实源 |
| historical | 历史记录，不作为当前事实或验收标准 |
| proposed | 提案 / RFC，尚未接受 |

## 当前源设计

| 文档 | 领域 | 状态 | 当前事实源 / 代码入口 |
|---|---|---|---|
| [source-designs/CLINE-DESIGN.md](source-designs/CLINE-DESIGN.md) | Cline 采集 | current | `src/usage_ledger/collectors.py`；`ARCHITECTURE.md` §6.7 |
| [source-designs/QODER-DESIGN.md](source-designs/QODER-DESIGN.md) | Qoder token / 活动 | partial | 历史 token 与活动；credits / est 见 `QODER-CREDITS-DESIGN.md` |
| [source-designs/QODER-CREDITS-DESIGN.md](source-designs/QODER-CREDITS-DESIGN.md) | Qoder credits / est | current | `ARCHITECTURE.md` §6.6 |
| [source-designs/TRAE-CN-CREDITS-DESIGN.md](source-designs/TRAE-CN-CREDITS-DESIGN.md) | Trae CN credits | current | `ARCHITECTURE.md` §6.9 |
| [source-designs/TRAE-CN-DESIGN.md](source-designs/TRAE-CN-DESIGN.md) | Trae CN hook 弱估算 / 历史探索 | partial | credits 见 `TRAE-CN-CREDITS-DESIGN.md`；hook 弱估算仍有效 |

## 架构决策 ADR

- [adr/ADR-0001-source-of-truth-db-as-archive.md](adr/ADR-0001-source-of-truth-db-as-archive.md) — 源是唯一事实来源，DB 是归档 / 索引层
- [adr/ADR-0002-pull-collection-no-daemon.md](adr/ADR-0002-pull-collection-no-daemon.md) — 拉取式采集，无常驻进程

## RFC

- [rfcs/README.md](rfcs/README.md) — RFC 触发条件与模板；当前无 RFC

## 历史文档

- [history/v0.4-design-review.md](history/v0.4-design-review.md) — v0.4 历史设计稿，已由 `usage-ledger.md` 与 `ARCHITECTURE.md` 取代
- [history/discussion-log.md](history/discussion-log.md) — 设计讨论纪要，仅用于追溯决策链

## 更新规则

- 新增设计文档必须在本索引登记状态、领域、当前事实源与代码入口。
- 被替代文档不得直接删除事实源指针；在头部写清 `superseded_by`。
- 历史文档不得作为验收标准；当前产品行为以 `../product-specs/usage-ledger.md` 为准，当前实现以 `../../ARCHITECTURE.md` 为准。
