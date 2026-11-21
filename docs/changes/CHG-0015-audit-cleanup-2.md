# CHG-0015 审计清理（二）：死代码、过期注释与测试文档校准

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`src/usage_ledger/collectors.py`、`src/usage_ledger/trae_auth.py`、`scripts/probe.py`、`tests/test_collectors.py`、`tests/test_trae_credits.py`、`README.md`、`ARCHITECTURE.md`
功能卡：[REQ-0001](../requirements/REQ-0001-usage-ledger.md)（无 AC 变更）
关联：CHG-0014（同主题前序清理）、[ARCHITECTURE.md](../../ARCHITECTURE.md) §11 P2-9

## 1. 摘要

CHG-0014 完成审计清理后，复核仍发现 4 处零行为影响的死代码 / 未用导入 / 过期注释，且 `ARCHITECTURE.md` §9 测试表自 CHG-0002 起未随测试增长更新；本变更清除这些残留并把文档校准到实测值，不改变任何运行时行为、数据口径或 AC。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：无 AC 变更；属 REQ-0001 持续维护中的技术债清理。
- 触发原因（缺陷/反馈/数据/技术债）：2026-11-17 全项目审计（CHG-0014）后的二次复核。
- 证据：
  1. `src/usage_ledger/collectors.py` `scan_qoder_transcripts`：`max_ts` 赋值后无任何读取点（全仓库仅 `.pyc` 命中）。
  2. `scripts/probe.py` `scan_codex`：`models = []` 从未 `append`，且被 `aggregate` 内同名局部变量遮蔽；注释 `(ts, cum, last)` 与元组实际 4 位（含 `model`）不符。
  3. `src/usage_ledger/trae_auth.py` `load_storage_credential`：`info = _check_storage_file(target)` 的返回值未被使用。
  4. 未用导入：`tests/test_collectors.py` 的 `time`、`patch`；`tests/test_trae_credits.py` 的 `stat`、`WindowTooLarge`（该类仅在 `trae_credits.py` 内部使用）。
  5. 文档漂移：`README.md` 状态行仍写 282 tests（CHG-0014 正文已写 284）；`ARCHITECTURE.md` §3 的 `collectors.py` / `probe.py` 行数、§9 测试表（缺 `test_collectors_edges.py` / `test_cli_output.py` / `test_aggregation.py`，且 `test_store` / `test_html` / `test_scheduler` 计数过期，总数 282）与实测不一致。
- 不做的后果：死代码与未用导入长期误导排障；文档测试计数失真，降低审计基线可信度。

## 3. 行为 / AC delta

- 新增：无。
- 修改：无。
- 删除：无。
- 无正式 AC 时，写预期行为变化：无运行时行为变化；`probe.py` 事件元组仍携带 `model` 并在 `probe.py:294` 消费，删除的只是未使用的独立列表与过期注释。

## 4. 影响范围与非目标

- 受影响模块/接口/数据/用户：无运行时接口、数据或用户可见变化；仅触及采集器内部死变量、探针注释、测试导入与文档。
- 本次明确不做：
  - 不修复 ARCHITECTURE §11 的 P2-10 ~ P2-15（另行立项）。
  - P2-2 中与本次重叠的 `max_ts` 随之关闭；`price_override` 表与 `open_store()` 仍保留，不在本变更处理。
  - 不引入 ruff / pyflakes 等 lint 门禁（防止未用导入回归需独立 CHG）。
  - 不新增或修改任何 AC、CLI 参数、SQLite schema、HTML 报表行为。
- 兼容性与迁移：无数据迁移、无配置变化。

## 5. 验证与观测

环境：macOS（Apple Silicon）、Python 3.14.6、Node v24.16.0；分支 `feat/audit-cleanup-2`，基线 main `6f33ceb`。

- 死代码核对：`grep -rn "max_ts" src scripts tests` 仅命中 `__pycache__`；`grep -rn "WindowTooLarge" src tests scripts` 仅命中 `trae_credits.py` 的定义与抛出；`wc -l` 实测 `collectors.py` = 1352、`probe.py` = 520。
- 测试文档核对：逐文件 `grep -c "def test_"` 合计 284，与 §9 表内合计一致。
- 自动化测试：
  - `python3 -m unittest discover -s tests -t .`：284 tests，0 failures / 0 errors / 0 skips，1.683s。
  - `uv run --with coverage python -m coverage run --branch --source=src/usage_ledger -m unittest discover -s tests -t .` + `python3 scripts/check_coverage.py coverage.json`：TOTAL 93.4%（阈值 85%，与 CHG-0014 持平）；store 96.7% / collectors 95.3% / cli 93.6% / scheduler 98.2%，全部 ok。
  - `python3 scripts/check_test_policy.py`：284 tests / 0 skip，2.008s（预算 5s），通过。
  - `python3 scripts/check_ac_map.py`：REQ-0001 45 criteria / 98 identifiers，通过（无 AC 变更）。
- 手工验证：无需浏览器或真实凭证；本次不触碰网络、凭证、SQLite 写入路径。
- 结果与证据链接：本 CHG 验证节；分支 `feat/audit-cleanup-2`。

## 6. 回滚方案

- 回滚方式：`git revert` 本 CHG 的提交，或还原本 CHG 涉及文件。
- 数据/配置兼容：无数据迁移、无接口变化，回滚无兼容问题。
- 回滚验证：回滚后 `python3 -m unittest discover -s tests -t .` 应仍为 284 tests / 0 skip。

## 7. 风险与未决问题（按需）

- 风险：低。所有删除项均经全仓库检索确认无读取点，且 284 tests 全绿。
- 未决问题：仓库仍无 lint 门禁，未来仍可能回归未用导入；P2-10 ~ P2-15 未修复。
- 处理方式：留待独立 CHG；本变更不扩大范围。

## 8. 关联与证据

- RFC/ADR：无。
- issue/PR（如有）：无；分支 `feat/audit-cleanup-2`。
- commit：本变更提交（分支 `feat/audit-cleanup-2`）。
- release：无（文档 / 死代码变更，无部署产物）。
- 日志/截图/测试报告：见 §5。

## 9. 变更记录

| 状态 | 操作人 | 证据/链接 |
|---|---|---|
| 开发中 | wayne | 2026-11-20 迁移到 `feat/audit-cleanup-2` worktree，应用 4 处死代码清理与文档校准 |
| 已验证 | wayne | 2026-11-20 284 tests / 0 skip、覆盖率 93.4%、三门禁通过 |