# CHG-0025 Qoder 模型显示名分层解析（i18n + 计费学习 + 静态兜底）

| 项 | 内容 |
|---|---|
| ID | CHG-0025 |
| 状态 | 已验证 |
| Owner | wayne |
| 所属模块 / 入口 | `src/usage_ledger/qoder_models.py`、`src/usage_ledger/collectors.py`、`src/usage_ledger/aggregation.py`、`src/usage_ledger/cli.py` |
| 关联 | [usage-ledger 产品规格](../../product-specs/usage-ledger.md)（无 AC 变更） |

## 1. 摘要

Qoder 模型以界面显示名展示，取代手工一一映射。三层解析覆盖 `qmodel_latest_preview -> Qwen4-Max-Preview` 等服务器下发键，内置模型随 Qoder 升级自动同步。无数据口径变化。

## 2. 变更理由与证据

- `usage html` 报表把 Qoder 模型显示为内部键 `qmodel_latest_preview`，而非界面上的 `Qwen4-Max-Preview`。
- 根因：`QODER_MODEL_LABELS` 是手工维护的一一映射，未收录该键，`qoder_model_label` 对未收录键原样返回；手工映射无法随 Qoder 新增模型扩展。
- 证据（本机只读）：计费缓存 `Cache/Cache_Data/*` 的 `model_category` 为 `Qwen4-Max-Preview`，其无歧义会话的 `chat_sessions.model` 为 `qmodel_latest_preview`。

## 3. 改动范围

分层解析，优先级 高 → 低：

1. **i18n（最高）**：读 Qoder 自带 dynamic-text（App 安装目录 `dynamic-text/qoder.json` + 用户目录 `qoder.v1.json`）的 `model.<key>.label`。这是 Qoder 自己的事实源，随版本升级自动更新；优先级最高，避免被启发式学习覆盖。
2. **learned**：从计费缓存 `model_category` 学习，**仅采用无歧义会话**（会话全部计费条目只有一个 `model_category` 才采纳；切换过模型的会话整段跳过），覆盖 i18n 未收录的服务器下发键。学习结果持久化到 `meta["qoder_model_labels"]`，作为缓存被驱逐后的兜底。
3. **seed（最低）**：静态兜底，仅在 i18n / learned 都取不到时使用（离线、CI、旧版 IDE 键如 `gm51model`）。

其它改动：

- `qoder_models.py`：`load_i18n_labels*`、`resolve_labels`、`qoder_model_label(model, labels=None)`。
- `collectors.py`：`learn_qoder_model_labels` / `learn_billing_labels`（无歧义会话 + 多数票，best-effort 解析 HTTP 缓存）；`scan_qoder_credit_sources` 附带 `result.model_labels`。
- `models.py`：`SourceResult.model_labels`。
- `aggregation.py`：`aggregate` / `match` / `_dim_value` 支持 `labels`。
- `cli.py`：`sync` 学习并持久化；`_load_records` 在**自动同步之后**构建 labels 再参与 `match`/`aggregate`（首次出现的新模型本次即生效）；有库路径**始终合并实时学习**（缓存变化无需等同步即可显示）；`report` / `html` / `est` / `live` / `top` 及 html 的 credits 区块使用显示名。
- 配置解耦：`USAGE_LEDGER_SOURCE_HOME` 只改数据目录，不再禁用 App 安装目录的 i18n；测试密闭改用独立开关 `USAGE_LEDGER_QODER_I18N` / `USAGE_LEDGER_QODER_CACHE`。
- 测试：`test_qoder_models.py`（i18n 解析、三层优先级、路径解耦、env 覆盖）；`test_collectors.py`（无歧义会话学习、切换模型跳过、缺源、损坏文件）；`test_cli.py`（报表显示名、显示名过滤、首次自动同步即生效、缓存变化免同步实时学习）。

**明确不适用的面**：`usage credits` 命令按 `day + source` 汇总，无模型列，不涉及显示名；本能力作用于 `report` / `html` / `est` / `live` / `top` 的模型维度，以及 HTML 报表内的 credits 区块。

## 4. 验证

- 命令：`python3 -m unittest discover -s tests -t .`、`uv run --with coverage ...` + `python3 scripts/check_coverage.py coverage.json`、`python3 scripts/check_test_policy.py`、`python3 scripts/check_ac_map.py`、`python3 -m compileall -q src tests scripts`。
- 环境：macOS（Apple Silicon）、Python 3.12；基线 main `f0c40d5`。
- 全量套件：374 tests / 0 failures / 0 errors / 0 skips；快速套件 2.21s（预算 5s）。
- 覆盖率：TOTAL 92.5%，collectors 92.4% / cli 93.3% / scheduler 98.2% / store 96.7%，全部达标。
- AC map：REQ-0001 49 criteria / 154 mapped identifiers（无 AC 变更）。
- 真实数据端到端（只读）：`load_i18n_labels` 取到 19 条；`learn_qoder_model_labels` 学到 `{dfmodel: DeepSeek-Flash, qmodel_latest_preview: Qwen4-Max-Preview}`；`usage html --stateless` 输出含 `Qwen4-Max-Preview`、无原始键 `qmodel_latest_preview`。

### 已知性能边界

实时学习需遍历 Qoder 计费缓存。本机实测：871 文件 / 41.5 MB / 约 276ms（首次）。已加**进程内缓存**（键 = 缓存目录文件数 + mtime 之和 + size 之和 + 活动库 mtime），同一命令内重复构建 labels 不再重复扫描；缓存或活动库变化即失效。跨进程每次命令仍扫描一次；若后续缓存显著增长，可再加磁盘级缓存（按签名失效）。

## 5. 回滚

还原上述文件改动即可；学习结果存于 `meta["qoder_model_labels"]`，回滚后不再读取；无数据迁移、无接口变化。