# 废除文档顺序编号规则

| 项 | 内容 |
|---|---|
| 状态 | 已验证 |
| 类型 | 变更文档 |
| 关联规格 | `docs/product-specs/usage-ledger.md` §8 变更追溯索引 |
| 适用目录 | `AGENTS.md`、`README.md`、`tests/test_docs_structure.py` |

## 摘要

废除“新增 REQ / CHG / ADR / RFC 文档必须顺序编号”的规则。历史编号冻结，仅用于追溯；新增文档使用语义化主题路径，状态由目录与文档头决定。

## 理由

顺序编号制造了 NEXT-ID 漂移、索引漏登记、历史硬编码测试与目录语义冲突。文档迁移到 product-specs / design-docs / exec-plans 后，路径和主题已足够表达身份，顺序编号不再提供相应价值。

## 改动

- AGENTS.md：需求先行、提交/PR 引用、文档地图改为语义化路径规则；声明历史编号冻结。
- README.md：删除“下一批 ID”，改为语义化命名规则。
- tests/test_docs_structure.py：删除 next-ID 和历史 CHG 编号硬编码断言，加入“不再要求顺序编号”的结构测试。
- 历史 `CHG-xxxx` / `ADR-xxxx` / `REQ-xxxx` 文件不重命名，验收锚点 `Rxx` 保留。

## 验证

- `python3 -m unittest tests.test_docs_structure -v`
- `python3 -m compileall -q src tests scripts`
- `python3 scripts/check_ac_map.py`
- `python3 scripts/check_test_policy.py`
