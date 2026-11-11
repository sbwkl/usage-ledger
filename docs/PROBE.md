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
- Qoder：`~/.qoder/projects/` 的 6,898 条记录 token 字段仍全为 0；但 v0.4 复核发现 IDE 的 `~/Library/Application Support/Qoder/SharedClientCache/cache/db/local.db` 有真实历史 token（19,963 行、2,700,982,026 tokens，覆盖 2026-06-01 ~ 2026-09-16），桌面端 `main.sqlite` 提供持续更新的活动元数据 → 改为 token + 活动双轨采集，详见 [QODER-DESIGN.md](QODER-DESIGN.md)。
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

---

## 6. Trae CN Phase 0 实测（2026-10-30）

> 授权范围：一次性读取 Keychain 密钥、安装 `sqlcipher`、复制加密库做只读解密。
> 约束：密钥不打印 / 不落盘；只读本地数据；不调用私有 API；不读 JWT；不读会话正文。
> **结论：Phase 0 不通过 → 按 [TRAE-CN-DESIGN.md](TRAE-CN-DESIGN.md) §4.3 走方案 D（维持不采集），未写任何采集代码。**

### 6.1 库形态

| 项 | 实测 |
|---|---|
| 路径 | `/Users/wayne/Library/Application Support/Trae CN/ModularData/ai-agent/database.db` |
| 大小 | 11,153,408 B = 4096 × 2723（与 SQLCipher 默认 `page_size=4096` 一致；也整除 1024，仅凭大小不能定页大小） |
| 头部 | 前 16 B 全随机；page 1 不含 `SQLite format 3`；256 种字节值 → 非明文 SQLite |
| 持有进程 | PID 61272（`Trae CN Helper --utility-sub-type=basil.mojom.NativeExtensionService`，加载 `…/modules/ai-agent/libharness.dylib`），持有 DB + WAL 的多个 pooled FD |
| WAL | `database.db-wal` 4,120,032 B，随应用活动增长 |

### 6.2 密钥探测（全部失败）

- 工具：`sqlcipher` CLI 3.54.1（SQLCipher 4.20.0）。成功判定 = `SELECT count(*) FROM sqlite_master` 无错误。
- 本机 Keychain 仅 3 项与 Trae 相关（元数据）：
  - `Trae CN Safe Storage` / `Trae CN Key`，24 B base64（Chromium OSCrypt 形态）
  - `Trae CN Safe Storage` / `Trae CN`，24 B base64
  - `Trae Safe Storage` / `Trae`（旧版 Trae；读取未返回，触发系统授权流程后终止，本次未取值）
- 对前两项的尝试（secret 只经 stdin 传给 `sqlcipher`，不打印、不进 argv、不落盘）：
  - 原样字符串作为 passphrase：SQLCipher 4 默认参数 / `PRAGMA cipher_compatibility = 3`
  - base64 解码后的 16 / 24 / 32 B 作为 raw key（`x'…'`）
  - PBKDF2-HMAC-SHA256 / SHA512（二进制内硬编码 salt、100000 轮、32 B）→ raw key
  - SHA-256(secret) → raw key
  - 结果：**全部返回 `file is not a database`**
- 其他明文侧负结果：进程 env（无密钥变量）、`~/.trae-cn`、`User/globalStorage/storage.json`、`state.vscdb`、`User/settings.json`、`product.json` 的 `bootConfig`（无 persistence / db / encrypt / key 字段）、`aha/TinyStorage`（仅 device_id / access_policy）、`aha/Remote_State`（feature flags）、logs。
- `Local Storage/config.db`（动态配置缓存）为固定派生密钥的 AES-256-CBC（前 16 B 为 IV），已只读解密核对：顶层仅 `iCubeApp` / `mf` / `is2b`，**无 `db_persistence`、无数据库密钥**；`iCubeApp` 下与库相关的只有 `aiAgentDbStoragePath` / `dbWritePoolMaxConnections` / `enableDbRwSplit` 等开关。

### 6.3 密钥来源定位（关键）

- harness 的 DB 层在配置结构 `+0x658` 处读取 `db_persistence` 节；缺失时报 `is required for DB persistence`（libharness `0x9048`，调用点 `0x23570`）。
- `db_persistence` 只在 `libharness.dylib` 中出现；全部应用 JS、`product.json`、用户数据目录、日志与缓存中**均无该字符串**。
- harness 的 boot config 通过 AHA IPC 实时获取：主进程日志有 `event:BootService.onBootConfigChanged` 广播，harness 侧有 `[AhaIPCSource] start_boot_config_stream` / `onDidBootConfigChanged deserialize`；`BOOT_CONFIG_FILE` 未设置，本机也不存在 boot config 文件。
- 结论：DB 密钥来自**运行时下发的 `db_persistence` 配置**（服务端下发或原生层注入），本地没有明文落盘；`PRAGMA key` 由 DB 层从该配置格式化得到（libharness `0x65b66bc`），harness 自带的 PBKDF2 辅助函数不被该路径调用。
- 本地获取只剩「IPC 抓包 / 进程内存扫描 / 注入」三条路，均被 [TRAE-CN-DESIGN.md](TRAE-CN-DESIGN.md) §1.3 明确排除，也超出本次授权。

### 6.4 只读性与清理

- 所有解密尝试只打开 `/tmp/trae-phase0/database.db` 副本；源库 size 保持 11,153,408 B，mtime 未变（15:47:51）；源目录无新增 `-journal`。`-wal` mtime 由运行中的 Trae 更新（18:48），与探针无关。
- 临时目录 `/tmp/trae-phase0`（约 1.7 GB：库副本、反汇编 / strings dump、测试脚本）已删除。

### 6.5 处置（方案 D，待评审确认）

- 不新增 `trae-cn` 采集器，不写实现代码。
- `usage doctor` 的 Trae CN 说明改为：「加密库存在，但密钥由 Trae 运行时下发，本地不可读 → 不采集」。
- 若后续 Trae 提供导出 / 公开接口，或用户明确授权 IPC / 内存级取证，再重新评估。

### 6.6 竞品方案复测（2026-10-31，内存扫描 → 仍不通过）

> 授权语境：用户要求「参考竞品的实现方案再试一次」，本次复测按一次性取证实验执行。
> 约束不变：密钥不打印 / 不落盘；只读本地数据；不修改 Trae 安装与配置；不读 JWT / 会话正文。
> **结论：竞品的内存扫描方案在 macOS 27 + 当前 Trae CN 构建上不可用；维持方案 D。**

竞品做法（Oh-My-Trae / trae-db-decrypt，Windows）：枚举 `Trae CN.exe` 进程内存，用正则找 64/96 位 hex
候选（96 位 = key + salt），再用 SQLCipher 4 的 HMAC-SHA512 校验 page 1，命中后交给 sqlcipher 解密。
本次把该流程原样移植到 macOS 并做了端到端验证：

1. **算法与移植可用（自测通过）**
   - 纯 Mach API 扫描器（`task_for_pid` + `mach_vm_region` + `mach_vm_read_overwrite`）与 lldb Python
     扫描器两版实现，均对自建 SQLCipher 测试库做了全链路自测：内存中植入 `x'<key>'` → 正则命中 →
     HMAC 校验通过 → `sqlcipher` 打开成功。两版自测均 PASS（含一次 74 MB / 22 区域扫描）。
   - 说明失败点不在算法、正则或 HMAC 参数（salt=page1[:16]、mac_salt=salt^0x3a、
     PBKDF2-HMAC-SHA512 2 轮、HMAC 覆盖 page1[16:4032]+pgno），而在目标进程的读取权限。

2. **macOS 27 的 taskport 限制**
   - `task_for_pid` 对任意 Trae 进程返回 `kr=5 (KERN_FAILURE)`，**root 也一样**。根因：授权权
     `system.privilege.taskport` 为 `allow-root=false, authenticate-user=true, class=user, group=_developer`，
     Developer mode 默认关闭。
   - 用户已执行 `sudo /usr/sbin/DevToolsSecurity -enable`（现为 enabled）。此后验证：
     Homebrew Python 等**非 hardened** 同用户进程可 attach；Trae 进程仍全部拒绝。

3. **根因：Trae CN 全进程 hardened runtime，且无 get-task-allow**
   - 主进程 PID 60950、utility PID 61272（`libharness.dylib` 持有者）及全部 Helper 均为
     `codesign flags=0x10000(runtime)`，entitlements 中**没有** `com.apple.security.get-task-allow`。
   - 受控实验（`/tmp/hardtest`，同一二进制三种签名）：
     | 签名 | attach 结果 |
     |---|---|
     | ad-hoc（无 runtime） | 成功 |
     | `--options runtime` | 拒绝 |
     | runtime + get-task-allow | 成功 |
   - `lldb process launch` 启动 hardened 二进制同样被拒；Apple `debugserver`（具备
     `com.apple.private.cs.debugger`）也拿不到 hardened Trae 的 task port。
   - 结论：这不是 Developer mode / 权限问题，而是 hardened runtime 策略；不重新签名（注入
     get-task-allow）就无法读取 Trae 内存。重签名会破坏现有签名/公证与自动更新，且属于修改应用本体，
     不在只读实验范围内，**不采纳**。

4. **备份旁路同样不可用**
   - 进程 env：`ICUBE_ENABLE_DATABASE_BACKUP=0`、`ICUBE_DATABASE_BACKUP_INTERVAL=300000`。
   - main.js 取值来源：`productService.iCubeApp?.dbBackup?.enable ?? false`（interval 默认 5 分钟），
     `product.json` 的 `iCubeApp` 中**无 `dbBackup` 键** → 产品配置默认关闭，非用户设置项。
   - `/Users/wayne/Library/Application Support/Trae CN/Backups` 为空；日志无 `[Backup]` 记录。
   - harness 备份实现含 `sqlite3_backup_init` 与 `SELECT sqlcipher_export('encrypted');`，即使开启，
     产出仍为 SQLCipher 加密库；`exportUserBuilderData` 也只是复制加密的 `database.db`。

5. **清理**：本复测脚本与报告位于 `/tmp/trae-keyprobe`、`/tmp/competitor`，均未保存密钥或明文库；
   全过程只读，源库大小/mtime 未变。临时自测库与报告可由用户随时删除。

**处置：维持 §6.5 的方案 D。** 仅当以下任一条件成立时再重新评估：
(a) Trae CN 后续版本提供明文导出/公开用量接口；(b) 用户明确授权修改应用签名并接受更新/公证副作用
（不推荐）；(c) Trae 改为非 hardened 构建。

### 6.7 额度 / credits 数据源复测（2026-11-01，仍不可得）

> 问题：能否像 Qoder 的 `usage credits` 那样统计 Trae CN 的额度用量？
> **结论：不能。额度真值只在服务端响应与加密库中；本地明文只有套餐/权益/活动配置，没有余额或消耗数值。**

逐项实测（全部只读）：

| 来源 | 实际内容 | 额度数值 |
|---|---|---|
| `User/globalStorage/state.vscdb`（122 key） | 仅 `cn.fast_request.lock_map`、`credits.*` 横幅弹窗状态、模型/工作台配置 | 无 |
| `User/globalStorage/storage.json`（31 key） | `iCubeServerData://icube.cloudide`（5,056 B）：`entitlementInfo`（Free、`fast_request_per=0`）、`commercialActivityInfo`（签到/新人/邀请奖励配置）、`originPayStatusData`（`is_credits_billing=true` 等套餐标志） | 无 used/remaining |
| `logs/*/main.log` | `/pay/ide_user_ent_usage`、`/ug/checkin_credits/status|claim` 的 `ttnet fetch request/response`，仅 URL + HTTP 200，无响应体 | 无 |
| `logs/*/window1/renderer.log` | `[CheckinCredits] invalidation reconciled {"statusRefreshResult":"fulfilled","creditsRefreshResult":"rejected"}`；`[CommercialActivityService]` 活动配置 | 无余额 |
| `Local Storage/leveldb` | 仅 `trae-cn-credits-billing-status:v1:<uid>` → `{"is_credits_billing":true,"should_force_switch":true}` | 无 |
| `Cache/Cache_Data`、`CachedData` | 命中 `ide_user_ent_usage` / `checkin_credits` 的文件均为前端 JS bundle（API client 代码），无响应 JSON | 无 |
| `Partitions/trae-webview` | 用量面板所在 webview；Local Storage 114 B，Cache 无 usage 字段 | 无 |
| `User/workspaceStorage/*/state.vscdb` | 仅聊天会话索引/输入历史，无 usage/token/credit 键 | 无 |

补充事实：

- 用量前端调用的接口（来自缓存 JS bundle，仅作事实记录，未调用）：
  `POST /trae/api/v1/pay/ide_user_ent_usage`（`require_usage` / `full_data`）、
  `POST /trae/api/v1/pay/query_user_usage_group_by_session`（按会话的用量历史）。
  二者都是服务端 POST，响应不落盘；调用需要登录态，属于设计 §1.3 的非目标。
- 加密库内是否另存 credits 无法验证（无密钥）；即便有，也与 token 一样不可读，不改变结论。
- 本地真正可得的只有「权益状态」：套餐身份（Free/Pro）、`is_credits_billing`、`fast_request_per`、
  签到/活动配置与已领取日期、API 刷新时间。这些不是用量，不足以构成额度轨。

**处置**：维持不做 Trae CN 的额度/credits 轴。仅当客户端开始把用量摘要写入日志、提供官方导出，
或开放公开接口时再评估。

### 6.8 Hooks 数据源探针（2026-11-01，可挂但无用量字段）

> 问题：Trae CN 是否有类 Claude Code 的 hook 机制，允许用户自己统计 token / 额度用量？
> **结论：有 Hooks，但 hook 输入里没有 token / 额度 / 对话记录路径，无法用于统计用量；最多只能记活动量。**

1. **配置位置**
   - 项目级：`<workspace>/.trae/hooks.json`（workbench 的 `contextAssetService` 中 `assetType:"hook"`、
     `projectRelPath:".trae/hooks.json"`、`globalRelPath:"hooks.json"`）。
   - 全局级：`<dataFolderName>/hooks.json`；`product.json` 的 `dataFolderName = .trae-cn`
     → `/Users/wayne/.trae-cn/hooks.json`（当前不存在）。
   - Settings > Hooks 可配置；UI 文案提示「支持配置项目级 Hooks」，并建议只在受信任工作区启用。
   - 运行时环境变量：`TRAE_PROJECT_DIR`、`TRAE_ENV_FILE`、`CLAUDE_ENV_FILE`、`CLAUDE_PROJECT_DIR`；
     本机 `/Users/wayne/Library/Application Support/Trae CN/ModularData/ai-agent/hooks_env` 为空目录。

2. **事件**（官方文档六个；本地二进制字符串另有 PreCompact / PostCompact）
   `SessionStart`、`UserPromptSubmit`、`PreToolUse`、`PostToolUse`、`Stop`、`Notification`，
   二进制中额外出现 `PreCompact`、`PostCompact`（文档未列出，未实测）。
   配置结构：`RawHooksConfig{version, hooks}` → `RawEventHookGroup{matcher, loop_limit}` →
   `RawHookItem{type: command|url, timeout, headers, allowedEnvVars, statusMessage}`。

3. **hook stdin 字段**（libharness 的 `harness/user-hooks/src/executor.rs` 序列化路径）
   - 公共：`session_id`、`cwd`、`hook_event_name`、`workspace_roots`、`agent_type`、`email`、`model`
   - 事件相关：`tool_name`、`tool_use_id`、`llm_tool_name`、`tool_input`、`tool_response`、`prompt`、
     `loop_count`、`loop_context`、`text_content`、`last_assistant_message`、`notification_type`、
     `title`、`trigger`、`custom_instructions`、`compact_summary`、`compact_summary_meta`、
     `stop_hook_active`、`selected_options`
   - **没有**：`token_usage`、`prompt_tokens`、`completion_tokens`、`credits`、`usage`、`quota`、
     `transcript_path`。全量搜索 libharness 的 hook 相关字符串均无这些字段。
   - hook 输出支持 `continue` / `stopReason` / `decision` / `reason` / `hookSpecificOutput` /
     `goal` / `ralph_loop`，都是流程控制，不回传用量。

4. **可做与不可做**
   - 不可做：精确 token / 额度统计。用量仍只在 SQLCipher 库与服务端响应中，hook 也拿不到库密钥。
   - 可做（若用户批准写入 hook 配置）：按 `UserPromptSubmit` / `Stop` / `PreToolUse` 计数会话数、
     轮次数、工具调用数，作为**活动量**轴；这不属于现有任何源的口径。
   - 不建议：用 `prompt` / `last_assistant_message` 估算 token——违反设计 §1.3「不估算 token」，
     且 hook 会拿到正文，与「不落正文」原则冲突。

**处置（2026-11-01 更新）**：按用户决定，改走 [TRAE-CN-DESIGN.md](TRAE-CN-DESIGN.md) §12 的 Plan H——
用 hooks 可见内容做 `trae-cn.est` **弱估算**（只记字符数/事件元数据，不落正文），
不以 hooks 采 token 真值或额度。安装 hook 需用户批准（全局 `/Users/wayne/.trae-cn/hooks.json`
或项目级 `<workspace>/.trae/hooks.json`）。仅当未来 Trae 提供用量字段/导出时，才考虑升级为真值轨。
