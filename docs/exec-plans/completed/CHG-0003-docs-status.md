# CHG-0003 修正 CHG-0001 / REQ-0001 的合并状态

类型：CHG
状态：已验证
Owner：wayne
所属模块/入口：`docs/`
功能卡：[REQ-0001 本地 AI 编码工具用量台账](../../product-specs/REQ-0001-usage-ledger.md)
关联：[CHG-0001 需求 / 变更文档体系对齐](CHG-0001-docs-alignment.md)、[PR #2](https://github.com/sbwkl/usage-ledger/pull/2)

## 1. 摘要

PR #2 已将 CHG-0001 合并到 `main`，但 CHG-0001 与 REQ-0001 仍写着“尚未合并 main”。本次只修正这两处过期状态与证据，不修改产品代码、需求行为或历史变更内容。

## 2. 变更理由与证据

- PR #2 状态为 `MERGED`，合并时间 `2026-11-15T11:00:43Z`，merge commit `5b5f98721339d53d59ada4db5d8650f9b6389996`。
- 过期位置：
  - CHG-0001 首部说明：“尚未合并 main”。
  - REQ-0001 §8 变更索引注：“尚未合并 main”。
- 不修正的后果：读者会误判 CHG-0001 仍未进入 `main`，与 `git log` 和 GitHub PR 事实冲突。

## 3. 行为 / AC delta

- CHG-0001 首部说明改为：已通过 PR #2 合并 `main`（`5b5f987`），状态保持“已验证”；文档变更没有部署/发布产物，不标“已发布”。
- REQ-0001 §8 同步该事实，并登记本 CHG。
- 不改变 REQ-0001 的任何产品行为或验收标准。

## 4. 影响范围与非目标

- 受影响：`docs/exec-plans/completed/CHG-0001-docs-alignment.md`、`docs/product-specs/REQ-0001-usage-ledger.md`、本文件。
- 非目标：不修改 CHG-0001 的其他内容；不新建 REQ；不改运行时代码、测试或 CI。
- 回滚：还原上述文档修改并删除本文件；无数据或配置影响。

## 5. 验证与观测

```bash
gh pr view 2 --repo sbwkl/usage-ledger --json state,mergedAt,mergeCommit
git log --oneline -1 5b5f987
grep -R "尚未合并 main" docs/exec-plans/completed/CHG-0001-docs-alignment.md \
  docs/product-specs/REQ-0001-usage-ledger.md
```

- 预期：PR #2 为 `MERGED`；`5b5f987` 存在；`grep` 无输出。
- 文档变更不触碰代码；仍运行快速套件确认工作区无意外代码改动。

## 6. 关联与证据

- issue/PR：[PR #4](https://github.com/sbwkl/usage-ledger/pull/4) 已创建（head `feat/docs-status`）；CHG-0001 的 PR #2 已合并。PR #4 基于 `main` `5b5f987`，该基线尚无 `.github/workflows/test.yml`，因此 PR 检查会等测试 workflow 进入 `main` 后才出现；本 CHG 的验证证据不依赖 CI。
- commit：`a701422`（`feat/docs-status`，基于 `main` `5b5f987`）。
- release：不涉及。

## 7. 变更记录

| 状态 | 操作人 | 证据/链接 |
|---|---|---|
| 提议 | wayne | code review 发现 CHG-0001 / REQ-0001 合并状态过期 |
| 已验证 | wayne | 2026-11-16 PR #2 与 `5b5f987` 核对通过；grep 无“尚未合并 main”；快速套件通过 |
