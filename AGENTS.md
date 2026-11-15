# AGENTS.md

本文件是 usage-ledger 的项目级补充约定；工作区根目录的 `../AGENTS.md` 仍然适用。本项目只做补充；冲突时以工作区根目录约定为准。

## 文档事实源

- 功能卡：`docs/requirements/`（`REQ-0001-usage-ledger.md` 产品功能、`REQ-0002-testing.md` 测试体系；含当前需求、EARS 验收、风险、变更索引）。
- 变更：`docs/changes/CHG-XXXX-*.md`。新变更先建 CHG，登记到对应 REQ 的变更索引，再写代码。
- 决策：`docs/adr/ADR-XXXX-*.md`。只有已做出、难回退的架构 / 技术选型才建。
- RFC：`docs/rfcs/`。跨团队、不可逆、技术不确定、影响公共接口 / 数据模型 / 安全隐私时建。
- 设计文档与阅读顺序：`docs/README.md`。`docs/DESIGN.md` 是历史设计稿，`docs/ARCHITECTURE.md` 是 As-Built；不要拿 DESIGN 里的未实现项当当前 AC。
- ID 按类型递增、不复用。当前下一批：`REQ-0003`、`CHG-0003`、`ADR-0003`。

## 开发与验证

- 快速测试：`python3 -m unittest discover -s tests -t .`；需要 Python ≥3.11 与 Node 24（HTML/JS 行为测试）。Node 缺失时 `check_test_policy.py` 会因未授权 skip 失败，不要把它当作“环境问题”忽略。
- 覆盖率：`uv run --with coverage python -m coverage run --branch --source=src/usage_ledger -m unittest discover -s tests -t .`，再 `uv run --with coverage python -m coverage json -o coverage.json` 与 `python3 scripts/check_coverage.py coverage.json`。
- 测试门禁：`python3 scripts/check_test_policy.py`（skip / expectedFailure 白名单、5 秒预算）与 `python3 scripts/check_ac_map.py`（REQ-0001 §5 AC→测试映射）。
- CI：`.github/workflows/test.yml` 在 PR、`main`、`sit` 上跑 Python 3.11–3.14 + Node 24；分支保护的 required checks 需要仓库管理员在 GitHub 上启用。
- 直接运行：`PYTHONPATH=src python3 -m usage_ledger <cmd>`。
- 本地重装：`uv tool install --force --no-cache .`。
- 分支：从最新 `main` 切 `feat/<特性名>`；集成走 `sit`；合并 `main` 前必须获得用户同意。
- 新特性先满足 DoR（REQ/CHG 已更新、AC delta 覆盖正常 / 异常 / 边界、依赖已链接），再实现。
- 完成后运行全量测试，更新 CHG 状态与证据；没有部署 / 监控证据不得标“已发布”。
- CHG 标“已验证”前，证据必须写全：精确命令、环境（OS / Python / Node / commit）、通过/失败/跳过数、覆盖率与基线变化、日志或 artifact 链接。缺任一项就保持“开发中”，并列出待补项。
- 提交信息引用 CHG ID；PR（如有）标题 / 描述引用 CHG 和 REQ。

## 边界

- 不要顺手修复 `docs/ARCHITECTURE.md` §11 的 P0 / P1 / P2 问题；它们需要独立 CHG。
- 不要逆向厂商私有 API、解密 Trae CN SQLCipher 库，或把估算值 / credits / token 真值相加。
- 默认离线；只有 Trae CN credits 的两条显式前台刷新路径可以联网。
