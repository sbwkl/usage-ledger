# Qoder 额度（credits）+ 估算 token 设计

> 日期：2026-10-30 ｜ 关联文档：[QODER-DESIGN.md](./QODER-DESIGN.md)（双轨台账）、[RESEARCH.md](./RESEARCH.md)（竞品调研）
> 状态：已实现（v0.5.0，2026-10-31）

## 0. 决策背景

- Qoder 新版客户端不再写 token 真值（旧 IDE 库止于 2026-09-16；消息 payload 无 usage 字段；缓冲库 usage 掩码全零；`chat_session_context_usage` 的 `tokenCountsAvailable=false`）。
- 用户决策：**同时统计"额度"与"token"**——额度走服务端真值（准确），token 参照 Token Monitor 的做法从转录文本估算（明确标注 est，不与真值相加）。
- 竞品印证：TokenTracker 直读同一个旧 IDE 库（现已同样断供）；Token Monitor 从转录估算；TokenTelemetry 跟踪 credits。
- **2026-10-31 实测修正（本机数据）**：转录 assistant `message.usage` 的 token 字段虽为 0，但保留了 `credits` / `original_credits` / `billable` / `context_usage_ratio` / `request_id`。其中 `billable=true` 的 credits 与 main.log 快照 `used` 增量逐段吻合（+18.16 vs +20、+31.62 vs +32、+8.30 vs +9、+12.17 vs +13；非 billable 期间快照零增量），确认为**配额消耗真值**。因此额度轨改为「转录每请求 credits 为主（细粒度、可归因）+ 日志快照余额为辅」，原"快照差分推导日消耗"降级为交叉校验。

## 1. 口径总览（四轨，互不可加）

| 轨道 | source | 数据性质 | 来源 | 时间范围 |
|---|---|---|---|---|
| token 真值 | `qoder` | 服务端真值（历史） | 旧 IDE `local.db`（只读） | 2026-06-01 ~ 2026-09-16 |
| 活动 | `qoder.activity` | 非token 指标 | 桌面端 `main.sqlite` | 至今，实时 |
| **额度** | `qoder.credits` | **服务端真值**（每请求计费） | `~/.qoder/projects/**/*.jsonl` 的 `usage.credits`（billable）；`logs/*/main*.log` 快照仅作余额与交叉校验 | 2026-09-16 起，持续 |
| **估算 token** | `qoder.est` | **估算值** | 同一转录：`context_usage_ratio` + 文本字符数 | 2026-09-16 起，持续 |

- 四轨分表分示，任何两轨都不相加；估算 token 永远带 `est` 标注。
- `usage report`（token）行为不变；新增 `usage credits` 命令与 HTML 额度卡片；估算 token 并入 HTML 新区块。

## 2. 数据源实测（2026-10-30 探测）

### 2.1 额度：main.log 的用量响应摘要（真值）

客户端调用 `GET https://openapi.qoder.sh/sash/api/v2/me/usage` 后在 main.log 写 INFO 摘要行：

```
[2026-10-30T05:43:50.369Z] [INFO] [main] [Auth] [AccountUsage] 用量响应摘要
{"operation":"account.getQuotaUsage","requestId":"<uuid>","method":"GET",
 "path":"/sash/api/v2/me/usage","host":"openapi.qoder.sh","status":200,
 "qoderUsage":{"usageType":"credits","totalUsagePercentage":0.1,
   "isQuotaExceeded":false,"userQuota":{"total":0,"used":0,"remaining":0,...,"unit":"credits"},
   "addOnQuota":{"total":2400,"used":243,"remaining":2157,"percentage":0.1,"unit":"credits"},
   "expiresAt":...},"enterpriseUsage":"missing"}
```

实测行为：

| 项 | 实测 |
|---|---|
| 触发频率 | 不定期（10-30 当天 9 次，间隔 20 分钟~3 小时；登录/窗口操作/后台刷新触发） |
| 快照位置 | `~/Library/Application Support/com.qoder.app.stable/logs/<启动时间戳>/main*.log` |
| 留存窗口 | 按启动分目录，实测仅保留最近 3 个（约 1 周），**旧目录会被清理** |
| 实测留存 | 2026-10-31 全量仅 3 个目录 / 41MB / **11 条摘要**（10-30 起），更早目录已无 AccountUsage 记录 |
| 关键噪声 | `used` 非单调（02:20=223 → 05:43=243 → 06:13=163），`total` 在 2300↔2400 波动：服务端配额池存在延迟合并/周期切换 |

**结论**：快照是服务端余额真值，但密度极低且 `used` 非单调，**不适合推导日消耗**；仅用于展示余额/总量和校验每请求 credits 汇总。

### 2.2 估算 token：`~/.qoder/projects/**/*.jsonl`（转录）

- 实时写入（Claude Code 风格）：`user`/`assistant` 消息行，`cwd`、`sessionId`、`timestamp`、`message.model` 齐全；正文在 `message.content[]`（text/thinking/tool_use/tool_result），真实用户输入另在 `humanInput.text`（与 content 首段重复，只能计一次）。
- 每条 assistant 行有 `message.usage`，token 字段全 0（客户端掩码），但保留：
  - `request_id`：一次请求的唯一键（实测 9,274 个，跨文件无重复）；
  - `credits` / `original_credits` / `billable`：每请求服务端计费；
  - `context_usage_ratio`：上下文占用比例（会话内单调递增，0.04~0.84），可换算输入 token。
- 转录含父会话与 `subagents/agent-*.jsonl`，均有独立 `sessionId`，直接全量扫描即可。

### 2.3 校准数据与可行性（2026-10-31 修正）

- 旧 IDE `local.db` 的 `chat_message.token_info` 有真值（prompt/completion/cached），但 **`content` 列是密文**，无法拟合「字符 → token」；且转录起始 2026-09-16，旧库 token 真值止于同日，二者 `requestId` 交集实测为 **0**，无法逐请求对齐。
- 因此 v1 采用两条独立先验：
  1. **输入**：`est_input = context_usage_ratio × 200,000`。旧库 gfmodel 的 prompt p50 = 96,570，而转录 gfmodel 的 ratio p50 ≈ 0.469 → 93.8k，吻合良好；`ratio` 缺失时该请求 est_input 记 0 并计数上报。
  2. **输出**：`est_output = chars_out ÷ factor[model]`。`factor` 用「转录每请求平均 chars_out ÷ 旧库同模型平均 completion_tokens」做聚合标定：gfmodel 2,661/691≈3.85、dfmodel 3,795/828≈4.58，其余模型用默认 3.8；带版本号入库。
- 该标定是**聚合先验**而非联合拟合，明确接受 ±30~40% 误差；不覆盖旧库 06-01~09-15 的估算（转录不存在）。

## 3. 额度采集设计（`qoder.credits`）

### 3.1 新表

```sql
-- 每请求计费真值（来自转录 usage.credits），request_id 天然幂等
CREATE TABLE IF NOT EXISTS usage_credit (
  request_id TEXT PRIMARY KEY,
  ts         REAL NOT NULL,
  day        TEXT NOT NULL,            -- 本地日期
  project    TEXT NOT NULL DEFAULT '',
  model      TEXT NOT NULL,
  session_id TEXT,
  credits    REAL NOT NULL DEFAULT 0,  -- 含非 billable 部分
  billable   INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_credit_day ON usage_credit(day);

-- 配额余额快照（来自 main.log），一次响应含 user/add_on 两类，故联合主键
CREATE TABLE IF NOT EXISTS usage_quota (
  request_id TEXT NOT NULL,
  quota_kind TEXT NOT NULL,            -- 'user' | 'add_on'
  ts         REAL NOT NULL,
  day        TEXT NOT NULL,
  total      INTEGER NOT NULL,
  used       INTEGER NOT NULL,
  remaining  INTEGER NOT NULL,
  unit       TEXT NOT NULL,
  raw_pct    REAL,
  expires_at INTEGER,
  PRIMARY KEY (request_id, quota_kind)
);
CREATE INDEX IF NOT EXISTS idx_quota_day ON usage_quota(day, quota_kind);
```

### 3.2 收割器

- **转录**：扫描 `~/.qoder/projects/**/*.jsonl`，按「一次响应」聚合（assistant 行同 `sessionId+timestamp`；usage 行携带 `request_id`），产出 credit 行（每请求一条）与 est 行（§4）。文件游标保存在 `meta['transcript_files']`（path → size/mtime/offset）：只读追加部分；文件被截断/重写则整文件重读。request_id 主键保证重复读取幂等；源文件被删除时历史行保留。
- **日志**：扫描 `logs/*/main*.log*`，逐行匹配 `[Auth] [AccountUsage] 用量响应摘要`；解析失败计数上报，不中断。全量重扫（实测 41MB/5 文件 <0.1s）+ `(request_id, quota_kind)` 主键幂等，不引入 offset 游标。
- **新鲜度签名**：`source_signatures()` 增加 `qoder.credits` = `max(mtime(转录文件), mtime(logs 目录树))`；`qoder.est` 复用转录签名。
- **收割时机**：并入现有自动刷新链（`_refresh_if_stale`）；日志目录会被清理，建议至少每日一次刷新（launchd 调度待用户确认）。

### 3.3 聚合口径

1. 日消耗 = 当日 `billable=1` 的 `credits` 求和（服务端计费值，小数保留）；同时列出 `billable=0` 的免费额度消耗（不计入配额）。
2. 按 request_id 去重；跨父/子代理转录重复出现只计一次。
3. 每个请求按本地日期、`cwd` 末段项目名、`model` 归集；不做任何插值。
4. 余额展示取 `add_on` 最新快照（`used/total/remaining`），并显示快照时间与年龄；`user` 配额本机恒 0，仍保留展示。
5. 交叉校验：快照相邻时间点之间的 billable credits 汇总应与 `used` 增量同量级（实测 +31.62 vs +32、+8.30 vs +9）；差异 >20% 时 doctor 告警，提示可能漏读转录。

### 3.4 命令与展示

- `usage credits [--range|--since|--until] [--format table|json]`：默认列 `day, credits, requests, free_credits, snapshots`；页脚输出最新快照余额与覆盖率。
- `usage doctor`：显示 `qoder.credits` 请求数/天数/最新转录时间、最新快照年龄（>24h 告警）、日志目录数、解析失败数、快照与 credits 交叉校验偏差。
- HTML：额度卡片（今日/本月 billable credits、免费 credits、最新余额）+ 每日消耗柱状图；口径注释「credits 为服务端每请求计费真值；余额来自本地日志快照；非 token、不可与 token 相加」。

## 4. 估算 token 设计（`qoder.est`）

### 4.1 采集

- 与额度共用一次转录扫描（§3.2），流式逐行解析；按 `sessionId+timestamp` 聚合同一响应。
- 行内统计：
  - `chars_out`：assistant 行 `text + thinking + json(tool_use.input)` 的字符数；
  - `chars_in`：user 行 `tool_result` 内容 + `humanInput.text`（无 humanInput 时用 text 内容）的字符数，归属到下一响应；
  - `request_id`：usage 行；无 usage 的行用 `sessionId:timestamp` 作为稳定键。
- **隐私边界**：正文仅在采集进程内存中用于计数，不落库、不写日志、不进错误信息；跨进程边界只有每请求的字符数/估算值与会话 ID。此为对 QODER-DESIGN §R4 原则的**显式放宽**（估算无法避免读文本），已评审确认。

### 4.2 估算口径（v1）

| 项 | 规则 |
|---|---|
| est_input | `round(context_usage_ratio × 200000)`；ratio 缺失记 0 并计数，不猜测 |
| est_output | `round(chars_out ÷ factor[model])`；factor: gfmodel 3.85、dfmodel 4.58、默认 3.8 |
| 粒度 | 每请求一行，聚合时按 (day, project, model) 汇总 |
| 系数来源 | 旧库同模型平均 completion 与转录 chars_out 的聚合标定（§2.3）；版本 `v1` 存 `meta['est_factor_version']` |
| 已知局限 | 200k 上下文窗口为 gfmodel 实测推断，其他模型若为 1M 窗口会低估；不重建逐轮上下文、不拆分缓存 |

### 4.3 新表 `usage_est`

```sql
CREATE TABLE IF NOT EXISTS usage_est (
  request_id TEXT PRIMARY KEY,
  ts         REAL NOT NULL,
  day        TEXT NOT NULL,
  project    TEXT NOT NULL DEFAULT '',
  model      TEXT NOT NULL,
  session_id TEXT,
  est_input  INTEGER NOT NULL DEFAULT 0,
  est_output INTEGER NOT NULL DEFAULT 0,
  chars_in   INTEGER NOT NULL DEFAULT 0,
  chars_out  INTEGER NOT NULL DEFAULT 0,
  ratio      REAL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_est_day ON usage_est(day);
```

- 增量追加读（文件游标），按 request_id 覆盖写，幂等；源文件删除时历史保留。
- `usage est` 聚合查询按天/模型/项目实时汇总，不再维护日聚合表。

### 4.4 展示

- HTML 新增「Qoder 估算 token（est）」区块：仅当筛选含 qoder 且有 est 数据时显示；明确标注「由转录文本 + 上下文比例估算，±30~40% 误差，不含缓存拆分，不可与真值/额度相加」。
- `usage est [--range|--since|--until] [--format table|json] [--group-by day,model,project]`，默认 `day,model`。

## 5. 风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 日志目录滚动清理，余额快照永久丢失 | 快照每日刷新并入自动刷新；doctor 告警最新快照年龄与目录数骤减；日消耗不依赖快照 |
| R2 | `used` 非单调/池重置 | 不再用快照差分推导日消耗；余额只展示最新值，交叉校验允许偏差并告警 |
| R3 | 客户端不再写 AccountUsage 日志或 usage.credits（schema drift） | doctor 统计命中率；连续 0 命中告警；转录解析失败隔离 |
| R4 | JSONL 转录格式变更/文件被清理 | 列存在性检查、错误隔离；已入库历史不删；文件截断自动整文件重读 |
| R5 | 估算漂移（模型/提示习惯变化） | 系数与窗口版本化；doctor 显示缺失 ratio 请求数；后续可用 credits 与 token 比例做月度校准 |
| R6 | 隐私放宽争议 | 正文不落库不写日志；仅字符数/比例/估算值跨边界；文档写明 |
| R7 | `credits` 语义误读（非 token） | 全程标注 credits；billable/免费分列；任何视图不与 token 相加 |

## 6. 验收

1. 额度：`usage credits` 的 billable credits 与 main.log 快照 `used` 增量逐段同量级（实测 4 个区间偏差 ≤10%）；重放同一转录/日志两次结果幂等。
2. 删除一个日志目录后重放，快照行数不变（request_id 主键），credits 不受影响。
3. 估算：gfmodel 的 est_input 聚合均值与旧库同模型 prompt p50（96,570）偏差 ≤40%；est_output 聚合均值与旧库 completion 均值（691）偏差 ≤40%。
4. doctor 新告警可注入 fixture 触发（快照过期、解析失败、ratio 缺失）。
5. 全部现有测试不回归（交付时 49 个：原 42 + 额度/估算采集、存储、CLI、HTML 新增 7）。

## 7. 明确不做

- 不调用 openapi.qoder.sh（零网络原则不变——额度真值来自客户端自己拉取后的本地日志）。
- 不做时级/turn 级上下文重建；不做成本折算（credits 非货币）。
- 不解密任何库、不读 Cookies/凭证。
