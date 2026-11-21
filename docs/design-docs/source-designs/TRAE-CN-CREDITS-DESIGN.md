# TRAE-CN-CREDITS-DESIGN.md —— Trae CN 以 Credits 为主轴的报告改造（已实现）

> 日期：2026-11-14 ｜ 版本：**v2.1（D1–D9 已批准并实现）** ｜ 状态：**已实现并通过 159 个单测** ｜ 基线：起始 usage-ledger v0.5.0 / `feat/cline` @ `2eb8764`，当前实现 0.6.0 / `feat/trae-cn-credits`
>
> 用户目标原话：
>
> > “Trae CN 的报告展示不对，这个 Agent 的 Credits 是准确的 token 是预估的，报告展示以 Credits 为主，与 qoder 类似。先编写实现文档给我审核，审核通过后按照开发流行进行开发。”
>
> 用户补充（v2）：
>
> > “D1 D2 允许，按照方案 A 实现，usage html 打开的报告需要是最新的数据，调整文档给我审核。”
>
> 用户批准（v2.1，2026-11-14）：
>
> > “D6 从 feat/cline 切，其他同意，文档审核通过开始实现。”
>
> **一句话结论**：Trae CN 本地没有可读的 credits 真值；方案 A 通过 Trae CN 客户端同源 usage 接口获取会话级 credits。D1–D9 已批准并实现，D6 采用从 `feat/cline` 切分支；`usage html` 在包含 Trae 时**默认先刷新再渲染**，保证生成的报告是最新快照；`--offline` 可跳过远程，刷新失败默认回退缓存并显式警告。

> 文档库状态：current（current）
> 当前事实源：ARCHITECTURE.md §6.9
> 索引：[design-docs/index.md](../index.md)
---

## 0. v2 变更摘要（相对 v1）

- **D1/D2 已批准**：允许读取本机登录凭证并访问 Trae CN 客户端同源用量接口。默认来源为 `storage.json` 的 `iCubeAuthInfo://icube.cloudide`（tc v5 本地解密）；`~/.trae-cn/trae-jwt-token` 是临时 token，usage 接口返回 401，已不再作为默认（2026-11-15 修正）。
- **`usage html` 不再始终离线**：只要 Trae 在报告范围内，渲染前默认执行一次 Trae credits 刷新；`--offline` 可跳过。
- **刷新失败软回退**：默认保留缓存并生成报告，同时在报告和命令行显式标注“刷新失败/数据时间”；`--strict-refresh` 可要求刷新失败即非 0 退出。
- **静态快照边界**：HTML 是生成时快照；再次双击旧文件不会更新，必须重新运行 `usage html`。
- **其余命令仍默认离线**：`usage report`、`usage credits`、`usage doctor`、`usage live`、自动同步不触发 Trae 远程调用；`usage sync --source trae-cn --remote` 继续用于手动/回填。
- **安全边界不变**：登录凭证只在刷新进程内读取，不落库/日志/HTML；不保存 prompt/正文/`user_input_preview`；不读 Keychain/Cookie、不解密 SQLCipher 库。
- **v3 凭证修正（2026-11-15）**：默认凭证从临时 token 改为 `storage.json` 的 tc v5 登录凭证；详见 [PROBE.md](../../references/PROBE.md) §6.10。

---

## 1. 目标与非目标

### 1.1 目标

1. 把 `trae-cn` 从 `estimate` 类改为 `credits` 类：`AGENT_KINDS["trae-cn"] = "credits"`。
2. 报告以 **Credits 为主**：每日用量、模型 Top、项目 Top（尽力而为）、明细表都以 credits 为主指标。
3. Token 继续作为**影子指标**：保留现有 hook 弱估算 `trae-cn.est`，显式标注“预估、不可与 credits 相加”，不把 API 返回的 token 冒充真值。
4. 风格与 Qoder 一致：同一套 KPI、图表、Top、明细；多选 Agent 时按 Agent 分列，不做跨单位、跨厂商的静默合计。
5. 报告取最新：`usage html` 在包含 Trae 时，渲染前默认执行一次 Trae credits 刷新；`--offline` 可跳过。`usage report` / `credits` / `doctor` / 自动同步仍默认离线；`usage sync --source trae-cn --remote` 继续用于手动/回填。
6. 凭证最小化：只在前台刷新/同步进程内读取本机登录凭证；不读 Keychain、不读浏览器 Cookie、不解密 SQLCipher 库、不写日志、不落库、不进 HTML。
7. 数据可追溯：记录最近同步时间、覆盖区间、会话数、错误；数据缺失时显示“缺少同步/刷新失败”的明确提示，不伪造 0。

### 1.2 非目标（首版不做）

- 不做 Trae CN 的活动指标（会话/提示/工具调用/时长）——活动轴仍只属于 Qoder。
- 不做 Trae 余额/套餐配额 KPI（`ide_user_ent_usage` 等）——首版只做已消费 credits；余额后续可加。
- 不把 API 的 `input_token/output_token/cache_read_token` 作为 token 真值；首版不落库，避免出现第三套 token 口径。
- 不做 SQLCipher 解密、内存扫描、进程注入、Keychain 读取、浏览器自动化、网络抓包。
- 不做 refresh token / 自动登录 / 多账号；登录凭证过期后要求用户重新登录 Trae CN。
- 不做后台定时联网；`usage html` 的刷新是命令内的前台同步调用，不是后台任务。现有 `live`/自动刷新逻辑不增加任何远程调用。
- 不做国际版 Trae；只处理 `api.trae.cn` 的 CN 账号。
- 不保存 `user_input_preview`、prompt、工具参数、响应正文；只保存用量元数据。

---

## 2. 现状与差距

### 2.1 当前实现

| 项 | 现状 |
|---|---|
| Agent 分类 | `trae-cn` = `estimate`（仅估算） |
| 报告主指标 | Trae 只有 hook 字符弱估算，没有 credits |
| 数据来源 | `~/.trae-cn/hooks` 事件文件（仅字符数/会话/项目/模型元数据） |
| 存储 | `usage_est`，`source='trae-cn.est'` |
| UI | 独立“Trae 弱估算”面板；`panel-credits` 只属于 Qoder |
| 用户感受 | 报告与 Trae 控制台的真实 credits 对不上 |

### 2.2 差距

用户要的是“Credits 准确”。但 Trae CN 的本机数据里没有逐会话/逐请求 credits：

- 加密库拿不到（SQLCipher，Phase 0 已失败，见 `docs/references/PROBE.md` §6.6）。
- `state.vscdb` / `storage.json` 只有权益和配置，没有 used/remaining（§6.7）。
- 日志只有请求 URL + HTTP 200，没有响应体；本机当前日志也没有 `ICubeUsageService` 余额行（§6.7 复测）。
- hooks 只有字符/事件元数据，没有 credits/token/quota（§6.8）。

因此：**不联网就得不到准确 credits**。这是本设计需要审核的核心前提。

---

## 3. 实测与证据

### 3.1 本机数据源盘点

| 数据源 | 结果 | 是否可用于 credits |
|---|---|---|
| `~/Library/Application Support/Trae CN/ModularData/ai-agent/database.db` | SQLCipher 加密；头部随机；WAL 活跃；Prior Phase 0 无法只读解密 | ❌ |
| `User/globalStorage/state.vscdb` | 122 个 key；无 usage/token/credits 数值 | ❌ |
| `User/globalStorage/storage.json` | 32 个 key；`iCubeServerData://icube.cloudide` 是权益/商业化配置，无 used/remaining | ❌ |
| `renderer.log` / `main.log` | 只有 URL + HTTP 200；无响应体；本机未发现 `ICubeUsageService` 余额行 | ❌ |
| hooks 事件 | 168 + 264 条；只有 session/tool/text 元数据；无 usage/credits/token_usage/quota | ❌ |
| `~/.trae-cn/trae-jwt-token` | 存在；925 B；权限 0600；内容是 `eyJ...` 开头的原始 JWT，**不是 JSON**；本设计阶段未把内容用于任何请求 | ⚠️ 临时 token，usage 接口 401；默认来源见 §6.10 |
| Trae CN 客户端同源 usage 接口 | 客户端日志可见 `query_user_usage_group_by_session` 请求（2026-11-14 16:53，HTTP 200）；竞品已实现请求/响应契约 | ✅ 唯一可行 |

> 说明：探针阶段本机 JWT 文件只做了“存在性/大小/权限/前缀”检查，没有把 token 写入文档、日志或数据库。D1/D2 批准后，实现只在前台刷新进程内读取凭证，仍不落库/日志/HTML。该临时 token 不被 usage 接口接受，2026-11-15 起默认改用 `storage.json` 的 tc v5 登录凭证（§6.10）。

### 3.2 客户端同源接口（竞品证据）

**端点**

```text
POST https://api.trae.cn/trae/api/v1/pay/query_user_usage_group_by_session
```

**请求头**（竞品 `TraeWorkAssistant` 实测形态）

```text
accept: application/json, text/plain, */*
accept-language: zh-CN,zh;q=0.9
authorization: Cloud-IDE-JWT <jwt>
content-type: application/json
user-agent: Mozilla/5.0 (...) Chrome/152.0.0.0 Safari/537.36
origin: https://www.trae.cn
referer: https://www.trae.cn/
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: same-site
```

**请求体**

```json
{
  "start_time": 1760000000,
  "end_time": 1762591999,
  "page_size": 20,
  "page_num": 1,
  "usage_type": [7]
}
```

- `start_time` / `end_time`：Unix **秒**。
- `page_size`：20（对齐控制台实测值）。
- `usage_type: [7]`：Cloud-IDE 会话积分消耗（竞品实测口径）。
- 单次窗口不能太大；竞品按 **30 天分块**，否则可能 400/9004 参数错误。

**响应（字段名来自竞品代码，本机尚未实测响应体）**

```json
{
  "total": 123,
  "user_usage_group_by_sessions": [
    {
      "usage_time": 1760000000,
      "credits_float": 1.23,
      "model_name": "claude-sonnet-4.5",
      "extra_info": {
        "input_token": 1000,
        "output_token": 200,
        "cache_read_token": 300
      },
      "amount_float": 1.2,
      "cost_money_float": 0.01,
      "session_id": "...",
      "mode": "agent",
      "user_input_preview": "..."
    }
  ]
}
```

**凭证与分页要点**

- JWT 只进 `authorization` 请求头，不进日志/返回值。
- `credits_float` 优先，旧字段 `amount_float` 兜底；两者都缺失时**跳过该行**，不伪造 0。
- 竞品分页上限：50 页（`TraeWorkAssistant`）/ 100 页（`TokenTracker`），单页 20。
- 竞品 `TokenTracker` 对超大窗口做二分降级；本设计首版采用 30 天分块 + 页数上限 + 必要时二分，失败即保留旧缓存。
- `TokenTracker` 同样把该接口做成显式 opt-in（环境变量开关），不默认联网。

**证据链接**（只读调研，未执行）：

- `smart-open/TraeWorkAssistant`：`src-tauri/src/commands/usage_history.rs`
- `xiufengsun/TokenTracker`：`src/lib/trae-cn-config.js`
- `SHADE-glitch/trae-cn-usage-tracker`：`docs/maintenance/trae-cn-format.md`
- 本机 Trae CN 3.4.18 日志：`/Users/wayne/Library/Application Support/Trae CN/logs/20261112T151232/window1/renderer.log`

**证据强度**：

- 端点、请求体、字段名、30 天分块、`usage_type: [7]` 来自两个独立竞品实现 + 本机客户端日志，可信度较高。
- 本机尚未实际调用该接口；实现第一步用 `--days 1` 做只读验证，核对 `credits_float` 与 Trae 控制台是否一致。
- `junhoyeo/tokscale` 曾表示 CN 后端未接入，与上述两个项目冲突；本设计不依赖 tokscale 的结论，以实际探测为准。

---

## 4. 政策与安全边界（D1/D2 已批准）

### 4.1 原政策与本次变更

README 原文：

> “采集层用成熟做法，报表层自己做；不为缺失数据编造 token，不爬私有 API，无任何网络行为。”

`docs/design-docs/source-designs/TRAE-CN-DESIGN.md` 原文：

> “不读取 `/Users/wayne/.trae-cn/trae-jwt-token`，不接触登录态。”
> “不调用 `api.trae.cn` 的 `ide_user_ent_usage` / `web_user_ent_usage` / `query_user_usage_group_by_session` 等私有接口。”

**D1/D2 已批准（2026-11-14）**：允许为 Trae credits 增加客户端同源接口访问，并允许自动读取本机 Trae CN 登录凭证。初版误用 `~/.trae-cn/trae-jwt-token`（临时 token，401）；2026-11-15 起默认读取 `storage.json` 的 `iCubeAuthInfo://icube.cloudide` 并在本地解密（tc v5），不读 Keychain/Cookie、不解密 SQLCipher 库。这仍是**定向、前台、可关闭**的例外，不扩大到其他源或其他 API。

### 4.2 已批准的定向例外

允许以下两个前台入口联网，二者共用同一 API client 与同一套凭证规则：

```text
入口 1（手动/回填）：
usage sync --source trae-cn --remote

入口 2（报告刷新）：
usage html [--source trae-cn | 不带 source]
  -> 若 Trae 在报告范围：渲染前先执行一次 Trae credits 刷新
  -> 再读 SQLite + 渲染静态 HTML

共同流程：
  读取本机登录凭证（仅本次进程内存）
  -> POST query_user_usage_group_by_session
  -> 只解析用量元数据
  -> 写 SQLite 缓存
```

边界：

1. **前台、可控**：只有 `usage sync --source trae-cn --remote` 或 `usage html`（Trae 在范围内）会联网；`usage html --offline`、`report`、`credits`、`doctor`、`live`、自动同步都不触发远程调用。
2. **单账号、低频**：只使用本机当前登录账号；不做多账号、不做并发、不做后台轮询。`usage html` 只拉报告窗口（默认 30 天），不是全量历史。
3. **凭证最小化**：默认读 `storage.json` 的 `iCubeAuthInfo://icube.cloudide` 并在本地解密 tc v5；用户显式提供 `--jwt-file` / `TRAE_CN_JWT` / `TRAE_CN_JWT_FILE` 时优先。不读 Keychain、不读浏览器 Cookie、不解密 SQLCipher 库。
4. **凭证不落盘**：解密后的 token 不写 SQLite、不写 meta、不写 HTML、不写日志、不进异常信息；错误只输出 HTTP 状态和脱敏后的错误码。
5. **内容不落盘**：不保存 `user_input_preview`、prompt、工具参数、响应正文；只保存 `session_id`、`usage_time`、`model_name`、`credits`、`mode`（可选）。
6. **失败软回退**：`usage html` 默认刷新失败时使用缓存继续出报告，并在命令行/HTML 显式标注“刷新失败 + 数据时间”；`--strict-refresh` 可改为失败即非 0 退出。`sync --remote` 失败时保留旧缓存并报错，不编造数据。
7. **TLS 不降级**：使用 Python 默认 SSL 校验；不关闭证书验证；不自定义代理。
8. **不做规避**：不伪造客户端指纹、不做验证码/风控绕过、不做抓包重放；请求头只是对齐竞品实测的 Web 路由形态。
9. **静态快照**：HTML 是生成时快照；再次打开旧文件不会自动更新。要“最新”，必须重新运行 `usage html`（默认会刷新）。

### 4.3 已批准决策

| 编号 | 问题 | 结论 |
|---|---|---|
| **D1** | 是否允许 Trae credits 的联网路径？ | **已批准 A1**：允许；`sync --remote` 与 `usage html` 前台刷新可联网；自动读取本机登录凭证 |
| **D2** | 是否允许自动读取本机登录凭证？ | **已批准**：默认读取 `storage.json` 的 `iCubeAuthInfo://icube.cloudide`（tc v5，本地解密）；临时 token 已因 401 弃用；支持 `--jwt-file` / `TRAE_CN_JWT` 覆盖；不读 Keychain/Cookie |

> v1 中的 A3（不联网）/A4（手工导入）不再作为本次实现路径，保留在附录作历史备选。

---

## 5. 方案对比

| 方案 | 数据 | 准确性 | 网络 | 凭证 | 复杂度 | 结论 |
|---|---|---|---|---|---|---|
| **A. 官方客户端同源 usage 接口（opt-in）** | 会话级 credits、模型、时间、token 字段 | 高（服务端计费） | `sync --remote` + `html` 默认刷新（`--offline` 可关） | 本机登录凭证 | 中 | **推荐** |
| B. 本地余额日志采样 | 余额/下限，不是逐会话 | 低，且本机当前没有该日志行 | 无 | 无 | 低 | 只能做余额趋势，不能做主报告 |
| C. SQLCipher 解密 | 理论上最全 | 高 | 无 | 需要密钥 | 极高，已失败 | 不采用 |
| D. 手工导入 dashboard 导出 | 取决于导出文件 | 高 | 无 | 无 | 中 | 备用；需先确认导出能力 |

**推荐 A**：只有 A 能同时满足“Credits 准确、每日/模型维度、与 Qoder 类似”。B/C/D 都不能提供稳定的逐会话 credits 主报告。

---

## 6. 推荐架构（方案 A）

### 6.1 数据流

```text
入口 1：usage sync --source trae-cn --remote [--days N]
入口 2：usage html [--source trae-cn | 不带 source]   # 渲染前默认刷新
        │
        ├─ 登录凭证解析（仅内存）
        │    --jwt-file > TRAE_CN_JWT > TRAE_CN_JWT_FILE > storage.json（iCubeAuthInfo tc v5）
        │
        ├─ Trae CN usage client（stdlib urllib）
        │    30 天分块 / page_size=20 / page_num=1..N / usage_type=[7]
        │    单页 300ms 间隔；超时 30s；页数上限；必要时窗口二分
        │
        ├─ 归一化（不保存 preview/正文）
        │    session_id, usage_time, model_name, credits, mode
        │
        ├─ SQLite: usage_credit(source='trae-cn', request_id='trae-cn:<session_id>')
        │    upsert，幂等；失败不写半批
        │
        └─ usage html
             -> 刷新成功：读取最新 credits
             -> 刷新失败：默认回退旧缓存 + 显式警告（--strict-refresh 则退出）
             -> payload.credits.rows[*].source
             -> Trae credits 主面板 + hook 弱估算影子
             -> 生成静态 HTML 快照
```

### 6.2 CLI 契约

#### 同步

```bash
# 只同步本地 hook 估算（现状，不联网）
usage sync --source trae-cn

# 显式联网同步 credits（新增）
usage sync --source trae-cn --remote

# 首次回填一年
usage sync --source trae-cn --remote --days 365

# 指定凭证文件（优先于 storage.json）
usage sync --source trae-cn --remote --jwt-file /path/to/token

# 只演练，不联网、不写库
usage sync --source trae-cn --remote --dry-run
```

参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--remote` | 关闭 | 只有显式指定才联网 |
| `--days N` | 30 | 同步最近 N 天；与 `--since` 二选一 |
| `--since YYYY-MM-DD` | 无 | 从本地日期 00:00 开始；优先于 `--days` |
| `--jwt-file PATH` | 无 | 显式凭证文件（优先于 storage.json） |
| `--dry-run` | 关闭 | 只打印计划（天数、分块数、凭证是否存在），不请求 |
| `--full` | 关闭 | 对 Trae 等价于 `--days 365`（首次回填） |

行为：

- `--remote` 只对 `trae-cn` 生效；其它 source 不受影响。
- `--remote` 同时保留本地 hook 估算同步（先本地、后远程；远程失败不影响本地估算）。
- 远程成功后才写 `usage_credit`；失败时整批不写，保留旧缓存，并更新 `source_state` 错误。
- 不自动重试 401/403；429/5xx 可重试 1 次（2 秒退避），仍失败则报错。
- 单次同步打印：`trae-cn.credits: N 会话 / X credits / 覆盖 YYYY-MM-DD..YYYY-MM-DD`。

#### 报告（默认刷新最新数据）

```bash
# 默认：Trae 在报告范围内时，渲染前刷新一次，再生成 HTML
usage html --source trae-cn --open
usage html --open

# 强制离线：只读缓存，不发起任何远程请求
usage html --source trae-cn --offline --open

# 刷新失败也生成回退报告（默认），但显式警告
usage html --open

# 刷新失败直接返回非 0（仍生成回退报告，便于排查）
usage html --open --strict-refresh

# 可选：N 秒内已成功同步则复用，减少重复请求
usage html --open --max-age 300

# credits 查询：默认离线、按 source 分列，不做跨 Agent 合计
usage credits
usage credits --source trae-cn
```

参数：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--offline` | 关闭 | 跳过 Trae 远程刷新，只读 SQLite 缓存；UI 显示“离线缓存” |
| `--max-age N` | `0` | `0` = 每次 `usage html` 都刷新；`N>0` = 最近 N 秒内成功同步且上次窗口覆盖本次请求范围时复用，减少重复请求 |
| `--strict-refresh` | 关闭 | 刷新失败时返回非 0；默认软回退缓存并继续出报告 |
| `--stateless` | 关闭 | 与远程 Trae 互斥：跳过远程刷新，Trae credits 显示“需要 SQLite 缓存”，不偷偷联网 |

行为：

- **Trae 在范围内**：`--source` 为空，或为 `trae-cn`；`--filter source=trae-cn` 同样视为在范围内。只选 `qoder`/`claude` 等不会触发 Trae 远程请求。
- **刷新窗口**：使用本次报告的 `--since/--until`（或默认 30 天）；`usage html` 不额外拉 365 天历史。
- **刷新成功**：写 `usage_credit`，更新 `source_state.last_sync_at`；stdout/stderr 打印本次同步的会话数/credits/覆盖区间，并写入 HTML 的 coverage。
- **刷新失败**：默认不阻断报告生成；stderr 打印脱敏警告，HTML coverage 标记 `refresh_error` + `last_sync_at`，UI 按有无缓存显示“当前为缓存数据”或“暂无缓存数据”，不伪造同步时间。`--strict-refresh` 时仍生成回退报告，但命令返回非 0。
- **离线**：`--offline` 不读登录凭证、不请求；UI 标记“离线缓存”，并显示缓存时间；没有缓存时显示空状态和同步命令。
- **静态快照**：`usage html` 每次运行都会重新生成文件；已经生成的 HTML 不会因为再次打开而更新。需要最新数据时重新运行命令。
- `usage credits` 默认展示所有 credit source；输出 source 列；Trae 的计数列叫“会话”，Qoder 叫“请求”；它不自动联网，需要最新数据时先 `usage sync --remote` 或跑一次 `usage html`。
- `usage report` / `usage doctor` 不触发 Trae 远程调用；doctor 只显示缓存状态和登录凭证是否存在/权限/可读性（只做 stat，不解密 token）。

实现落点：

- `cmd_html` 在 `_load_records` / `_load_credit_payload` 之前调用 `_refresh_trae_credits_remote(...)`；异常捕获后继续渲染，并把错误放进 coverage。
- `_load_credit_payload` 只读 SQLite；不得在里面触发远程请求，避免 `report`/`credits` 间接联网。
- 远程刷新与 `sync --remote` 共用 `TraeCreditsClient` + `upsert_trae_credits`，保证幂等和错误处理一致。

### 6.3 远程客户端细节

- 纯标准库：`urllib.request` + `json` + `datetime`；不新增依赖。
- 时间：`start_time`/`end_time` 为 Unix 秒；本地日期用现有 `local_day()` 归日。
- 分块：从 `end_ts` 向过去切，每块 `CHUNK_DAYS=30`，边界不重叠；`end_time` 不取未来：结束日为当天时取当前时刻，历史日期取当天 23:59:59。
- 分页：`page_size=20`；`page_num` 从 1 递增；累计行数 ≥ `total` 或读到空页时停止；短页但 `total` 未达时继续翻页，避免静默漏行；`MAX_PAGES=100`。
- 超限：若 `total > page_size * MAX_PAGES`，把当前 30 天窗口二分，最多 4 层；仍超限则失败并给出“缩短 --days”提示。
- 限速：每页之间 `sleep(0.3s)`；不并发。
- 超时：30 秒/请求。
- 解析：
  - `user_usage_group_by_sessions` 必须是 list；否则报错。
  - `session_id` 空 -> 跳过（无法幂等）。
  - `usage_time` 缺失/非法 -> 跳过；若数值 > 10^11 视为毫秒并除以 1000。
  - `credits_float` 优先；缺失才用 `amount_float`；都缺失 -> 跳过并计数。
  - `model_name` 空 -> `unknown`。
  - `mode` 可选，只用于诊断，不写入主表。
  - `user_input_preview` 直接丢弃，不读入内存以外的结构（或读入后立即丢弃，不落库）。
- 幂等：`request_id = "trae-cn:" + session_id`；同一会话重复拉取时更新同一行，不累加。
- 去重：同一批内若 session 重复，保留 `usage_time` 更新的那条；不求和。
- 失败：整批 fetch 成功后才 `upsert_credits`；中途失败不写部分结果。
- `usage html` 刷新复用同一 client；窗口 = 报告窗口；先检查 `source_state.last_sync_at`、`trae_credits_last_window` 与 `--max-age`，只有“时间够新且窗口覆盖本次范围”才跳过网络；刷新失败不写半批，只更新错误状态。

### 6.4 同步窗口与历史

- 默认 30 天：覆盖报告默认区间，请求量小。
- 首次历史：`--days 365` 或 `--full`，约 13 个 30 天块。
- 不做游标：每次按窗口重拉并 upsert，避免“会话后续更新/跨天”导致漏数；30 天窗口通常 1 个块，成本可控。
- 不做删除：API 不再返回的旧会话保留在本地，避免历史突然消失；如需清理，用现有 `prune` 另行设计（本设计不改 prune）。
- 日粒度限制：API 是**会话级**，credits 归属 `usage_time` 所在本地日；不是逐请求日粒度。若一个会话跨天，无法拆分。报告需注明这一点。
- 项目维度：API 没有 project 字段；首版用 hook 事件的 `session -> project` 做**尽力映射**，未命中显示 `-`。2026-11-15 本机实测 200 个 credits session 与 hook session **零重叠**，当前无法关联、全部显示 `-`；若必须完整项目维度，另立“本地会话元数据只读探针”任务，不读正文。

### 6.5 Token 处理

- 保留现有 `trae-cn.est`（hook 字符弱估算）作为影子。
- API 的 `extra_info` token 字段**首版不落库、不进主报告**；原因：
  1. 用户明确“token 是预估的”，不能因为 API 带了 token 就冒充真值；
  2. 避免出现 hook est / API token / token 真值三套口径；
  3. 首版聚焦 credits，减少字段和测试面。
- 若后续需要，可新增 `trae-cn.api-est` 影子轨，单独标注“Trae 报告 token（估算）”，不与 hook est 相加；不在本设计范围。

### 6.6 Credits 汇总规则

- **不跨 Agent 相加**：Qoder 与 Trae 的 credits 是不同厂商的计费单位，不能静默求和。
- 单选一个 credit Agent：显示该 Agent 的总量、日均、Top、明细。
- 多选 Qoder + Trae：
  - KPI 按 Agent 分块；
  - 图表用分组柱/多序列，不堆叠成一个总数；
  - Top 榜单按 Agent 分组排名，不做跨 Agent 排名；
  - 明细表有 `Agent` 列；合计按 Agent 分列，并标注“不可相加”。
- token + credits 同时选中：继续沿用现有“分单位汇总”，不把 credits 加到 token 上。

---

## 7. 存储改造

### 7.1 `usage_credit` 增加 source

现有表：

```sql
CREATE TABLE usage_credit (
  request_id TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  day TEXT NOT NULL,
  project TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL,
  session_id TEXT,
  credits REAL NOT NULL DEFAULT 0,
  billable INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
```

迁移（SQLite 不支持直接改 PK，保留原 PK，新增列即可）：

```sql
ALTER TABLE usage_credit ADD COLUMN source TEXT NOT NULL DEFAULT 'qoder';
CREATE INDEX IF NOT EXISTS idx_credit_source_day ON usage_credit(source, day);
```

- 旧 Qoder 行自动变成 `source='qoder'`。
- Trae 行：`source='trae-cn'`，`request_id='trae-cn:<session_id>'`，`billable=1`，`free_credits=0`。
- 不新增 `preview`、`prompt`、`token` 列；不改变 Qoder 行语义。
- 迁移在 `SqliteStore._migrate()` 中做，幂等。

### 7.2 查询方法

| 方法 | 改动 |
|---|---|
| `upsert_credits` | 写入 `source`；按 `request_id` upsert（Trae 已带前缀） |
| `credit_daily` | 按 `(day, source)` 聚合，返回 `source` |
| `credit_rows` | 按 `(day, source, model, project)` 聚合，返回 `source` |
| `credits_totals` | 按 `source` 返回字典；不再返回单一行合计 |
| `credit_count` | 可加 `source` 过滤（默认全部） |
| `credit_bounds` | 可加 `source` 过滤（默认全部） |
| `latest_quota` | 首版不动，仍只返回 Qoder 快照 |

`usage_quota` 首版不加 `source`：Trae 余额不在 v1 范围。若后续要做 Trae 余额，再迁移该表。

### 7.3 source_state / meta

新增：

```text
source_state.source = 'trae-cn.credits'
  status: ok / error / empty
  records_total: 会话数
  last_sync_at: 最近成功同步时间
  last_event_ts: 最大 usage_time
  last_error: 脱敏错误（不含登录凭证）
```

- 不用文件 mtime 判断远程缓存是否过期；用 `last_sync_at` + `--max-age`。
- 可选 meta：`trae_credits_last_window`（记录上次请求的 days/since）和 `trae_credits_last_attempt`（最近一次尝试时间，无论成败），用于诊断；不存登录凭证。
- `usage html` 默认先刷新，刷新失败时更新 `status/last_error`、保留 `last_sync_at`，然后读缓存渲染；`--offline` 只读这些状态，不触发远程。

### 7.4 兼容性

- 旧数据库打开后自动加列，Qoder 报告行为不变。
- 旧 HTML/旧测试中 `credits.rows` 没有 `source` 的地方，JS 用 `row.source || "qoder"` 兼容。
- 不删除旧 `credits.totals` 字段；改为按 source 的 map；同步更新测试。

---

## 8. HTML payload 改造

### 8.1 `agents`

```json
{
  "claude": "token",
  "codex": "token",
  "opencode": "token",
  "kilo": "token",
  "cline": "token",
  "qoder": "credits",
  "trae-cn": "credits"
}
```

`KIND_LABELS` 保持：`credits` = “精确 Credits”。`estimate` 暂时保留（当前无 Agent 使用，未来可用）。

### 8.2 `credits`

```json
{
  "rows": [
    {
      "day": "2026-11-14",
      "source": "trae-cn",
      "model": "claude-sonnet-4.5",
      "project": "-",
      "credits": 1.23,
      "free_credits": 0,
      "requests": 1,
      "free_requests": 0
    }
  ],
  "days": [
    {
      "day": "2026-11-14",
      "source": "trae-cn",
      "credits": 1.23,
      "free_credits": 0,
      "requests": 1,
      "free_requests": 0,
      "snapshots": 0
    }
  ],
  "totals": {
    "qoder": { "credits": 0, "free_credits": 0, "requests": 0, "days": 0, "models": 0 },
    "trae-cn": { "credits": 1.23, "free_credits": 0, "requests": 1, "days": 1, "models": 1 }
  },
  "quota": {
    "user": { "...": "Qoder 快照，首版不变" },
    "add_on": { "...": "Qoder 快照，首版不变" }
  }
}
```

- `requests` 在 Trae 行表示“会话数”；UI 根据 `source` 显示“会话”。
- `quota` 保持 Qoder 结构，避免无意义的嵌套迁移；Trae 首版不显示余额 KPI。
- `credits.days` 保留，按 `(day, source)`；图表主要用 `rows`。

### 8.3 coverage

```json
{
  "trae-cn.credits": {
    "available": true,
    "last_sync_at": "2026-11-14T17:30:00+08:00",
    "last_attempt_at": "2026-11-14T17:30:00+08:00",
    "since": "2026-10-15",
    "until": "2026-11-14",
    "sessions": 123,
    "status": "ok",
    "refresh_mode": "auto",
    "refresh_error": null,
    "stale": false,
    "error": null
  },
  "trae-cn.est": {
    "available": true,
    "events": 432,
    "version": "trae-hook-v1"
  }
}
```

- `refresh_mode`：`auto`（html 默认刷新）、`offline`（`--offline`）、`stateless`（`--stateless`）、`disabled`（Trae 不在范围内）。
- `refresh_error`：本次刷新失败的脱敏原因；成功/离线为 `null`。不含登录凭证/请求头/响应体。
- `stale`：本次刷新失败、或 `last_sync_at` 超过 2 天、或 `--offline` 且缓存较旧时为 `true`。
- 没有同步数据时 `available=false`：无刷新错误显示“未同步”，刷新失败显示“刷新失败，暂无缓存数据”；不显示 0 作为真实值。
- 刷新失败但已有缓存时仍展示缓存，并在 HTML 状态条显示“Trae credits 刷新失败，当前为缓存数据 · last_sync_at”。
- 顶部覆盖摘要、KPI 空状态与状态条统一按 `refresh_error` 使用“刷新失败”，否则使用“未同步”。

### 8.4 不进入 payload 的内容

- 登录凭证、请求头、原始 API 响应、`user_input_preview`、prompt、工具参数、响应正文、refresh token。
- 同步错误只保留脱敏后的状态码/错误码。

---

## 9. UI 改造

### 9.1 Agent 分类与 chip

- `trae-cn` chip 的 badge 从“仅估算”变成“精确 Credits”。
- 单击只看该 Agent、再次点击恢复全部、⌘/Ctrl/Shift 多选、至少保留一个——**交互不变**，只改分类和数据过滤。
- `present` 检测不能把 Trae credits 误算成 Qoder：
  - `present.qoder` 只在 Qoder 有 credits / shadow est / activity 时为真；
  - `present["trae-cn"]` 在 Trae 有 credits 或 hook est 时为真。

### 9.2 选择过滤（必须改）

当前的 `creditRowsFor()` 只判断“有任意 credit Agent 被选中”，没有按 source 过滤；加入 Trae 后必须改：

```js
function creditRowsFor(ignore) {
  if (!hasCreditsSelected()) return [];
  return CREDIT_ROWS.filter(function (row) {
    return state.agents.has(row.source) && matchesFilters(row, ignore);
  });
}

function qoderEstRowsFor(ignore) {
  if (!state.shadow || !state.agents.has("qoder")) return [];
  return EST.filter(function (row) { return matchesFilters(row, ignore); });
}

function hasTraeEstimateSelected() {
  return state.agents.has("trae-cn") && TRAE_EST.length > 0;
}
```

其它必须同步修改的地方：

| 函数/位置 | 问题 | 改法 |
|---|---|---|
| `creditRowsFor` | 不按 Agent 过滤 | 加 `state.agents.has(row.source)` |
| `dimensionRows` | 硬编码 `source:"qoder"` | 用 `row.source`；只加入已选 credit Agent |
| `navTotal` | 任意 credit Agent 都返回全部 credits | 按 agent 过滤 source |
| `qoderEstRowsFor` | 只要选任意 credits 就显示 Qoder 影子 | 要求选中 `qoder` |
| `hasEstimateSelected` | Trae 改类后为空，导致 est 面板消失 | 新增 `hasTraeEstimateSelected()`，Trae 弱 est 面板用它 |
| `renderKpis` | “仅估算”section 依赖 `hasEstimateSelected` | Trae 弱 est 作为 Trae credits 的影子 section |
| `renderCharts` | est 面板依赖 `hasEstimateSelected` | 改用 `hasTraeEstimateSelected()` |
| `syncShell` | 单位标签只区分 credits/est | 支持 `credits + 影子 est` / `credits + trae 弱 est` 同时出现 |
| `renderCoverage` | 只描述 Qoder credits | 增加 Trae credits 的同步时间/范围/会话数/刷新模式/错误/stale |

### 9.3 KPI

- **Credits 主区**按 Agent 分块：
  - Qoder：`区间 billable credits`、`免费 credits`、`区间日均`、`最新额度余额`、可选影子 est。
  - Trae：`区间 credits`、`会话数`、`覆盖天数`、`模型数`、可选 `trae 弱 est` 影子卡片。
  - 多选时两个块并列，不出现“总 credits”。
- 没有 Trae credits 缓存时：显示“未同步”空状态卡片；若本次刷新失败则显示“刷新失败 + 暂无缓存数据 + 脱敏原因”；文案包含 `usage html`（默认刷新）或 `usage sync --source trae-cn --remote`
- 刷新失败但已有缓存：显示“缓存数据”徽标 + `last_sync_at`，并保留数值；不要显示成“当前实时”。
- 没有 hook 弱估算时：Trae 影子卡片显示“无 hook 估算”，不显示 0 作为真实值。

### 9.4 每日图表

- **单选 Qoder**：保持现有 billable/free 堆叠柱 + 可选 Qoder est 虚线。
- **单选 Trae**：单序列“Trae credits”柱状图；不显示“免费（不计配额）”图例。
- **同时选中 Qoder + Trae**：切换为**分组柱状图**（同一天每个 source 一根柱），不堆叠成一个总数；图例为 `Qoder` / `Trae CN`；标题或副标题写“credits 按 Agent 分列，不可相加”。
- 图表下方提示：
  - Trae 是会话级归属日，不是逐请求日；
  - 未同步时显示“缺 Trae credits，运行 `usage html` 或 `usage sync --source trae-cn --remote`”；
  - 刷新失败且已有缓存时显示“当前为缓存数据（last_sync_at）”；无缓存时不显示缓存字样。

实现上可以给现有 `renderStackChart` 增加 `mode: "stacked" | "grouped"`，复用坐标轴、tooltip、图例；不引入新图表库。

### 9.5 Top 榜单

- 单选一个 credit Agent：沿用现有 Top 模型/项目榜单，以 credits 为主指标。
- 同时选中 Qoder + Trae：
  - 按 Agent 分组展示（两个小节或带 Agent 标签的组），各自排名；
  - 不把 Qoder credits 和 Trae credits 相加后排名；
  - 项目维度 Trae 未映射时显示 `-`，并在 footnote 说明“Trae API 无 project 字段；当前 hook session 与 credits session 无法关联，项目维度不可用”。
- token + credits 同时选中：保持现有双单位逻辑；不要因为 credits 主指标而隐藏 token Top。

### 9.6 明细表

- 增加/复用 `Agent` 列：credits 行的 source 显示为 `qoder` / `trae-cn`。
- 单位列：credits 行 `unit:"credit"`，`unitLabel:"credits"`；Trae 的计数列显示“会话”，Qoder 显示“请求”。
- 合计行：
  - 按 source 分别输出 `qoder: X credits`、`trae-cn: Y credits`；
  - 不输出跨 source 的单一 credits 合计；
  - 估算合计继续标注“不可相加”。
- `reportRows()` 当前硬编码 `source:"qoder"`，改为 `row.source || "qoder"`；`tableInfo()` 按 source 分组。

### 9.7 影子指标

- Qoder 影子 est：仍由 `state.shadow` 开关控制；只有选中 Qoder 时才显示；和 Qoder credits 同图虚线/同 KPI 块，标注“不可与 credits 相加”。
- Trae 弱 est：独立 `panel-est` 图（输入/输出），只有选中 Trae 且存在 hook 数据时显示；KPI 作为 Trae credits 的影子卡片；不参与 credits 总量。
- 两套影子不能合并成一个“est 总计”。

### 9.8 数据新鲜度与刷新状态

- 报告顶部/筛选区旁增加 Trae 数据状态：
  - 刷新成功：`Trae credits 已刷新 · HH:MM:SS`（低调显示，不抢主指标）。
  - `--offline`：`Trae credits 离线缓存 · last_sync_at`。
  - 刷新失败且有缓存：`Trae credits 刷新失败，当前为缓存数据 · last_sync_at · 原因`；用警示色，但不遮挡报告。
  - 刷新失败且无缓存：`Trae credits 刷新失败，暂无缓存数据 · 原因`，不显示虚假同步时间。
  - 无缓存且未失败：`Trae credits 未同步`，附 `usage html` / `usage sync --source trae-cn --remote`。
- footer 增加一行：
  `Trae credits 来源：本机 opt-in API 同步；最近成功同步 <last_sync_at>；本次模式 <auto/offline/stateless>`
- `coverage["trae-cn.credits"]` 驱动上述状态；不要在 JS 里猜测新鲜度。
- 命令行同样输出：
  - 成功：`trae-cn.credits: refreshed N sessions / X credits（YYYY-MM-DD..YYYY-MM-DD）`
  - 失败：`trae-cn.credits: refresh failed, using cached data from <last_sync_at> (<redacted error>)`
  - 离线：`trae-cn.credits: offline cache from <last_sync_at>`

### 9.9 文案

需要改的现有文案：

- `NO_TOKEN_NOTICE`：
  - 旧：“无 token 真值：Trae CN（仅 hook 字符弱估算）…”
  - 新：“Trae CN token 仅 hook 弱估算；credits 为服务端会话级计费真值，`usage html` 渲染前默认刷新（或 `usage sync --source trae-cn --remote`）。”
- `renderShadowNote` / footer：
  - 旧：“Qoder credits 为服务端每请求计费真值…”
  - 新：“Credits 按 Agent 分列：Qoder 为逐请求计费，Trae CN 为会话级计费；不同 Agent 的 credits 不可相加。”
- Credits 图标题：
  - 单选 Trae：“Trae CN 每日 credits（会话归属日）”
  - 多选：“每日 credits（按 Agent 分列，不可相加）”
- 页脚数据边界：
  - “Trae credits 来自本机 opt-in API 同步；`usage html` 默认刷新，失败时回退缓存；不保存 prompt/正文；离线/失败时显示数据时间。”

---

## 10. 开发与验收流程

### 10.1 分支基线

当前 `feat/cline` 比 `main` 多 9 个提交，包含本轮报告重构、Agent 多选、Trae 独立来源等前置 UI；`main` 还没有这些。新特性不能直接基于 `main` 实现，否则会冲突或重复。

可选：

| 编号 | 做法 | 优点 | 风险 |
|---|---|---|---|
| **B1 推荐** | 先把 `feat/cline` 合并到 `main`（需用户明确同意），再从最新 `main` 切 `feat/trae-cn-credits` | 符合 AGENTS.md；后续干净 | 需要先审核/合并 feat/cline |
| B2 | 直接从 `feat/cline` 切 `feat/trae-cn-credits` | 立刻可开发 | 基线不是 main；feat/cline 合并后需 rebase/再次集成 |
| B3 | 等 feat/cline 合并后再开始 | 最稳 | 延后开发 |

> AGENTS.md 要求“任何分支合并进 main 都必须先征得用户同意”。本文不擅自合并。

### 10.2 TDD 顺序

1. 先写失败测试：
   - `tests/test_trae_credits.py`：API 客户端、分块、分页、凭证脱敏、幂等。
   - `tests/test_store.py`：`usage_credit.source` 迁移、按 source 查询、旧数据保留。
   - `tests/test_html.py`：`agents["trae-cn"] == "credits"`、payload source、选择过滤、无跨源合计、Trae 弱 est 仍存在。
   - `tests/test_cli_trae.py`：`sync` 不带 `--remote` 不联网；`html` 默认刷新；`html --offline` 不联网；`html --source qoder` 不触发 Trae；`html` 刷新失败回退缓存；`--strict-refresh` 非 0；`--stateless` 不联网；`--max-age` 复用策略。
2. 实现存储迁移和查询。
3. 实现 API client + sync。
4. 实现 CLI 参数与错误处理。
5. 实现 payload/UI 分类和过滤。
6. 更新文档和回归测试。
7. 跑全量测试。

### 10.3 测试矩阵

| 测试 | 断言 |
|---|---|
| 登录凭证头 | `Authorization: Cloud-IDE-JWT <token>`；token 不出现在 stdout/stderr/DB/HTML；`storage.json` 0644 等宽权限由 `doctor` 告警 |
| 请求体 | Unix 秒；`usage_type:[7]`；`page_size:20`；30 天分块 |
| 分页 | `total` 到达即停；空页停止；短页未达 `total` 继续翻页；超过 100 页报错/二分 |
| 幂等 | 同一 session 二次同步仍只有一行，credits 被更新而非累加 |
| 缺字段 | 缺 `session_id`/`usage_time` 跳过；缺 credits 跳过并计数 |
| 凭证错误 | 401/403 提示重新登录，无 token 泄露；旧缓存保留 |
| 网络错误 | 失败不写半批；`source_state` 记录脱敏错误 |
| sync 默认离线 | `usage sync --source trae-cn` 不带 `--remote` 时 transport 抛异常也不会被调用 |
| HTML 默认刷新 | `usage html` 在 Trae 范围内会调用 transport；成功后可读到新 credits |
| HTML 离线 | `usage html --offline` 不调用 transport；coverage `refresh_mode=offline` |
| HTML 范围排除 | `usage html --source qoder` 不触发 Trae transport |
| HTML 刷新失败 | 默认继续渲染缓存；coverage `refresh_error`/`stale=true`；stderr 有警告 |
| strict-refresh | `usage html --strict-refresh` 刷新失败返回非 0，但仍生成回退报告 |
| stateless | `usage html --stateless` 跳过远程；Trae credits 显示“需要 SQLite 缓存” |
| max-age | `--max-age 300` 且 `last_sync_at` 在 300 秒内、上次窗口覆盖本次范围时不调用 transport；超时/范围更大则刷新 |
| 新鲜度状态 | payload 包含 `last_sync_at`、`refresh_mode`、`refresh_error`、`stale` |
| 分类 | `payload["agents"]["trae-cn"] == "credits"` |
| 选择 | 只选 Trae 时不出现 Qoder 行；只选 Qoder 时不出现 Trae 行 |
| 多选 | Qoder+Trae 出现两个 KPI 块；无跨源总 credits；图表分组 |
| 影子 | Trae 弱 est 仍显示；Qoder shadow 只在选中 Qoder 时显示 |
| 迁移 | 旧 `usage_credit` 无 source -> 自动补 `qoder`；数据不丢 |

### 10.4 命令

```bash
python3 -m unittest discover -s tests -t .
python3 -m compileall -q src
```

（项目当前无 pytest/ruff 依赖；以 unittest 为准。实现时如需额外静态检查，优先用 stdlib `py_compile`，不新增依赖。）

### 10.5 人工验收（实现完成后）

1. `usage sync --source trae-cn --remote --days 1`，确认：
   - 网络只发一次窗口请求；
   - 输出会话数/credits；
   - 登录凭证未出现在任何输出/DB/HTML。
2. 打开 Trae CN 控制台，对照最近一天 credits 是否一致。
3. `usage html --source trae-cn --open`，确认：
   - 命令输出包含 `trae-cn.credits: refreshed ...`；
   - Trae 以 Credits 为主；
   - token 弱估算在影子区；
   - 没有跨源合计；
   - 报告显示最近同步时间。
4. `usage html --source trae-cn --offline --open`，确认：
   - 不发起网络请求；
   - 显示“离线缓存 · last_sync_at”；
   - 数据与上一步一致。
5. `usage html --source qoder --open`，确认不触发 Trae 网络请求、Qoder 报告无回归。
6. `usage sync --source trae-cn --remote`（30 天）后复跑，确认幂等、无重复行。
7. 模拟刷新失败（断网/临时改错凭证）后 `usage html --open`，确认回退缓存、显示警告；`--strict-refresh` 返回非 0。

### 10.6 下游影响（Perch）

Perch 的 `render_usage_report` 会调用 `usage html --output <cache>/usage-report.html`。升级后该命令默认会触发 Trae credits 刷新：

- 如果 Perch 希望保持“打开时才刷新”，当前默认即可；
- 如果 Perch 不希望自动联网，需要在 Perch 侧传 `--offline` 或 `--max-age N`；
- Perch 的调用参数变更属于 Perch 项目，不在本分支实施；实现时会在交付说明里注明。

---

## 11. 文档更新

| 文件 | 更新 |
|---|---|
| `README.md` | 政策改为“默认离线；Trae credits 在 `sync --remote` 或 `usage html` 刷新时联网”；来源表 Trae 从“弱估算”改为“Credits + token 弱估算”；新增 `--offline`/`--strict-refresh`/静态快照说明 |
| `docs/design-docs/source-designs/TRAE-CN-DESIGN.md` | 顶部加“历史文档”说明：credits 轴由本文取代；hook 弱估算设计继续有效 |
| `docs/references/PROBE.md` | §6.9：客户端 usage 接口证据、临时 token 形态；§6.10：临时 token 401 → storage.json tc v5 凭证来源修正 |
| `ARCHITECTURE.md` | §7.4 更新：Trae 归入 credits；多 source credits 分列；不跨源合计 |
| `docs/design-docs/source-designs/TRAE-CN-CREDITS-DESIGN.md` | 本文；审核通过后作为实现依据 |

README 政策建议文案：

> 默认离线。Trae CN credits 在两种前台场景联网：用户执行 `usage sync --source trae-cn --remote`，或执行 `usage html` 且 Trae 在报告范围内（渲染前刷新一次）。两种场景都从本机读取 Trae CN 登录凭证（默认 `storage.json` 的 tc v5 blob，本地解密），调用 Trae CN 客户端同源的用量接口，只把会话级 credits/模型/时间写入本地库；不保存 prompt/正文，不写凭证，不后台轮询。`usage html --offline`、`report`、`credits`、`doctor` 默认不联网。HTML 是生成时快照，需重新运行 `usage html` 才会更新。

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 接口未公开、随时变更 | 同步失败 | 失败关闭、保留缓存、错误可见；不编造数据 |
| 登录凭证过期/未被接受 | 401 | 提示重新登录；不自动刷新；不读 Keychain |
| 请求过多/风控 | 被限流 | 前台触发、仅报告窗口、20/页、300ms 间隔、页数上限、无并发；`--offline` / `--max-age` 可减少请求 |
| `usage html` 每次联网 | 延迟、重复请求 | 默认只拉报告窗口；`--max-age` 可设新鲜度复用；`--offline` 完全跳过；Perch/脚本可显式传 `--offline` 或 `--max-age` |
| 凭证泄露 | 严重 | 仅刷新进程内存读取；不落盘/日志/HTML；错误脱敏；文件 0600 警告 |
| 保存用户内容 | 隐私 | 丢弃 `user_input_preview`，不存 prompt/工具参数/响应体 |
| 跨厂商 credits 相加 | 误导 | KPI/图表/Top/表合计全部按 source 分列 |
| 会话跨天 | 日归属偏差 | 文案注明“会话归属日”；不假装逐请求 |
| 项目维度缺失 | Trae Top 项目全部为 `-` | 当前 hook/credits session 零重叠；文案明确“无法关联”，后续另立探针 |
| 缓存过期 | 报告看起来旧 | `usage html` 默认刷新；`--offline`/刷新失败且已有缓存时显示 last_sync_at 与“缓存数据”徽标；无缓存时明确显示“暂无缓存数据”；`stale=true` |
| 重复计数 | 数据虚高 | `request_id=trae-cn:<session_id>` upsert；同批去重 |
| feat/cline 未合并 | 分支冲突 | 先合并 feat/cline（需同意）或从 feat/cline 切分支 |

---

## 13. 决策清单

| 编号 | 决策 | 结论 |
|---|---|---|
| **D1** | Trae credits 联网路径 | **已批准 A1**：`sync --remote` + `usage html` 前台刷新；自动读本机登录凭证 |
| **D2** | 凭证来源 | **已批准**：默认读 `storage.json` 的 `iCubeAuthInfo://icube.cloudide`（tc v5，本地解密）；临时 token 已因 401 弃用；支持 `--jwt-file` / `TRAE_CN_JWT` 覆盖 |
| **D3** | Qoder + Trae credits 是否合计？ | **已批准推荐项**：不合计，按 Agent 分列；图表分组，Top 分组，表合计分列 |
| **D4** | token 影子来源 | **已批准推荐项**：保留现有 hook 弱估算；首版不用 API token 字段 |
| **D5** | v1 是否做 Trae 余额/配额？ | **已批准推荐项**：不做，只做已消费 credits |
| **D6** | 分支基线 | **已批准 B2**：从 `feat/cline` 切 `feat/trae-cn-credits`，不先合并 main |
| **D7** | 默认同步窗口 | **已批准推荐项**：30 天；首次历史用 `--days 365` / `--full` |
| **D8** | Trae 项目维度 | **已批准推荐项**：hook session→project 尽力映射；未命中显示 `-`；不做额外本地探针 |
| **D9** | `usage html` 刷新策略 | **已批准推荐项**：默认每次刷新；`--offline` 跳过；`--max-age N` 复用；`--strict-refresh` 失败非 0 |

实现状态（2026-11-15）：D1–D9 全部落地；凭证默认来源已修正为 `storage.json` 的 tc v5 登录凭证（临时 token 401），30 天真实同步 200 会话 / 829.23 credits；`python3 -m unittest discover -s tests -t .` 通过 159 个测试。评审修订已补齐：无缓存刷新失败文案、汇总/KPI/状态条措辞统一、结束时间不取未来、短页未达 `total` 继续翻页、移除不可达 estimate Agent 分支、CLI 错误统一脱敏（含 `sync --remote`）、`storage.json` group/world 可读告警、项目维度明确为当前不可关联。版本升至 0.6.0。分支 `feat/trae-cn-credits`，按 AGENTS.md 保留提交记录并推送；合并到 `main` 前仍需用户明确同意。

---

## 14. 附：首版不做但可后续扩展

- Trae 余额/套餐配额（`ide_user_ent_usage` / 权益包）。
- API token 字段作为独立的 `trae-cn.api-est` 影子轨。
- 项目维度的完整映射（本地会话元数据只读探针）。
- dashboard 手工导出导入（零网络备用路径）。
- SQLCipher 解密（维持不做）。
- 多账号/多凭证。