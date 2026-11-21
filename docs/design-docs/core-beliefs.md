# 核心工程信念

本文件定义 design-docs 的 agent-first operating principles。它不是产品文案，而是约束设计与实现取舍的工程原则。

## 1. 源是唯一事实来源

- 各 AI 编码工具自己落盘的日志 / SQLite 才是真值。
- SQLite 只是归档、索引和同步状态，不是权威副本。
- `report` 与 `--stateless report` 必须一致。
- 相关决策：`adr/ADR-0001-source-of-truth-db-as-archive.md`。

## 2. 拉取式采集，无常驻进程

- 数据由工具自己写入磁盘；系统在查看 / 同步时拉取。
- 无常驻 daemon；每小时增量与每日全量只是调度策略。
- 相关决策：`adr/ADR-0002-pull-collection-no-daemon.md`。

## 3. 四轨分离，永不混加

- token 真值、活动指标、credits 额度、est 估算分别记录、分别展示。
- 禁止把 credits 当 token，禁止把 est 与真值相加，禁止跨厂商静默合计。

## 4. 缺失数据不伪造

- 厂商未落盘的 token 不猜；本地读不到的额度不造。
- `doctor` / report / HTML 必须显式说明缺口。
- 估算必须标注为估算，且不得伪装成真值。

## 5. 默认离线，联网显式

- 默认只读本地源、只写本地 SQLite。
- 唯一联网例外是 Trae CN credits 的两条显式前台刷新路径。
- 凭证只在刷新进程内使用，不落库、不写日志、不进 HTML。

## 6. 仓库是系统记录

- 聊天、issue、Slack 中的结论若未回写仓库，对 agent 等于不存在。
- 设计理由、决策链和验证证据必须进入版本库。
- `AGENTS.md` 只做地图，详细事实源放在仓库内的 specs / architecture / design docs / plans 中。

## 7. 渐进披露

- `AGENTS.md` 短小稳定，只提供入口与硬规则。
- `ARCHITECTURE.md` 提供顶层实现图。
- `docs/design-docs/index.md` 提供设计知识目录与状态。
- agent 按需深入具体文档，而不是一开始吞下全部细节。

## 8. 机械约束优于口头规范

- 用结构测试、链接检查、AC 映射、CI 门禁 enforce 文档结构与行为约束。
- 规范若不能被检查，就容易漂移。
- 文档状态、事实源指针、目录结构都应可测试。
