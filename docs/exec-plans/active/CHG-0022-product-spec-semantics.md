# CHG-0022 产品规格语义重构

| 项 | 内容 |
|---|---|
| ID | CHG-0022 |
| 状态 | 待验证 |
| Owner | wayne |
| 所属模块 / 入口 | `ARCHITECTURE.md`、`docs/product-specs/`、`AGENTS.md`、`tests/ac_map.json` |
| 关联 | [usage-ledger.md](../../product-specs/usage-ledger.md) |

## 1. 摘要

把旧 REQ 文档从“需求管理工件”调整为符合 product-specs 语义的产品规格：REQ-0001 转为 `usage-ledger.md`；REQ-0002 融入 `ARCHITECTURE.md` §9 测试体系。保留所有 R 编号和验收内容，确保 AC 门禁不中断。

## 2. 变更理由与证据

- 用户确认 REQ-0002 属于架构的一部分，应融入 `ARCHITECTURE.md`。
- 用户同意 REQ-0001 应按 product-specs 语义重构。
- 旧文档路径迁移后正文仍自称为 REQ / 需求卡，目录语义与文档语义不一致。

## 3. 改动范围

- 重命名并重构 REQ-0001 为 `docs/product-specs/usage-ledger.md`。
- 将 REQ-0002 内容合并进 `ARCHITECTURE.md` §9，删除独立 REQ-0002 文件。
- 更新 AGENTS、README、索引、全仓引用、`tests/ac_map.json`。
- 扩展 `tests/test_docs_structure.py` 钉住新语义。

## 4. 验证

- 命令：`python3 -m unittest tests.test_docs_structure -v`、`python3 -m compileall -q src tests scripts`、`python3 scripts/check_ac_map.py`、`python3 -m unittest discover -s tests -t .`
- 环境：macOS，Python 3.12，基线 `8fc7132`。
- 结构测试：9 passed；Markdown 本地链接 0 missing。
- 全量快速套件：349 tests / 1 pre-existing failure / 0 skip；失败仍是 `test_report_auto_syncs_new_codearts_messages`（`130 != 230`），非本变更引入。
- 静态检查：`compileall` 通过；`check_ac_map.py` 通过（49 criteria / 154 identifiers）。

## 5. 回滚

按 git revert 与文件重命名反向恢复；无运行时行为变化。
