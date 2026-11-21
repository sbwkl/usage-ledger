# CHG-0024 PR #13 审核意见修复

| 项 | 内容 |
|---|---|
| ID | CHG-0024 |
| 状态 | 已验证 |
| Owner | wayne |
| 所属模块 / 入口 | `README.md`、`docs/product-specs/usage-ledger.md`、`docs/design-docs/`、`tests/test_docs_structure.py` |
| 关联 | [usage-ledger.md](../../product-specs/usage-ledger.md) |

## 1. 摘要

修复 PR #13 审核发现的三类轻微问题：README / 产品规格中的状态与流程漂移、两个标签与链接目标不一致、partial 设计文档缺少 `superseded_by` 元数据。

## 2. 改动范围

- README 下一批 CHG ID 改为 `CHG-0024`，集成流程改为 `tmp/integration-*` 临时分支。
- 产品规格中 CHG-0020 状态改为「已验证」，并登记 CHG-0020~0024。
- 修正 `docs/design-docs/index.md` 标签链接目标。
- 为 QODER / TRAE partial 设计文档补充 `superseded_by`。
- 扩展 `tests/test_docs_structure.py` 钉住审核修复。

## 3. 验证

- `python3 -m unittest tests.test_docs_structure -v`：14 passed
- Markdown 本地链接：0 missing
- `python3 -m compileall -q src tests scripts`：通过
- `python3 scripts/check_ac_map.py`：49 criteria / 154 identifiers passed
- `python3 -m unittest discover -s tests -t .`：354 tests / 1 pre-existing failure / 0 skip
  - `test_report_auto_syncs_new_codearts_messages`（`130 != 230`）已在干净基线复现，非本变更引入

## 4. 回滚

按 git revert 恢复；无运行时行为变化。
