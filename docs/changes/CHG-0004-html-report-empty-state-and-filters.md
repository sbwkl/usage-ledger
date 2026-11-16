# CHG-0004 HTML 报表空状态与筛选联动修复

类型：CHG
状态：开发中
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：[CHG-0005 HTML 报表展示与交互优化](CHG-0005-html-report-display-and-interaction.md)、[REQ-0001 §3.6](../requirements/REQ-0001-usage-ledger.md)

## 1. 摘要

修复 HTML 报表在“数据日期早于浏览器当天”、区间为空、活动图/活动表、模型/项目筛选上的 6 类误导行为：日期预设锚定数据截止日、空区间只显示一个空状态、Trae 区分“区间无数据 / 未同步”、活动图使用完整日期轴、活动表排序真实可用、维度选项随日期/搜索联动且 chip 与 KPI 同口径；同时把初始范围默认改为近 7 天（截至数据日，保留“全部”预设）。不改变 token / credits / est / activity 分轨与“任何两轨都不相加”的口径。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：REQ-0001 G1（统一台账、明确标注口径）、R8（活动仅 Qoder 且不参与计算）、R15（HTML 边界标注）。
- 触发原因：2026-11-16 对 2026-11-15 生成的报告做 1440px / 500px 实际使用，以下问题均可复现。
- 证据（报告：范围 `2026-06-01 ~ 2026-11-15`，generated `2026-11-15T08:00:38+08:00`；308 token 行、122 credit 行、8 Trae est 行、144 activity 行 / 84 活跃日、200 Trae 会话）：

1. **空区间误导**：点击“今日”（2026-11-16）后 17 张 KPI 全 0、三张图空白、主表与活动表 0 行；Trae KPI 显示“未同步”，同屏状态条仍写“已刷新 · 200 会话”，额度卡仍显示 `2,520 credits`。根因是预设用浏览器 `TODAY` 而非 `DATA_UNTIL`（[html_report.py:602](../../src/usage_ledger/html_report.py#L602)、[html_report.py:1026](../../src/usage_ledger/html_report.py#L1026)）；Trae KPI 在 `!rows.length` 时直接走“未同步”（[html_report.py:1366](../../src/usage_ledger/html_report.py#L1366)）。
2. **活动图时间轴压缩**：144 行活动只覆盖 84 个活跃日，`2026-07-09 → 2026-08-22` 的 44 天空档在图上表现为相邻柱；token / credits 图按完整日期枚举，同一日期在两张图上的横坐标不一致。根因是活动图只取 `byDay.keys()`（[html_report.py:2485](../../src/usage_ledger/html_report.py#L2485)）。
3. **活动表假排序**：9 个表头是 `<button class="th-btn">`，没有监听器、没有 `aria-sort`；点击日期、工具调用、运行时长均不改变行序（[html_report.py:2655](../../src/usage_ledger/html_report.py#L2655)）。
4. **维度筛选不联动**：把范围收窄到 15 天（103 行）后，模型下拉仍有 38 项、项目下拉仍有 40 项，包含大量 0 行选项；选中后得到空表且不会回退。日期变化只 `renderAll()`，不重建下拉（[html_report.py:1041](../../src/usage_ledger/html_report.py#L1041)）；`dimensionRows()` 只按 Agent 取数（[html_report.py:836](../../src/usage_ledger/html_report.py#L836)）。
5. **chip 与 KPI 口径不一致**：近 7 天 KPI 总 Token 为 `142.83M`，但顶部 chip 仍显示全时段 `claude 382.39M`、`codex 752.94M`；chip 用全量 `navTotal()`（[html_report.py:855](../../src/usage_ledger/html_report.py#L855)），且没有“全部时间”标签。
6. **“全选”语义不完整**：“全选”清空模型 / 项目但保留搜索；“重置筛选”清空全部，两个动作边界不一致（[html_report.py:915](../../src/usage_ledger/html_report.py#L915)、[html_report.py:1105](../../src/usage_ledger/html_report.py#L1105)）。

- 不做的后果：快照报告在生成次日进入“全 0 但仍有数字”的矛盾状态；活动图与 token 图无法按日期对齐；用户会误以为活动表可排序、chip 数字是当前区间；窄化筛选后得到空表却不知道原因。
- 用户补充需求（2026-11-16）：默认时间范围改为近 7 天，不再默认全量；这是对 REQ-0001 §3.6 “默认取全部数据覆盖”的 AC 变更，实现时需同步 §3.6 与 §5。近 7 天按 `DATA_UNTIL` 倒推 6 天（含端点），保留“全部”预设。

## 3. 行为 / AC delta

> 拟新增 REQ-0001 §5 的 R19–R26 与 R39。**当前阶段不写入 REQ §5 与 `tests/ac_map.json`**：仓库门禁要求每条 R 至少映射一个真实存在的测试（[scripts/check_ac_map.py](../../scripts/check_ac_map.py)），而实现与测试尚未开始。进入“开发中”时先把 R19–R26、R39 写入 REQ §5，并在同一 CHG 内补齐 `tests/ac_map.json` 映射；在此之前以本节为 AC 事实源。

- **R19**：When the report is opened after the data-until date, the system shall anchor the “最新 / 7 / 30 / 90 天” presets and the date pickers to `DATA_UNTIL`, display “数据截至 YYYY-MM-DD”, and reject or clamp dates after `DATA_UNTIL`; the preset previously labeled “今日” shall be labeled “最新”.
- **R20**：While Trae CN is selected and the current range has no Trae credit rows but cached credit data exists outside the range, the system shall show “当前区间无 Trae credits” instead of “未同步”; it shall show “未同步” only when no credit cache exists, and “刷新失败（使用缓存）” only when refresh failed and cache is being used.
- **R21**：When the current range has no token, credit, estimate, or activity rows, the system shall render one page-level empty state, hide zero-only KPI blocks, blank charts, the empty main table, and the activity block; a quota snapshot shown in this state shall be labeled “最新快照，与区间无关”.
- **R22**：When the activity chart renders for a selected range, the system shall use the same full-date buckets as the token / credits charts, plot zero for days without activity, and display “活跃 N 天 / 共 M 天” coverage; it shall not compress gaps by enumerating only days with data.
- **R23**：When a user activates an activity table column header, the system shall sort rows by that column in ascending / descending order and expose `aria-sort`; if a column is not sortable, the header shall be a plain `th` without button styling.
- **R24**：When the date range or search changes, the system shall rebuild model and project options from rows matching all other active filters, show each option’s row count, exclude zero-row options, and clear a selected value that no longer matches; rebuilding on search input shall be debounced.
- **R25**：While a date range is active, agent chips shall show totals for the current range and use the same unit / scope as the KPI blocks; if all-time totals are kept, the chip label shall explicitly say “全部时间”.
- **R26**：When the user activates “全选”, the system shall only change agent selection and shall not clear model, project, or search; “重置筛选” shall clear all filters including search.
- **R39**：When the report loads without a valid persisted filter state, the system shall set the initial range to the last 7 calendar days ending at `DATA_UNTIL` (inclusive), clamp the start to `DATA_SINCE` when fewer than 7 days exist, keep the “全部” preset available, and apply the same range to all unit panels; a valid persisted state shall take precedence over the default.

边界与异常：`DATA_UNTIL` 为空时，“最新”回退到浏览器当天并显示“无数据”；日期选择器夹紧后不得出现未来日期；默认近 7 天没有任何数据时，显示 R21 的空状态并提示切换到“全部”，不得把缺失显示成 0；`DATA_UNTIL` 早于浏览器当天时，默认区间仍以 `DATA_UNTIL` 为终点（快照语义）；Trae 无缓存且刷新成功但无数据时显示“无 credits 数据”，不得伪造 0；活动表无行时表头也不渲染；维度下拉在 0 选项时显示“当前筛选无模型 / 项目”而不是空白控件。

## 4. 影响范围与非目标

- 受影响：`src/usage_ledger/html_report.py` 的日期状态、Trae KPI 文案、活动图 / 活动表、维度下拉、chip 汇总、筛选动作；`tests/test_html.py` 的 Node 行为测试。
- 非目标：
  - 默认范围改为近 7 天（R39），保留“全部”；不改变单表结构、不改变 token / credits / est / activity 分轨与“不相加”口径。
  - 不新增单位 tab、不做每张图独立日期范围；这些会改变 REQ-0001 §3.6 的 AC，需单独评审。
  - 不改 Python 采集、SQLite schema、CLI 参数或联网路径。
  - 不处理展示层重构（表格冻结列 / KPI 布局 / 覆盖说明 / Top 8 编码 / 粘性筛选），见 CHG-0005。
- 兼容性 / 迁移：无 schema / DB / CLI 变化；旧 HTML 快照不自动更新，需重新生成；旧报告的 payload 字段不变。

## 5. 验证与观测

- 自动化测试（实现时新增，`tests/test_html.py` 的 Node harness；最终名称以实现为准）：
  - `test_presets_anchor_to_data_until`
  - `test_default_range_is_last_seven_days`
  - `test_trae_kpi_distinguishes_out_of_range_from_unsynced`
  - `test_empty_range_renders_single_empty_state`
  - `test_activity_chart_uses_full_date_buckets`
  - `test_activity_table_sort_updates_aria_sort`
  - `test_dimension_selects_follow_date_and_search`
  - `test_agent_chip_totals_follow_range`
  - `test_select_all_preserves_other_filters_reset_clears_all`
- 手工验收（Chrome 1440×900 与 500×900）：
  1. 用 2026-11-15 生成的报告在 2026-11-16 打开；清空 URL / localStorage 后首次加载默认应为 11-09 ~ 11-15；点“最新”仍为 11-15；点“全部”为 06-01 ~ 11-15；页面显示“数据截至 2026-11-15”；日期选择器不能选 11-16 之后。
  2. 用空区间 fixture（或已知无数据的日期）生成报告：只出现一个空状态，并提示切换到“全部”；不出现 17 张 0 卡、空白图、空表、活动块；Trae 不显示“未同步”；若显示额度卡，必须带“最新快照，与区间无关”。
  3. 选中 trae-cn，范围设为 10 月：KPI 显示“当前区间无 Trae credits”，不是“未同步”。
  4. 点“全部”，全选 qoder，查看活动图：07-09 → 08-22 之间应有 0 值空档，横轴与 token 图逐日对齐；显示“活跃 84 天 / 共 168 天”覆盖率。
  5. 点击活动表“工具调用”表头：行序变化，箭头 / `aria-sort` 更新；再点反向；不可排序列不是按钮。
  6. 把范围收窄到最近 15 天：模型 / 项目下拉的选项数下降且只含非零行；选择后不出现空表；切换日期时失效选项被清空。
  7. 近 7 天时 chip 数字等于 KPI 的区间总 Token；若保留全时段数字，chip 必须有“全部时间”。
  8. 选中模型后点“全选”：模型筛选保持；点“重置筛选”：模型 / 项目 / 搜索全部清空。
- 回归：`python3 -m unittest discover -s tests -t .`；`python3 scripts/check_test_policy.py`；`python3 scripts/check_ac_map.py`；覆盖率按 [README.md 的测试与门禁](../../README.md#测试与门禁) 的命令执行。实现后附通过数、跳过数、覆盖率变化与 commit。
- 观测：HTML 无外部请求、CSP 不变；页面 console 零错误；Node 缺失时测试按现有白名单策略处理，不静默 skip。

## 6. 回滚方案

- 回滚方式：单文件前端改动，回退 `html_report.py` 中本 CHG 的改动并重新生成报告；无 DB / schema / CLI 影响。
- 数据 / 配置兼容：旧报告仍可打开；新报告与旧报告的数据 payload 兼容，仅前端状态与文案变化。
- 回滚验证：回滚后跑全量测试；用同一份报告确认日期预设恢复旧行为（仅作为回滚证据，不作为期望行为）。

## 7. 风险与未决问题

- 风险：默认近 7 天会让 Qoder credits（09-16 起）、Trae credits（11-02 起）、Trae est（11-07 起）等短周期轨在默认视图里数据点很少；保留“全部”预设、覆盖率提示和空状态 CTA，避免误读为“没有数据”。
- 风险：把 chip 改为区间口径会改变现有视觉记忆；需要评审确认（R25 提供了“全部时间”标签的替代路径）。
- 风险：每次输入都重建下拉在 308 行规模下可忽略；大库（数万行）需在 `renderAll` 层缓存筛选结果，避免重复扫描。实现时先测 10 万行内存过滤耗时，超过 50ms 再加 debounce / 缓存。
- 风险：活动图补零后柱子变细，稀疏区间可能更难读；用“活跃 N/M 天”覆盖率和 tooltip 补偿。
- 未决：`DATA_UNTIL` 为空（空库）时“最新”的行为；建议回退到浏览器今天并显示“无数据”，实现时补边界测试。
- 未决：日期选择器完全禁止未来日期，还是允许选择但显示空状态；本 CHG 选择“禁止 / 夹紧”，避免再次出现“未来全 0”。
- DoR：用户已于 2026-11-16 审核通过范围；实现时把 R19–R26、R39 写入 REQ §5 并补 `tests/ac_map.json` 映射；REQ-0001 §3.6 的默认范围需由“全部数据覆盖”改为“近 7 天”。

## 8. 关联与证据

- 功能卡：[REQ-0001](../requirements/REQ-0001-usage-ledger.md) §3.6、R8、R15。
- 同批展示优化：[CHG-0005](CHG-0005-html-report-display-and-interaction.md)。
- 实测报告：`usage html` 生成于 `2026-11-15T08:00:38+08:00`；payload 统计与视口测量见 §2。
- commit / PR / release：待实现。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（待评审） | 2026-11-16 基于实际报告与 1440 / 500 视口测量创建 |
| 提议（补充） | wayne（待评审） | 2026-11-16 用户补充：默认范围改为近 7 天（R39） |
| 就绪 | wayne | 2026-11-16 用户审核通过 CHG-0004 范围 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 开始实现 |
