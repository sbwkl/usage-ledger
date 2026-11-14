import json
import os
import stat
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from src.usage_ledger.models import Estimate
from src.usage_ledger.store import SqliteStore
from src.usage_ledger.trae_credits import (API_URL, PAGE_SIZE, STALE_AFTER,
                                           TraeCreditsClient, TraeCreditsError,
                                           TraeFetchResult, TraeSessionUsage,
                                           WindowTooLarge, can_reuse_last_sync,
                                           chunk_windows, credits_coverage,
                                           jwt_file_info, local_day,
                                           normalize_session, report_window,
                                           resolve_jwt, sync_trae_credits,
                                           window_bounds)


def usage_item(uid, ts=1_700_000_000, credits=1.5, model="claude-sonnet",
               **extra):
    row = {"session_id": uid, "usage_time": ts, "credits_float": credits,
           "amount_float": credits, "model_name": model, "mode": "agent"}
    row.update(extra)
    return row


class FakeTransport:
    def __init__(self, pages, status=200):
        self.pages = pages
        self.status = status
        self.calls = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append({"url": url, "headers": headers, "payload": payload,
                           "timeout": timeout})
        page = payload["page_num"]
        if callable(self.pages):
            body = self.pages(payload)
        elif isinstance(self.pages, dict):
            body = self.pages[page]
        else:
            body = self.pages[page - 1]
        if isinstance(body, tuple):
            status, body = body
        else:
            status = self.status
        return status, json.dumps(body).encode("utf-8")


class JwtTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "jwt")
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("  eyJhbGciOiJIUzI1NiJ9.payload.signature\n")
        os.chmod(self.path, 0o600)

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_file_and_prefix(self):
        credential = resolve_jwt(self.path, env={})
        self.assertEqual(credential.token, "eyJhbGciOiJIUzI1NiJ9.payload.signature")
        self.assertTrue(credential.source.startswith("file:"))
        self.assertIsNone(credential.warning)
        self.assertNotIn("eyJ", repr(credential))

    def test_env_precedence_and_prefix(self):
        env = {"TRAE_CN_JWT": "Bearer abc.def.ghi",
               "TRAE_CN_JWT_FILE": "/nonexistent"}
        credential = resolve_jwt(env=env)
        self.assertEqual(credential.token, "abc.def.ghi")
        self.assertEqual(credential.source, "env:TRAE_CN_JWT")

    def test_explicit_file_wins_over_env(self):
        env = {"TRAE_CN_JWT": "from-env"}
        credential = resolve_jwt(self.path, env=env)
        self.assertTrue(credential.token.startswith("eyJ"))

    def test_env_file_path(self):
        env = {"TRAE_CN_JWT_FILE": self.path}
        credential = resolve_jwt(env=env)
        self.assertEqual(credential.token, "eyJhbGciOiJIUzI1NiJ9.payload.signature")

    def test_default_uses_storage_json(self):
        from tests.test_trae_auth import VALID_B64
        storage = os.path.join(self.tmp.name, "storage.json")
        with open(storage, "w", encoding="utf-8") as fh:
            json.dump({"iCubeAuthInfo://icube.cloudide": VALID_B64}, fh)
        os.chmod(storage, 0o600)
        credential = resolve_jwt(env={"TRAE_CN_STORAGE": storage})
        self.assertEqual(credential.token, "test-token-not-real")
        self.assertTrue(credential.source.startswith("storage:"))
        self.assertNotIn("test-token", repr(credential))
        info = jwt_file_info(env={"TRAE_CN_STORAGE": storage})
        self.assertEqual(info["source"], "storage.json")
        self.assertTrue(info["readable"])
        self.assertIsNone(info["expires_at"])
        self.assertNotIn("test-token", json.dumps(info))

    def test_default_missing_storage_raises(self):
        missing = os.path.join(self.tmp.name, "storage.json")
        with self.assertRaises(TraeCreditsError) as caught:
            resolve_jwt(env={"TRAE_CN_STORAGE": missing})
        self.assertIn("未找到 Trae CN 登录凭证", str(caught.exception))

    def test_storage_expired_raises(self):
        from tests.test_trae_auth import EXPIRED_B64
        storage = os.path.join(self.tmp.name, "storage.json")
        with open(storage, "w", encoding="utf-8") as fh:
            json.dump({"iCubeAuthInfo://icube.cloudide": EXPIRED_B64}, fh)
        os.chmod(storage, 0o600)
        with self.assertRaises(TraeCreditsError) as caught:
            resolve_jwt(env={"TRAE_CN_STORAGE": storage})
        self.assertIn("过期", str(caught.exception))

    def test_explicit_file_wins_over_storage(self):
        from tests.test_trae_auth import VALID_B64
        storage = os.path.join(self.tmp.name, "storage.json")
        with open(storage, "w", encoding="utf-8") as fh:
            json.dump({"iCubeAuthInfo://icube.cloudide": VALID_B64}, fh)
        os.chmod(storage, 0o600)
        credential = resolve_jwt(self.path, env={"TRAE_CN_STORAGE": storage})
        self.assertTrue(credential.token.startswith("eyJ"))
        self.assertTrue(credential.source.startswith("file:"))

    def test_missing_file_does_not_leak(self):
        with self.assertRaises(TraeCreditsError) as caught:
            resolve_jwt(os.path.join(self.tmp.name, "missing"), env={})
        self.assertIn("JWT 文件不存在", str(caught.exception))

    def test_permission_warning(self):
        os.chmod(self.path, 0o644)
        credential = resolve_jwt(self.path, env={})
        self.assertIn("chmod 600", credential.warning)
        info = jwt_file_info(self.path, env={})
        self.assertTrue(info["exists"])
        self.assertEqual(info["mode"], 0o644)
        self.assertNotIn("token", info)
        self.assertNotIn("eyJ", json.dumps(info))

    def test_missing_info(self):
        info = jwt_file_info(os.path.join(self.tmp.name, "missing"), env={})
        self.assertFalse(info["exists"])
        self.assertFalse(info["readable"])


class WindowTest(unittest.TestCase):
    def test_report_window_default(self):
        start, end = report_window(until="2026-10-30")
        self.assertEqual(end, date(2026, 10, 30))
        self.assertEqual(start, date(2026, 10, 1))

    def test_report_window_since(self):
        self.assertEqual(report_window("2026-10-01", "2026-10-30", 90),
                         (date(2026, 10, 1), date(2026, 10, 30)))
        with self.assertRaises(ValueError):
            report_window("2026-10-02", "2026-10-01")

    def test_chunk_windows_covers_range_without_overlap(self):
        start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
        end = int(datetime(2026, 10, 30, 23, 59, tzinfo=timezone.utc).timestamp())
        windows = chunk_windows(start, end, 30)
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0][0], start)
        self.assertEqual(windows[-1][1], end)
        self.assertEqual(windows[0][1] + 1, windows[1][0])
        self.assertEqual(chunk_windows(end, start), [])

    def test_window_bounds_cover_local_days(self):
        start, end = window_bounds(date(2026, 10, 30), date(2026, 10, 30))
        self.assertEqual(local_day(start), "2026-10-30")
        self.assertEqual(local_day(end), "2026-10-30")
        self.assertGreater(end, start)


class ClientTest(unittest.TestCase):
    def test_request_shape_and_pagination(self):
        pages = {
            1: {"total": 25,
                "user_usage_group_by_sessions": [usage_item("s%d" % i) for i in range(20)]},
            2: {"total": 25,
                "user_usage_group_by_sessions": [usage_item("s%d" % i) for i in range(20, 25)]},
        }
        transport = FakeTransport(pages)
        sleeps = []
        client = TraeCreditsClient("jwt-value", transport=transport,
                                   sleep=sleeps.append, page_delay=0.3)
        result = client.fetch_window(1000, 2000)
        self.assertEqual(len(result.rows), 25)
        self.assertEqual(result.pages, 2)
        self.assertEqual(result.requests, 2)
        self.assertEqual(result.total, 25)
        self.assertEqual(sleeps, [0.3])
        first = transport.calls[0]
        self.assertEqual(first["url"], API_URL)
        self.assertEqual(first["headers"]["authorization"],
                         "Cloud-IDE-JWT jwt-value")
        self.assertEqual(first["headers"]["origin"], "https://www.trae.cn")
        self.assertEqual(first["payload"], {
            "start_time": 1000, "end_time": 2000, "page_size": 20,
            "page_num": 1, "usage_type": [7]})

    def test_nested_data_shape(self):
        transport = FakeTransport([{
            "code": 0,
            "data": {"total": 1, "user_usage_group_by_sessions": [usage_item("s1")]},
        }])
        result = TraeCreditsClient("jwt", transport=transport,
                                   sleep=lambda _: None).fetch_window(1, 2)
        self.assertEqual(len(result.rows), 1)

    def test_retry_on_server_error_once(self):
        calls = {"n": 0}

        def pages(_payload):
            calls["n"] += 1
            if calls["n"] == 1:
                return 503, {"code": 503}
            return 200, {"total": 0, "user_usage_group_by_sessions": []}

        transport = FakeTransport(pages)
        sleeps = []
        result = TraeCreditsClient("jwt", transport=transport,
                                   sleep=sleeps.append).fetch_window(1, 2)
        self.assertEqual(result.rows, [])
        self.assertEqual(result.requests, 2)
        self.assertEqual(sleeps, [2.0])

    def test_auth_error_is_redacted(self):
        transport = FakeTransport([{"code": 401}], status=401)
        with self.assertRaises(TraeCreditsError) as caught:
            TraeCreditsClient("super-secret-jwt", transport=transport,
                              sleep=lambda _: None).fetch_window(1, 2)
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertNotIn("super-secret-jwt", str(caught.exception))
        self.assertEqual(caught.exception.status, 401)

    def test_api_error_code(self):
        transport = FakeTransport([{"code": 9004, "message": "bad"}])
        with self.assertRaises(TraeCreditsError) as caught:
            TraeCreditsClient("jwt", transport=transport,
                              sleep=lambda _: None).fetch_window(1, 2)
        self.assertIn("9004", str(caught.exception))
        self.assertNotIn("bad", str(caught.exception))

    def test_normalization_and_skip_reasons(self):
        good, reason = normalize_session(usage_item("s1", ts=1_700_000_000_123,
                                                    credits=None, amount_float=2.5,
                                                    model=""))
        self.assertIsNone(reason)
        self.assertEqual(good.ts, 1_700_000_000.123)
        self.assertEqual(good.credits, 2.5)
        self.assertEqual(good.model, "unknown")
        self.assertEqual(normalize_session({"session_id": "", "usage_time": 1})[1],
                         "session")
        self.assertEqual(normalize_session({"session_id": "s", "usage_time": "bad"})[1], "ts")
        self.assertEqual(normalize_session({"session_id": "s", "usage_time": 1})[1], "credits")
        self.assertEqual(normalize_session([])[1], "shape")

    def test_duplicate_session_keeps_newer(self):
        pages = [{"total": 2, "user_usage_group_by_sessions": [
            usage_item("same", ts=100, credits=1),
            usage_item("same", ts=200, credits=2),
        ]}]
        result = TraeCreditsClient("jwt", transport=FakeTransport(pages),
                                   sleep=lambda _: None).fetch_window(1, 2)
        self.assertEqual(result.rows[0].ts, 200)
        self.assertEqual(result.rows[0].credits, 2)

    def test_window_too_large_splits(self):
        def pages(payload):
            span = payload["end_time"] - payload["start_time"]
            if span > 1000:
                return {"total": PAGE_SIZE * 101,
                        "user_usage_group_by_sessions": [
                            usage_item("x%d" % i) for i in range(PAGE_SIZE)]}
            return {"total": 0, "user_usage_group_by_sessions": []}

        transport = FakeTransport(pages)
        client = TraeCreditsClient("jwt", transport=transport,
                                   sleep=lambda _: None)
        result = client.fetch_range(1, 4000)
        self.assertGreater(len(transport.calls), 1)
        self.assertEqual(result.rows, [])
        self.assertGreater(result.requests, 1)

    def test_fetch_range_chunks_30_days(self):
        transport = FakeTransport([
            {"total": 0, "user_usage_group_by_sessions": []},
            {"total": 0, "user_usage_group_by_sessions": []},
        ])
        start = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())
        end = int(datetime(2026, 10, 30, tzinfo=timezone.utc).timestamp())
        result = TraeCreditsClient("jwt", transport=transport,
                                   sleep=lambda _: None).fetch_range(start, end)
        self.assertEqual(result.windows, 2)
        self.assertEqual(len(transport.calls), 2)
        self.assertLess(transport.calls[0]["payload"]["start_time"],
                        transport.calls[0]["payload"]["end_time"])


class SyncTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SqliteStore(os.path.join(self.tmp.name, "usage.db"))
        self.store.upsert_estimates([
            Estimate(request_id="e1", ts=1.0, day="2026-10-30", project="proj",
                     model="trae-cn", session="s1", est_input=10, est_output=2,
                     chars_in=1, chars_out=1, ratio=None,
                     source="trae-cn.est"),
        ])

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def sync(self, rows, jwt_file=None, client_cls=None):
        class FakeClient:
            def __init__(self, jwt, **kwargs):
                self.jwt = jwt

            def fetch_range(self, start, end):
                return TraeFetchResult(rows=rows, total=len(rows), pages=1,
                                       requests=1, skipped=0, windows=1,
                                       start_ts=start, end_ts=end)

        return sync_trae_credits(self.store, "2026-10-30", "2026-10-30",
                                 jwt_file=jwt_file,
                                 client_cls=client_cls or FakeClient)

    def test_sync_is_idempotent_and_maps_project(self):
        rows = [TraeSessionUsage("s1", 1_700_000_000, 1.25, "claude-sonnet"),
                TraeSessionUsage("s2", 1_700_000_100, 2.5, "gpt-4.1")]
        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "jwt"
            jwt.return_value.warning = None
            first = self.sync(rows)
            second = self.sync(rows)
        self.assertEqual(first.sessions, 2)
        self.assertEqual(first.credits, 3.75)
        self.assertEqual(first.cached_sessions, 2)
        self.assertEqual(second.cached_sessions, 2)
        self.assertEqual(self.store.credit_count("trae-cn"), 2)
        daily = self.store.credit_daily(source="trae-cn")
        self.assertEqual(daily[0]["credits"], 3.75)
        rows = self.store.credit_rows(source="trae-cn")
        by_session = {row["project"]: row for row in rows}
        self.assertIn("proj", by_session)
        self.assertEqual(by_session["proj"]["free_credits"], 0.0)
        state = self.store.source_state("trae-cn.credits")
        self.assertEqual(state["status"], "ok")
        self.assertEqual(state["records_total"], 2)
        window = json.loads(self.store.get_meta("trae_credits_last_window"))
        self.assertEqual(window["since"], "2026-10-30")

    def test_auth_failure_marks_error_without_creating_rows(self):
        class FakeClient:
            def __init__(self, jwt, **kwargs):
                pass

            def fetch_range(self, start, end):
                raise TraeCreditsError("API 认证失败（HTTP 401）", status=401)

        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "jwt"
            jwt.return_value.warning = None
            with self.assertRaises(TraeCreditsError):
                self.sync([], client_cls=FakeClient)
        state = self.store.source_state("trae-cn.credits")
        self.assertEqual(state["status"], "error")
        self.assertIn("401", state["last_error"])
        self.assertEqual(self.store.credit_count("trae-cn"), 0)

    def test_failure_preserves_previous_sync_time(self):
        rows = [TraeSessionUsage("s1", 1_700_000_000, 1.25, "m")]
        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "jwt"
            jwt.return_value.warning = None
            self.sync(rows)
        before = self.store.source_state("trae-cn.credits")["last_sync_at"]

        class FakeClient:
            def __init__(self, jwt, **kwargs):
                pass

            def fetch_range(self, start, end):
                raise TraeCreditsError("网络错误：timeout")

        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "jwt"
            jwt.return_value.warning = None
            with self.assertRaises(TraeCreditsError):
                self.sync([], client_cls=FakeClient)
        after = self.store.source_state("trae-cn.credits")["last_sync_at"]
        self.assertEqual(before, after)
        self.assertEqual(self.store.credit_count("trae-cn"), 1)

    def test_unexpected_error_is_redacted(self):
        class BadClient:
            def __init__(self, jwt, **kwargs):
                pass

            def fetch_range(self, start, end):
                raise RuntimeError("boom Cloud-IDE-JWT abc.def.ghi")

        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "abc.def.ghi"
            jwt.return_value.warning = None
            with self.assertRaises(RuntimeError):
                self.sync([], client_cls=BadClient)
        state = self.store.source_state("trae-cn.credits")
        self.assertNotIn("abc.def.ghi", state["last_error"])
        self.assertIn("<redacted>", state["last_error"])

    def test_coverage_and_max_age(self):
        rows = [TraeSessionUsage("s1", 1_700_000_000, 1.25, "m")]
        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "jwt"
            jwt.return_value.warning = None
            self.sync(rows)
        coverage = credits_coverage(self.store, "auto", None,
                                    "2026-10-01", "2026-10-30")
        self.assertTrue(coverage["available"])
        self.assertEqual(coverage["sessions"], 1)
        self.assertFalse(coverage["stale"])
        self.assertEqual(coverage["refresh_mode"], "auto")
        self.assertTrue(can_reuse_last_sync(self.store, "2026-10-30",
                                            "2026-10-30", 3600))
        self.assertFalse(can_reuse_last_sync(self.store, "2026-09-01",
                                             "2026-10-30", 3600))
        self.assertFalse(can_reuse_last_sync(self.store, "2026-10-30",
                                             "2026-10-30", 0))

    def test_stale_coverage(self):
        with patch("src.usage_ledger.trae_credits.resolve_jwt") as jwt:
            jwt.return_value.token = "jwt"
            jwt.return_value.warning = None
            self.sync([TraeSessionUsage("s1", 1_700_000_000, 1.25, "m")])
        future = datetime.now(timezone.utc) + STALE_AFTER + timedelta(seconds=1)
        coverage = credits_coverage(self.store, "offline", None,
                                    "2026-10-01", "2026-10-30", now=future)
        self.assertTrue(coverage["stale"])
        self.assertEqual(coverage["refresh_mode"], "offline")

    def test_no_store_coverage(self):
        coverage = credits_coverage(None, "stateless", None,
                                    "2026-10-01", "2026-10-30")
        self.assertFalse(coverage["available"])
        self.assertTrue(coverage["stale"])
        self.assertEqual(coverage["refresh_mode"], "stateless")


if __name__ == "__main__":
    unittest.main()
