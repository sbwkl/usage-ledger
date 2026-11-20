#!/usr/bin/env python3
"""Antigravity 采集探针（只读）。

回答两个问题，供 CHG 评审使用：

1. 解析规则对不对 —— `brain/<conv>/.system_generated/logs/transcript_full.jsonl`
   里哪些 step 带 token，`input_tokens` 与 `cache_read_tokens` 是否互斥，
   `chunks/` 下的同名文件是不是重复数据。
2. 去重规则够不够 —— 两个 app data dir 之间会话是否重叠，同一会话内
   `step_index` 是否唯一，合并后是否会产生重复记录。

只读文件，不写任何数据，不联网。用法：

    python3 scripts/probe_antigravity.py [HOME]

HOME 默认取 `os.path.expanduser("~")`，便于指向 fixture 目录做回归。
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

# IDE / hub 与独立 agy CLI 的 app data dir。两者互不复用，见 CHG 的 §2。
DEFAULT_ROOTS = (
    ("ide", os.path.join(".gemini", "antigravity")),
    ("cli", os.path.join(".gemini", "antigravity-cli")),
)

TRANSCRIPT = "transcript_full.jsonl"

# 采集器实际会读的文件集合：会话 ID -> 绝对路径。
Conversation = tuple[str, str]          # (agent, conversation_id)
Step = dict


def conversation_id(path: str) -> str:
    # .../brain/<convId>/.system_generated/logs/transcript_full.jsonl
    return os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(path))))


def transcript_files(home: str, root: str) -> list[str]:
    """返回 root 下所有 transcript_full.jsonl（chunks/ 镜像单独校验，不进主集合）。"""
    found = []
    for dirpath, _dirnames, filenames in os.walk(os.path.join(home, root)):
        if TRANSCRIPT in filenames:
            found.append(os.path.join(dirpath, TRANSCRIPT))
    return sorted(found)


def read_steps(path: str) -> tuple[list[Step], list[tuple[int, str]]]:
    """读一个 transcript，返回 (step 列表, 无法解析的片段)。

    不能按行 json.loads：实测 129 个文件里有 4 个文件在写入时留下了游离片段
    （形如独立一行的 `}]}`），按行解析会连带丢掉后面的合法 step。这里用
    `JSONDecoder.raw_decode` 流式扫描，失败时从下一个 `{` 重新同步。
    """
    with open(path, "r", errors="replace") as fh:
        text = fh.read()

    steps: list[Step] = []
    bad: list[tuple[int, str]] = []
    decoder = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n:
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            nl = text.find("\n", i)
            frag = text[i:nl if nl >= 0 else n]
            bad.append((text.count("\n", 0, i) + 1, frag[:80]))
            nxt = text.find("{", i + 1)
            if nxt < 0:
                break
            i = nxt
            continue
        steps.append(obj)
        i = end
    return steps, bad


def has_tokens(step: Step) -> bool:
    return "input_tokens" in step or "output_tokens" in step


def tokens(step: Step) -> tuple[int, int, int]:
    return (step.get("input_tokens") or 0,
            step.get("output_tokens") or 0,
            step.get("cache_read_tokens") or 0)


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def load(home: str) -> tuple[dict[str, list[str]], dict[str, list[Step]]]:
    """扫两个 root，返回 (agent -> 文件列表, agent -> 全部 step)。

    每个 step 会带上探针用的 `_conv`，仅为归因，采集器实现里不需要。
    """
    per_root: dict[str, list[str]] = {}
    all_steps: dict[str, list[Step]] = {}
    for agent, root in DEFAULT_ROOTS:
        files = transcript_files(home, root)
        per_root[agent] = files
        steps: list[Step] = []
        for path in files:
            got, _bad = read_steps(path)
            for step in got:
                step["_conv"] = conversation_id(path)
                step["_file"] = path
            steps.extend(got)
        all_steps[agent] = steps
    return per_root, all_steps


def main(argv: list[str]) -> int:
    home = os.path.expanduser(argv[1] if len(argv) > 1 else "~")
    print("HOME = %s" % home)
    per_root, all_steps = load(home)

    # ---------- 1. 文件与 step 盘点 ----------
    section("1. 文件与 step 盘点")
    type_counter: Counter = Counter()
    source_counter: Counter = Counter()
    parse_errors: list[tuple[str, int, str]] = []
    for agent, _root in DEFAULT_ROOTS:
        steps = all_steps[agent]
        print("%-4s %-30s 文件 %3d  step %5d"
              % (agent, dict(DEFAULT_ROOTS)[agent], len(per_root[agent]), len(steps)))
        for step in steps:
            type_counter[step.get("type")] += 1
            source_counter[step.get("source")] += 1
        for path in per_root[agent]:
            _steps, bad = read_steps(path)
            parse_errors.extend((path, ln, frag) for ln, frag in bad)

    print("step type 分布：%s" % dict(type_counter.most_common(8)))
    print("step source 分布：%s" % dict(source_counter.most_common(8)))
    print("JSON 解析失败（游离片段）：%d 行" % len(parse_errors))
    for path, ln, frag in parse_errors[:5]:
        print("   %s:%d  %s" % (os.path.basename(os.path.dirname(os.path.dirname(
            os.path.dirname(path))))[:8], ln, frag))

    # 重同步可能把片段里的字符串误判成对象，采集器必须用形状校验兜底
    malformed = []
    for agent, steps in all_steps.items():
        for step in steps:
            if not isinstance(step, dict) or not isinstance(step.get("step_index"), int):
                malformed.append((agent, repr(step)[:80]))
    print("形状异常（非 dict 或 step_index 非整数）：%d" % len(malformed))
    for agent, frag in malformed[:5]:
        print("   %s %s" % (agent, frag))

    # ---------- 2. token 字段语义 ----------
    section("2. token 字段语义（input_tokens 是否含 cache_read_tokens）")
    tok_steps = [s for steps in all_steps.values() for s in steps if has_tokens(s)]
    print("带 token 字段的 step：%d" % len(tok_steps))

    cache_gt_input = 0
    input_ge_cache = 0
    zero_triples = 0
    ctx_series: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
    for agent, steps in all_steps.items():
        for step in steps:
            if not has_tokens(step):
                continue
            i, _o, c = tokens(step)
            if i == 0 and c == 0:
                zero_triples += 1
            if c > i:
                cache_gt_input += 1
            else:
                input_ge_cache += 1
            ctx_series[(agent, step["_conv"])].append(
                (step.get("created_at") or "?", i + c))

    print("cache_read > input 的 step：%d  → 证明 input_tokens 不含 cache"
          % cache_gt_input)
    print("input >= cache_read 的 step：%d" % input_ge_cache)
    print("input 与 cache_read 同时为 0：%d" % zero_triples)

    regressions = []
    for _key, series in ctx_series.items():
        series.sort(key=lambda p: p[0])
        for (t0, v0), (t1, v1) in zip(series, series[1:]):
            if v1 + 2000 < v0:      # 容忍上下文压缩带来的小幅回落
                regressions.append((_key[1][:8], t0, v0, t1, v1))
    print("上下文长度明显回落的相邻 step：%d（压缩 / 新话题属正常）" % len(regressions))
    for conv, t0, v0, t1, v1 in regressions[:5]:
        print("   %s  %s(%d) → %s(%d)" % (conv, t0, v0, t1, v1))

    # ---------- 3. 去重规则 ----------
    section("3. 去重规则校验")

    ids = {agent: {conversation_id(p) for p in paths}
           for agent, paths in per_root.items()}
    overlap = ids["ide"] & ids["cli"]
    print("3.1 两个 app data dir 的会话 ID 重叠：%d %s"
          % (len(overlap), sorted(o[:8] for o in overlap) or ""))

    dup_step_index = []
    for agent, files in per_root.items():
        for path in files:
            steps, _ = read_steps(path)
            counts = Counter(s.get("step_index") for s in steps)
            for idx, n in counts.items():
                if n > 1:
                    dup_step_index.append((path, idx, n))
    print("3.2 同一文件内 step_index 重复：%d 处" % len(dup_step_index))
    for path, idx, n in dup_step_index[:5]:
        print("   %s step_index=%s ×%d" % (path, idx, n))

    print("3.3 chunks/ 镜像对比（一致则采集只读 transcript_full.jsonl）")
    identical = differs = missing = 0
    for agent, files in per_root.items():
        for path in files:
            chunks_dir = os.path.join(os.path.dirname(path), "chunks", "transcript_full")
            if not os.path.isdir(chunks_dir):
                missing += 1
                continue
            main_idx = [s.get("step_index") for s in read_steps(path)[0]]
            chunk_idx: list = []
            for name in sorted(os.listdir(chunks_dir)):
                if name.endswith(".jsonl"):
                    chunk_idx.extend(s.get("step_index")
                                     for s in read_steps(os.path.join(chunks_dir, name))[0])
            if sorted(main_idx) == sorted(chunk_idx):
                identical += 1
            else:
                differs += 1
                if differs <= 3:
                    print("   不一致：%s  main=%d chunk=%d"
                          % (conversation_id(path)[:8], len(main_idx), len(chunk_idx)))
    print("   一致 %d / 不一致 %d / 无 chunks 目录 %d" % (identical, differs, missing))

    # 采集器实际使用的 key：(app_data_dir, conv, step_index)
    merged: dict[tuple[str, str, object], Step] = {}
    for agent, steps in all_steps.items():
        for step in steps:
            if not has_tokens(step):
                continue
            merged[(agent, step["_conv"], step.get("step_index"))] = step
    print("3.4 按 (app_data_dir, conv, step_index) 合并后：%d 条（原始带 token %d 条）"
          % (len(merged), len(tok_steps)))

    # ---------- 4. 合并后的用量视图 ----------
    section("4. 合并后的用量（模拟 usage-ledger 的一次采集）")
    by_agent_model: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    by_day: Counter = Counter()
    days: list[str] = []
    for (agent, _conv, _idx), step in sorted(merged.items()):
        i, o, c = tokens(step)
        model = step.get("model") or "unknown"
        agg = by_agent_model[(agent, model)]
        agg[0] += i
        agg[1] += o
        agg[2] += c
        day = (step.get("created_at") or "")[:10]
        by_day[day] += 1
        days.append(day)

    print("%-5s %-26s %8s %8s %9s" % ("agent", "model", "input", "output", "cache_read"))
    for (agent, model), (i, o, c) in sorted(by_agent_model.items()):
        print("%-5s %-26s %8d %8d %9d" % (agent, model, i, o, c))
    print("\n合计 input=%d output=%d cache_read=%d"
          % (sum(v[0] for v in by_agent_model.values()),
             sum(v[1] for v in by_agent_model.values()),
             sum(v[2] for v in by_agent_model.values())))
    print("覆盖日期：%s ~ %s（%d 天）"
          % (min(days) if days else "-", max(days) if days else "-", len(by_day)))
    for day in sorted(by_day):
        print("   %s  %d 条" % (day, by_day[day]))

    # ---------- 5. 缺口 ----------
    section("5. 缺口与风险")
    total_model = sum(1 for steps in all_steps.values() for s in steps
                      if s.get("source") == "MODEL")
    no_token = sum(1 for steps in all_steps.values() for s in steps
                   if s.get("source") == "MODEL" and not has_tokens(s))
    print("MODEL step 共 %d，其中 %d 条无 token 字段（%.1f%%）"
          % (total_model, no_token,
             100.0 * no_token / total_model if total_model else 0.0))
    print("→ 采集器必须静默跳过无 token 的 MODEL step，不能记为错误。")
    print("带 token 的会话数：%d" % len(ctx_series))
    print("→ 历史会话没有 token，报表在记账上线前为空属预期。")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))