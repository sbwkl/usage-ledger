# SQLite 数据库结构（生成物）

来源：`src/usage_ledger/store.py` 的 `SCHEMA` 与 `_migrate()`。

表：`source_state`、`usage_turn`、`usage_daily`、`usage_activity`、`price_override`、`usage_credit`、`usage_quota`、`usage_est`、`meta`。

索引：`day,source`、`model`、`project`、`archived`、`source,day`、`day,quota_kind`。
