# CHG-0020 文档结构调整与开发流程入规

| 项 | 内容 |
|---|---|
| ID | CHG-0020 |
| 状态 | 已验证 |
| Owner | wayne |
| 所属模块 / 入口 | `AGENTS.md`、`ARCHITECTURE.md`、`docs/`、`tests/test_docs_structure.py` |
| 关联 | [usage-ledger.md](../../product-specs/usage-ledger.md) |

## 1. 摘要

按用户指定结构重排文档树，并把新开发流程维护进 `AGENTS.md`。无运行时行为变化。

## 2. 变更理由与证据

- 用户给出必须遵守的目录树与开发流程。
- 旧结构文档地图与物理结构不一致；本次迁移让事实源、设计文档、计划、参考资料、生成物各归其位。

## 3. 改动范围

- `docs/ARCHITECTURE.md` → `ARCHITECTURE.md`。
- 设计稿 / 讨论 → `docs/design-docs/`；调研 / 探针 → `docs/references/`。
- 新增领域宪章、索引、技术债账本、DB schema 快照、产品规格索引。
- 更新全仓引用、`AGENTS.md` 文档地图与开发流程。
- 新增 `tests/test_docs_structure.py`。

## 4. 验证

- 命令：`python3 -m unittest tests.test_docs_structure -v`、`python3 -m compileall -q src tests scripts`、`python3 scripts/check_ac_map.py`、`python3 -m unittest discover -s tests -t .`
- 环境：macOS，Python 3.12（仓库支持 3.11–3.14），commit `4abafdd` 基线上的 `feat/docs-restructure`。
- 结构测试：4 passed。
- 全量快速套件：344 tests / 1 pre-existing failure / 0 skip。失败项是 `tests.test_cli.CodeArtsCliTest.test_report_auto_syncs_new_codearts_messages`（`130 != 230`）；已在 detached HEAD `4abafdd` 的干净基线复现，非本变更引入。
- 静态检查：`compileall` 通过；`check_ac_map.py` 通过（49 criteria / 154 identifiers）。
- 覆盖率：未生成新报告，本变更无运行时代码行为变化（仅 `trae_auth.py` 注释路径同步）。

## 5. 回滚

按 git revert 与文件移动反向恢复；无数据迁移。
