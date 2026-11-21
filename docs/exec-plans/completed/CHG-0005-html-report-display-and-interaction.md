# CHG-0005 HTML 报表展示与交互优化

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[usage-ledger.md 本地 AI 编码工具用量台账](../../product-specs/usage-ledger.md)
关联：[CHG-0004 HTML 报表空状态与筛选联动修复](CHG-0004-html-report-empty-state-and-filters.md)、[usage-ledger.md §3.6](../../product-specs/usage-ledger.md)

## 1. 摘要

优化 HTML 报表的静态展示与交互：宽表冻结标识列并按单位分组、KPI 按单位成组且只保留一个主卡、覆盖说明与页脚合并、Top 8 条形与百分比同口径、图表控件放回所属面板、粘性筛选与回到顶部、图表支持触控 / 键盘、活动表分页与冻结、统一术语与格式、筛选状态可恢复、提供可选的“聚焦有数据区间”。默认范围由 CHG-0004 R39 改为近 7 天；本 CHG 不进一步改变默认值、单表结构、分轨口径与任何数据计算。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：usage-ledger.md G1（在一个视图里回答用量问题并明确标注口径）、R15（HTML 边界标注）。
- 触发原因：2026-11-16 对 2026-11-15 生成的报告做 1440px / 500px 实际使用；以下问题均为主观可用性缺陷，不影响数据正确性，但直接影响“能否读出来”。
- 证据：
  1. **宽表**：明细表 21 列、`scrollWidth` 1828px；1440px 下容器 1236px（约 592px 默认不可见），500px 下容器 436px（约 4.2 屏）。横向滚动后日期 / Agent / 模型 / 项目全部消失；没有冻结列、列分组表头或合计行；同时有 50 行分页与 `max-height:660px` 的纵向内滚动（[html_report.py:237](../../../src/usage_ledger/html_report.py#L237)、[html_report.py:2335](../../../src/usage_ledger/html_report.py#L2335)）。
  2. **图表密度**：当前默认全量 168 天（v0.6.0）；Qoder credits 从 09-16 开始、Trae credits 从 11-02 开始、Trae est 从 11-07 开始；三张图的缺失提示分别为 87 / 130 / 163 天。图表卡在 1440px 高 1295px、500px 高 1435px，三张图纵向堆叠，大量空区间占据首屏。
  3. **KPI 布局**：17 张卡在 1440px 排成 `7/1/4/5` 行（“轮次”孤行），500px 排成 `3/3/2/3/1/3/2`（“区间日均”孤行）；总 Token 与额度卡都用了 `primary`；出现重复的“精确 Credits”分组标题；500px 下额度值 `2,520 credits` 的 `clientWidth 119 / scrollWidth 122`，被省略号截断（[html_report.py:158](../../../src/usage_ledger/html_report.py#L158)、[html_report.py:277](../../../src/usage_ledger/html_report.py#L277)）。
  4. **覆盖说明与页脚**：覆盖说明 1440px 高 78px、500px 高 153px，是一段分号连接的长文本；页脚 500px 高 417px、8 段，和覆盖说明 / 状态条重复。阴影开关关闭时仍列“Qoder 影子估算 09-16~11-13”；未选 Trae 时仍显示 Trae 状态；页脚“308 行 token 聚合”是库内全部 token 行（含本页未展示的 109 行 Qoder 历史 token），而表格是 199 token + 122 credits + 8 Trae est = 329 行；页脚“108 行估算聚合”也包含默认不显示的 Qoder 影子行（[html_report.py:1161](../../../src/usage_ledger/html_report.py#L1161)、[html_report.py:2703](../../../src/usage_ledger/html_report.py#L2703)、[html_report.py:2775](../../../src/usage_ledger/html_report.py#L2775)）。
  5. **Top 8 编码**：条形长度按当前第一名归一化，百分比按总量计算；模型第一的条形是满格，标签却是 `31.1%`（[html_report.py:2066](../../../src/usage_ledger/html_report.py#L2066)、[html_report.py:2054](../../../src/usage_ledger/html_report.py#L2054)）。
  6. **控件作用域**：“Token 指标”和“影子：Qoder 估算 token”都放在图表卡头部；前者只控制 Token 面板，后者控制 Credits 面板里的影子线；下面的“估算”面板只属于 Trae；右侧影子轴没有轴标题（[html_report.py:331](../../../src/usage_ledger/html_report.py#L331)）。
  7. **导航**：页面内容 1440px 约 3.9k 高、500px 约 5.3k 高；筛选器只在最顶部，没有粘性筛选或回到顶部。
  8. **触控 / 键盘**：图表 `hit` 只监听 `mouseenter / mousemove / mouseleave`，触屏点击不会固定 tooltip；SVG 数据点不可聚焦；Agent chip 与分页按钮的点击区域偏小；零值单元格对比度偏低。tooltip 边缘夹紧用固定 `half=110`，而 CSS 最大宽度是 290px（[html_report.py:1750](../../../src/usage_ledger/html_report.py#L1750)、[html_report.py:212](../../../src/usage_ledger/html_report.py#L212)）。
  9. **活动表**：144 行、9 列、`min-width:900px`，500px 下同样横向滚动；没有分页，还嵌在可折叠块里形成第二层滚动；折叠时仍会在每次 `renderAll()` 重绘（[html_report.py:2655](../../../src/usage_ledger/html_report.py#L2655)）。
  10. **术语 / 格式**：`trae-cn` / `Trae CN`、`est` / `估算`、`turns` / `轮次`、`Tokens 合计` / `总 Token`、`used` / `已用` 混用；`fmtCredits` 与 `fmtQuota` 的小数位不一致。
  11. **状态**：只有主题写入 `localStorage`；日期、Agent、模型、项目、搜索、排序、页码刷新后全部丢失，也无法把“近 30 天 + qoder + 某模型”的视图分享出去。
- 用户补充需求（2026-11-16）：切换 Agent 时，“模型 - 项目 - 搜索”这一行的控制宽度和位置要保持稳定，不能随选项集合变化而伸缩。代码路径：`.filter-line` 是 `flex-wrap`（[html_report.py:132](../../../src/usage_ledger/html_report.py#L132)），`select` 只有 `max-width:230px`、没有固定宽度（[html_report.py:134](../../../src/usage_ledger/html_report.py#L134)）；`applyAgentSelection()` 清空模型 / 项目并调用 `rebuildDimensionSelects()`（[html_report.py:915](../../../src/usage_ledger/html_report.py#L915)、[html_report.py:991](../../../src/usage_ledger/html_report.py#L991)），选项变化会改变 select 的固有宽度，搜索框没有宽度约束，整行可能重新换行。
- 不做的后果：报表能算但读不动；宽表让人只看到前几列，图表空区间稀释有效信息，页脚数字对不上会削弱信任；手机 / 触控与键盘用户基本无法使用图表。

## 3. 行为 / AC delta

> R27–R38 与 R40 已写入 [usage-ledger.md §5.7](../../product-specs/usage-ledger.md)，并在 `tests/ac_map.json` 映射到表内测试类；本节保留为本次 AC delta 记录。R35 依赖 CHG-0004 R23（活动表排序）；R30 的 chip 口径依赖 CHG-0004 R25；R40 的筛选行布局与 CHG-0004 R24 的选项重建共用同一套状态。

### 3.1 明细表

- **R27**：When the detail table is wider than its container, the system shall keep the identity columns visible while scrolling horizontally, and group token / credits / est columns under labeled headers; it shall remain one table. At widths above 640px, day / agent / model / project are frozen; at 640px and below, day / agent are frozen and model / project remain reachable by horizontal scroll.
- **R28**：The detail table shall show a totals row per unit and per vendor (Qoder credits and Trae credits shall not be summed together), hide columns that are empty for all rows in the current filter, and prevent cross-unit totals. Pagination shall offer page size and direct page jump; at 1440px the table shall not add a second vertical scroll container (pagination replaces the inner vertical scroll; at ≤640 an inner scroll is allowed).

边界：无行时不渲染合计行；只有一种单位时其他单位的合计列显示 `—`；合计行不计入“本页行数”；隐藏全空列后至少保留日期与 Agent 两列。

### 3.2 KPI、覆盖说明与 Top 8

- **R29**：The KPI area shall group cards by unit (Token / Credits / Est), use exactly one primary card, keep each unit’s cards together, avoid orphan rows at 1440px and 500px, and render values fully at 500px without ellipsis. A unit with no rows in the current range shall collapse into one “无数据” card instead of N zero cards.
- **R30**：The system shall consolidate coverage, Trae status, generation time, and row-count explanations into one collapsible “口径与数据覆盖” block; Trae status shall be shown only when trae-cn is selected; the Qoder shadow range shall be shown only when the shadow toggle is on or explicitly marked “未计入”; footer counts shall distinguish “库内 / 本页”; generation time shall appear once. Missing-day hints shall be summarized as coverage (“活跃 N/M 天”), not a 10-date list.

边界：coverage 为空时显示“无覆盖信息”；未选 Trae 时不渲染 Trae 状态；阴影关闭时不出现影子范围；页脚不得把库内未展示的 Qoder 历史 token 行计入“本页”。

- **R31**：In Top 8, bar length and percentage shall use the same denominator, or the label shall explicitly say “相对第一”; the sort label shall name the active unit and scope (“按 tokens 排序 · 当前区间”). If the grand total is 0, percentages shall show `—` rather than `0%` / `NaN`.

### 3.3 图表与活动表

- **R32**：The token metric selector shall live in the Token panel, the Qoder shadow toggle in the Credits panel, the estimate panel shall be labeled “Trae 弱估算”, and the shadow axis shall have a title; each control shall have an accessible name and its scope shall be visible. If shadow data is unavailable, the toggle shall be hidden or disabled with a reason; if a panel has no rows, it shall show one empty card rather than a blank chart.

- **R33**：While the user scrolls past the top bar, a compact sticky filter bar (date, agents, search) shall remain available, with a back-to-top control; at ≤640px it shall collapse into a button / sheet that can be dismissed with Escape, and shall not cover content when the page is short.

- **R34**：Chart tooltips and data points shall support pointer / tap and keyboard focus, with clamped positioning based on the actual tooltip width; a focused point shall expose an accessible label, and Escape or focus loss shall dismiss the tooltip. No chart information shall be available only on mouse hover.

- **R35**：The activity table shall paginate (or show top N with “展开全部”), keep date / project visible while scrolling, and show the current row count and page. It shall not render when the activity block is collapsed or the range has no activity; rows above the current page shall not be mounted in the DOM.

边界：活动 0 行时隐藏整个活动块；折叠时跳过重绘；活动排序沿用 CHG-0004 R23；≤640px 允许内滚动。

### 3.4 术语、状态与聚焦

- **R36**：All user-facing labels shall use one display-name map and formatter; internal keys (`trae-cn`, `turns`, `used`, `est`) shall not appear raw; credits / quota decimals and units shall be consistent. If token-row `turns` and activity `turns` have different semantics, they shall be labeled “记录数” and “轮次” respectively and defined in the coverage block. Unknown keys may fall back to the raw value, but known keys must use the map.

- **R37**：When filters, sort, or page change, the system shall persist them in the URL hash or `localStorage` and restore them on load; URL state shall win when both exist. Invalid agents, dates, models, projects, or page numbers shall be dropped or clamped; persisted state shall not contain token, credit, quota, or session values. The theme toggle shall remain persisted.

- **R38**：The system shall provide an opt-in “聚焦有数据区间” toggle that sets the range to the union of days with data for the selected units and shows the resulting start / end; the default is the last 7 days per CHG-0004 R39, and disabling the toggle restores that default range. If no selected unit has data, the toggle shall be disabled with a reason.

边界：默认关闭；默认范围由 CHG-0004 R39 定义为近 7 天；聚焦后仍显示数据截止日与覆盖率；日期范围手动修改会关闭聚焦状态或重新计算并提示。

### 3.5 筛选行布局

- **R40**：When the agent selection changes, the system shall keep the model / project / search row’s control widths and positions stable; select controls shall use fixed widths (or fixed flex-basis) so option changes do not resize the row, long values shall truncate with ellipsis while the dropdown still shows full text, and the search input shall keep a stable width. At ≤640px the row may wrap at fixed breakpoints, but switching agents shall not change the wrapping or order.

边界：无选项时保持控件宽度并显示禁用的“无可用模型 / 项目”；长项目名 / 模型名用省略号 + `title`；切换 Agent 前后在 1440 与 500 下测量控件的 bounding box，宽高与 x/y 不得变化（整行隐藏等整体位移除外）。

## 4. 影响范围与非目标

- 受影响：`src/usage_ledger/html_report.py` 的 CSS / 页面结构 / 前端状态；`tests/test_html.py` 的 Node 行为测试；实现后需同步 `ARCHITECTURE.md` 的 HTML 前端说明（如涉及）。
- 非目标：
  - 默认范围由 CHG-0004 R39 调整为近 7 天；本 CHG 不进一步改变默认值、单表结构、token / credits / est / activity 分轨与“不相加”口径。
  - 不做单位 tab、不做每张图独立日期范围、不做跨厂商 credits 合计。
  - 不改 Python 采集、SQLite schema、CLI 参数、联网路径或 HTML payload 字段。
  - 不包含 P2 候选：搜索 placeholder 带 Agent、表格行 Agent 色点、Top 8 “其他”聚合行、CSV / 打印导出、周聚合标识、主题按钮 `aria-pressed`、手动列显隐。它们可在本 CHG 验收后另建 CHG。
- 兼容性 / 迁移：旧的 HTML 快照不受影响；新增的 URL hash / localStorage 键在旧版本中会被忽略；无数据迁移。

## 5. 验证与观测

- 自动化测试（新增 14 个，`tests/test_html.py` 的 Node / 静态 harness）：
  - `HtmlTableLayoutTest`：`test_table_keeps_identity_columns_and_groups`、`test_table_totals_are_unit_scoped_and_empty_columns_hidden`、`test_table_pagination_page_size_and_jump`
  - `HtmlKpiLayoutTest`：`test_kpi_groups_have_single_primary_and_no_ellipsis`
  - `HtmlCoverageBlockTest`：`test_coverage_block_is_single_and_conditional`
  - `HtmlTopListTest`：`test_top_bars_share_denominator_with_labels`
  - `HtmlChartControlsTest`：`test_chart_controls_live_in_their_panels`
  - `HtmlNavigationTest`：`test_sticky_filter_bar_and_back_to_top`
  - `HtmlChartA11yTest`：`test_chart_points_focusable_and_tooltip_clamped`
  - `HtmlActivityPagingTest`：`test_activity_table_paginates_and_skips_when_collapsed`
  - `HtmlLabelsTest`：`test_display_names_and_formatters_are_consistent`
  - `HtmlStatePersistenceTest`：`test_filters_round_trip_via_url_state`
  - `HtmlFocusRangeTest`：`test_focus_range_toggle_is_opt_in`
  - `HtmlFilterLayoutTest`：`test_filter_row_width_stable_across_agents`
- 门禁结果（2026-11-16，`feat/html-report-ux`，worktree）：
  - `python3 -m unittest discover -s tests -t .`：269 tests，OK，0 skip
  - `python3 scripts/check_test_policy.py`：269 tests，0 failures / 0 errors / 0 skips；fast suite 1.547s（budget 5.0s）
  - `python3 scripts/check_ac_map.py`：usage-ledger.md 40 criteria / 87 mapped identifiers，passed
  - 分支覆盖率：TOTAL 93.6%（threshold 85.0%，baseline 80.9%），各模块均通过 `check_coverage.py`
- 手工验收（Chrome 1440×900 与 500×900；条件允许补 Safari）：
  1. 横向滚动明细表：日期 / Agent / 模型 / 项目保持可见；Token / Credits / Est 分组表头清晰；合计行按单位 / 厂商分列，不出现跨单位合计。
  2. 500px：KPI 值不被省略号截断；没有孤行；额度卡是复合卡而不是第二张主卡。
  3. 覆盖说明与页脚合并为一个可折叠区块；只出现一次生成时间；未选 Trae 时看不到 Trae 状态；阴影关闭时看不到影子范围；页脚“库内 / 本页”数字与表格一致。
  4. Top 8：第一名的条形不再被误读为 100%；标签与条形同口径，或明确写“相对第一”。
  5. 图表控件出现在各自面板；影子轴有标题；无影子数据时开关隐藏 / 禁用并有原因。
  6. 向下滚动后粘性筛选条可用；500px 下折叠为按钮 / 抽屉，Escape 可关闭；回到顶部可用。
  7. 用键盘 Tab 到图表数据点：tooltip 出现且有可读标签；Escape 关闭；500px 下点击固定 tooltip，点空白关闭。
  8. 活动表分页 / 展开可用；折叠活动块后 DOM 中没有活动表行；活动 0 行时整个块隐藏。
  9. 页面术语统一：不出现原始 `trae-cn`、`turns`、`used`、`est` 作为用户标签；credits / quota 小数位一致。
  10. 设置日期 + Agent + 模型 + 搜索 + 排序 + 页码后刷新：状态恢复；把 URL 发给另一个本地报告（不同 payload）时，无效状态被丢弃而不是报错；URL / localStorage 中不含用量数值。
  11. 打开“聚焦有数据区间”：范围收缩到有数据的最早 / 最晚日，关闭后恢复默认近 7 天（R39）。
  12. 记录“模型 / 项目 / 搜索”三个控件的 bounding box（1440 与 500）；依次切换 qoder、codex、全选、trae-cn；控件宽度、位置和换行保持不变；长模型 / 项目名以省略号显示，下拉展开仍能看到全名；搜索框不跳行。
  实测（`PYTHONPATH=src python3 -m usage_ledger html --offline --output /tmp/usage-report-chg5.html`，数据截至 2026-11-16）：
  1. 1440px：明细表宽 1716px、容器 1238px；横向滚动 600px 后日期 / Agent / 模型 / 项目表头 x 坐标保持 102 / 198 / 378 / 548；组表头为 Token / Credits / 估算；`cache_write` 等全空列隐藏；4 行合计分别为 Token、Qoder credits、Trae CN credits、Trae 弱估算；页大小 25 时 14 页，跳转到第 2 页显示 26–50；表内 clientHeight = scrollHeight = 1553（无第二层纵向滚动）。
  2. 500px：KPI 两列，Token 8 卡、Qoder/Trae 各 4 卡均无单卡孤行；额度值 `2,540 credits` 完整显示；表内允许纵向滚动（clientHeight 486 / scrollHeight 1553），模型 / 项目不再冻结但可横向到达。
  3. KPI 实测 3 组 / 17 卡 / 1 张主卡，单卡宽度 309px；估算组只有一张卡时占满整行（1272px）。
  4. Top 8 第一名显示 `100.0%`，标签为“相对第一 · 按 tokens 排序 · 当前区间”；总计为 0 的百分比返回 `—`。
  5. 控件位于所属面板：Token 指标在 Token 面板、影子开关在 Credits 面板、估算面板标题为“Trae 弱估算”；打开影子后 credits 图出现“影子估算（右轴）”标题与图例。
  6. 滚动 1400px 后 `filter-shell` 带 `sticky-enabled stuck`，回到顶部按钮显示；500px 下筛选折叠为按钮 / 抽屉，Escape 关闭。
  7. 键盘聚焦图表 hit：`tabindex=0`、`aria-label` 含日期与各序列值，tooltip 在容器内；Escape / 失焦隐藏。点击 hit 固定 tooltip，点击图表空白关闭。
  8. 活动表展开后 30 行/页，共 5 页（147 行），下一页显示 31–60；折叠时 `renderActivity` 直接返回；日期 / 项目列 sticky。
  9. 页面可见文本不再出现原始 `trae-cn` / `turns` / `used` / `est` 标签；模型键 `trae-cn` 显示为 `Trae CN`；“记录数”与“轮次”在覆盖块中定义。仅后端 notice 中的 CLI 命令保留 `--source trae-cn` 参数。
  10. URL hash 恢复日期、Agent、模型、搜索、指标、排序、页码与页大小；无效 Agent / 日期 / 模型 / 页大小被丢弃或夹紧；hash 中无 token / credits / quota / session 数值。
  11. “聚焦有数据区间”默认关闭；打开后范围为 2026-06-05 ~ 2026-11-16，关闭恢复默认 2026-11-10 ~ 2026-11-16；无数据时开关禁用并提示“无可聚焦的数据区间”。
  12. 1440px 下依次切换 Qoder / Codex / 全选 / Trae CN，模型 / 项目 / 搜索控件 bounding box 均为 `(132,161,189,34)` / `(366,161,189,34)` / `(600,160,739,36)`；500px 抽屉内切换同样不变。
- 回归：上述门禁命令全部通过；`git diff --check` 无空白错误。
- 观测：HTML 无外部请求、CSP 不变；Chrome DOM 注入检查无 JS error；Safari 未实测，列为未决项。

## 6. 回滚方案

- 回滚方式：回退 `html_report.py` 中本 CHG 的 CSS / 结构 / 前端状态改动并重新生成报告；无 DB / schema / CLI 影响。
- 数据 / 配置兼容：旧报告不受影响；新增 URL hash / localStorage 键在回滚后会被忽略，不会导致页面报错；用户可手动清除。
- 回滚验证：回滚后跑全量测试；用同一份报告确认页面恢复旧布局与旧交互。

## 7. 风险与未决问题

- 风险：`position: sticky` 冻结列与横向滚动在 Safari / 窄屏上容易错位；实现时在 Chrome 与 Safari 各做一次 1440 / 500 手工核对。
- 风险：合计行容易被读成“跨单位总计”；必须按单位 / 厂商分列，并在覆盖说明中写明“不可相加”。
- 风险：粘性筛选条在小屏占用垂直空间；≤640px 折叠为按钮 / 抽屉，页面短于 800px 时不显示。
- 风险：URL hash 可能被分享；只允许日期、Agent、模型、项目、搜索、排序、页码，不含 token / credits / quota / session 值。搜索词可能包含项目名，需在覆盖说明中提示“链接会包含筛选词”。
- 风险：聚焦区间会改变图表密度；保持 opt-in，默认近 7 天不变。
- 风险：固定 select 宽度可能截断长项目名；用省略号 + `title`，下拉展开仍显示全名；500px 下用固定断点换行，避免切换 Agent 时跳行。
- 未决：17 张 KPI 卡的最终分组与主卡选择（建议总 Token 为主卡，额度改为“余额 + 进度”复合卡）；评审时可调整，但不改变“只有一个主卡”的 AC。
- 未决：表格在 500px 下是否值得保留 21 列，还是提供“精简列”预设；本 CHG 先做冻结 + 隐藏全空列，不做手动列显隐（P2）。
- 未决：活动表分页大小（建议 30 / 50 / 100）；实现时与主表保持一致。
- DoR：用户已于 2026-11-16 审核通过范围；实现时把 R27–R38、R40 写入 REQ §5 并补 `tests/ac_map.json`；usage-ledger.md §3.6 的“页首显示 Trae 状态”需改为“仅选中 Trae 时显示”，默认范围需改为近 7 天（CHG-0004 R39），chip 口径需与 CHG-0004 R25 同步。
- 实施拆分建议：可按 5a（表格 / KPI / 覆盖说明 / Top 8 / 控件）与 5b（粘性筛选 / 图表触控 / 活动表 / 术语 / 状态 / 聚焦）两个 PR 提交；验收与回滚仍以本 CHG 为单位。若评审要求独立回滚，再拆为两份 CHG。

## 8. 关联与证据

- 功能卡：[usage-ledger.md](../../product-specs/usage-ledger.md) §3.6、R15。
- 同批正确性修复：[CHG-0004](CHG-0004-html-report-empty-state-and-filters.md)。
- 实测报告：`usage html` 生成于 `2026-11-15T08:00:38+08:00`；payload 统计与视口测量见 §2。
- commit：`ebc48fe`（实现 + 测试）；`sit` / `main` 尚未合并，合并 `main` 需用户明确同意。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（待评审） | 2026-11-16 基于实际报告与 1440 / 500 视口测量创建 |
| 提议（补充） | wayne（待评审） | 2026-11-16 用户补充：切换 Agent 时筛选行宽度稳定（R40）；默认范围随 CHG-0004 R39 改为近 7 天 |
| 就绪 | wayne | 2026-11-16 用户审核通过 CHG-0005 范围 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 开始实现 |
| 已验证 | wayne | 2026-11-16 自动化 269 tests / 0 skip、覆盖率 93.6%、AC map 40 criteria 通过；Chrome 1440 / 500 手工验收 R27–R38、R40；commit `ebc48fe` |
