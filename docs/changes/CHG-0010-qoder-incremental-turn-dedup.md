# CHG-0010 Qoder turn credits 增量去重与历史重复清理

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`usage sync` / `collectors.py`、`cli.py`、`store.py`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../requirements/REQ-0001-usage-ledger.md)
关联：[CHG-0006 Qoder turn credits](CHG-0006-qoder-turn-credits.md)、[REQ-0001 R41](../requirements/REQ-0001-usage-ledger.md)

## 1. 摘要

Qoder turn credits 原先只与“本批转录扫描结果”去重。增量同步跳过未变化转录文件时，历史转录 `request_id` 不在本批结果中，数据库 turn 行会以 `qoder-turn:*` 再写一次，导致同一请求重复计入 credits。本 CHG 让去重集合包含库中已持久化的 Qoder request ID，并删除历史上已写入的重复 turn 行。

## 2. 变更理由与证据

- 对应功能卡：REQ-0001 R9 / R41（Qoder 双源 credits 合并、去重）。
- 触发原因：2026-11-16 code review 发现增量路径未使用持久化 request ID。
- 证据：
  1. `_sync_into()` 传入 `transcript_files` 状态；未变化转录文件不会重扫。
  2. `scan_qoder_turn_credits()` 仅用 `result.credits` 构造 `seen`，增量同步时为当前批 turn 行。
  3. 两轮复现：第一轮转录写入 `r1`；第二轮在 Qoder DB 增加 `turn_credits_request_set_id=r1` 的行，转录文件未变化；修复前 SQLite 保留 `r1` 与 `qoder-turn:s1:m3` 两条记录。
- 不做的后果：同一请求被重复计入 Qoder credits；全量同步也不会删除已写入的重复行。

## 3. 行为 / AC delta

- 修改 R41：去重集合由“本批转录请求”扩展为“本批转录请求 + 库中已持久化 Qoder request ID”；匹配的 turn 行不写入，且删除同一 `qoder-turn:<session_id>:<message_id>` 的历史重复行。
- 预期行为：
  - 首次全量同步照旧写入转录与不重复的 turn 行。
  - 后续增量同步即使跳过转录文件，也不会重新写入已存在的 transcript request。
  - 已存在的重复 turn 行在下一次同步时被清理；转录请求保留。
  - `--stateless` 仍按全量扫描去重，不依赖库状态。
- 非目标：不改 Qoder 数据口径，不改变 transcript / turn 金额优先级之外的采集规则。

## 4. 影响范围与非目标

- 受影响：`SqliteStore.credit_request_ids` / `delete_credits`、`collect_all` / `_sync_into` 的 Qoder 参数传递、turn credits 扫描。
- 不影响：Trae CN、token、活动、报表聚合；无 schema 迁移。

## 5. 验证与观测

- 自动化：`QoderCliTest.test_incremental_backfill_skips_turn_request_seen_in_transcript` 覆盖两轮 backfill、已被污染的库和清理结果；`QoderTurnCreditsTest` 保持通过。
- 手工：`usage backfill` 第二轮后 `usage_credit` 不再出现重复 `qoder-turn:*`，Qoder credits 合计回到 transcript 值。
- 结果与证据：
  - 自动化：282 tests / 0 failures / 0 errors / 0 skips；新增测试修复前 `credit_count=3`，修复后为 `2`，重复 request ID 被删除。
  - 全量门禁：278→282 tests、0 skip；覆盖率 93.4%；AC map 45 criteria / 98 identifiers。
- 观测：`turn_credits:duplicate` 计数继续记录匹配次数；重复清理不新增用户可见提示。

## 6. 回滚方案

- 回滚方式：移除持久化 request ID 参数和 `delete_credits` 调用，恢复仅按本批结果去重。
- 数据兼容：清理仅删除由本功能生成的重复 turn 行；回滚不回填。
- 回滚验证：重跑两轮 backfill 测试，确认旧行为（credit_count=3）复现。

## 7. 风险与未决问题

- 风险：每次 Qoder 同步需读取库中全部 Qoder request ID。当前量级为千级，成本可接受；若未来达到百万级，再改为增量索引。
- 风险：删除历史重复行依赖 `turn_credits_request_set_id` 与转录 request ID 的语义一致；现有采集规则已按此前提去重。
- 未决：是否需要提供一次性 `doctor --fix` 报表；本 CHG 在同步路径内自动清理。

## 8. 关联与证据

- 功能卡：REQ-0001 R9 / R41。
- 文档修正：CHG-0006 §2 的 11-16 数据注明为首次扫描时点，最终值以 §5 为准。
- commit：`3a121d0`（实现 + 测试）。
- 测试：`tests.test_cli.QoderCliTest.test_incremental_backfill_skips_turn_request_seen_in_transcript`。

## 9. 变更记录

| 状态 | 操作人 | 证据 / 链接 |
|---|---|---|
| 提议 | wayne（评审反馈） | 2026-11-16 code review finding 1 |
| 开发中 | wayne | 2026-11-16 在 `feat/html-report-ux` 实现去重与清理 |
| 已验证 | wayne | 2026-11-16 282 tests / 0 skip；两轮 backfill 复现通过 |
