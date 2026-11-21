# CHG-0009 明细表填满卡片宽度

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[usage-ledger.md 本地 AI 编码工具用量台账](../../product-specs/usage-ledger.md)
关联：[CHG-0005 HTML 报表展示与交互](CHG-0005-html-report-display-and-interaction.md)、[usage-ledger.md R45](../../product-specs/usage-ledger.md)

## 1. 摘要

当明细表的自然列宽总和小于卡片内容宽度时，表格仍按自然宽度渲染，右侧留下大块空白。本 CHG 在保持冻结标识列宽和粘性偏移不变的前提下，把卡片剩余宽度平均分给非冻结数据列；自然宽度大于卡片时（如窄屏或宽表）仍保持横向滚动。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：usage-ledger.md G1（在一个视图里回答用量问题）、R27 / R28（明细表布局）。
- 触发原因：用户 2026-11-16 反馈“所有的 Agent 明细部分，每行的右边都留有空白，这是 bug 还是设计”，确认按“把剩余宽度分给非冻结数据列”修复。
- 证据：
  1. 旧逻辑在 `renderDataTable` 中把 `table.style.width` / `minWidth` 固定为所有列自然宽度之和；`STICKY_WIDTHS` 为 96 / 90 / 90 / 170 / 160，数值列 74，文本列 108。
  2. 1440px 下卡片内容宽约 1236px；Qoder / Trae 默认列自然宽度仅 664px，右侧空白约 572px。混合表自然宽度 1272px，已横向滚动，无此问题。
  3. 500px 下卡片内容宽约 436px，自然宽度仍大于容器，横向滚动是预期行为。
- 不做的后果：单选 Qoder / Trae 等列数较少的 Agent 时，明细表持续右空，页面重心失衡。

## 3. 行为 / AC delta

- 新增：R45（剩余宽度分配、冻结列宽不变、窄屏保持横向滚动）。
- 预期行为：
  - 可用宽度大于自然总宽时，表格宽度取可用宽度；仅扩大非冻结列，冻结列宽和 `left` 偏移不变。
  - 剩余宽度在非冻结列间平均分配，像素余数给最后一列，确保列宽之和等于表格宽度。
  - 可用宽度小于或等于自然总宽时，保持自然宽度，不压缩冻结列，继续由 `.table-wrap` 横向滚动。
  - 重绘（切换 Agent、日期、分页、窗口 resize）复用同一计算，无新增状态或持久化字段。
- 非目标：不改列定义、合计行、排序、分页和 sticky 断点；不改 payload 或数据采集。

## 4. 影响范围与非目标

- 受影响：HTML 内联 JS 的列宽计算与 `renderDataTable` 调用参数；`HtmlTableLayoutTest`。
- 不影响：CLI 输出、SQLite 归档、采集与刷新逻辑。
- 兼容性：纯展示层；旧报告不迁移。

## 5. 验证与观测

- 自动化：新增 `test_table_fills_available_width_without_moving_identity_columns`，断言宽屏填满、冻结列宽不变、数据列均衡、窄屏不压缩、无可用宽度时回退自然宽度；全量测试 / AC map / 覆盖率门禁。
- 手工：生成 mixed / qoder / trae-cn 三份报告，在 1440px 与 500px 下测量 `#table-wrap` 与 `#detail-table` 宽度并截图。
- 指标 / 日志：无新增埋点；以 DOM 尺寸和截图为准。
- 结果与证据：
  - 1440px：Qoder / Trae 表格 664px → 1236px，等于卡片内容宽；冻结列宽 `[96, 90, 170, 160]`；两个数据列各 360px；`scrollWidth = clientWidth = 1236`。
  - 500px：Qoder / Trae 表格保持 664px，容器 436px，`scrollWidth 664 > clientWidth 436`，横向滚动保留；冻结列宽不变。
  - 混合表 1440px：自然宽度 1272px > 容器 1236px，行为与修复前一致，仍横向滚动。
  - 全量：278 tests / 0 failures / 0 errors / 0 skips。
- 截图：`/tmp/chg9-qoder-1440.png`、`/tmp/chg9-qoder-500.png`、`/tmp/chg9-trae-1440.png`、`/tmp/chg9-trae-500.png`、`/tmp/chg9-mixed-1440.png`、`/tmp/chg9-mixed-500.png`。

## 6. 回滚方案

- 回滚方式：删除 `tableColumnWidths` / `frozenWidth`，恢复 `renderDataTable` 中逐列自然宽度求和并写入 table width。
- 数据兼容：纯展示层，无迁移。
- 回滚验证：生成单选 Qoder 报告，确认右侧空白恢复，原有表布局测试通过。

## 7. 风险与未决问题

- 风险：数据列较少时，平均分配会让数值列明显变宽，数值右对齐留下列内空白。缓解：优先保证表格与卡片边界对齐；若后续需要更紧凑的列内布局，另建 CHG 调整对齐或列权重。
- 风险：`clientWidth` 在隐藏容器中为 0。缓解：仅在实际渲染且宽度可用时扩展；不可用时回退自然宽度。
- 未决：是否按列内容权重而非平均分配；本 CHG 采用简单、可测试的平均分配。

## 8. 关联与证据

- 功能卡：[usage-ledger.md](../../product-specs/usage-ledger.md) R45。
- commit：`26f30ad`（实现 + 测试）。
- 截图 / 测试报告：`/tmp/chg9-report.html`、`/tmp/chg9-qoder.html`、`/tmp/chg9-trae.html` 及上述 PNG。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（待评审） | 2026-11-16 用户反馈 + 旧表格宽度逻辑 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 按 TDD 实现 |
| 已验证 | wayne | 2026-11-16 278 tests / 0 skip、AC map 45/93、覆盖率 93.3%；1440px 填充与 500px 滚动实测通过 |
