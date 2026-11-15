import json
import os
import sqlite3
import tempfile
import unittest

from src.usage_ledger.collectors import (_as_int, _content_chars, _json_obj,
                                         _message_chars, est_factor, scan_claude,
                                         scan_cline, scan_codex, scan_qoder_activity,
                                         scan_qoder_quota, scan_qoder_tokens,
                                         scan_qoder_transcripts, scan_sqlite_agent)


class ConversionHelperTest(unittest.TestCase):
    def test_as_int(self):
        self.assertEqual(_as_int(True), 0)
        self.assertEqual(_as_int(7), 7)
        self.assertEqual(_as_int(3.9), 3)
        self.assertEqual(_as_int("12.7"), 12)
        self.assertEqual(_as_int("oops"), 0)
        self.assertEqual(_as_int(None), 0)

    def test_json_obj(self):
        self.assertEqual(_json_obj({"a": 1}), {"a": 1})
        self.assertEqual(_json_obj('{"a": 1}'), {"a": 1})
        self.assertEqual(_json_obj("{broken"), {})
        self.assertEqual(_json_obj("[1, 2]"), {})
        self.assertEqual(_json_obj(None), {})

    def test_content_chars(self):
        self.assertEqual(_content_chars("hello"), (0, 5))
        self.assertEqual(_content_chars(None), (0, 0))
        self.assertEqual(_content_chars([
            "not-a-dict",
            {"type": "text", "text": "abc"},
            {"type": "thinking", "thinking": "de"},
            {"type": "tool_use", "input": {"x": 1}},
            {"type": "tool_result", "content": "toolout"},
            {"type": "tool_result", "content": [{"text": "inner"}, "skip"]},
        ]), (len("toolout") + len("inner"), len("abc") + len("de") + len('{"x": 1}')))

    def test_message_chars(self):
        self.assertEqual(_message_chars("assistant", {
            "message": {"content": [{"type": "text", "text": "hi"}]}}), (0, 2))
        self.assertEqual(_message_chars("user", {
            "humanInput": {"text": "prompt"},
            "message": {"content": [{"type": "text", "text": "prompt"}]}}),
            (len("prompt"), 0))
        self.assertEqual(_message_chars("user", {
            "message": {"content": [{"type": "text", "text": "abc"},
                                    {"type": "tool_result", "content": "xy"}]}}),
            (5, 0))
        self.assertEqual(_message_chars("user", {
            "message": {"content": "plain"}}), (5, 0))
        self.assertEqual(_message_chars("user", {
            "humanInput": "not-a-dict",
            "message": {"content": [{"type": "text", "text": "abc"}]}}), (3, 0))

    def test_est_factor(self):
        self.assertEqual(est_factor("gfmodel"), 3.85)
        self.assertEqual(est_factor(None), 3.8)
        self.assertEqual(est_factor("unknown"), 3.8)


class ClaudeEdgeTest(unittest.TestCase):
    def test_malformed_and_skipped_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "edge.jsonl")
            lines = [
                '{"type":"assistant"',
                '{"type":"user","note":"assistant"}',
                json.dumps({"type": "assistant",
                            "message": {"usage": {"input_tokens": 1}}}),
                json.dumps({"type": "assistant", "uuid": "zero",
                            "message": {"usage": {"iterations": [],
                                                  "input_tokens": 0}}}),
                json.dumps({"type": "assistant",
                            "message": {"usage": {"iterations": [],
                                                  "input_tokens": 5}}}),
                json.dumps({"type": "assistant", "uuid": "t1",
                            "message": {"usage": {"iterations": [],
                                                  "input_tokens": 5}}}),
                json.dumps({"type": "assistant", "uuid": "t2", "timestamp": "nope",
                            "message": {"usage": {"iterations": [],
                                                  "input_tokens": 5}}}),
                json.dumps({"type": "assistant", "uuid": "ok",
                            "timestamp": "2026-10-01T00:00:00Z",
                            "message": {"usage": {"iterations": [],
                                                  "input_tokens": 5, "output_tokens": 1}}}),
            ]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            blocked = os.path.join(tmp, "blocked.jsonl")
            with open(blocked, "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            os.chmod(blocked, 0)
            try:
                result = scan_claude(tmp)
            finally:
                os.chmod(blocked, 0o600)
        self.assertEqual(len(result.records), 1)
        record = result.records[0]
        self.assertEqual(record.key, "claude:ok")
        self.assertEqual(record.model, "unknown")
        self.assertIsNone(record.project)
        self.assertEqual(record.session, "edge")
        self.assertEqual(result.key_kinds["skipped:intermediate"], 1)
        self.assertEqual(result.key_kinds["zero-usage"], 1)
        self.assertGreaterEqual(len(result.errors), 4)


class CodexEdgeTest(unittest.TestCase):
    def test_bad_lines_and_zero_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            sessions = os.path.join(tmp, "sessions")
            archived = os.path.join(tmp, "archived")
            os.makedirs(sessions)
            path = os.path.join(sessions, "edge.jsonl")
            lines = [
                "{broken",
                json.dumps({"type": "session_meta",
                            "payload": {"id": "s1", "cwd": "/tmp/proj",
                                        "base_instructions": {
                                            "provenance": {"model": "gpt-a"}}}}),
                json.dumps({"type": "turn_context", "payload": {"model": "gpt-b"}}),
                json.dumps({"type": "event_msg",
                            "timestamp": "2026-10-01T00:00:00Z",
                            "payload": {
                    "type": "token_count",
                    "info": {"last_token_usage": {"input_tokens": 5},
                             "total_token_usage": {"total_tokens": 5,
                                                   "input_tokens": 5}}}}),
                json.dumps({"type": "event_msg",
                            "timestamp": "2026-10-01T00:00:02Z",
                            "payload": {"type": "token_count", "info": {
                                "last_token_usage": {"input_tokens": 0},
                                "total_token_usage": {"total_tokens": 5,
                                                      "input_tokens": 5}}}}),
                json.dumps({"type": "event_msg", "timestamp": "banana",
                            "payload": {"type": "token_count", "info": {
                                "last_token_usage": {"input_tokens": 5},
                                "total_token_usage": {"total_tokens": 10,
                                                      "input_tokens": 10}}}}),
                json.dumps({"type": "other"}),
            ]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            with open(os.path.join(sessions, "no_events.jsonl"), "w",
                      encoding="utf-8") as fh:
                fh.write(json.dumps({"type": "session_meta",
                                     "payload": {"id": "s2"}}) + "\n")
            result = scan_codex(sessions, archived)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0].model, "gpt-b")
        self.assertEqual(result.key_kinds["zero-usage"], 1)
        self.assertEqual(result.files, 2)


class ClineEdgeTest(unittest.TestCase):
    def _session(self, root, name, meta=None, messages=None, filename=None):
        session_dir = os.path.join(root, name)
        os.makedirs(session_dir)
        if meta is not None:
            with open(os.path.join(session_dir, name + ".json"), "w",
                      encoding="utf-8") as fh:
                fh.write(meta)
        if messages is not None:
            target = os.path.join(session_dir, filename or (name + ".messages.json"))
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(messages)
        return session_dir

    def test_empty_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_cline(tmp)
        self.assertTrue(result.available)
        self.assertEqual(result.records, [])
        self.assertIn("会话目录为空", result.notes[-1])

    def test_session_shapes_and_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._session(tmp, "bad_meta", meta="{broken")
            self._session(tmp, "fallback_name", meta=json.dumps(
                {"workspace_root": "/tmp/proj-fb", "model": "meta-model",
                 "provider": "meta-provider"}),
                messages=json.dumps({"sessionId": "s-fb", "messages": [
                    "not-a-dict",
                    {"role": "user", "metrics": {"inputTokens": 9}},
                    {"role": "assistant", "metrics": {}},
                    {"role": "assistant", "metrics": {"inputTokens": 1,
                                                      "outputTokens": 1},
                     "ts": 0},
                    {"role": "assistant", "metrics": {"inputTokens": 10,
                                                      "outputTokens": 2,
                                                      "cacheReadTokens": 1},
                     "ts": 1700000000000},
                ]}), filename="other.messages.json")
            self._session(tmp, "top_list", messages="[]")
            self._session(tmp, "no_messages_array", messages="{}")
            session_dir = self._session(tmp, "blocked", messages="{}",
                                        filename="blocked.messages.json")
            blocked = os.path.join(session_dir, "blocked.messages.json")
            os.chmod(blocked, 0)
            try:
                result = scan_cline(tmp)
            finally:
                os.chmod(blocked, 0o600)
        by_key = {rec.key: rec for rec in result.records}
        self.assertEqual(list(by_key), ["cline:s-fb:1700000000:4"])
        record = by_key["cline:s-fb:1700000000:4"]
        self.assertEqual(record.project, "proj-fb")
        self.assertEqual(record.model, "meta-model")
        self.assertEqual(record.provider, "meta-provider")
        self.assertEqual((record.counts.input, record.counts.output,
                          record.counts.cache_read), (9, 2, 1))
        self.assertEqual(result.key_kinds["skipped:ts"], 1)
        self.assertEqual(result.key_kinds["missing:id"], 1)
        self.assertGreaterEqual(len(result.errors), 3)


class SqliteEdgeTest(unittest.TestCase):
    def test_open_failure_and_query_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_sqlite_agent(tmp, "opencode")
            self.assertFalse(result.healthy)
            self.assertTrue(result.errors)
            db = os.path.join(tmp, "broken.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE message (x TEXT)")
            conn.commit()
            conn.close()
            result = scan_sqlite_agent(db, "opencode")
            self.assertFalse(result.healthy)
            self.assertIn("查询失败", result.errors[0][1])

    def test_row_shapes_without_session_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "rows.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE message (id TEXT, session_id TEXT, "
                         "time_created INTEGER, time_updated INTEGER, data TEXT)")
            conn.execute("CREATE TABLE session_message (id TEXT PRIMARY KEY, "
                         "session_id TEXT, type TEXT, time_created INTEGER, "
                         "time_updated INTEGER, data TEXT)")
            conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?)",
                         ("m1", "s1", "assistant", 1700000000000, None,
                          "{broken"))
            conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?)",
                         ("m2", "s1", "assistant", 1700000000000, None,
                          json.dumps({"tokens": {"input": 0}})))
            conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?)",
                         ("m3", "s1", "assistant", 0, None,
                          json.dumps({"tokens": {"input": 5}})))
            conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?)",
                         ("m4", "s1", "assistant", 1700000000000, None,
                          json.dumps({"tokens": {"input": 5},
                                      "model": {"id": "dict-model"},
                                      "providerID": "top-provider",
                                      "path": {"cwd": "/tmp/proj-d/"}})))
            conn.execute("INSERT INTO session_message VALUES (?,?,?,?,?,?)",
                         ("m5", "s1", "assistant", 1700000000000, None,
                          json.dumps({"tokens": {"input": 2},
                                      "model": "string-model"})))
            conn.commit()
            conn.close()
            result = scan_sqlite_agent(db, "opencode")
        by_key = {rec.key: rec for rec in result.records}
        self.assertEqual(set(by_key), {"opencode:m4", "opencode:m5"})
        self.assertEqual(by_key["opencode:m4"].model, "dict-model")
        self.assertEqual(by_key["opencode:m4"].provider, "top-provider")
        self.assertEqual(by_key["opencode:m4"].project, "proj-d")
        self.assertEqual(by_key["opencode:m5"].model, "string-model")
        self.assertIsNone(by_key["opencode:m5"].provider)
        self.assertEqual(result.key_kinds["zero-usage"], 1)
        self.assertGreaterEqual(len(result.errors), 1)


class QoderEdgeTest(unittest.TestCase):
    def test_token_open_schema_and_row_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_qoder_tokens(tmp)
            self.assertFalse(result.healthy)
            db = os.path.join(tmp, "token.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE chat_message (id TEXT)")
            conn.commit()
            conn.close()
            result = scan_qoder_tokens(db)
            self.assertFalse(result.available)
            self.assertIn("schema drift", result.errors[0][1])

            db = os.path.join(tmp, "bad_query.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE chat_message (x TEXT)")
            conn.execute("CREATE TABLE chat_session (x TEXT)")
            conn.commit()
            conn.close()
            result = scan_qoder_tokens(db)
            self.assertFalse(result.healthy)
            self.assertIn("查询失败", result.errors[0][1])

    def test_token_missing_id_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "token.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE chat_message (id TEXT, session_id TEXT, "
                         "role TEXT, gmt_create INTEGER, model_info TEXT, "
                         "token_info TEXT)")
            conn.execute("CREATE TABLE chat_session (session_id TEXT, "
                         "project_name TEXT, project_uri TEXT, session_type TEXT, "
                         "preferred_model_info TEXT)")
            conn.execute("INSERT INTO chat_message VALUES (?,?,?,?,?,?)",
                         ("", "s1", "assistant", 1700000000000,
                          '{"model_key":"m"}', '{"prompt_tokens":5}'))
            conn.execute("INSERT INTO chat_message VALUES (?,?,?,?,?,?)",
                         ("m2", "s1", "assistant", 0,
                          '{"model_key":"m"}', '{"prompt_tokens":5}'))
            conn.commit()
            conn.close()
            result = scan_qoder_tokens(db)
        self.assertEqual(result.records, [])
        self.assertEqual(len(result.errors), 2)
        self.assertIn("缺少 id/gmt_create", result.errors[0][1])

    def test_activity_open_failure_and_schema_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_qoder_activity(tmp)
            self.assertFalse(result.healthy)
            db = os.path.join(tmp, "activity.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE other (x TEXT)")
            conn.commit()
            conn.close()
            result = scan_qoder_activity(db)
            self.assertFalse(result.available)
            self.assertIn("schema drift", result.errors[0][1])

    def test_activity_cursor_backwards_forces_full_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "activity.db")
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE chat_session_messages (id TEXT PRIMARY KEY, "
                         "session_id TEXT, role TEXT, payload_json TEXT, "
                         "created_at INTEGER, updated_at INTEGER)")
            conn.execute("CREATE TABLE chat_sessions (session_id TEXT PRIMARY KEY, "
                         "cwd TEXT)")
            conn.execute("INSERT INTO chat_sessions VALUES ('s1', '/tmp/proj')")
            conn.execute("INSERT INTO chat_session_messages VALUES (?,?,?,?,?,?)",
                         ("u1", "s1", "user", "{}", 1700000000000, None))
            conn.commit()
            conn.close()
            result = scan_qoder_activity(db, cursor_ms=2000000000000)
        self.assertTrue(result.activities)
        self.assertEqual(result.cursor_ms, 1700000000000)

    def test_transcript_edge_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "transcripts")
            os.makedirs(root)
            path = os.path.join(root, "session.jsonl")
            lines = [
                "not json but has \"type\"",
                json.dumps({"foo": 1}),
                json.dumps({"type": "system", "timestamp": "2026-10-01T00:00:00Z"}),
                json.dumps({"type": "assistant", "timestamp": "bad",
                            "message": {}}),
                json.dumps({"type": "user", "timestamp": "2026-10-01T00:00:00Z",
                            "message": {"content": "hello"}}),
                json.dumps({"type": "assistant", "cwd": "/tmp/proj",
                            "sessionId": "s1",
                            "timestamp": "2026-10-01T00:00:01Z",
                            "message": {"model": "gfmodel",
                                        "content": [{"type": "text", "text": "hi"}],
                                        "usage": {"request_id": "r1", "credits": 1.5,
                                                  "billable": True,
                                                  "context_usage_ratio": 0.5}}}),
                json.dumps({"type": "assistant",
                            "timestamp": "2026-10-01T00:00:01Z",
                            "message": {"content": [{"type": "text", "text": "!!"}],
                                        "usage": {"request_id": "r1", "credits": 2.0,
                                                  "billable": True,
                                                  "context_usage_ratio": 0.5}}}),
                json.dumps({"type": "assistant",
                            "timestamp": "2026-10-01T00:00:02Z",
                            "message": {"content": [{"type": "text", "text": "ok"}]}}),
            ]
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            broken_link = os.path.join(root, "broken.jsonl")
            os.symlink(os.path.join(tmp, "missing-file"), broken_link)
            blocked = os.path.join(root, "blocked.jsonl")
            with open(blocked, "w", encoding="utf-8") as fh:
                fh.write("{}\n")
            os.chmod(blocked, 0)
            try:
                result = scan_qoder_transcripts(root)
            finally:
                os.chmod(blocked, 0o600)
        self.assertEqual(result.key_kinds["missing:timestamp"], 1)
        self.assertGreaterEqual(len(result.errors), 3)
        self.assertIn("r1", {credit.request_id for credit in result.credits})
        self.assertEqual(next(row for row in result.credits if row.request_id == "r1").credits,
                         2.0)
        self.assertTrue(result.estimates)
        self.assertEqual(next(iter(result.estimates)).project, "proj")

    def test_transcript_resume_reads_from_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "transcripts")
            os.makedirs(root)
            path = os.path.join(root, "session.jsonl")
            first = json.dumps({"type": "user", "timestamp": "2026-10-01T00:00:00Z",
                                "message": {"content": "prompt"}}) + "\n"
            second = json.dumps({"type": "assistant",
                                 "timestamp": "2026-10-01T00:00:01Z",
                                 "message": {"model": "m",
                                             "content": [{"type": "text", "text": "a"}],
                                             "usage": {"context_usage_ratio": 0.1}}}) + "\n"
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(first + second)
            state = {path: {"size": len(first), "mtime_ns": 0,
                            "offset": len(first), "cwd": "/tmp/proj",
                            "model": "m"}}
            result = scan_qoder_transcripts(root, file_state=state)
        self.assertEqual(len(result.estimates), 1)
        self.assertTrue(result.transcript_state[path]["offset"] > 0)

    def test_quota_log_edge_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            bucket = os.path.join(tmp, "20260101")
            os.makedirs(bucket)
            log = os.path.join(bucket, "main.log")
            lines = [
                "no marker line\n",
                "[2026-01-01T00:00:00] INFO 用量响应摘要 no-json-here\n",
                "[bad-time] INFO 用量响应摘要 " + json.dumps(
                    {"operation": "GetUserUsage", "requestId": "r0",
                     "qoderUsage": {"addOnQuota": {"total": 1, "used": 1,
                                                   "remaining": 0}}}) + "\n",
                "[2026-01-01T00:00:01] INFO 用量响应摘要 " + json.dumps(
                    {"operation": "GetUserUsage"}) + "\n",
                "[2026-01-01T00:00:02] INFO 用量响应摘要 " + json.dumps(
                    {"operation": "GetUserUsage", "requestId": "r1",
                     "qoderUsage": {"userQuota": "not-a-dict",
                                    "addOnQuota": {"total": "bad", "used": 1,
                                                   "remaining": 0}}}) + "\n",
                "[2026-01-01T00:00:03] INFO 用量响应摘要 " + json.dumps(
                    {"operation": "GetUserUsage", "requestId": "r2",
                     "qoderUsage": {"addOnQuota": {"total": 10, "used": 2,
                                                   "remaining": 8,
                                                   "unit": "credits"},
                                    "totalUsagePercentage": 0.2}}) + "\n",
            ]
            with open(log, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
            blocked_dir = os.path.join(tmp, "20260102")
            os.makedirs(blocked_dir)
            blocked = os.path.join(blocked_dir, "main2.log")
            with open(blocked, "w", encoding="utf-8") as fh:
                fh.write("x\n")
            os.chmod(blocked, 0)
            try:
                result = scan_qoder_quota(tmp)
            finally:
                os.chmod(blocked, 0o600)
        self.assertEqual(len(result.quota), 1)
        self.assertEqual(result.quota[0].request_id, "r2")
        self.assertEqual(result.key_kinds["quota:parse_error"], 1)
        self.assertGreaterEqual(len(result.errors), 1)


if __name__ == "__main__":
    unittest.main()
