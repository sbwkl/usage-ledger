# CHG-0021 文档工件迁移到规范目录

| 项 | 内容 |
|---|---|
| ID | CHG-0021 |
| 状态 | 已验证 |
| Owner | wayne |
| 所属模块 / 入口 | `AGENTS.md`、`docs/`、`tests/test_docs_structure.py`、`tests/ac_map.json` |
| 关联 | [usage-ledger.md](../../product-specs/usage-ledger.md) |

## 1. 摘要

把规范外的 `docs/requirements/`、`docs/changes/`、`docs/adr/`、`docs/rfcs/` 工件迁入规范目录：REQ → `docs/product-specs/`，CHG → `docs/exec-plans/completed/`，ADR / RFC → `docs/design-docs/`。无运行时行为变化。

## 2. 变更理由与证据

- 用户明确要求 docs 目录只保留规范列出的文件夹，并将已有文档放入最合适的新目录。
- 规范外目录仍被 AGENTS / README / AC 映射引用，需同步迁移而非删除。

## 3. 改动范围

- 移动 REQ / CHG / ADR / RFC 工件并清理旧目录。
- 更新全仓路径引用、AGENTS 文档地图、`tests/ac_map.json`。
- 扩展 `tests/test_docs_structure.py` 钉住严格目录集合与新工件位置。

## 4. 验证

- 命令：`python3 -m unittest tests.test_docs_structure -v`、`python3 -m compileall -q src tests scripts`、`python3 scripts/check_ac_map.py`、`python3 -m unittest discover -s tests -t .`
- 环境：macOS，Python 3.12，基线 `f800a9a`。
- 结构测试：9 passed；Markdown 本地链接 0 missing。
- 全量快速套件：344 tests / 1 pre-existing failure / 0 skip；失败仍是 `test_report_auto_syncs_new_codearts_messages`（`130 != 230`），已在干净基线复现，非本变更引入。
- 静态检查：`compileall` 通过；`check_ac_map.py` 通过（路径已切到 `docs/product-specs/usage-ledger.md`）。

## 5. 回滚

按 git revert 与文件移动反向恢复；无数据迁移。
