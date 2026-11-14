# usage-ledger 架构文档（As-Built）

| 项 | 内容 |
|---|---|
| 文档状态 | **待审核**（v1.1，2026-11-11 增补 Trae CN hook 估算与 Cline） |
| 代码基线 | `usage-ledger 0.5.0`；main `a2c9fce`（Trae CN）+ `feat/cline`（Cline） |
| 文档定位 | 描述**当前实现如何工作**，不是新方案。设计沿革与动机见 [DESIGN.md](DESIGN.md)、[QODER-DESIGN.md](QODER-DESIGN.md)、[QODER-CREDITS-DESIGN.md](QODER-CREDITS-DESIGN.md)、[TRAE-CN-DESIGN.md](TRAE-CN-DESIGN.md)、[CLINE-DESIGN.md](CLINE-DESIGN.md) |
| 验收基线 | `python3 -m unittest discover -s tests -t .` → **83 tests OK** |
| 阅读顺序 | 审核者先看 §0、§10、§11、§12；实现细节按需查 §4–§9 |

---

## 0. 结论摘要

- 系统是一个**拉取式、离线、单机**的用量台账：只读各 AI 编码工具自己落盘的日志/库，归一成统一记录，归档进本地 SQLite，再聚合成 CLI 表格与单文件 HTML。
- 对外是 **7 个源**（claude / codex / opencode / kilo / cline / qoder / trae-cn）；Qoder 在内部拆成 **4 条互不相加的轨道**（token 历史真值 / 活动 / credits 额度 / 估算 token），Trae CN 只有 hook 弱估算一条轨道。
- **源是唯一事实来源**；数据库只承担三件事：抗删除归档、聚合索引、同步状态。`--stateless` 完全绕过数据库。
- 唯一持久状态：`~/.local/share/usage-ledger/usage.db`（可用环境变量覆盖）。无常驻进程、无网络、零第三方依赖。
- 当前最需要审核的四个现状问题（详见 §11）：
  1. **P0：`prune` 后再 `sync` 会重放旧记录，下一次 `prune` 把同一段数据重复累加进 `usage_daily`**，已用最小用例复现（100 → 200）。
  2. **P1：`usage live` 实际约 2.3s**（本机实测），与 README 的 `<0.3s` 不符；原因是它顺带全量扫描了 1.65GB Qoder 旧 token 库与全部转录。
  3. **P1：读命令的降级行为不一致**：`report` 在库不存在时降级为读源，`credits` / `est` 会静默新建一个空库。
  4. **P2：设计文档与实现漂移**：`DESIGN.md` 仍是 v0.4「待审核」方案稿，其中 `NullStore`、计价、预算告警、WorkBuddy、zstd 等均未实现。

---

## 1. 系统定位与边界

### 1.1 一句话定位

> 一个只读本地日志、只写本地 SQLite、能算出「我今天每个平台每个模型花了多少 token」的离线工具。

### 1.2 目标与非目标

| 目标 | 当前状态 |
|---|---|
| 跨平台按 天 × 源 × 模型 × 项目 出 token | 已实现（`report` / `top` / `export` / `html`） |
| 极轻量：零第三方依赖、无常驻进程 | 已实现（Python ≥3.11 标准库） |
| 完全离线、无遥测 | 已实现（代码中无网络调用） |
| 只读源、不存正文 | 已实现（例外：Qoder 估算在内存中统计字符数，见 §8.1） |
| 长期留存、抗源删除 | 已实现（`archived` 标记 + 每日全量重扫） |
| 历史可回填 | 已实现（`backfill` 复用 `sync --full`） |
| 实时视图 | 已实现 `live`，但性能不达设计目标（§11 P1） |
| 计价 / 预算告警 / 额度轴（Trae/ChatGPT） | **未实现**（价格表为空，`cost_equiv_usd` 恒为 `unknown`） |
| GUI / TUI / 社交 / 云同步 / 多设备 | 明确不做 |

### 1.3 数据可得性（本机事实）

| 平台 | 本地 token 真值 | 其他可用数据 | 本系统处置 |
|---|---|---|---|
| Claude Code | 有（JSONL `message.usage`） | — | `claude` 源 |
| Codex CLI | 有（JSONL `token_count`） | — | `codex` 源 |
| OpenCode | 有（SQLite `message` / `session_message`） | — | `opencode` 源 |
| Kilo | 有（与 OpenCode 同构） | — | `kilo` 源 |
| Cline（CLI / Desktop） | 有（`~/.cline/data/sessions/**/*.messages.json` 的 `metrics`） | — | `cline` 源（§6.7） |
| Qoder | 仅历史（IDE 旧库，止于 2026-09-16） | 活动元数据、每请求 credits、转录文本 | 四轨（§6.4–6.6） |
| Trae CN | 无（加密库，密钥运行时下发） | 官方 hooks 的事件元数据（会话/工具/字符数） | `trae-cn.est` hook 弱估算（§6.8） |
| ChatGPT 桌面 | 无本地数据 | 无 | 不采集，`doctor` 说明 |
| WorkBuddy | 推测有（本机未安装） | — | 未实现 |

### 1.4 六条架构原则

1. **源是唯一事实来源**，DB 不是权威副本；读库与直读源必须给出一致答案。
2. **只追加事实**：同一条记录重复采集只做幂等覆盖，不做累加。
3. **四轨不相加**：token 真值、活动、credits、估算 token 分表、分命令、分展示。
4. **只读、零网络、零遥测**：不写源目录、不调用私有 API。
5. **拉取式、无常驻**：数据由 agent 自己落盘，任意时刻读盘都能拿到已落盘的全部数据。
6. **失败隔离**：单个源/文件解析失败不阻断其他源；错误进 `source_state` 与 `doctor`。

---

## 2. 架构总览

```
┌────────────────────────────── 数据源（全部只读） ──────────────────────────────┐
│ Claude Code JSONL   Codex JSONL   OpenCode / Kilo SQLite   Cline sessions JSON  │
│ Qoder IDE local.db  Qoder main.sqlite  Qoder transcripts  Qoder logs  Trae hooks │
└───────────────────────────────────┬─────────────────────────────────────────────┘
                                    │  collectors.py
                                    │  · glob / sqlite mode=ro / query_only
                                    │  · 逐文件错误隔离、行级去重、mtime/offset 跳过
                                    ▼
                         SourceResult × 9（统一中间模型）
   claude │ codex │ opencode │ kilo │ cline │ qoder │ qoder.activity │ qoder.credits
                                │ trae-cn.est
                                    │
              ┌─────────────────────┼──────────────────────────┐
              │                     │                          │
              ▼                     ▼                          ▼
      直读路径（无 DB）        store.py（SQLite WAL）      调度器 scheduler.py
      --stateless                usage_turn                 launchd:
      live                       usage_daily                 每小时 :07 sync
      doctor                     usage_activity              00:15 sync --full
                                 usage_credit                00:20 prune
                                 usage_quota
                                 usage_est
                                 source_state / meta
                                    │
                                    ▼
                              aggregation.py
              · 维度聚合（day/week/month/source/model/project/session）
              · 过滤、缺失日期、源 ∪ 库合并
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
              cli.py（table/json/csv）        html_report.py（单文件 HTML）
```

### 2.1 分层职责

| 层 | 模块 | 职责 | 不负责 |
|---|---|---|---|
| 采集 | `collectors.py` | 定位源、解析、映射为 `Record/Activity/Credit/QuotaSnapshot/Estimate`、行级去重 | 不写库、不做聚合 |
| 归一 | `models.py` + `pricing.py` | 统一字段模型；模型名别名归一 | 计价（当前为空实现） |
| 存储 | `store.py` | schema、幂等 upsert、按天替换活动、归档、prune、查询 | 不做业务聚合 |
| 聚合 | `aggregation.py` | 多维分桶、成本口径合并、过滤、缺失日期 | 不接触文件/DB |
| 展示 | `cli.py` | 参数、读写路径选择、自动刷新、表格/JSON/CSV | 不直接解析源 |
| 展示 | `html_report.py` | 服务端聚合结果 → 单文件离线交互页 | 不访问源/DB |
| 调度 | `scheduler.py` | 生成/安装/查询 launchd plist | 不执行采集 |
| 探针 | `scripts/probe.py` | 开发期全量只读扫描，独立于包 | 不参与运行时 |

---

## 3. 模块清单

| 文件 | 行数 | 关键符号 | 说明 |
|---|---:|---|---|
| `src/usage_ledger/models.py` | 141 | `Counts` `Record` `Activity` `Credit` `QuotaSnapshot` `Estimate` `SourceResult` | 唯一中间模型；`SourceResult.add()` 内置按 key 去重（同 key 保留 token 总量更大者） |
| `src/usage_ledger/collectors.py` | 1265 | `scan_claude` `scan_codex` `scan_sqlite_agent` `scan_cline` `scan_qoder_*` `scan_trae_cn_est` `source_signatures` `collect_all` | 7 个公开源、9 个 `SourceResult` |
| `src/usage_ledger/trae_hooks.py` | 326 | `install` `uninstall` `status` `event_files` `trae_event_dir` | Trae CN hook 脚本与事件文件管理；不解析源库 |
| `src/usage_ledger/store.py` | 678 | `SqliteStore`、`SCHEMA` | 8 张表 + `meta`；WAL；批量 upsert；按天替换活动 |
| `src/usage_ledger/aggregation.py` | 110 | `aggregate` `match` `merge_records` `missing_days` `period_label` | 纯函数，可单测 |
| `src/usage_ledger/pricing.py` | 38 | `ALIASES` `PRICES` `normalize_model` `cost_for_record` | 别名表可用；价格表为空，成本恒 `unknown` |
| `src/usage_ledger/scheduler.py` | 135 | `JOBS` `build_plist` `install` `uninstall` `status` | 3 个 launchd 任务 |
| `src/usage_ledger/cli.py` | 1724 | `main` `build_parser` `_sync_into` `_refresh_*_if_stale` `cmd_*` | 全部命令与读写路径编排 |
| `src/usage_ledger/html_report.py` | 2576 | `build_payload` `render_html` `TEMPLATE`、`AGENT_KINDS` | 内联 CSS/JS/SVG；payload 占位符替换 |
| `scripts/probe.py` | 521 | `scan_*` `aggregate` `main` | 独立只读探针，标准库 only |

依赖方向（无环）：

```
cli  → collectors, store, aggregation, html_report, pricing, scheduler
html_report → models
store → models
collectors → models
aggregation → models
pricing / scheduler → （无内部依赖）
scripts/probe.py → （独立，不 import 包）
```

> `build/lib/usage_ledger/` 是本地构建缓存（已 gitignore），内容落后于 `src/`；`uv tool install` 以 `src/` 为准。不要把 `build/` 当源码。

---

## 4. 运行时数据流

### 4.1 九个采集结果

`collect_all()` 返回 9 个 `SourceResult`，但对外只暴露 7 个源：

| `SourceResult.name` | 对外源 | 产出 | 落库目标 |
|---|---|---|---|
| `claude` | claude | `Record` | `usage_turn` |
| `codex` | codex | `Record` | `usage_turn` |
| `opencode` | opencode | `Record` | `usage_turn` |
| `kilo` | kilo | `Record` | `usage_turn` |
| `cline` | cline | `Record` | `usage_turn` |
| `qoder` | qoder | `Record`（历史 token） | `usage_turn` |
| `qoder.activity` | qoder | `Activity` | `usage_activity` |
| `qoder.credits` | qoder | `Credit` + `QuotaSnapshot` + `Estimate` | `usage_credit` / `usage_quota` / `usage_est` |
| `trae-cn.est` | trae-cn | `Estimate` | `usage_est`（`source='trae-cn.est'`） |

`SourceResult` 同时携带：`available`、`complete`、`errors`、`notes`、`key_kinds`、`affected_days`、`cursor_ms`、`transcript_state`、`seen_keys`、`dup_dropped`。

### 4.2 写路径：`sync` / `backfill` / 自动刷新

```
usage sync [--source X] [--since D] [--full] [--dry-run]
      │
      ├─ source_signatures()        每个源的最新 mtime（微秒）
      ├─ store.source_mtimes()      库中上次记录的签名
      ├─ 读 meta：activity_cursor / transcript_files
      │
      ├─ collect_all()
      │    ├─ qoder token 库 mtime 未变 → 跳过 1.65GB 全表扫描
      │    └─ 转录文件 size+mtime 未变 → 跳过该文件；变了则从 offset-1MB 续读
      │
      ├─ 逐 SourceResult 分派：
      │    ├─ qoder.activity → replace_activity_days(受影响天 ∪ 今天/昨天)
      │    ├─ qoder.credits  → upsert_credits + upsert_estimates + 保存 transcript_files
      │    └─ 其余          → upsert_records(cost_fn=cost_for_record)
      │
      ├─ update_source_state(source, files, records, status, error, last_ts, last_mtime)
      │
      └─ 仅当 full 且 !since 且该源 healthy：
           mark_archived(source, 本轮出现的 key 集合)
           set_meta("full_scan_at:<source>", 时间)
```

要点：

- `backfill` 等价于 `sync --full`（`cmd_backfill` 直接改写参数后复用 `cmd_sync`）。
- `--since` 只过滤要写入的 token 记录，**不过滤活动、credits、估算**；且带 `--since` 时不做归档判定。
- 自动刷新（`_refresh_if_stale`）与手动 `sync` 走**同一条** `_sync_into` 代码路径，因此幂等语义一致。
- 归档判定只在“该源本轮完整成功”时执行；源目录缺失/解析失败不会误标（`result.healthy`）。

### 4.3 读路径与自动刷新

| 命令 | 读取方式 | 刷新动作 | 库不存在时 |
|---|---|---|---|
| `report` / `export` / `top` / `html` | `SqliteStore.fetch_records(include_daily=True)` | `_refresh_if_stale`（按源 mtime > 库中签名） | `report` 降级为直读源并 warning；`html` 同 `_load_records` |
| `report --live` | 库 ∪ 直读源（按 key 合并，源覆盖库） | 先 auto-sync，再直读源 | 降级直读 |
| `activity` | `fetch_activity` | 只看 `qoder.activity` 签名，变了才重算 | 降级直读 |
| `credits` | `credit_daily` / `credits_totals` / `latest_quota` | 只看 `qoder.credits` / `qoder.est` 签名 | **自动建库**（空库） |
| `est` | `est_rows` / `est_totals` | 同上 | **自动建库**（空库） |
| `html` | 同时走 `report` 与 `credits` 两条链路 | 两套刷新 | 记录侧降级、额度侧建库 |
| `live` | `collect_all()`，不碰库 | 无 | 无关 |
| `doctor` | 读库元信息 + `collect_all()` | 无（不写库） | 只报“DB 不存在” |
| `prune` / `schedule` / `pricing` | 本地 | 无 | `prune` 会建库 |

自动刷新的输出固定走 **stderr**（`auto-sync: ...`），保证 `--format json|csv` 的 stdout 干净。

### 4.4 三档新鲜度（实现现状）

| 档 | 路径 | 实际延迟 | 常驻 |
|---|---|---|---|
| L1 直读 | `usage live`、`usage --stateless ...` | 全源约 **2.3s**（本机实测，见 §8.4），单源 claude 约 0.2s | 无 |
| L1.5 库 + 源合并 | `report --live` | 自动刷新 + 直读，秒级 | 无 |
| L2 库 | `report` 等 | ≤ 同步周期（默认每小时） | 无 |
| L3 daemon | 未实现 | — | — |

### 4.5 调度

`usage schedule install` 生成并加载 3 个 LaunchAgent：

| job | label | 触发 | 命令 |
|---|---|---|---|
| sync | `local.usage-ledger.sync` | 每小时第 7 分钟 | `usage sync` |
| full | `local.usage-ledger.full` | 每日 00:15 | `usage sync --full` |
| prune | `local.usage-ledger.prune` | 每日 00:20 | `usage prune --keep-days 90` |

plist 中显式注入 `PATH`、`USAGE_LEDGER_HOME`、`USAGE_LEDGER_SOURCE_HOME`、可选 `USAGE_LEDGER_DB`；优先使用 PATH 中的 `usage`，否则退回 `python -m usage_ledger` + `PYTHONPATH=src`。`RunAtLoad=false`，不常驻。

---

## 5. 数据模型

### 5.1 表清单

数据库：`~/.local/share/usage-ledger/usage.db`（`USAGE_LEDGER_DB` 可覆盖；同目录含 `-wal`/`-shm`）。

| 表 | 主键 | 内容 | 写入者 | 读取者 | 保留策略 |
|---|---|---|---|---|---|
| `source_state` | `source` | 每源同步状态、签名、记录数、错误 | `_sync_into` / `_store_*_result` | `doctor`、自动刷新 | 永久 |
| `usage_turn` | `id`（去重键） | token 明细，一行一次调用/事件 | `upsert_records` | `fetch_records`、prune | 90 天后仅 `archived=0` 行被压缩 |
| `usage_daily` | `(day,source,model,project,session_id)` | 日聚合，prune 时从 turn 汇总 | `prune` | `fetch_records(include_daily=True)` | 永久 |
| `usage_activity` | `(source,day,project)` | Qoder 活动指标（日 × 项目） | `replace_activity_days`（整日重建） | `fetch_activity` | 永久，不 prune |
| `usage_credit` | `request_id` | Qoder 每请求 credits（真值） | `upsert_credits` | `credit_daily` 等 | 永久，不 prune |
| `usage_quota` | `(request_id,quota_kind)` | Qoder 配额余额快照 | `upsert_credits` | `latest_quota` | 永久，不 prune |
| `usage_est` | `request_id` | 估算 token（`qoder.est` / `trae-cn.est`，按 `source` 区分） | `upsert_estimates` | `est_rows` 等 | 永久，不 prune |
| `price_override` | `model_pattern` | 手工价格覆盖 | **无** | **无** | 未使用（预留） |
| `meta` | `key` | 游标与全局状态 | `set_meta` | 各处 | 永久 |

### 5.2 四轨语义

| 轨道 | source 标签 | 数据性质 | 时间范围 | 命令 | 可加性 |
|---|---|---|---|---|---|
| token 真值 | `qoder` | 服务端逐调用真值（历史） | 2026-06-01 ~ 2026-09-16 | `report` / `top` / `html` | 可与其他 token 源相加，但仅限历史区间 |
| 活动 | `qoder.activity` | 非 token 指标 | 2026-06-01 ~ 现在 | `activity` / `html` | **不可**与任何 token 相加 |
| 额度 | `qoder.credits` | 服务端每请求计费真值 | 2026-09-16 ~ 现在 | `credits` / `html` | **不可**与 token 相加 |
| 估算 token | `qoder.est` | 估算值（±30~40%） | 2026-09-16 ~ 现在 | `est` / `html` | **不可**与真值/额度相加 |
| Trae CN 估算 | `trae-cn.est` | hook 字符数弱估算（误差更大，无 ratio） | 安装 hook 起 | `est --source trae-cn` / `html` | **不可**与任何 token 相加 |

Cline 是真值 token 源（`cline`），没有附加轨道；其 `inputTokens` 含缓存，采集时已扣除（§6.7）。

### 5.3 统一记录模型

`Counts` 五个互不重叠字段：`input` / `output` / `cache_read` / `cache_write` / `reasoning`。`Record` 另含 `source/day/model/project/session/key/counts/ts/model_raw/provider/agent/sidechain/cost/cost_source/turns`。

`SourceResult.add()`：同 key 重复出现时 `dup_dropped += 1`，保留 `counts.total()` 更大的那条。这是采集层的第一道幂等。

### 5.4 去重键（实现值）

| 源 | 去重键 | 说明 |
|---|---|---|
| claude | `claude:<message.id 或 uuid>` | 同一 `message.id` 的中间态行被 `"iterations" in usage` 过滤掉 |
| codex | `codex:<文件名 stem>:<累计 total_tokens>` | 累计值在文件内单调；归档副本同 stem 同累计值 → 只计一次 |
| opencode / kilo | `<source>:<message.id>` | 两个 DB（`opencode.db`、`opencode-stable.db`）共用此键 |
| cline | `cline:<message.id>`；缺失时 `cline:<session>:<ts>:<index>` | `.compaction.json` 是 `.messages.json` 的子集，不读取，避免重复 |
| qoder token | `qoder:<chat_message.id>` | 一行 assistant 消息 = 一次模型调用 |
| qoder activity | `(source='qoder.activity', day, project)` | 整日 DELETE 后重建，天然幂等 |
| qoder credit | `request_id`（来自转录 `usage.request_id`） | 跨父/子代理转录重复出现只计一次 |
| qoder est | `<sessionId>:<timestamp>` | 同一响应多行 assistant 合并 |
| qoder quota | `(requestId, quota_kind)` | 一次响应含 `user` / `add_on` 两类 |
| trae-cn est | `trae-cn:<uid>`；缺失时 `<session>:<ts>:<event>:<file>:<line>` | 事件按 `(ts,file,line)` 重放，同一 uid 只计一次 |

### 5.5 `archived` 生命周期

```
sync --full（每日 00:15，且该源 healthy、无 --since）
      │
      ├─ 本轮源中出现的 key        → archived = 0（源里还在，可重建）
      └─ 库中有、本轮未出现的 key  → archived = 1（源里没了，必须保留）
```

- 单源解析失败/目录缺失 → `result.healthy == False` → **跳过**该源归档判定。
- `upsert_records` 对新写入行一律 `archived=0`。
- `prune` 只删除 `day < cutoff AND archived=0` 的明细，先汇总进 `usage_daily`。
- `archived=1` 的明细**永不被 prune**；`doctor` 报告“已保全 N 条源已删除的历史记录”。

### 5.6 prune 与日聚合（含已知缺陷）

`prune(keep_days=90)`：

1. 选出 `day < cutoff AND archived=0` 的明细；
2. 按 `(day,source,model,project,session_id)` 汇总 `INSERT ... ON CONFLICT DO UPDATE` 进 `usage_daily`（累加语义）；
3. `DELETE` 这批明细；
4. `archived=1` 行保持原样，只报告数量。

**已知缺陷（P0，见 §11）**：第 3 步删除后，下一次 `sync` 会从源重新解析并 upsert 同一批旧记录（采集器没有“已 prune 水位”概念），再下一次 `prune` 会把它们**再次累加**进 `usage_daily`。已复现：同一条 100 input 的记录，两次 prune 后 `fetch_records` 合计 200。

### 5.7 `meta` 键

| key | 用途 |
|---|---|
| `activity_cursor:qoder` | 活动库处理到的 `MAX(updated_at)`（epoch ms） |
| `activity_stall:qoder` | 活动库在更新但 cursor 连续未推进的次数（≥3 告警） |
| `activity_messages:qoder` | 上次活动的消息总数（用于 stall 判定） |
| `transcript_files` | Qoder 转录逐文件游标：`path → {offset,size,mtime_ns,cwd,model}` |
| `est_factor_version` | 估算系数版本（当前 `v1`） |
| `full_scan_at:<source>` | 上次成功全量重扫时间（>26h 由 doctor 告警） |

### 5.8 日期归属

- 所有 `day` 均由本地时区 `datetime.fromtimestamp(ts)` 得出；不使用 UTC 日期。
- Qoder 活动按 `created_at` 归属；受影响天重算时额外覆盖今天与昨天，防止跨天/晚到 metrics。
- Qoder 转录按 `timestamp` 归属；`usage.credits` 与 `est` 同日。

---

## 6. 采集规格（逐源）

### 6.1 Claude Code（`claude`）

- 路径：`~/.claude/projects/**/*.jsonl`，递归包含 `subagents/`。
- 记录：`type == "assistant"` 且 `message.usage` 含 `"iterations"` 键（用于排除流式中间态）；`counts.total()==0` 跳过。
- 映射：`input←input_tokens`、`output←output_tokens`、`cache_read←cache_read_input_tokens`、`cache_write←cache_creation_input_tokens`。
- 元数据：`model←message.model`、`project←basename(cwd)`、`session←sessionId`、`key←claude:<message.id || uuid>`。
- 实测：103 文件 / 3,887 记录 / 214ms。

### 6.2 Codex CLI（`codex`）

- 路径：`~/.codex/sessions/**/*.jsonl` + `~/.codex/archived_sessions/**/*.jsonl`；`.jsonl.zst` 只统计数量并提示，未解压。
- 记录：`event_msg` 且 `payload.type == "token_count"`；事件按 timestamp 排序。
- 增量：**首事件**用 `last_token_usage`（规避跨 rollout 继承累计基线）；其余事件用累计值逐字段差分。
- 拆分：`input = max(Δinput_tokens − Δcached_input_tokens, 0)`、`cache_read = Δcached_input_tokens`、`output = max(Δoutput_tokens − Δreasoning_output_tokens, 0)`、`reasoning = Δreasoning_output_tokens`、`cache_write = Δcache_write_input_tokens`。
- 模型：取事件之前最近一次 `turn_context.payload.model`，回退 `session_meta.base_instructions.provenance.model`。
- 去重键：`codex:<stem>:<cumulative total_tokens>`，使 `sessions/` 与 `archived_sessions/` 的同一 rollout 只计一次。
- 实测：69 文件 / 4,604 记录 / 306ms。

### 6.3 OpenCode / Kilo（`opencode`、`kilo`）

- 路径：`~/.local/share/opencode/opencode.db`（另尝试 `opencode-stable.db`）、`~/.local/share/kilo/kilo.db`；只读 URI。
- 兼容两代 schema：新版 `session_message`（`type='assistant'`，可 LEFT JOIN `session_v2.directory`）与旧版 `message`（`data.role == 'assistant'`）；旧表中与 `session_message` 同 id 的行不重复读取。
- 映射：`tokens.input/output/reasoning`、`tokens.cache.read/write`；`model←data.model.id` 或 `data.modelID`；`project←basename(path.cwd)` 或 `session_v2.directory`；`ts←time_created`。
- 去重键：`<source>:<message.id>`。
- 实测：opencode 9,625 记录；kilo 717 记录（未单独计时，包含在全量 2.25s 内）。

### 6.4 Qoder token 历史（`qoder`）

- 路径：`~/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db`（`USAGE_LEDGER_QODER_TOKEN_DB` 可覆盖），约 1.65GB，旧 IDE 库。
- SQL 只取 `id/session_id/gmt_create/model_info/token_info` 与 `chat_session` 的项目/会话类型，不碰 `content`。
- 行：`role='assistant'`、`token_info` 非空且非 `''/null/{}`、`prompt+completion > 0`。
- 映射：`input = max(prompt_tokens − cached_tokens, 0)`、`cache_read = cached_tokens`、`output = completion_tokens`、`cache_write=0`、`reasoning=0`；`model←model_info.model_key`，回退 `preferred_model_info`；`project←project_name`，回退 `basename(project_uri)`；`agent←session_type`。
- 去重键：`qoder:<message.id>`。每条 assistant 消息 = 一次真实模型调用（agent loop 中不合并）。
- 优化：`sync` 路径下若 token 库 mtime 未变，整体跳过；`live` 路径没有这个跳过（§11 P1）。
- 实测：19,956 记录 / 1,724ms。

### 6.5 Qoder 活动（`qoder.activity`）

- 路径：`~/Library/Application Support/com.qoder.app.stable/main.sqlite`（`USAGE_LEDGER_QODER_ACTIVITY_DB` 可覆盖）。
- 表：`chat_session_messages` LEFT JOIN `chat_sessions`；角色 `COALESCE(role, payload.role)`。
- 指标（按天 × 项目）：
  - `sessions`：当天有 user 消息的 distinct session；
  - `prompts`：user 消息数；
  - `assistant_calls`：assistant 消息数；
  - `assistant_with_metrics`：带 `turnMetrics` 的 assistant 数（解释 turns/duration 的缺失）；
  - `turns` / `duration_ms`：`payload.turnMetrics.turnCount/durationMs` 求和；
  - `tool_calls`：`payload.parts[].type == 'tool'` 计数。
- 增量：读 `activity_cursor`；`MAX(updated_at) < cursor` 视为库回滚，转全量；`MAX(updated_at) <= cursor` 直接返回“无新消息”；否则用 `cursor − 120s` 找受影响消息，推导受影响天，再**整日重算**（DELETE + INSERT），并强制覆盖今天/昨天。
- JSON 安全：所有表达式先 `json_valid()`；启动时检查 JSON1 扩展；非法 payload 按 0 处理。
- 实测：105 行活动 / 446ms；全量按日重建约 0.4~0.5s。

### 6.6 Qoder 额度 / 估算 / 余额（`qoder.credits`）

一次转录扫描同时产出 credit 与 estimate：

- 转录路径：`~/.qoder/projects/**/*.jsonl`（含 subagents），逐文件游标；文件变大从 `offset − 1MiB` 续读并丢弃半行，文件截断则从头读。
- 响应聚合：同一 `sessionId + timestamp` 的多条 assistant 行合并为一个响应；`chars_out = text + thinking + json(tool_use.input)` 字符数；`chars_in` 来自上一条 user 的 `tool_result` + `humanInput.text`（二选一，不重复计）。
- credit：`usage.request_id` 存在且 `usage.credits` 为数字时写一行；`billable` 照抄。键 = `request_id`。
- estimate：`est_input = round(context_usage_ratio × 200000)`；`est_output = round(chars_out ÷ factor[model])`，factor：`gfmodel 3.85` / `dfmodel 4.58` / 默认 `3.8`；`ratio` 缺失则该请求不计估算并计数。键 = `sessionId:timestamp`。
- 余额快照：扫 `~/Library/Application Support/com.qoder.app.stable/logs/*/main*.log*`，匹配 `用量响应摘要`，解析 `userQuota` / `addOnQuota` 的 total/used/remaining 与 `totalUsagePercentage`；键 = `(requestId, quota_kind)`。
- 实测：284 个转录/日志文件 / 9,815 credit / 9,815 est / 26 快照 / 1,509ms。

### 6.7 Cline（`cline`）

- 路径：`~/.cline/data/sessions/<session>/<session>.messages.json`（消息）+ 同名 `.json`（元数据：`session_id` / `workspace_root` / `cwd` / `provider` / `model`）；`.compaction.json` 是消息子集，忽略。
- 记录：`role == "assistant"` 且含 `metrics`；`metrics` 缺失跳过并计数；`counts.total()==0` 跳过。
- 映射：`cache_read←cacheReadTokens`、`cache_write←cacheWriteTokens`、`input = max(inputTokens − cacheReadTokens − cacheWriteTokens, 0)`（Cline 的 `inputTokens` 含缓存，与其成本公式同口径）、`output←outputTokens`（含推理 token，未单列）、`reasoning=0`。
- 元数据：`model←modelInfo.id`，回退会话元数据 `model`；`provider←modelInfo.provider`，回退元数据 `provider`；`project←basename(workspace_root || cwd)`；`session←sessionId`，回退目录名；`ts←ts`（毫秒；>1e11 才除以 1000）。
- 去重键：`cline:<message.id>`；缺 id 时 `cline:<session>:<ts>:<index>`。
- 实测（2026-11-11）：20 会话 / 1,806 assistant / 1,806 记录 / 108ms；range 2026-08-11..2026-11-11；input 11,559,216 / output 1,020,011 / cache_read 131,382,471 / cache_write 0。
- 详见 [CLINE-DESIGN.md](CLINE-DESIGN.md)。

### 6.8 Trae CN hook 弱估算（`trae-cn.est`）

- 路径：事件文件 `~/.local/share/usage-ledger/trae-cn/*.jsonl`（`USAGE_LEDGER_HOME` 下），由 `usage hooks install trae-cn --scope global` 写入 `~/.trae-cn/hooks.json` 的 hook 产生。
- 事件只含 `event` / `session` / `project` / `tool` / `chars_in` / `chars_out` / 可选 `model` / `ts`，不落正文。
- 重放：按 `(ts, file, line)` 排序，维护每会话上下文 `ctx`；`UserPromptSubmit` / `PostToolUse` 累加 `chars_in`，`PreToolUse` / `Stop` 以 `chars_out` 产出一条 `Estimate` 并累加。
- 估算：`est_input = min(round(ctx / factor) + overhead, window)`、`est_output = round(chars_out / factor)`；默认 `factor=3.8`、`overhead=0`、`window=200000`，可用 `USAGE_LEDGER_TRAE_EST_*` 覆盖；`ratio=None`。
- 去重键：`trae-cn:<uid>`；缺失时 `<session>:<ts>:<event>:<file>:<line>`。
- 详见 [TRAE-CN-DESIGN.md](TRAE-CN-DESIGN.md)。

---

## 7. 查询与输出契约

### 7.1 聚合

`aggregate(records, dims, period)`：

- 支持维度：`day` / `week` / `month` / `source` / `model` / `project` / `session`。
- `week` 用 ISO 周（`YYYY-Www`），`month` 用 `YYYY-MM`。
- 成本：若桶内无任何已知成本 → `None` + `unknown`；全部已知 → 求和 + 多数来源；部分已知 → 求和 + `partial`。
- 同时输出 `total`（五字段之和）与 `turns`。

`merge_records(db, source)`：按 key 合并，**源覆盖库**（`report --live` 使用）。

`missing_days(records, since, until)`：显式列出无数据日期，避免“没采到”被当成 0。

### 7.2 CLI 矩阵

| 命令 | 写库 | 支持 `--stateless` | 输出格式 | 备注 |
|---|---|---|---|---|
| `sync [--source] [--since] [--full] [--dry-run]` | 是 | 否（报错退出 2） | 文本 | `--since` 只过滤 token 记录 |
| `backfill [--since] [--source]` | 是 | 否 | 文本 | = `sync --full` |
| `live [--source] [--session] [--watch]` | 否 | 无关 | 文本 | 不落库；`--watch` 前台循环 |
| `report` / `export` | 读 + 自动刷新 | 是 | table/json/csv | `export` 强制 csv |
| `top <models\|sources\|projects\|sessions>` | 读 + 自动刷新 | 是 | table/json | 按 total 降序，`--limit` |
| `activity` | 读 + 活动刷新 | 是 | table/json/csv | 仅 `qoder` 有数据 |
| `credits` | 读 + 额度刷新 | 是 | table/json | 余额走 stderr |
| `est` | 读 + 额度刷新 | 是 | table/json/csv | 标注 `est`；含 `qoder.est` 与 `trae-cn.est` |
| `html` | 读 + 双刷新 | 是 | 写 HTML 文件 | 单文件、离线 |
| `doctor [--probe <source>]` | 否 | 是（跳过 DB 段） | 文本 | 源健康 + 归档 + 覆盖 |
| `pricing [model]` | 否 | 无关 | 文本 | 当前全部 `unknown` |
| `prune [--keep-days N] [--dry-run]` | 是 | 否 | 文本 | 默认 90 天 |
| `schedule install\|uninstall\|status` | 改 LaunchAgents | 无关 | 文本 | `--dry-run` 仅 install |

全局：`usage --version`、`usage --stateless <cmd>`。

### 7.3 输出契约

- `table`：纯文本对齐表，无 ANSI 颜色。
- `json`：固定 schema 的数组/对象；`report` 输出行数组（不含总计）。
- `csv`：RFC4180，UTF-8。
- **stdout 只放数据**；页脚提示、覆盖说明、自动刷新消息、成本免责声明全部走 **stderr**。
- 退出码：`0` 正常；`2` 参数错误（`ValueError` 捕获）。设计中的 `1/3` 未实现。

### 7.4 HTML 报表

- 生成：服务端把 token 行按 `(day,source,model,project)`、credits 行与估算行按 `(day,model,project)` 聚合，和活动/额度/覆盖信息一起序列化为 JSON，替换模板占位符。
- 安全：payload 中 `<` 转义为 `\u003c`；CSP `default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:` → **零外部请求**。
- 客户端职责：
  - 按 `agents` 映射把来源分为 `精确 Token` / `精确 Credits` / `仅估算` 三组，生成顶部 Agent 导航；总览只聚合 token 类来源；
  - 每个 Agent 页复用同一套四块（每日用量 / 模型 Top 8 / 项目 Top 8 / 明细），单位为 tokens / credits / est tokens；
  - Qoder 页以 credits 为主指标，「影子：估算 token」默认关闭；开启后在每日图上叠加估算虚线（右轴），Top 8 显示影子标注，明细追加影子列并按 `(day,model,project)` 补出只有估算的行；
  - 日期范围按页面记忆，默认取该页数据覆盖；>200 天自动按周聚合；
  - 活动指标折叠在 Qoder 页底部，与 credits/token 明确隔离；浅/深色主题（`localStorage`）。
- payload 结构：

```json
{
  "generated_at": "...",
  "range": {"since": "...", "until": "..."},
  "agents": {"claude":"token","codex":"token","opencode":"token","kilo":"token",
             "cline":"token","qoder":"credits","trae-cn":"estimate"},
  "rows": [{"day":"...","source":"...","model":"...","project":"...",
            "input":0,"output":0,"cache_read":0,"cache_write":0,"reasoning":0,
            "total":0,"turns":0,"cost_equiv_usd":null,"cost_source":"unknown"}],
  "activity": [{"day":"...","source":"qoder","project":"...",
                "sessions":0,"prompts":0,"assistant_calls":0,
                "assistant_with_metrics":0,"turns":0,"tool_calls":0,"duration_ms":0}],
  "credits": {"days":[{"day":"...","credits":0,"requests":0,"free_credits":0,"snapshots":0}],
              "rows":[{"day":"...","model":"...","project":"...","credits":0,
                       "free_credits":0,"requests":0,"free_requests":0}],
              "totals":{...},
              "quota":{"add_on":{...},"user":{...}}},
  "est": {"rows":[{"day":"...","model":"...","project":"...","est_input":0,"est_output":0,
                    "requests":0,"chars_in":0,"chars_out":0,"missing_ratio":0}],
          "totals":{...},"factor_version":"v1"},
  "trae_est": {"rows":[{"day":"...","model":"...","project":"...","est_input":0,
                         "est_output":0,"requests":0,"chars_in":0,"chars_out":0}],
               "totals":{...},"factor_version":"trae-hook-v1"},
  "coverage": {"qoder":{"token_since":"...","token_until":"...",
                         "activity_since":"...","activity_until":"..."}},
  "notices": ["..."]
}
```

### 7.5 `doctor` 检查项

- DB 路径、明细/日聚合行数、`archived` 保全数、活动汇总、credits/est 计数、最新额度快照及年龄（>24h 告警）。
- `source_state` 每源状态、`full_scan_at`、WAL 大小（>1MB 告警）。
- 逐源扫描：文件数、记录数、token 总量、近 7 天记录数、错误、状态。
- 异常提示：token 全 0、记录数较上次下降 >50%、>26h 未成功同步、Qoder token 库 >30 天未更新、活动连续 3 次 cursor 未推进、额度日志解析失败、credits 与快照增量偏差 >20%。
- `--probe <source>`：打印模型/活动月度分布。

---

## 8. 横切机制

### 8.1 只读与隐私

| 约束 | 实现 |
|---|---|
| 源只读 | SQLite `file:...?mode=ro` + `PRAGMA query_only=ON`；JSONL 只 `open(..., "r")` |
| 不存正文 | token 表只存计数与元数据；Qoder token SQL 不 SELECT `content` |
| 活动不取正文 | `role/turnMetrics/parts.type` 由 SQLite JSON1 在库内提取，payload 不进 Python |
| 估算的例外 | 转录正文仅在采集进程内存中用于统计字符数；落库只有 `chars_in/chars_out/ratio/est_*`，不写日志、不进错误信息 |
| 项目路径 | 统一存 `basename`；设计中的 `full/hash` 模式未实现 |
| 网络 | 无任何网络调用 |
| 凭证 | 不读取任何账号凭证 |

### 8.2 失败隔离

- 单文件解析失败 → 记入 `SourceResult.errors`，继续下一个文件；转录 JSON 错误最多记录 20 条。
- 单源失败 → 其他源照常；`_status()` 输出 `unsupported` / `error` / `partial` / `ok`。
- 归档判定仅在 `healthy` 时执行，避免一次故障永久误标。
- 自动刷新失败（`sqlite3.Error` / `OSError`）→ stderr 警告，继续使用库中现有数据。

### 8.3 幂等与并发

- token：行级去重键 + `ON CONFLICT DO UPDATE`。
- 活动：按受影响天 `DELETE` + `INSERT`，事务内完成。
- credits/est/quota：业务主键 upsert。
- 单命令单连接；WAL + `busy_timeout=5000`；launchd 与手动命令可能重叠，但写操作幂等，最坏情况是重复计算采集而非重复计数（prune 缺陷除外）。

### 8.4 性能实测（2026-11-01，本机）

| 场景 | 实测 | 设计预算 |
|---|---:|---|
| claude 采集 | 214ms | — |
| codex 采集 | 306ms | — |
| opencode + kilo 采集 | 含在全量内 | — |
| Qoder token 全表 | 1,724ms | ≤3s |
| Qoder 活动全量 | 446ms | ≤2s |
| Qoder credits/est/quota | 1,509ms | — |
| `collect_all`（全源，2026-11-01 数据量） | **2.25s** | `live` <0.3s（未达标） |
| cline 采集（1,806 记录 / 20 会话） | 108ms | —（2026-11-11 实测） |
| 83 项单测 | 0.72s | —（2026-11-11 实测） |

> `live` 慢的根因不是解析算法，而是它调用 `collect_all()`：即使只需要 token 记录，也会扫描 Qoder 旧库（1.7s）和全部转录（1.5s），并计算活动与额度。

### 8.5 路径、环境变量与配置

| 项 | 默认值 / 覆盖方式 |
|---|---|
| 数据库 | `~/.local/share/usage-ledger/usage.db`；`USAGE_LEDGER_DB` 直接指定文件 |
| 数据目录 | `USAGE_LEDGER_HOME` |
| 源根目录 | `~/.`；`USAGE_LEDGER_SOURCE_HOME`（测试用） |
| Qoder token 库 | `USAGE_LEDGER_QODER_TOKEN_DB` |
| Qoder 活动库 | `USAGE_LEDGER_QODER_ACTIVITY_DB` |
| Cline 会话目录 | `~/.cline/data/sessions`（随 `USAGE_LEDGER_SOURCE_HOME` 变化） |
| Trae CN hook 配置 | `~/.trae-cn/hooks.json`（`usage hooks install trae-cn --scope global`） |
| Trae CN 事件文件 | `~/.local/share/usage-ledger/trae-cn/*.jsonl`（`USAGE_LEDGER_HOME` 下） |
| launchd 日志 | `~/.local/state/usage-ledger/{sync,full,prune}.log/.err` |
| 安装 | `uv tool install .` → `~/.local/bin/usage` |

无配置文件；所有可调项均为命令参数或环境变量。

---

## 9. 测试体系

83 个测试，全部标准库 `unittest`：

| 文件 | 数量 | 覆盖 |
|---|---:|---|
| `tests/test_collectors.py` | 24 | Claude 中间态/子代理、Codex 累计差分与归档副本去重、Cline metrics 映射/回退/坏文件隔离、签名、OpenCode 新旧 schema、Qoder token 回退/去重、活动指标与增量、credits/est/日志、子源签名独立 |
| `tests/test_store.py` | 7 | upsert 幂等、archived 标记/恢复、prune 汇总与保留、活动按天替换、credits/quota/est、source_state |
| `tests/test_cli.py` | 14 | backfill 幂等、report 与 stateless 一致、stateless 不写库、分组过滤、自动刷新、单源刷新、Cline 回填与自动刷新、doctor 缺口、源不可用时不归档、Qoder 四轨落库、token mtime 跳过、活动单独刷新、doctor 双台账 |
| `tests/test_cli_trae.py` | 6 | Trae CN hook 安装/状态/同步与 est 查询链路 |
| `tests/test_trae_collector.py` | 12 | Trae CN 事件重放、上下文累加、去重、坏行隔离、参数覆盖 |
| `tests/test_trae_hooks.py` | 9 | hook 配置合并/卸载、事件文件、脚本与隐私边界 |
| `tests/test_html.py` | 9 | payload 转义/离线、空页、活动归一、命令写文件、空源、输出目录/区间校验、Qoder Agent 页与 credits/est 聚合 |
| `tests/test_scheduler.py` | 2 | plist 日历/环境、dry-run 不写 |

测试手法：临时 HOME + `USAGE_LEDGER_SOURCE_HOME` / `USAGE_LEDGER_DB`；Claude/Codex 用脱敏 JSONL fixture；OpenCode/Qoder 在测试内建最小 SQLite；`tests/qoder_helpers.py` 提供建库与日志构造器。

**未覆盖**：HTML 内联 JS 的行为（只断言 HTML 字符串）、真实 launchd 加载、真实上游 schema 漂移、`prune → sync → prune` 重复累计路径（本次发现 P0 的原因）。

---

## 10. 设计文档与实现的偏差

| # | 设计文档说法 | 实现现状 | 影响 |
|---|---|---|---|
| 1 | `NullStore` / `SqliteStore` 同一存储接口（DESIGN §4.3） | 无存储抽象；`--stateless` 是 CLI 分支，`open_store()` 为未使用的死代码 | 文档误导；扩展新存储需改 CLI |
| 2 | 计价表 + `price_override` + `pricing-recalc`（DESIGN §9） | `PRICES` 仅 `gpt-5.5` 且全为 `None`；`cost_for_record()` 恒返回 `(None,"unknown")`；`price_override` 无读写 | 成本列永远为空，属已知搁置 |
| 3 | 预算告警、`quota` 命令（DESIGN §8/§10.6） | 未实现 | README 已标为后续 |
| 4 | `archived=1` 行压成日聚合后永久保留（DESIGN §7.3） | `archived=1` 明细永不压缩/删除 | 长期 DB 增长；与设计语义不同但更安全 |
| 5 | WorkBuddy / zstd / L3 daemon | 未实现 | README 已标为 P1/v2 |
| 6 | `paths.mode = full/basename/hash` | 无配置，固定 `basename` | 隐私选项未实现 |
| 7 | 退出码 3（源不可用） | 只有 0 / 2 | 脚本判断能力弱 |
| 8 | `usage_daily` 是长期查询主表 | 仅 `prune` 写入；常规查询同时读 `usage_turn` 与 `usage_daily` | 依赖 prune 是否运行；与 P0 缺陷相关 |
| 9 | DESIGN.md 状态「v0.4 待审核」 | 实际已是 v0.5 并含 credits/est 四轨 | 文档漂移，需在本次审核中定去留 |

---

## 11. 问题清单与风险

### P0 — 数据正确性

**P0-1 `prune` 后重新同步导致 `usage_daily` 重复累计**

- 复现：写入一条 120 天前的明细 → `prune(90)`（daily=100）→ 再次 `upsert_records` 同一记录（模拟下一次 sync）→ `prune(90)`（daily=200）→ `fetch_records` 合计 200。
- 根因：采集器没有“已 prune 水位”；`sync` 每次都从源重放全部历史；`prune` 对 daily 采用累加写入。
- 触发条件：已安装 `prune` 任务 + 源中存在 >90 天历史（本机 Qoder 2026-06~07 数据在 2026-11-01 已超过 90 天）。
- 可选修复方向：
  - A. 增加 per-source `pruned_before` 水位，采集/写入时丢弃早于水位的记录；
  - B. `prune` 改为“重算 daily 区间”而非累加（先删除区间 daily 再重建）；
  - C. 不再物理删除 `usage_turn`，查询只读 turn（牺牲体积与 prune 的意义）；
  - D. `usage_daily` 只用于源已删除的归档（`archived=1`），`archived=0` 的旧明细直接保留。
- 建议：A + B 同时做（水位防重放，区间重建保证可恢复），或选 C 简化。需用户拍板。

### P1 — 行为与性能

**P1-1 `usage live` 未达 `<0.3s`，且扫描了不需要的轨**

- 实测全源 2.25s；`qoder` token 1.7s + credits/est 1.5s。
- `live` 只消费 `Record`，却执行 `collect_all()`，包含活动与 credits/est/quota。
- 修复方向：`live` 默认跳过 `qoder.credits` 与活动；Qoder token 仅在 `--source qoder` 时扫描；或引入 `collect_sources(..., tracks=...)`。

**P1-2 读命令建库行为不一致**

- `report` / `html` 在 DB 不存在时降级读源；`credits` / `est` 直接 `SqliteStore(db_path())` 建空库。
- 影响：`usage credits --stateless` 无副作用，但不带 `--stateless` 会悄悄生成 DB；用户可能误以为已归档。
- 修复方向：统一为“库不存在 → 降级直读 + stderr warning”，或统一为“先建库再同步”。

**P1-3 `report --live` 只合并 token，不合并活动/额度/估算**

- `_load_records` 的 `--live` 分支只对 `records` 做 `merge_records`；活动来自库，额度来自 `_load_credit_payload`（其内部先 auto-refresh）。
- 影响：同一次 `html --live` 中，token 是实时合并值，活动/额度可能是刷新前值；语义不统一。
- 修复方向：`--live` 对四轨统一“源优先”，或文档明确只保证 token 实时。

### P2 — 一致性与可维护性

| ID | 问题 | 说明 |
|---|---|---|
| P2-1 | `archived=1` 明细永不压缩 | 与 DESIGN §7.3 不同；长期体积增长，但保全更强 |
| P2-2 | `price_override` 表、`open_store()`、`max_ts` 为死代码 | 需清理或补齐 |
| P2-3 | `export --format json` 被强制改 csv | `cmd_export` 直接覆盖 `args.format`，参数无效 |
| P2-4 | `top` 不支持 `--range` / `--source` / `--model` | 只有 `--since/--until`；与 report 能力不一致 |
| P2-5 | `activity --source claude` 返回空 | `cmd_activity` 只处理 qoder；其他源静默空结果 |
| P2-6 | `usage_daily.cost_source = MAX(cost_source)` | 文本列取最大值，语义不明确；当前成本全 unknown 暂不暴露 |
| P2-7 | `_refresh_if_stale` 用 `signature > stored` | mtime 回退（文件恢复/时钟回拨）不会触发刷新；其他刷新函数用 `!=`，三套判定不一致 |
| P2-8 | `build/lib/` 落后于 `src/` | 本地构建缓存，已 gitignore；排查问题时易误读 |
| P2-9 | 未提交改动 | `html_report.py`、`test_html.py` 与 4 份文档在工作区未提交；发布前需确认 |

### 已明确接受的风险

- 厂商停止写 token（Qoder 新客户端）→ 用额度 + 估算双轨显式替代，不伪造真值。
- Trae CN 加密库不可读 → 只读官方 hooks 事件做弱估算（`trae-cn.est`），不伪造 token 真值。
- 估算误差 ±30~40% → 全链路 `est` 标注，永不与真值相加。
- 流式生成中的 token 在磁盘上不存在 → `live` 只能看到“上一个已完成 turn”。
- `.zst` 归档未解压 → `doctor` 报数量，不静默。

---

## 12. 审核决策点

请重点确认以下事项；确认后我再改代码或文档。

1. **架构文档的定位**：`docs/ARCHITECTURE.md` 作为“当前实现基线”长期维护；`DESIGN.md` 是否降级为历史方案（加 `Superseded` 标记）？还是把 DESIGN 更新到 v0.5？
2. **P0-1 修复方向**：选 A（prune 水位）、B（区间重算）、C（不物理删）、D（daily 仅存 archived），还是组合？我倾向 **A + B**，代价是新增一个 meta 水位与 prune 重建逻辑。
3. **`live` 性能**：是否按 P1-1 让 `live` 默认跳过 Qoder 四轨（只保留 token 源），把完整四轨留给 `doctor` / `report` / `html`？
4. **读命令建库**：`credits` / `est` 是否改为与 `report` 一致的“库不存在 → 直读 + warning”？
5. **四轨展示边界**：`report --live` 是否要保证活动/额度也实时（P1-3），还是明确“只有 token 实时”？
6. **未实现项**：计价、预算告警、WorkBuddy、zstd、`paths.mode` 是否继续搁置？本次文档是否把它们标为“明确不做 / 待排期”？

---

## 附录 A：一次典型查询的完整链路

```
usage report --since 7d --group-by day,model --format json
  │
  ├─ _effective_range → since=今日-7d, until=None
  ├─ _load_records
  │    ├─ DB 存在 → SqliteStore
  │    ├─ _refresh_if_stale(store, None)
  │    │    ├─ source_signatures() 取 11 个签名
  │    │    ├─ 与 source_state.last_file_mtime 比较
  │    │    └─ 有变化 → _sync_into(public sources, quiet=True)
  │    ├─ fetch_records(since, until, source/model/project filters)
  │    │    ├─ usage_turn 明细
  │    │    └─ usage_daily 聚合（若已 prune）
  │    ├─ （--live 时）collect_all() + merge_records（源覆盖库）
  │    └─ 按 since/until + match(filters) 再过滤
  ├─ aggregate(records, ("day","model"), period="day")
  ├─ _write_rows(..., "json") → stdout
  └─ _footnotes(records, since, until)
       ├─ 成本免责声明 → stderr
       ├─ 无 token 源说明 → stderr
       └─ 缺失日期 → stderr
```

## 附录 B：术语

| 术语 | 含义 |
|---|---|
| 源（source） | 一个 AI 编码工具的本地日志/库；对外 5 个 |
| 轨道（track） | 同一平台下语义不同的数据轴；Qoder 四轨 |
| 记录（Record） | 一次调用/事件归一后的 token 计数与元数据 |
| 去重键（key） | 行级幂等标识，重复采集只覆盖不累加 |
| 签名（signature） | 源文件最新 mtime（微秒），用于判断是否需要刷新 |
| 归档（archived） | 源中已不存在的历史记录，DB 永久保留 |
| `est` | 估算 token，非服务端真值 |
| credits | Qoder 服务端每请求计费单位，非 token、非货币 |
