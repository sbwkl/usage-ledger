# CHG-0013 明细合计的来源专用列显示

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../../product-specs/REQ-0001-usage-ledger.md)
关联：[CHG-0007 Trae CN credits 展示结构对齐 Qoder](CHG-0007-trae-report-parity.md)、[REQ-0001 R42](../../product-specs/REQ-0001-usage-ledger.md)

## 1. 摘要

同时选中 Qoder 与 Trae CN 时，合计行按厂商分开，但来源专用列没有来源标记：Qoder 合计行在 Trae 的“会话”列显示 `0`，Trae 合计行在 Qoder 的“免费 credits / 请求 / 免费请求”列显示 `0`。本 CHG 给来源专用列标注所属 source，其他厂商的明细 / 合计单元格显示 `—`。

## 2. 变更理由与证据

- 对应功能卡：REQ-0001 R42（Trae 不提供的字段显示 `—`；两家 credits 不合并）。
- 触发原因：2026-11-16 code review 发现合计行按单位过滤，未按来源过滤。
- 证据：`tableTotals.valuesFor()` 只检查 `column.unit`；合计渲染只比较 `column.unit !== total.unit`，来源专用列在对方合计行以 0 渲染。
- 不做的后果：`0` 会被误读为“真实为零”，与“不适用显示 —”的口径冲突。

## 3. 行为 / AC delta

- 修改 R42：来源专用列（Qoder 免费 credits / 请求 / 免费请求，Trae 会话）在对方来源的明细行和合计行显示 `—`。
- 预期行为：
  - Qoder 合计行的 Trae “会话”列为 `—`。
  - Trae 合计行的 Qoder 免费 / 请求列为 `—`。
  - 同一来源的合法零值仍显示 `0`，不能被误判为不适用。
  - 来源通用列（credits / token 列）行为不变。
- 非目标：不改变合计分组、排序或跨单位规则。

## 4. 影响范围与非目标

- 受影响：`reportColumns()` 的 source 元数据、`tableTotals()`、明细与合计渲染、`HtmlTableLayoutTest`。
- 不影响：后端聚合、CLI 输出、采集。

## 5. 验证与观测

- 自动化：扩展 `HtmlTableLayoutTest.test_table_totals_are_unit_scoped_and_empty_columns_hidden`，覆盖 Qoder / Trae 来源专用列的 `—` 与合法 0。
- 手工：Qoder + Trae、近 7 天报表中，Qoder 合计“会话”为 `—`，Trae 合计“请求”为 `—`；行内同样显示 `—`。
- 结果与证据：
  - 自动化：282 tests / 0 failures / 0 errors / 0 skips。
  - 浏览器：合计行 `Qoder credits 合计 [611.61, 2,591, —]`、`Trae CN credits 合计 [584.10, —, 147]`。

## 6. 回滚方案

- 回滚方式：移除列的 `source` 标记和渲染判断，恢复按单位显示 0。
- 数据兼容：纯展示层，无迁移。
- 回滚验证：两厂商合计行的 0 重新出现，新增断言失败。

## 7. 风险与未决问题

- 风险：来源专用列现在依赖列的 `source` 属性；未来新增来源字段必须同时标注，否则仍按通用列显示。
- 未决：是否把来源专用列也用于图表 tooltip；本 CHG 只改明细表。

## 8. 关联与证据

- 功能卡：REQ-0001 R42。
- commit：`3a121d0`（实现 + 测试）。
- 浏览器证据：`/tmp/review-fix-totals-1440.png`。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（评审反馈） | 2026-11-16 code review finding 4 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 实现 |
| 已验证 | wayne | 2026-11-16 单测与浏览器合计行实测通过 |
