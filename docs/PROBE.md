# PROBE.md —— 实测探针报告（DESIGN v0.4 的落地校验）

> 探针脚本：[`scripts/probe.py`](../scripts/probe.py) ｜ 生成日期：2026-10-22 ｜ 数据来源：本机实测
> 用途：在写正式框架之前，用一次全量只读扫描回答 DESIGN 里的待决问题，并**校正 9 处与实际格式不符的规格**。

---

## 0. 结论摘要

| 项 | 结果 |
|---|---|
| 全量扫描耗时 | **0.72s**（4 源、16,799 条记录、约 190MB 日志）→ DESIGN 的 "~1.5s" 偏保守，实际远够用 |
| 记录总量 | 16,799 条（claude 3,887 / codex 4,388 / opencode 7,848 / kilo 676） |
| token 总量 | **2,138,112,250**，其中 **cache_read 占 95.8%**（2,048,651,519） |
| 计价可用性 | 21 个 source×model 组合里 **18 个是 free/别名模型** → LiteLLM 快照基本查不到 |
| 规格偏差 | **9 处**（见 §2），其中 3 处会导致数量级错误 |
| 新出现的风险 | Codex **同一 session 跨 rollout 文件续写**（2 例），与 DESIGN 假设的"归档即副本"不同 |

---

## 1. 实测快照

### 1.1 各源概况

| 源 | 文件数 | 命中行 | 去重后记录 | 丢弃重复 | 活跃天数 | 日期范围 | 解析错误 |
|---|---|---|---|---|---|---|---|
| claude | 103 | 5,559 | 3,887 | 1,672 | 13 | 2026-06-05 ~ 2026-07-18 | 0 |
| codex | 68 | 4,388 | 4,388 | 0 | 26 | 2026-06-27 ~ 2026-10-22 | 0 |
| opencode | 1 | 7,848 | 7,848 | 0 | 29 | 2026-08-06 ~ 2026-10-21 | 0 |
| kilo | 1 | 676 | 676 | 0 | 3 | 2026-10-20 ~ 2026-10-22 | 0 |

补充事实（本次一并复核，仍成立）：

- Claude Code 的 `subagents/` transcript：**89 个文件**（分布在 2 个 subagents 目录），占 Claude 记录的一半量级 —— 必须递归扫。
- Codex：50 个 `sessions/` + 18 个 `archived_sessions/`；`.jsonl.zst` **0 个**（v1 不必实现 zstd）。
- OpenCode：`storage/message/` **不存在**（只有 `migration/`、`session_diff/`）→ 双存储去重当前不成立。
- Qoder：6,898 条记录，4 个 token 字段**全部为 0**（复核通过）→ 仍不采集。
- Cursor 生态清理作业仍在：`~/.cursor/projects/.agent-data-cleanup-2026-10-20`、`-2026-10-21`。

### 1.2 模型清单（source × model）

| 源 | 模型 | 记录数 | input | output | cache_read | reasoning | 合计 |
|---|---|---|---|---|---|---|---|
| opencode | space-bunny-free | 4,533 | 18,957,355 | 1,547,468 | 844,995,017 | 938,246 | 866,438,086 |
| claude | kimi-for-coding | 3,887 | 4,202,208 | 986,780 | 360,345,570 | 0 | 365,534,558 |
| codex | stealth/space-bunny-alpha | 1,657 | 5,588,197 | 588,206 | 187,815,601 | 0 | 193,992,004 |
| kilo | minimax/minimax-m3.1-flash:free | 678 | 5,677,712 | 192,907 | 137,765,690 | 941,674 | 144,577,983 |
| opencode | deepseek-v4-flash-free | 2,051 | 9,694,201 | 1,095,864 | 130,524,032 | 269,988 | 141,584,085 |
| codex | nvidia/nemotron-3-ultra-550b-a55b:free | 788 | 11,943,497 | 122,350 | 118,190,880 | 52,167 | 130,308,894 |
| codex | minimax/minimax-m3.1-flash:free | 625 | 10,292,345 | 158,667 | 87,974,661 | 367,572 | 98,793,245 |
| opencode | deepseek-v4.1-flash-free | 1,162 | 7,388,433 | 425,235 | 81,917,440 | 620,163 | 90,351,271 |
| codex | deepseek-v4-flash | 643 | 1,656,315 | 181,677 | 48,251,136 | 268,986 | 50,358,114 |
| codex | gpt-5.6-terra | 300 | 1,529,922 | 72,210 | 23,015,680 | 22,829 | 24,640,641 |
| codex | gpt-5.6-sol | 276 | 1,194,639 | 85,007 | 20,243,712 | 41,616 | 21,564,974 |
| opencode | step-5-preview-free | 8 | 418,636 | 6,562 | 2,900,800 | 547 | 3,326,545 |
| opencode | nemotron-3-ultra-free | 26 | 391,181 | 3,198 | 1,455,840 | 781 | 1,851,000 |
| opencode | nemotron-3.5-lightning-free | 47 | 385,951 | 11,363 | 889,984 | 14,100 | 1,301,398 |
| codex | ox-alpha | 40 | 127,393 | 8,898 | 1,157,888 | 0 | 1,294,179 |
| codex | openrouter/free | 31 | 625,088 | 2,640 | 252,224 | 7,670 | 887,622 |
| opencode | big-pickle | 21 | 129,350 | 9,914 | 649,042 | 1,829 | 790,135 |
| codex | gpt-5.5 | 8 | 120,864 | 2,052 | 212,992 | 29 | 335,937 |
| codex | stealth/ox-alpha | 16 | 41,969 | 4,630 | 277,056 | 0 | 323,655 |
| codex | minimax/minimax-m3:free | 4 | 42,791 | 236 | 43,384 | 175 | 86,586 |

**这张表就是 Q2 的答案**：除 `gpt-5.6-terra` / `gpt-5.6-sol` / `gpt-5.5` / `deepseek-v4-flash` 外，
其余 16 个模型 ID 都是 **free 档或平台别名**（`space-bunny-free`、`big-pickle`、`stealth/ox-alpha`、`kimi-for-coding`…），
LiteLLM 快照里**一个都查不到**。→ 若不做别名映射，`cost_equiv_usd` 的覆盖率不足 20%，且总量会被
"把 free 记成 0"掩盖成"没花钱"。

### 1.3 合计

| 源 | 记录数 | input | output | cache_read | cache_write | reasoning | 合计 |
|---|---|---|---|---|---|---|---|
| claude | 3,887 | 4,202,208 | 986,780 | 360,345,570 | 0 | 0 | 365,534,558 |
| codex | 4,388 | 33,163,020 | 1,226,573 | 487,435,214 | 0 | 761,044 | 522,585,851 |
| kilo | 676 | 5,677,013 | 192,530 | 137,538,580 | 0 | 941,198 | 144,349,321 |
| opencode | 7,848 | 37,365,107 | 3,099,604 | 1,063,332,155 | 0 | 1,845,654 | 1,105,642,520 |
| **合计** | **16,799** | **80,407,348** | **5,505,487** | **2,048,651,519** | **0** | **3,547,896** | **2,138,112,250** |

- **cache_read 占 95.8%** → 报表若不把 cache 单独列出来，"总 token"会被 cache 淹没，失去意义。
- cache_write 全量为 **0**（本机四个源都没产生缓存写入计数）→ §9.2 的 cache_write 计价规则本机用不到，但字段仍要留。
- 项目维度：`tongxing-air` 一个项目占了 1.30B（61%），`feature-article-crawler` 249M。

### 1.4 交叉校验（自洽性）

| 校验 | 结果 |
|---|---|
| Codex 累计增量法 vs 独立统计的 `total_tokens` 合计 | 522,585,851 vs 522,585,849（差 2，浮点取整）✅ |
| Codex `last_token_usage` vs 累计增量 | 4,328 个事件 100% 吻合 ✅ |
| Claude 同键重复行的 usage 是否一致 | 1,339 组多行，usage **完全一致** ✅ |
| 各源解析错误 | 0 ✅ |

---

## 2. 与 DESIGN v0.4 的 9 处偏差（必须修订规格）

> 标 ⛔ 的会造成数量级错误；标 ⚠️ 的会造成漏计/口径错。

| # | DESIGN 的说法 | 实测事实 | 影响 |
|---|---|---|---|
| 1 ⛔ | §5.2「模型名…以事件内的 model 字段为准」 | `event_msg/token_count` 里**没有模型名**；模型在同文件 `turn_context.payload.model`（老文件在 `session_meta.base_instructions.provenance.model`）。实测共 12 个 Codex 模型 | 不改则 model 全为 unknown，无法按模型出数 |
| 2 ⛔ | §5.2 未提及 | 存在**第二条 token 流** `token_usage_record`（新格式，每个 API 响应一条，带 `response_id`/`turn_id`/`usage`/`turn_token_usage`）。**它与 `token_count` 是同一条流的两种记录，不能相加**；42 个老文件根本没有它 | 相加 → 约 1.6 倍虚增 |
| 3 ⛔ | §5.2 未提及 | 同一 session 被**续写成第二个 rollout 文件**，新文件的累计值**继承**旧文件基线（实测 91,857,868 恰好等于前一个文件的末值） | 首事件按"累计值"取增量会凭空多算 91.9M |
| 4 ⛔ | §5.2「`last_token_usage` 是增量」 | `last_token_usage` 确实等于本次增量（4,328/4,328），但**同一事件会被重复写入多次**（累计值不变）→ 直接求和 `last` 会多算约 3M（0.6%）。必须取**累计值的增量** | 量级小但会破坏 ≤2% 交叉校验 |
| 5 ⛔ | §5.2「`input ← input_tokens - cached_input_tokens`」方向正确，但未提 reasoning | Codex 的 `input_tokens` **已包含** `cached_input_tokens`；且 `reasoning_output_tokens` 是 `output_tokens` 的**子集**（`total = input + output`，reasoning ⊂ output）。不拆开则 cache 被重复计、reasoning 被重复计 | 不拆 → cache_read 虚高 1.2 倍 |
| 6 ⚠️ | §5.2 字段映射 | 存在 `cache_write_input_tokens` 字段（本机恒为 0） | 字段表漏项 |
| 7 ⛔ | §5.1/RESEARCH「无任何中间态记录，usage 在 turn 结束那一刻落盘」 | **Claude Code 会写入"进行中"的 assistant 行**：同一 `message.id` 反复出现，`output_tokens=0`、`cache_read=0`、`cache_creation=null`，最后才补一条完整行（含 `usage.iterations` 与 `cache_creation` 明细）。实测 **550 条**中间态行 | 只取首行 → input 虚高 2.7 倍（11.5M vs 4.2M）、cache_read 少算 7.3M |
| 8 ⚠️ | §5.1「去重键优先用 `requestId`」 | 本机 Claude Code 日志**根本没有 `requestId` 字段**，只能退回 `message.id`（5,559 条最终行 → 3,887 个唯一 id，1,672 条重复，usage 完全一致） | 去重键规格需按实际格式重写 |
| 9 ⚠️ | §5.2 坑 5「`archived_sessions` 是 `sessions/` 里同一次会话的副本」 | **本机 0 个同名文件** → 归档不是副本，是被移走的独立 rollout。真正的新风险是"同一 session 跨文件续写"（见 #3），R13 的成因要重写 | 验收项"副本只算一次"当前无法验证 |

### 2.1 修订后的各源采集规则（探针已实现并验证）

**Claude Code**
```
遍历 ~/.claude/projects/**/*.jsonl（含 subagents/）
仅保留 usage 中含 "iterations" 键的行（= 完整行，排除 550 条中间态行）
去重键 = message.id（重复行 usage 完全一致，保留任一即可）
字段：input←input_tokens, output←output_tokens,
      cache_read←cache_read_input_tokens, cache_write←cache_creation_input_tokens
```

**Codex**
```
遍历 ~/.codex/sessions/**/*.jsonl + ~/.codex/archived_sessions/**/*.jsonl
按文件分组，事件按 timestamp 排序
模型 = 该事件之前最近一次 turn_context.payload.model（回退 session_meta 的 provenance.model）
增量：
  首事件  → 用 last_token_usage 各字段（规避"累计值继承基线"）
  其余事件 → max(cum[i] - cum[i-1], 0)，逐字段
拆分（保证五项互不重叠）：
  input     = max(Δinput_tokens - Δcached_input_tokens, 0)
  cache_read= Δcached_input_tokens
  output    = max(Δoutput_tokens - Δreasoning_output_tokens, 0)
  reasoning = Δreasoning_output_tokens
  cache_write = Δcache_write_input_tokens
去重键 = rollout 文件名 stem + 事件累计 total_tokens（文件内单调，唯一）
```

**OpenCode / Kilo**（同一 adapter，原规格正确）
```
读 opencode.db / kilo.db（mode=ro），message 表
tokens.input / output / reasoning / cache.read / cache.write 五项互不重叠，可直接求和
去重键 = message.id
```

---

## 3. 待决问题的实测答案

| # | 问题 | 实测依据 | 建议 |
|---|---|---|---|
| **Q2** | 等价成本是否作主指标 | 21 个模型组合里 18 个是 free/别名，LiteLLM 查不到；真实可计价的只有 `gpt-5.6-terra`(24.6M)、`gpt-5.6-sol`(21.6M)、`gpt-5.5`、`deepseek-v4-flash`(50.4M)，合计不足总 token 的 6% | **不作为主指标**。改为：token 数为主，成本作为"可计价部分"的附加列 + `cost_source=unknown` 显式标注。要么补一张 `free 别名 → 真实模型` 映射表（工作量小、价值高），要么承认成本列长期为空 |
| **Q8** | 预算阈值与金额基数 | 同上 | 预算先按 **token 阈值**（如日均 cache+input 的 3σ 尖峰告警）做，等价成本告警放到别名表齐备之后 |
| **Q11** | 缺失日期是否标注 | claude 活跃 13 天 / codex 26 / opencode 29 / kilo 3，缺日极常见 | **必须标 `—(no data)`**，否则"这天没干活"和"这天没采到"无法区分 |
| **Q13** | 要不要数据库 | Codex 已有 18 个归档 rollout（归档是真实发生的）；Cursor 清理作业每天跑；全量扫描仅 0.72s | **要（SqliteStore）**，但理由不是"查询快"（0.72s 根本不需要索引），而是**抗删除**：日志确实在被上游清理。DB 的第一价值是"归档"，第二价值才是查询 |
| Q1/Q4/Q6/Q9/Q10/Q12 | 其余 | 无冲突 | 直接采纳 DESIGN 的建议值（basename / 90 天 / Python / 每小时增量+每日全量 / 立即 backfill / L1 live） |
| Q3/Q5/Q7 | 其余 | 无冲突 | 不碰额度轴 / 不依赖 ccusage / v1 不做多设备 |

---

## 4. v1 范围建议（相对 DESIGN 的里程碑表做减法）

DESIGN 的 6.5 人日里，有相当部分花在"锦上添花"上。按探针实测，建议 v1 只保留：

**保留**
- 4 个 collector（claude / codex / opencode+kilo 合并 adapter）+ 单元测试 fixture
- SQLite schema（`usage_turn` / `usage_daily` / `source_state`）+ `sync` + `backfill`
- `report`（按 天 × 源 × 模型，cache 单列）+ `top` + `--format json/csv`
- `doctor`（含"哪些源无 token 数据"的显式说明）
- launchd 每小时增量 + 每日全量重扫
- `archived` 标记（这是本工具相对 ccusage/tokscale 的唯一实质差异，**不能砍**）

**砍掉 / 推后**
- `NullStore` 双实现（先只做 SqliteStore，`--stateless` 作为 v1.1）
- zstd 解压（本机 0 个 .zst）
- Cline / WorkBuddy（未安装）
- 额度轴（Q3）
- L3 daemon（FSEvents）
- `pricing-recalc`、`quota`、`budget` 告警（等别名表齐备）
- 模型别名表只做**你实际在用的 21 个**（而不是 LiteLLM 全量快照）—— 一张 21 行的表，本周五分钟

**顺序调整（关键）**
```
探针（已完成，0.72s）
   ↓
M1' 4 个 collector + 单测          ← 只依赖探针里的规则，不依赖框架
   ↓
M2' SQLite 落库 + sync + backfill   ← 立刻把 4 个月的日志固化进自己的库（防删）
   ↓
M3' report + doctor + launchd        ← 装上定时任务，丢失窗口压到 1h
   ↓
M4' 计价/别名表 + 告警（可选）
```
理由：探针已证明"**现在还能读到全部历史**"，但 Cursor 清理作业每天在跑、
Codex 归档在持续发生。**先固化数据，再完善报表**，比 DESIGN 原顺序（报表在归档之前）更安全。

---

## 5. 复现方式

```bash
python3 scripts/probe.py                    # 全量快照
python3 scripts/probe.py --days 7           # 只看最近 7 天
python3 scripts/probe.py --source codex     # 只扫某个源
python3 scripts/probe.py --json /tmp/p.json # 机器可读输出
```
脚本严格只读（SQLite 用 `mode=ro` URI），不写任何源目录，标准库 only。
