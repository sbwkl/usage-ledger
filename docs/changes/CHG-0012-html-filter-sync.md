# CHG-0012 HTML 筛选后的页脚与 Top 8 同步

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：[CHG-0005 HTML 报表展示与交互](CHG-0005-html-report-display-and-interaction.md)、[CHG-0008 口径说明改为问号帮助层](CHG-0008-coverage-help-popover.md)、[REQ-0001 R30 / R38](../requirements/REQ-0001-usage-ledger.md)

## 1. 摘要

筛选变更后，帮助层中的“本页”行数仍显示初始化时的值；Top 8 点击模型 / 项目时也没有走下拉筛选的聚焦重算和选项重建流程。本 CHG 让页脚随每次 `renderAll()` 刷新，并让 Top 8 的维度选择复用同一刷新顺序。

## 2. 变更理由与证据

- 对应功能卡：REQ-0001 R30（页脚区分库内 / 本页）、R38（聚焦有数据区间）。
- 触发原因：2026-11-16 code review 发现两处更新路径不一致。
- 证据：
  1. `renderFooter()` 只在初始化时调用一次；`renderAll()` 调用 `renderReport()`，不刷新页脚。
  2. `pickModel()` / `pickProject()` 只设置 state 并 `renderAll()`；下拉处理器额外调用 `refreshFocusAfterFilterChange()` 和 `rebuildDimensionSelects()`。
- 不做的后果：筛选后帮助层行数与表格不一致；开启聚焦后点击 Top 8，日期范围和模型 / 项目选项可能停留在旧集合。

## 3. 行为 / AC delta

- 修改 R30：页脚“本页”明细 / 活动计数随筛选变化刷新。
- 修改 R38：Top 8 点击模型 / 项目与下拉筛选走相同的聚焦重算和选项重建顺序。
- 预期行为：
  - 修改 Agent、日期、模型、项目或搜索后，帮助层中的本页行数即时更新。
  - 聚焦开启时点击 Top 8，日期范围收缩到新筛选的有数据区间，模型 / 项目选项同步重建。
  - 再次点击同一项取消筛选，行为一致。
- 非目标：不改 Top 8 排名口径、不分页。

## 4. 影响范围与非目标

- 受影响：`renderAll()`、`pickModel()`、`pickProject()`、相关 JS 测试。
- 不影响：筛选状态持久化、表格、图表、采集。

## 5. 验证与观测

- 自动化：`HtmlFocusRangeTest.test_top8_dimension_pick_refreshes_focus_and_selects` 断言调用顺序；`test_footer_refreshes_after_filters` 断言 `renderAll()` 调用页脚。
- 手工：1440px 下将帮助层保持打开，点击 Top 8 模型；页脚本页计数从 445 行明细 / 140 行活动更新为 12 / 10，日期切换到该模型的有数据区间。
- 结果与证据：
  - 自动化：282 tests / 0 failures / 0 errors / 0 skips。
  - 浏览器：`top8 click` 后 `#model=space-bunny-free`，日期 `2026-10-07..2026-10-18`，页脚计数同步变化。

## 6. 回滚方案

- 回滚方式：移除 `renderAll()` 中的 `renderFooter()`，移除 Top 8 的两个刷新调用。
- 数据兼容：纯展示层，无迁移。
- 回滚验证：页脚保持旧值，Top 8 测试失败。

## 7. 风险与未决问题

- 风险：每次重绘都重建页脚说明，长文本节点会被重新创建。当前帮助层默认关闭，开销可接受。
- 未决：是否把页脚拆成只更新计数的轻量路径；本 CHG 先保持一致优先。

## 8. 关联与证据

- 功能卡：REQ-0001 R30 / R38。
- commit：`3a121d0`（实现 + 测试）。
- 浏览器证据：`/tmp/review-fix-report.html`、`/tmp/review-fix-1440.png`。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（评审反馈） | 2026-11-16 code review findings 3 / 5 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 实现 |
| 已验证 | wayne | 2026-11-16 单测与浏览器筛选实测通过 |
