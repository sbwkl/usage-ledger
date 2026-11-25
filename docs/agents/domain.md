# Domain 文档

工程类 skill 在探索本仓库时应如何消费领域文档。

## 探索前先读

- 仓库根目录的 **`GLOSSARY.md`**。
- **`docs/design-docs/adr/`**：阅读与即将改动区域相关的 ADR。本仓库 ADR 位于 design-docs 之下，不在 `docs/adr/`。

这些文件尚不存在时**静默继续**：不要提示缺失，也不要建议预先创建。`/domain-modeling` skill（经 `/grill-with-docs` 与 `/improve-codebase-architecture` 进入）会在术语或决策实际敲定时惰性创建它们。

## 文件结构

单上下文仓库：

```
/
├── GLOSSARY.md
├── docs/design-docs/adr/
│   ├── ADR-0001-source-of-truth-db-as-archive.md
│   └── ADR-0002-pull-collection-no-daemon.md
└── src/
```

## 使用 glossary 的词汇

当输出涉及领域概念（issue 标题、重构提案、假设、测试名）时，使用 `GLOSSARY.md` 定义的术语，不要漂移到 glossary 明确避免的同义词。

需要的概念还不在 glossary 里时，这是一个信号：要么你在发明项目不用的语言（重新考虑），要么存在真实缺口（记下来交给 `/domain-modeling`）。

## 标记 ADR 冲突

输出与现有 ADR 矛盾时，显式指出而不是静默覆盖：

> _与 ADR-0001（DB 作为归档层）矛盾，但值得重开讨论，因为……_
