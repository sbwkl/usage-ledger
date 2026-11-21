# Cline 用量采集设计（As-Built）

| 项 | 内容 |
|---|---|
| 文档状态 | 已实现（v1，2026-11-11） |
| 代码入口 | `src/usage_ledger/collectors.py` → `scan_cline()` |
| 对外源 | `cline`（token 真值，参与 `report` / `top` / `html` 与成本口径） |
| 验收 | `python3 -m unittest discover -s tests -t .`（含 `ClineTest` / `ClineCliTest`） |

---

## 1. 数据可得性（本机实测）

样本：Cline CLI `3.0.66`，`~/.cline/data/sessions/` 下 20 个会话。

| 指标 | 实测 |
|---|---|
| 会话数 | 20 |
| assistant 消息 | 1,821 |
| 带 `metrics` 的 assistant | 1,806（99.2%） |
| 采集耗时 | 0.11s（20 个 `.messages.json`） |
| 时间覆盖 | 2026-08-11 ~ 2026-11-11 |

缺失的 15 条多为中断/失败响应，没有 `metrics`，采集时跳过并计数。

---

## 2. 目录与文件

```
~/.cline/data/sessions/
└── <session_id>/
    ├── <session_id>.json            # 会话元数据（cwd/workspace_root/provider/model）
    ├── <session_id>.messages.json   # 消息列表（token 唯一来源）
    └── <session_id>.compaction.json # 压缩快照（messages 是主文件的子集，不读取）
```

- 只读 `*.messages.json` 与同名 `.json` 元数据；不读 `data/db/*.db`、日志、settings。
  消息正文随 JSON 解析进入内存，但只提取 `metrics` 与元数据，不落库、不写日志、不进错误信息。
- `.compaction.json` 中的 message id 与主文件重叠（本机 7/7 会话均为子集），读取会导致重复，
  因此显式忽略。
- 会话元数据解析失败不影响 token 采集，只记录 error。

---

## 3. 消息结构（节选）

```json
{
  "id": "msg_1Et2_0Lz",
  "role": "assistant",
  "ts": 1794379608536,
  "modelInfo": {"id": "cline-free/nemotron-3.5-super-vl", "provider": "cline-pass"},
  "metrics": {
    "inputTokens": 12436,
    "outputTokens": 505,
    "cacheReadTokens": 8672,
    "cacheWriteTokens": 0
  }
}
```

- `ts`：epoch 毫秒（本机样本全部为整数）。
- `modelInfo` 可能缺失；`metrics` 可能整体缺失；两者都按回退规则处理。

---

## 4. 归一映射

| 目标字段 | 来源 | 说明 |
|---|---|---|
| `source` | 固定 `cline` | |
| `key` | `cline:<message.id>` | 缺 id 时用 `session:ts:index` 兜底并计数 |
| `day` | `local_day(ts / 1000)` | 本地时区，与全项目一致 |
| `input` | `max(inputTokens − cacheRead − cacheWrite, 0)` | **关键口径**，见 §5 |
| `output` | `outputTokens` | 含推理 token，本项目不单列 |
| `cache_read` | `cacheReadTokens` | 缺省 0 |
| `cache_write` | `cacheWriteTokens` | 缺省 0 |
| `reasoning` | 0 | Cline 未拆分 |
| `model` | `modelInfo.id` → 会话 `model` → `unknown` | |
| `provider` | `modelInfo.provider` → 会话 `provider` | |
| `session` | 消息文件 `sessionId` → 元数据 `session_id` → 目录名 | |
| `project` | `workspace_root` → `cwd` 的 basename | 不落完整路径 |

`Counts` 五字段互不重叠：`input + output + cache_read + cache_write` 等于服务端
`inputTokens + outputTokens`，不会因缓存 token 被重复计算。

---

## 5. `inputTokens` 包含缓存（证据）

Cline CLI 二进制内的成本计算函数按如下方式扣减：

```js
Math.max(0, usage.inputTokens - usage.cacheReadTokens - usage.cacheWriteTokens) / 1e6 * inputPrice
  + usage.cacheReadTokens / 1e6 * cacheReadPrice
  + usage.cacheWriteTokens / 1e6 * cacheWritePrice
```

因此 `inputTokens` 是**含缓存**的 prompt 总量；若直接入库会把缓存重复计一次。
本机 1,806 条记录中 `input >= cacheRead + cacheWrite` 全部成立（0 例为负），扣除后无异常。

---

## 6. 幂等、增量与归档

- **行级去重**：`cline:<message.id>`，同一消息重复采集只覆盖不累加。
- **签名**：会话 `*.messages.json` 与元数据 `*.json` 的最新 mtime（微秒）；mtime 变新才触发自动
  sync，检查成本为一次目录遍历 + stat。
- **压缩**：Cline 执行上下文压缩后，旧消息可能从 `.messages.json` 消失。每日
  `sync --full` 会把这些 key 标记为 `archived=1`，明细永久保留、不会重复计数。
- **失败隔离**：单个会话文件 JSON 解析失败只记入该源 `errors`，不影响其他会话与其他源。

---

## 7. 边界与未覆盖

- **不含成本**：`metrics.totalCost` 存在，但本项目成本表为空，暂不消费；`cost_source` 仍为
  `unknown`。
- **不拆推理 token**：`outputTokens` 含 reasoning，无法从会话文件拆分。
- **仅 Cline CLI/Desktop**：VS Code 扩展旧版
  `saoudrizwan.claude-dev/tasks/*/ui_messages.json` 形态尚无本机样本，未实现。
- **不回溯已删除会话**：源文件被删除后，只能依赖本地 DB 的 `archived` 记录。

---

## 8. 测试

| 用例 | 覆盖 |
|---|---|
| `ClineTest.test_metrics_mapping_and_fallbacks` | 缓存扣除、模型/项目/会话回退、无 metrics、0 token |
| `ClineTest.test_missing_root_is_unavailable` | 源目录缺失 |
| `ClineTest.test_broken_session_file_is_isolated` | 单文件损坏隔离 |
| `SignatureTest.test_cline_signature` | mtime 签名存在/缺失 |
| `ClineCliTest.*` | `backfill` 落库、`--stateless` 一致、自动增量刷新 |

Fixture：`tests/fixtures/cline/sessions/`（两个脱敏会话 + 一个 compaction 文件）。
