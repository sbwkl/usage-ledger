# CHG-0023 设计文档语义分层与索引重构

| 项 | 内容 |
|---|---|
| ID | CHG-0023 |
| 状态 | 待验证 |
| Owner | wayne |
| 所属模块 / 入口 | `docs/design-docs/`、`AGENTS.md`、`README.md`、`ARCHITECTURE.md`、`tests/test_docs_structure.py` |
| 关联 | [usage-ledger.md](../../product-specs/usage-ledger.md) |

## 1. 摘要

依据 OpenAI Harness Engineering 对 repository knowledge store 的定义，把 `docs/design-docs/` 从“设计文档堆放目录”改造成可索引、带验证状态的设计知识库：分层为 `adr/`、`rfcs/`、`source-designs/`、`history/`，升级 `index.md` 与 `core-beliefs.md`，并为每份设计文档增加文档库状态与当前事实源指针。

## 2. 变更理由与证据

- 用户给出的目录结构来自 OpenAI Harness Engineering；其中明确要求 design documentation 被 catalogued and indexed，包含 verification status 与 core beliefs。
- 当前 `design-docs/` 混合了当前设计、历史设计、ADR、RFC、讨论纪要，缺少状态与当前事实源指针。
- agent legibility 要求所有设计知识仓库本地可发现、可验证、可渐进披露。

## 3. 改动范围

- 移动 ADR 到 `adr/`，源设计到 `source-designs/`，历史设计 / 讨论到 `history/`，RFC 留在 `rfcs/`。
- 重写 `index.md`，建立状态表与当前源设计表。
- 扩展 `core-beliefs.md`，加入仓库是系统记录、渐进披露、机械约束等 agent-first 原则。
- 为所有设计文档添加“文档库状态 / 当前事实源 / 索引”头部。
- 更新全仓引用与结构测试。

## 4. 验证

- 命令：`python3 -m unittest tests.test_docs_structure -v`、`python3 -m compileall -q src tests scripts`、`python3 scripts/check_ac_map.py`、`python3 -m unittest discover -s tests -t .`
- 环境：macOS，Python 3.12，基线 `457ae6d`。
- 结构测试：13 passed；Markdown 本地链接 0 missing。
- 全量快速套件：353 tests / 1 pre-existing failure / 0 skip；失败仍是 `test_report_auto_syncs_new_codearts_messages`（`130 != 230`），非本变更引入。
- 静态检查：`compileall` 通过；`check_ac_map.py` 通过（49 criteria / 154 identifiers）。

## 5. 回滚

按 git revert 与文件移动反向恢复；无运行时行为变化。
