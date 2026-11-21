# CHG-0006 补齐 Qoder 桌面端 turn credits

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage credits` / `usage html` / `src/usage_ledger/collectors.py`
功能卡：[usage-ledger.md 本地 AI 编码工具用量台账](../../product-specs/usage-ledger.md)
关联：[usage-ledger.md R9 / R41](../../product-specs/usage-ledger.md)、[CHG-0007 Trae CN 展示结构对齐](CHG-0007-trae-report-parity.md)

## 1. 摘要

Qoder 新桌面端从 2026-11-13 晚间起不再把逐请求 `usage.credits` 写进转录，而是把每轮 `turn_credits` 写入 `main.sqlite.chat_session_messages`；现有采集只读转录，导致 11-14 ~ 11-16 的 Qoder credits 在报表中消失。本 CHG 增加 `turn_credits` 只读采集，与转录逐请求 credits 合并、去重，并让源签名跟踪活动库变化。

## 2. 变更理由与证据

- 对应功能卡的问题/目标：usage-ledger.md G1（在一个视图里回答用量问题）、R9（Qoder credits 真值）。
- 触发原因：用户 2026-11-16 反馈“qoder 14 号之后没有数据，这是不对的，14 15 16 都有数据”。
- 证据：
  1. 当前 `usage html` payload 的 Qoder credit rows 最晚为 `2026-11-13`；同一 payload 的 Qoder activity rows 已覆盖 `2026-11-14 ~ 2026-11-16`。
  2. `~/.qoder/projects/**/*.jsonl` 在 11-14 ~ 11-16 仍有新 assistant 消息，但消息内没有 `message.usage`；采集器在缺少 `context_usage_ratio` 时提前返回，连 credits 也不产出。
  3. `main.sqlite.chat_session_messages` 的 `turn_credits` 覆盖：
     - 11-12：1 条，2.14 credits
     - 11-13：3 条，5.23 credits
     - 11-14：13 条，67.75 credits
     - 11-15：43 条，102.92 credits
     - 11-16：26 条，112.50 credits（首次扫描时点；验证阶段数据库继续写入，最终为 27 条 / 123.40，见 §5）
  4. 抽样核对 11-13 22:28 / 22:33 / 22:34 的 DB `turn_id`，对应转录中同时间的 user / assistant 消息均无 `usage`；DB 的 `turn_credits_request_set_id` 也没有命中任何转录 `usage.request_id`。因此两源在样本上互补，不是同一请求的重复记录。
- 不做的后果：Qoder 最近 3 天在 credits KPI、图表、Top 8、明细表中全部显示为无数据；用户会误以为没有消耗。

## 3. 行为 / AC delta

- 修改：R9 增加桌面端 `turn_credits` 来源，仍只写 `qoder.credits`。
- 新增：R41（`turn_credits` 的键、时间、项目 / 模型映射、与转录 request 的去重、源签名）。
- 预期行为：
  - 读到 `turn_credits`（包括 0）时，每条 assistant 消息产出 1 条 Qoder credit，`request_id = qoder-turn:<session_id>:<message_id>`，`billable = true`，本地日按 `created_at` 归属。
  - 项目取 `chat_sessions.cwd` 的 basename；模型取 `chat_sessions.model`，缺失时为 `unknown`。
  - `turn_credits_request_set_id` 若等于转录中已见 `usage.request_id`，跳过 DB 行，转录优先。
  - 旧版 Qoder 库没有 `turn_credits` 列时不报错、不伪造数据，只记录跳过原因。
  - `source_signatures` 的 `qoder.credits` 包含 `main.sqlite` 与其 WAL，保证 `usage html` / 查看命令自动同步。
  - `usage credits --source qoder`、`usage html --source qoder`、`backfill` 均使用合并后的结果。
- 非目标：不改 `qoder.activity`、`qoder.est`、token 真值、Trae CN credits；不做跨厂商 credits 相加；不联网。

## 4. 影响范围与非目标

- 受影响：Qoder credits 采集、源签名、SQLite `usage_credit` 写入、CLI / HTML payload。
- 不影响：token 记录、活动聚合、Qoder 额度快照、Trae CN API 同步。
- 兼容性：无 schema 迁移；DB 行使用独立 `request_id` 前缀，旧转录 request 不受影响；旧库无列时静默跳过。

## 5. 验证与观测

- 自动化测试：
  - 新增 `QoderTurnCreditsTest`：读取 / 映射 / 0 credits / 空值 / 旧 schema / 与转录 request-set 去重 / 合并结果。
  - 扩展 `QoderSignatureTest`：活动库 mtime 变化会推进 `qoder.credits` 签名。
  - 全量 `python3 -m unittest discover -s tests -t .`、`check_test_policy.py`、`check_ac_map.py`、覆盖率门禁。
- 手工验证：
  - 用本机 `usage html` 生成报告，确认 Qoder credits 的 payload 与图表覆盖 11-14 ~ 11-16，且 11-12 / 11-13 既有转录行不被重复追加。
  - 对比 SQLite `usage_credit` 的日聚合与 DB `turn_credits` 日聚合（差值为转录独有请求）。
- 观测：`usage doctor` / `usage credits` 的 qoder.credits 覆盖日期与 notes 应说明合并来源；无新数据时不应重复写入。
- 结果与证据：
  - 自动化：`python3 -m unittest discover -s tests -t .` → 276 tests / 0 failures / 0 errors / 0 skips；`scripts/check_test_policy.py` 通过；`scripts/check_ac_map.py` → 43 criteria / 91 mapped identifiers；覆盖率 93.3%（collectors 95.2%）。
  - 手工：`USAGE_LEDGER_DB=/tmp/usage-ledger-chg6.db PYTHONPATH=src python3 -m usage_ledger backfill --source qoder` 后，`credits --since 2026-11-10 --until 2026-11-16` 的日值为 11-14 67.75/13、11-15 102.92/43、11-16 123.40/27；`usage html --source qoder --offline` payload 同样覆盖 11-14..16。
  - 融合检查：11-12/13 同时存在转录行（1367/536 请求）和 DB turn 行（1/3 条），按 `qoder-turn:` 前缀分列；样本未出现重复 request_set_id。

## 6. 回滚方案

- 回滚方式：移除 `scan_qoder_turn_credits` 调用及签名中的活动库路径，恢复只读转录。
- 数据兼容：已写入的 `qoder-turn:*` 行会被忽略；不影响转录行；可保留或按 source / request_id 前缀清理。
- 回滚验证：重跑 `usage credits --source qoder`，输出回到与 CHG 前一致的转录覆盖。

## 7. 风险与未决问题

- 风险：DB `turn_credits` 是 turn 级金额，转录是 request 级；若未来同一 turn 同时写两处，可能重复。当前以 `turn_credits_request_set_id` 与转录 request_id 的精确匹配做第一层保护，样本未发现重复。
- 风险：`chat_sessions.cwd` 为 `/private/tmp` 时项目显示 `tmp`；与转录项目命名可能不同，这是源字段差异，不做猜测。
- 未决：若 DB 未来提供 `billable` / 免费拆分，再扩展本 CHG；当前按 `billable=true` 计入。

## 8. 关联与证据

- 功能卡：[usage-ledger.md](../../product-specs/usage-ledger.md) R9、R41。
- 实测报告：`/tmp/usage-report-sit.html`（2026-11-16 生成）。
- commit：`735d00a`（实现 + 测试 + 文档）。
- 日志 / 截图 / 测试报告：`/tmp/usage-ledger-chg6.db`、`/tmp/chg6-qoder.html`、`/tmp/coverage-run.log`。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（待评审） | 2026-11-16 用户反馈 + DB / 转录 / 报表 payload 实测 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 开始实现 |
| 已验证 | wayne | 2026-11-16 276 tests / 0 skip、覆盖率 93.3%、AC map 43/91；本机 Qoder 11-14..16 已出现在 credits payload；commit `735d00a` |
