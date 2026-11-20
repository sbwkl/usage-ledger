"""腾讯 CodeBuddy CN 采集测试用的目录构造器。

CodeBuddy 把每次模型调用的 token 写进两处镜像日志：

<home>/Library/Application Support/CodeBuddy CN/logs/<启动时间>/window<N>/exthost/
    Tencent-Cloud.coding-copilot/腾讯云代码助手.log          # ISO 时间戳
<home>/Library/Application Support/CodeBuddyExtension/Logs/CodeBuddyIDE/
    <YYYY-MM-DD>/<workspace>__<hash>.log                      # 方括号时间戳

项目维度来自 genie-history/<base64url(cwd)>/current.json 的 conversationId → cwd。
"""

import base64
import json
import os

CN_LOG_REL = os.path.join(
    "Library", "Application Support", "CodeBuddy CN", "logs",
    "20261120T151025", "window7", "exthost",
    "Tencent-Cloud.coding-copilot")
IDE_LOG_REL = os.path.join(
    "Library", "Application Support", "CodeBuddyExtension", "Logs",
    "CodeBuddyIDE", "2026-11-20")
GENIE_REL = os.path.join(
    "Library", "Application Support", "CodeBuddy CN", "User",
    "globalStorage", "tencent-cloud.coding-copilot", "genie-history")

DEFAULT_TRACE = "a8e5acced6f3fc473ada2289b956dcaa"
DEFAULT_CONVERSATION = "2fc5374e3cfc49958bae3fc026b30d98"
DEFAULT_WORKSPACE = "/Users/wayne/workspace/playground"
DEFAULT_MODEL_ID = "hy4flash-free"


def usage(input_tokens=None, output_tokens=20, cache_tokens=400, cache_miss=600,
          credit=0, thinking_tokens=0, cache_write=0):
    """构造 usage JSON；inputTokens 默认含 cacheTokens（实测语义）。"""
    if input_tokens is None:
        input_tokens = cache_tokens + cache_miss
    total = input_tokens + output_tokens
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total,
        "cacheTokens": cache_tokens,
        "cachedWriteTokens": cache_write,
        "cachedMissTokens": cache_miss,
        "lastTokens": total,
        "credit": credit,
        "thinkingTokens": thinking_tokens,
    }


def metric_line(trace, step, usage_value, style="iso", timestamp=None):
    payload = json.dumps(usage_value, separators=(",", ":"))
    if style == "iso":
        prefix = timestamp or "2026-11-20 15:28:08.671"
        head = "%s [info] [AgentReporter] [%s] " % (prefix, trace)
    else:
        prefix = timestamp or "[11/20/2026, 3:28:08 PM.672]"
        head = "%s [Info] [AgentReporter] [%s]  " % (prefix, trace)
    return ("%sStep execution metrics: step=%s, duration=3997ms, usage=%s"
            % (head, step, payload))


def summary_line(trace, step, style="iso"):
    if style == "iso":
        head = "2026-11-20 15:28:08.671 [info] [AgentReporter] [%s] " % trace
    else:
        head = "[11/20/2026, 3:28:08 PM.672] [Info] [AgentReporter] [%s]  " % trace
    return "%sStep execution metrics: step=%s, duration=3997ms" % (head, step)


def start_line(trace, conversation=DEFAULT_CONVERSATION, style="iso"):
    if style == "iso":
        head = "2026-11-20 15:28:04.660 [info] [AgentReporter] [%s] " % trace
    else:
        head = "[11/20/2026, 3:28:04 PM.660] [Info] [AgentReporter] [%s]  " % trace
    return ("%sonAgentStart: userInput=hi agent=craft mode=craft "
            "conversationId=%s requestId=409ea55db7d34484a766ec44eedc5a87"
            % (head, conversation))


def model_line(trace, model_id=DEFAULT_MODEL_ID, name="Hy4 flash", style="iso"):
    if style == "iso":
        head = "2026-11-20 15:28:04.652 [info] [CraftInvokableAgent] [%s] " % trace
    else:
        head = "[11/20/2026, 3:28:04 PM.652] [Info] [CraftInvokableAgent] [%s] " % trace
    return "%sPreparing model: %s (%s)" % (head, name, model_id)


def write_log(home, lines, root="cn", name="腾讯云代码助手.log"):
    directory = os.path.join(home, CN_LOG_REL if root == "cn" else IDE_LOG_REL)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")
    return path


def encoded_workspace(workspace, suffix=""):
    """厂商命名：padding 的 '=' 写成 '_'；部分无 padding 目录还追加 '__'。"""
    encoded = base64.urlsafe_b64encode(workspace.encode("utf-8")).decode("ascii")
    return encoded.replace("=", "_") + suffix


def write_genie(home, conversation=DEFAULT_CONVERSATION,
                workspace=DEFAULT_WORKSPACE, name="current.json", suffix=""):
    directory = os.path.join(home, GENIE_REL,
                             encoded_workspace(workspace, suffix))
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"conversationId": conversation,
                   "lastUpdated": "2026-11-20T07:28:03.578Z"}, fh)
    return path
