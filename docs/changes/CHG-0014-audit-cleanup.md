# CHG-0014 审计清理：重复键、死代码与过期文档引用

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`src/usage_ledger/pricing.py`、`src/usage_ledger/html_report.py`、`README.md`、`docs/ARCHITECTURE.md`
功能卡：[REQ-0001](../requirements/REQ-0001-usage-ledger.md)（无 AC 变更）

## 问题

2026-11-17 全项目审计（282 tests / 覆盖率 93.4% / 三门禁全绿基线）发现 4 处零行为影响的确定问题：

1. `pricing.py` ALIASES 中 `"minimax/minimax-m3.1-flash:free"` 重复定义（第 7 行与第 24 行，值相同）；字典字面量静默去重，无测试护栏。
2. `html_report.py` `buildStackBuckets` 中 `bucket.label = weekly ? bucket.start.slice(5) : bucket.start.slice(5)` 两个分支完全相同，是死三元表达式。
3. `README.md` 变更日志引用过期：第 98 行仍写「CHG-0001 ~ CHG-0007」并把 0006/0007 称为「本次修复」；第 65 行括注仅 0004/0005 已验证。实际 CHG-0001 ~ 0013 全部存在且已验证。
4. `docs/ARCHITECTURE.md` §3 模块表行数漂移：`trae_auth.py` 写 368（实际 362）、`trae_credits.py` 写 512（实际 517），且缺 `qoder_models.py` 一行。

## 改动

- 删除 `pricing.py` 第 24 行重复键；新增 `tests/test_pricing.py` 用 AST 断言 ALIASES 无重复键（先失败后通过）。
- `html_report.py` 死三元简化为 `bucket.label = bucket.start.slice(5)`；行为不变，由既有 Node 图表测试覆盖。
- 修正 `README.md` 两处过期引用；同步「下一批可用 ID」为 `CHG-0015`（README 与 docs/README.md）。
- 修正 ARCHITECTURE §3 两处行数并补 `qoder_models.py` 行；§9 测试表补 `tests/test_pricing.py`。
- 登记本 CHG 到 REQ-0001 §8 变更索引与 docs/README.md 索引。
- 把审计新发现登记到 ARCHITECTURE §11 P2-10 ~ P2-15（只登记，不修复；修复各自需独立 CHG）。

不改动任何运行时行为、数据口径或 AC；不触碰 ARCHITECTURE §11 的 P0/P1/P2（各自需独立 CHG）。

## 验证

环境：macOS 27.0.1（Apple Silicon）、Python 3.14.6、Node v24.16.0；分支 `feat/audit-cleanup`，基线 main `826c7a0`。

- TDD：`python3 -m unittest tests.test_pricing` 修复前失败（重复键 `minimax/minimax-m3.1-flash:free`），删除重复键后通过。
- `python3 -m unittest discover -s tests -t .`：284 tests，0 failures / 0 errors / 0 skips（基线 282 + 新增 2）。
- `uv run --with coverage python -m coverage run --branch --source=src/usage_ledger -m unittest discover -s tests -t .` + `uv run --with coverage python -m coverage json -o coverage.json` + `python3 scripts/check_coverage.py coverage.json`：TOTAL 93.4%（阈值 85%，基线 80.9%，与修复前持平）；store 96.7% / collectors 95.3% / cli 93.6% / scheduler 98.2%，全部 ok。
- `python3 scripts/check_test_policy.py`：284 tests / 0 skip，1.689s（预算 5s），通过。
- `python3 scripts/check_ac_map.py`：REQ-0001 45 criteria / 98 mapped identifiers，通过（无 AC 变更）。
- HTML 死三元简化由既有 Node 图表行为测试覆盖（0 skip 即全部执行）。

## 回滚

还原本 CHG 涉及文件即可；无数据迁移、无接口变化。重复键与死三元的删除不改变任何输出。