# Issue tracker：GitHub

本仓库的 issues 与 specs 以 GitHub issues 形式存放。所有操作使用 `gh` CLI。

## 约定

- **创建 issue**：`gh issue create --title "..." --body "..."`，多行 body 用 heredoc。
- **读取 issue**：`gh issue view <number> --json number,title,body,labels,comments`。
- **列出 issues**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加 `--label` / `--state` 过滤。
- **把 issue 设为父 issue 的子 issue**：`gh issue create --parent <parent> ...`，或之后 `gh issue edit <parent> --add-sub-issue <child>`（`gh` 2.94+）。旧版 `gh`：`gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`（database id，见下方 **阻塞**）。子 issue 不可用时，在子 issue 正文顶部写 `Part of #<parent>`。
- **阻塞**：使用 GitHub 原生 issue dependencies（UI 可见的规范表示）。加边：`gh issue create --blocked-by <n>,<n> ...` 或 `gh issue edit <child> --add-blocked-by <blocker>`（`gh` 2.94+）。旧版 `gh`：`gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`，其中 `<blocker-db-id>` 是 blocker 的数字 **database id**（`gh api repos/<owner>/<repo>/issues/<n> --jq .id`，不是 `#number` 或 `node_id`）。依赖不可用时，退化为在子 issue 正文顶部写 `Blocked by: #<n>, #<n>`。所有 blocker 关闭后即视为解除阻塞。
- **统计未解除的 blocker**：`gh api repos/<owner>/<repo>/issues/<n> --jq .issue_dependencies_summary.blocked_by`（仅未关闭 blocker；0 表示可以开工）。`gh issue view <n> --json blockedBy` 也会列出已关闭 blocker，需过滤：`--jq '[.blockedBy.nodes[] | select(.state == "OPEN")] | length'`。
- **评论 issue**：`gh issue comment <number> --body "..."`
- **加 / 移除标签**：`gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **关闭**：先用 `gh issue comment <number> --body "..."` 写明原因，再 `gh issue close <number>`。对已关闭 issue，`gh issue close --comment` 会落评论且退出码 0。

`gh` 在克隆目录内运行时自动从 `git remote -v` 推断仓库。

issue 只建到用户自己的仓库；除非用户拥有 `mattpocock/skills`，否则绝不往那里建。fork 场景下 `gh` 可能默认指向上游，因此会话内第一次 `gh issue create` 前先用 `gh repo view --json nameWithOwner` 核对目标，不是用户自己的仓库时先向用户确认。

## PR 作为 triage 输入

**PR 作为请求面：否。** _（若本仓库把外部 PR 当 feature request 处理，改为 `yes`；`/triage` 读取此开关。）_

设为 `yes` 时，PR 与 issue 走相同标签与状态，用 `gh pr` 对应命令：

- **读 PR**：`gh pr view <number>`，再 `gh pr view <number> --comments`（非 TTY 时 `--comments` 只打印评论不含正文），diff 用 `gh pr diff <number>`。
- **列出待 triage 的外部 PR**：`gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`。
- **评论 / 标签 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 上 issue 与 PR 共用一个编号空间，裸 `#42` 可能是两者之一：先 `gh pr view 42`，失败再 `gh issue view 42`。

## 当 skill 说「publish to the issue tracker」

创建一个 GitHub issue。

## 当 skill 说「fetch the relevant ticket」

按 **读取 issue** 一节的方式读取。

## Wayfinding 操作

供 `/wayfinder` 使用。**map** 是一条 issue，**child** issue 作为工单。

- **Map**：一条带 `wayfinder:map` 标签的 issue，承载 Notes / Decisions-so-far / Fog 正文。`gh issue create --label wayfinder:map`。
- **Child ticket**：以 GitHub sub-issue 形式挂到 map 下的 issue（见 **把 issue 设为父 issue 的子 issue**）。子 issue 不可用时，把 child 加入 map 正文的任务列表并在 child 正文顶部写 `Part of #<map>`。标签：`wayfinder:<type>`（`research`/`prototype`/`grilling`/`task`）。被认领后工单 assign 给驱动开发的会话。
- **阻塞**：见 **约定** 一节的 **阻塞**。
- **Frontier 查询**：列出 map 的开放 children（`gh issue list --state open`，限定 map 的 sub-issues / 任务列表），剔除有未关闭 blocker（见 **统计未解除的 blocker**，或 `Blocked by` 行中有未关闭 issue）或已有 assignee 的；按 map 顺序取第一个。
- **Claim**：`gh issue edit <n> --add-assignee @me`，作为会话的第一次写操作。
- **Resolve**：`gh issue comment <n> --body "<answer>"`，然后 `gh issue close <n>`，再把上下文指针（gist + 链接）追加到 map 的 Decisions-so-far。
