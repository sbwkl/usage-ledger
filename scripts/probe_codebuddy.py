#!/usr/bin/env python3
"""腾讯 CodeBuddy CN 采集探针（只读）。

回答四个问题，供 CHG-0019 评审使用：

1. 用量数据在哪 —— CodeBuddy CN 的 exthost 日志与 CodeBuddyIDE 日志是否都写入
   `Step execution metrics: ... usage={...}`，两种时间戳格式能否解析。
2. token 字段语义 —— `inputTokens` 是否含 cache read、`outputTokens` 是否逐 step 独立、
   `totalTokens` 为什么不能直接用、`thinkingTokens` 是否已包含在 output 中。
3. 去重规则 —— 两个日志目录是否镜像同一批事件，`(traceId, step)` 能否作为去重键。
4. 元数据可得性 —— traceId → conversationId / model / project（genie-history）覆盖率。

只读扫本地日志与 SQLite，不写任何文件、不联网。用法：

    python3 scripts/probe_codebuddy.py [HOME]

HOME 默认 `~`，便于指向临时 fixture 做回归。
"""

from __future__ import annotations

import base64
import glob
import json
import os
import re
import sys
from collections import Counter

METRIC_RE = re.compile(
    r"\]\s+\[AgentReporter\]\s+\[([^\]]+)\]\s+Step execution metrics:\s*"
    r"step=(\d+),\s*duration=([^,]+),\s*usage=(\{.*\})\s*$"
)
TRACE_START_RE = re.compile(
    r"\]\s+\[AgentReporter\]\s+\[([^\]]+)\]\s+onAgentStart:.*?"
    r"conversationId=([0-9a-f]+)\s+requestId=([0-9a-f]+)"
)
MODEL_RE = re.compile(
    r"\]\s+\[([^\]]+)\]\s+Preparing model:\s*(.*?)\s+\(([^)]+)\)\s*$"
)


def section(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def log_roots(home: str) -> tuple[list[str], list[str]]:
    cn = glob.glob(os.path.join(
        home, "Library", "Application Support", "CodeBuddy CN", "logs",
        "**", "Tencent-Cloud.coding-copilot", "*.log"), recursive=True)
    ide = glob.glob(os.path.join(
        home, "Library", "Application Support", "CodeBuddyExtension", "Logs",
        "CodeBuddyIDE", "**", "*.log"), recursive=True)
    return cn, ide


def parse_metric(line: str) -> tuple[str, int, dict] | None:
    m = METRIC_RE.search(line)
    if not m:
        return None
    try:
        usage = json.loads(m.group(4))
    except (TypeError, ValueError):
        return None
    return m.group(1), int(m.group(2)), usage


def parse_line_ts(line: str) -> str | None:
    iso = re.match(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}", line)
    if iso:
        return iso.group(1)
    bracket = re.match(r"^\[(\d{2})/(\d{2})/(\d{4}),", line)
    if bracket:
        return "%s-%s-%s" % (bracket.group(3), bracket.group(1), bracket.group(2))
    return None


def genie_workspaces(home: str) -> dict[str, str]:
    base = os.path.join(home, "Library", "Application Support", "CodeBuddy CN",
                        "User", "globalStorage", "tencent-cloud.coding-copilot",
                        "genie-history")
    result: dict[str, str] = {}
    for path in glob.glob(os.path.join(base, "**", "current.json"), recursive=True):
        try:
            conversation_id = json.load(open(path, encoding="utf-8"))["conversationId"]
            encoded = os.path.basename(os.path.dirname(path))
            decoded = base64.urlsafe_b64decode(
                encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        except (OSError, ValueError, KeyError, TypeError):
            continue
        result[conversation_id] = os.path.basename(decoded.rstrip("/"))
    return result


def main(argv: list[str]) -> int:
    home = os.path.expanduser(argv[1] if len(argv) > 1 else "~")
    cn, ide = log_roots(home)
    print("HOME = %s" % home)
    print("CodeBuddy CN exthost 日志：%d 个" % len(cn))
    print("CodeBuddyIDE 日志：%d 个" % len(ide))

    events: dict[tuple[str, int], dict] = {}
    per_root: Counter = Counter()
    bad_usage = 0
    summary_only = 0
    for root_name, paths in (("cn", cn), ("ide", ide)):
        for path in paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for line in lines:
                # 终端回显里也会出现同样的字面量，必须要求行首是日志时间戳
                if not (re.match(r"^\d{4}-\d{2}-\d{2} ", line)
                        or re.match(r"^\[\d{2}/\d{2}/\d{4},", line)):
                    continue
                if not re.search(r"\] \[AgentReporter\] \[[^\]]+\]\s+Step execution metrics:", line):
                    continue
                if "usage=" not in line:
                    summary_only += 1
                    continue
                parsed = parse_metric(line)
                if parsed is None:
                    bad_usage += 1
                    continue
                trace, step, usage = parsed
                per_root[root_name] += 1
                key = (trace, step)
                if key in events:
                    if events[key]["usage"] != usage:
                        events[key]["conflict"] = True
                    continue
                events[key] = {
                    "usage": usage, "day": parse_line_ts(line), "path": path,
                }

    section("1. 用量行与去重键")
    print("含 usage 的指标行：cn=%d, ide=%d；同内容的无 usage 摘要行=%d；坏 JSON=%d"
          % (per_root["cn"], per_root["ide"], summary_only, bad_usage))
    print("唯一 (traceId, step)：%d（两目录镜像，需按该键去重）" % len(events))
    print("去重后两目录同一键的 usage 不一致：%d"
          % sum(1 for e in events.values() if e.get("conflict")))

    section("2. token 字段语义")
    identity = missing = bad_total = zero = 0
    monotonic_output = True
    prev_out: dict[str, int] = {}
    sums: Counter = Counter()
    days: Counter = Counter()
    for (trace, step), event in sorted(events.items()):
        u = event["usage"]
        try:
            i = int(u["inputTokens"])
            o = int(u["outputTokens"])
            cr = int(u["cacheTokens"])
            miss = int(u["cachedMissTokens"])
            total = int(u["totalTokens"])
            think = int(u["thinkingTokens"])
            cw = int(u.get("cachedWriteTokens") or 0)
        except (KeyError, TypeError, ValueError):
            missing += 1
            continue
        identity += int(i == cr + miss)
        bad_total += int(total != i + o)
        zero += int(o == 0 and miss == 0 and cr == 0)
        monotonic_output &= o >= prev_out.get(trace, 0)
        prev_out[trace] = o
        for field, value in (("input(=cachedMissTokens)", miss), ("output", o),
                             ("cache_read", cr), ("cache_write", cw)):
            sums[field] += value
        sums["thinkingTokens（已含在 output，不另计）"] += think
        days[event["day"] or "-"] += 1
    n = len(events) - missing
    print("inputTokens == cacheTokens + cachedMissTokens：%d / %d" % (identity, n))
    print("totalTokens != inputTokens + outputTokens：%d / %d" % (bad_total, n))
    print("outputTokens 逐 step 单调不减：%s（False 表示逐 step 独立计数）" % monotonic_output)
    print("全零 usage 行：%d" % zero)
    print("按非重叠口径合计：%s" % dict(sums))
    print("覆盖日期：%s ~ %s" % (min(days) if days else "-", max(days) if days else "-"))

    section("3. 元数据覆盖率（trace → conversation / model / project）")
    starts: dict[str, str] = {}
    models: dict[str, str] = {}
    for root in cn + ide:
        try:
            with open(root, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not (re.match(r"^\d{4}-\d{2}-\d{2} ", line)
                            or re.match(r"^\[\d{2}/\d{2}/\d{4},", line)):
                        continue
                    m = TRACE_START_RE.search(line)
                    if m:
                        starts[m.group(1)] = m.group(2)
                    m = MODEL_RE.search(line)
                    if m:
                        models[m.group(1)] = m.group(3)
        except OSError:
            continue
    workspaces = genie_workspaces(home)
    traces = {trace for trace, _step in events}
    print("trace 数：%d" % len(traces))
    print("有 conversationId 的 trace：%d / %d" % (sum(t in starts for t in traces), len(traces)))
    print("有 modelId 的 trace：%d / %d" % (sum(t in models for t in traces), len(traces)))
    print("conversationId 可映射到 workspace 的 trace：%d / %d"
          % (sum(starts.get(t, "") in workspaces for t in traces), len(traces)))
    print("modelId 分布：%s" % dict(Counter(models.get(t, "-") for t in traces).most_common()))
    print("project 分布：%s" % dict(Counter(
        workspaces.get(starts.get(t, ""), "-") for t in traces).most_common()))

    section("4. 额度（credits）")
    print("usage.credit 取值：%s（全为 0，不作为 credits 真值采集）"
          % dict(Counter(str(e["usage"].get("credit")) for e in events.values()).most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
