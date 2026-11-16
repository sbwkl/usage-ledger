# CHG-0011 HTML 布尔筛选状态恢复

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：[CHG-0005 HTML 报表展示与交互](CHG-0005-html-report-display-and-interaction.md)、[REQ-0001 R37](../requirements/REQ-0001-usage-ledger.md)

## 1. 摘要

HTML 报表把 `shadow` / `focusRange` 以布尔值写入 URL，读回时只接受原生 `true` 或字符串 `"1"`，导致 `"true"` 被当成 false。刷新后估算和聚焦开关恢复为关闭。本 CHG 统一布尔解析，保留 localStorage 与旧链接兼容。

## 2. 变更理由与证据

- 对应功能卡：REQ-0001 R37（筛选状态 URL / localStorage 往返）。
- 触发原因：2026-11-16 code review 发现 URLSearchParams 序列化为 `"true"`，恢复逻辑不识别。
- 证据：`stateSnapshot()` 返回原生布尔；`persistState()` 使用 `URLSearchParams.set`，URL 中为 `shadow=true` / `focusRange=true`；`applyPersistedState()` 只接受 `true` 或 `"1"`。
- 不做的后果：浏览器刷新或分享链接后，估算与聚焦范围被静默关闭，URL 与页面状态不一致。

## 3. 行为 / AC delta

- 修改 R37：URL / localStorage 中的布尔字段接受原生 `true`、`1`、`"1"`、`"true"`；其他值按 false。
- 预期行为：
  - 打开估算或聚焦后刷新，开关保持打开，日期 / 页面状态与刷新前一致。
  - 旧版 `"1"` 链接和 localStorage 布尔值继续有效。
  - 无效值仍安全回退为 false。
- 非目标：不改变 URL 字段格式；不移除 localStorage 回退。

## 4. 影响范围与非目标

- 受影响：`persistedFlag()`、`applyPersistedState()`、`HtmlStatePersistenceTest`。
- 不影响：数据查询、筛选逻辑、图表和表格。

## 5. 验证与观测

- 自动化：新增 `HtmlStatePersistenceTest.test_url_boolean_state_round_trip`，覆盖 URLSearchParams 的 `"true"` / `"false"`、原生布尔和旧版 `"1"`。
- 手工：1440px 下打开估算与聚焦，刷新后 `#shadow` / `#focus-range` 均保持勾选，起始 / 结束日期保持。
- 结果与证据：
  - 自动化：282 tests / 0 failures / 0 errors / 0 skips。
  - 浏览器：`shadow=true` 刷新后仍为 true；`focusRange=true` 刷新后仍为 true，日期保持 `2026-06-05..2026-11-16`。

## 6. 回滚方案

- 回滚方式：恢复 `raw.shadow === true || raw.shadow === "1"` 的解析。
- 数据兼容：URL / localStorage 无需迁移。
- 回滚验证：刷新后开关恢复关闭，新增测试失败。

## 7. 风险与未决问题

- 风险：接受 `"true"` 后，手工构造的异常字符串仍可能被忽略；当前按严格白名单处理。
- 未决：无。

## 8. 关联与证据

- 功能卡：REQ-0001 R37。
- commit：`3a121d0`（实现 + 测试）。
- 浏览器证据：`/tmp/review-fix-report.html`；验证输出见本次文档提交。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（评审反馈） | 2026-11-16 code review finding 2 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 实现 |
| 已验证 | wayne | 2026-11-16 单测与刷新恢复实测通过 |
