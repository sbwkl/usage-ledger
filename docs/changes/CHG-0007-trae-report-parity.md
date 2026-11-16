# CHG-0007 Trae CN credits 展示结构对齐 Qoder

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage html` / `src/usage_ledger/html_report.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：[REQ-0001 R42 / R43](../requirements/REQ-0001-usage-ledger.md)、[CHG-0006 Qoder turn credits](CHG-0006-qoder-turn-credits.md)、[CHG-0005 HTML 报表展示与交互](CHG-0005-html-report-display-and-interaction.md)

## 1. 摘要

Trae CN 选中后的 KPI 名称、估算分组、图表和明细表与 Qoder 差异过大。本 CHG 把两家 credits 的展示骨架统一为同一套四卡 KPI、同一 credits 图表容器和同一明细表结构；Trae 没有的字段显示 `—` 并说明原因，不编造免费额度或活动数据。Qoder 影子估算与 Trae 弱估算统一由“估算”开关控制，默认关闭，避免 Trae 默认页比 Qoder 多出一整组估算区。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：REQ-0001 G1（在一个视图里回答用量问题）、R15（分轨边界）、R29（KPI 分组）、R32（图表控件）。
- 触发原因：用户 2026-11-16 反馈“Trae CN 的报告展示结构与其他 Agent 有大量不同，这是不对的，他的报告格式应该和 Qoder 相同”。
- 证据（均来自 `/tmp/usage-report-sit.html`，2026-11-16 生成，1440 × 2200 视口）：
  1. Qoder 选中：KPI 为“最新额度余额 / 区间 billable credits / 免费 credits / 区间日均”，只有一个 credits KPI 组、一个 credits 图表；明细只有 credits 列。
  2. Trae 选中：KPI 为“区间 credits / 会话数 / 覆盖天数 / 模型数”，额外出现“估算”KPI 组、Trae 弱估算图表，明细同时混入 credits 与估算行，并出现“单位”列。
  3. 差异来源不是数据缺失：Trae 的 credits 是会话级、无额度快照/免费字段；弱估算本来属于独立轨。当前实现把“数据差异”直接映射成了“页面结构差异”，导致同一报表在不同 Agent 下像两个产品。
- 不做的后果：用户无法在 Agent 之间用同一套位置和标签读 credits；Trae 的估算轨会挤占 credits 主视图，且容易被误读为同一指标。

## 3. 行为 / AC delta

- 新增：R42（credits KPI / 图表 / 明细表的跨 Agent 结构统一）、R43（估算统一开关与默认隐藏）。
- 修改：REQ-0001 §3.6 的 KPI / 图表 / 明细表描述；原“Trae credits 显示区间 credits / 会话数 / 覆盖天数 / 模型数”改为统一四卡。
- 预期行为：
  - Qoder 与 Trae 都按以下顺序显示四张卡，且只有第一张是主卡：
    1. `区间 credits`：Qoder 为 billable credits，Trae 为会话级 credits；副文案分别给出请求数 / 会话数与真值口径。
    2. `免费 credits`：Qoder 显示免费金额与免费请求数；Trae 显示 `—`，副文案“Trae API 不返回免费额度”。
    3. `区间日均`：区间 credits ÷ 有数据天数；副文案给出天数，Trae 额外给出模型数。
    4. `最新额度余额`：Qoder 显示快照余额与已用比例；Trae 显示 `—`，副文案“Trae CN 不提供额度快照”。
  - 单个 Agent 的 credits 图表使用同一容器、坐标轴、图例与 tooltip 结构；Qoder 保留 billable / 免费双序列，Trae 只有 billable 单序列，不伪造免费序列，并在提示中说明。
  - Trae 明细表默认只包含 credits 行；Qoder 影子估算 / Trae 弱估算统一由 credits 面板的“估算”开关控制，默认关闭。关闭时估算不进入 KPI、图表、Top 8、明细表和页脚本页计数；打开后两家分别显示，仍不可与 credits 相加。
  - 开关文案与 `aria-label` 根据选中 Agent 生成：仅 Qoder 为“估算：Qoder 影子估算”，仅 Trae 为“估算：Trae 弱估算”，两者同时选中为“估算：Qoder 影子 / Trae 弱估算”。
  - 活动区块仍只在 Qoder 选中且有点活动数据时显示；不为 Trae 造空活动区块。
  - 覆盖说明与页脚明确写出“Trae 无免费额度 / 额度快照字段”“Trae 弱估算默认隐藏（开关关闭）”。
- 非目标：不改 Trae credits 数值、API、认证或会话归属日；不改 Qoder 的转录 / DB 采集；不把 Qoder 与 Trae credits 相加；不为 Trae 造活动、额度或免费数据。

## 4. 影响范围与非目标

- 受影响：HTML KPI 渲染、credits 图表、估算开关、明细表行与列、Top 8、覆盖说明、页脚术语。
- 不影响：后端 credits 数值与存储、CLI `credits` 输出、源采集逻辑（Qoder 采集见 CHG-0006）。
- 兼容性：旧报告是静态文件，不受影响；新报告默认隐藏 Trae 弱估算，但同一页面可通过开关恢复查看，数据未删除。

## 5. 验证与观测

- 自动化测试：
  - 新增 `HtmlCreditParityTest`：四卡顺序 / 标签 / 主卡唯一性、Trae 不支持字段为 `—`、默认仅 credits 行、开关打开后估算行与 KPI 出现、覆盖文案。
  - 更新 `HtmlChartControlsTest`：开关文案与动态 `aria-label`。
  - 更新受 `hasTraeEstimateSelected` / `traeRowsFor` 影响的 Node 片段测试。
  - 全量测试、AC map、覆盖率与静态检查。
- 手工验证：
  - 重新生成报告，分别只选 Qoder / 只选 Trae，在 1440px 截图核对四张 KPI 卡、单一 credits 图表与明细列顺序一致。
  - 打开“估算”开关后，两家分别出现估算 KPI / 图表 / 明细行；关闭后恢复默认结构。
  - 500px 下 KPI 不溢出、估算开关可用。
- 指标 / 日志：无新增运行期埋点；验证以 DOM 快照、payload 和截图为准。
- 结果与证据：
  - 自动化：`python3 -m unittest discover -s tests -t .` → 276 tests / 0 failures / 0 errors / 0 skips；`HtmlCreditParityTest` 覆盖四卡标签 / 主卡 / Trae 不支持字段 / 估算开关；覆盖率 93.3%，AC map 43/91。
  - 手工：`/tmp/chg7-report.html` 在 1440px 与 500px 下，Qoder 和 Trae 均显示四卡（区间 credits / 免费 credits / 区间日均 / 最新额度余额）；Trae 默认无估算 KPI / 图表 / 明细行，打开“估算：Trae 弱估算”后出现 Trae 弱估算 KPI、图表和明细行；浏览器 console 无报错。
  - 结构差异保留说明：Trae 的免费 credits 与额度余额显示 `—`，不伪造 0；活动区块仍仅由 Qoder 数据驱动。

## 6. 回滚方案

- 回滚方式：恢复 `renderTraeCreditKpis` 独立 KPI、取消 Trae 估算开关门控、恢复明细混排。
- 数据兼容：纯展示层，无数据迁移；回滚不需要清理存储。
- 回滚验证：重跑测试并生成报告，确认 Trae 恢复旧结构。

## 7. 风险与未决问题

- 风险：默认隐藏 Trae 弱估算会让已有用户以为数据消失。缓解：开关文案明确写出“Trae 弱估算”，覆盖块与页脚说明默认隐藏及原因。
- 风险：Trae 免费额度字段缺失，显示 `—` 而不是 `0`；这比填 0 更诚实，但可能与 Qoder 的 0 形成视觉差异。
- 未决：Trae 未来若提供额度 / 免费字段，再在统一四卡中填充，不改变结构。

## 8. 关联与证据

- 功能卡：[REQ-0001](../requirements/REQ-0001-usage-ledger.md) R15、R29、R32、R42、R43。
- 截图：`/tmp/report-qoder.png`、`/tmp/report-trae.png`（2026-11-16，1440px）。
- commit：`735d00a`（实现 + 测试 + 文档）。
- 日志 / 截图 / 测试报告：`/tmp/chg7-report.html`、`/tmp/chg7-qoder.png`、`/tmp/chg7-trae.png`、`/tmp/chg7-qoder-500.png`、`/tmp/chg7-trae-500.png`。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（待评审） | 2026-11-16 用户反馈 + 1440px Qoder / Trae 报告截图 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 开始实现 |
| 已验证 | wayne | 2026-11-16 276 tests / 0 skip、覆盖率 93.3%；1440 / 500px 截图与估算开关实测通过；commit `735d00a` |
