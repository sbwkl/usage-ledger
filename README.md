# usage-ledger

> macOS 上的**极轻量**跨 AI 编码工具 **token 用量台账**。零 UI、零社交、零云同步、零第三方依赖。

一个只读本地日志、只写本地 SQLite、算出"我今天每个平台每个模型花了多少 token"的离线工具。

**状态**：设计评审中（[DESIGN.md](docs/DESIGN.md) v0.4 待拍板 13 个问题）

---

## 它解决什么

你同时用 opencode / qoder / chatgpt / claude code / kilo / trae CN / workbuddy，桌面版和 CLI 都用。想知道**每个平台、每个模型**的 token 用量。

现有工具都不合适：ccusage 极简但只覆盖 18 个源；tokscale 覆盖 60 个但带 TUI 和排行榜；TokenTracker / Token Monitor 带桌面宠物和多设备同步。

**本项目的立场**：采集层用成熟做法，报表层自己做；不估算、不爬私有 API、无任何网络行为。

---

## 覆盖能力（含现实边界）

| 平台 | token 统计 | 说明 |
|---|---|---|
| Claude Code | ✅ | 含 cache read/write |
| OpenCode（CLI + 桌面） | ✅ | 与 Kilo 同构，一个 adapter |
| Kilo（CLI + 桌面） | ✅ | |
| Codex CLI | ✅ | 注意"增量 vs 累计"口径 |
| WorkBuddy | ✅ | P1，需先安装核实样本 |
| Qoder | ❌ | **订阅套餐本地 token 恒为 0**（实测 6898 条），只有 credits |
| Trae CN | ❌ | 本地只有额度键，无 token 字段 |
| ChatGPT 桌面端 | ❌ | 无本地数据，只有配额 |

> 缺口是**厂商不下发**，不是解析器写不出来。任何工具都无法凭空造出这三个平台的 token 数。工具会在 `doctor` 与报告页脚显式说明，避免"看起来没花"与"没采到"混淆。

---

## 核心设计要点

- **源是唯一事实来源**。DB 是可插拔的"归档 + 索引"层，不是权威副本
  - `NullStore`（零 DB、零定时任务）/ `SqliteStore`（归档 + 索引，默认）
  - `usage report`（读库）与 `usage --stateless report`（读源）输出必须完全一致
- **拉取式采集**，不需要常驻进程：数据由 agent 自己落盘，任何时刻读盘都拿得到已落盘的全部数据
- **实时性三档**：`usage live`（直读源，<0.3s）→ `--live` 合并 → 读库（≤1h）
- **丢失窗口 ≤ 1h**：每小时增量 + 每日全量重扫，路径显式覆盖 `archived_sessions/` `.zst` `storage/` `subagents/`
- **历史可回填**：`usage backfill` 一次性导入既有日志
- **只读、隐私**：不写源目录，不存 prompt/正文，项目路径可哈希

---

## 目录结构

```
usage-ledger/
├── docs/
│   ├── DESIGN.md       实现方案（v0.4，含 DDL / CLI / 计价 / 里程碑 / 风险）
│   ├── RESEARCH.md     调研报告（竞品横评 + 本机数据可得性实测）
│   └── DISCUSSION.md   讨论纪要（决策链 + 文档修订记录 + 待决问题）
├── src/                待实现（collectors / store / report / pricing）
├── tests/fixtures/     待补（各源脱敏 fixture）
└── scripts/
```

---

## 技术选型

Python ≥3.11，**标准库 only**（`sqlite3` / `json` / `argparse` / `zoneinfo`），零第三方包，单文件可执行；SQLite（WAL）存储；launchd 调度；`osascript` 通知。

---

## 下一步

1. 评审 [DESIGN.md](docs/DESIGN.md) v0.4（重点 §4.3 存储层、§7.3 归档判定、§10 采集模型）
2. 拍板 [DISCUSSION.md](docs/DISCUSSION.md) 的 Q1–Q13
3. 进入 M0：骨架 + CLI + schema + `doctor`
4. 尽早安装并 `usage backfill --since 2026-06-01`
