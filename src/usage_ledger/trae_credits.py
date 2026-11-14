from __future__ import annotations

import json
import os
import re
import stat
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, time as dt_time, timedelta, timezone

from .models import Credit
from .trae_auth import TraeAuthError, load_storage_credential, storage_info

API_URL = "https://api.trae.cn/trae/api/v1/pay/query_user_usage_group_by_session"
TRAE_CREDITS_SOURCE = "trae-cn.credits"
TRAE_EST_SOURCE = "trae-cn.est"
CHUNK_DAYS = 30
PAGE_SIZE = 20
MAX_PAGES = 100
MAX_SPLIT_DEPTH = 4
PAGE_DELAY = 0.3
RETRY_DELAY = 2.0
REQUEST_TIMEOUT = 30
STALE_AFTER = timedelta(days=2)
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/152.0.0.0 Safari/537.36")


class TraeCreditsError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class WindowTooLarge(Exception):
    pass


@dataclass
class JwtCredential:
    token: str = field(repr=False)
    source: str
    warning: str | None = None


@dataclass(frozen=True)
class TraeSessionUsage:
    session_id: str
    ts: float
    credits: float
    model: str
    mode: str = ""


@dataclass
class TraeFetchResult:
    rows: list[TraeSessionUsage] = field(default_factory=list)
    total: int = 0
    pages: int = 0
    requests: int = 0
    skipped: int = 0
    windows: int = 0
    start_ts: int = 0
    end_ts: int = 0

    @property
    def credits(self) -> float:
        return round(sum(row.credits for row in self.rows), 6)


@dataclass
class TraeSyncResult:
    sessions: int
    credits: float
    cached_sessions: int
    skipped: int
    pages: int
    requests: int
    since: str
    until: str
    jwt_warning: str | None = None


def _strip_jwt_prefix(token: str) -> str:
    lowered = token.lower()
    for prefix in ("cloud-ide-jwt ", "bearer "):
        if lowered.startswith(prefix):
            return token[len(prefix):].strip()
    return token


def _read_jwt_file(path: str) -> JwtCredential:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            token = _strip_jwt_prefix(fh.read().strip())
    except FileNotFoundError as exc:
        raise TraeCreditsError(
            "JWT 文件不存在：%s；请先登录 Trae CN，或用 --jwt-file/TRAE_CN_JWT 指定"
            % path) from exc
    except OSError as exc:
        raise TraeCreditsError("JWT 文件不可读：%s（%s）" % (path, exc.strerror)) from exc
    if not token:
        raise TraeCreditsError("JWT 文件为空：%s" % path)
    warning = None
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & 0o077:
            warning = "JWT 文件权限为 %04o，建议 chmod 600 %s" % (mode, path)
    except OSError:
        pass
    return JwtCredential(token=token, source="file:%s" % path, warning=warning)


def resolve_jwt(explicit_file: str | None = None,
                env: dict | None = None) -> JwtCredential:
    env = os.environ if env is None else env
    if explicit_file:
        return _read_jwt_file(os.path.abspath(os.path.expanduser(explicit_file)))
    token = (env.get("TRAE_CN_JWT") or "").strip()
    if token:
        return JwtCredential(token=_strip_jwt_prefix(token), source="env:TRAE_CN_JWT")
    jwt_file = (env.get("TRAE_CN_JWT_FILE") or "").strip()
    if jwt_file:
        return _read_jwt_file(os.path.abspath(os.path.expanduser(jwt_file)))
    try:
        credential = load_storage_credential(env=env)
    except TraeAuthError as exc:
        raise TraeCreditsError(str(exc)) from exc
    return JwtCredential(token=credential.token,
                         source="storage:%s" % credential.path,
                         warning=credential.warning)


def _file_info(target: str, source: str) -> dict:
    info = {"source": source, "path": target, "exists": False, "readable": False,
            "size": None, "mode": None, "warning": None, "error": None,
            "expires_at": None}
    try:
        st = os.stat(target)
    except OSError:
        info["error"] = "文件不存在"
        return info
    info["exists"] = True
    info["readable"] = os.access(target, os.R_OK)
    info["size"] = st.st_size
    info["mode"] = stat.S_IMODE(st.st_mode)
    if info["mode"] & 0o077:
        info["warning"] = "JWT 文件权限过宽，建议 chmod 600 %s" % target
    return info


def jwt_file_info(path: str | None = None, env: dict | None = None) -> dict:
    env = os.environ if env is None else env
    if path:
        return _file_info(os.path.abspath(os.path.expanduser(path)), "file")
    if env.get("TRAE_CN_JWT"):
        return {"source": "env:TRAE_CN_JWT", "path": None, "exists": True,
                "readable": True, "size": None, "mode": None, "warning": None,
                "error": None, "expires_at": None}
    if env.get("TRAE_CN_JWT_FILE"):
        return _file_info(os.path.abspath(os.path.expanduser(env["TRAE_CN_JWT_FILE"])),
                          "env:TRAE_CN_JWT_FILE")
    return storage_info(env=env)


def http_post_json(url: str, headers: dict, payload: dict,
                   timeout: float = REQUEST_TIMEOUT) -> tuple[int, bytes]:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(65536)
        except OSError:
            body = b""
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise TraeCreditsError("网络错误：%s" % reason) from exc


def report_window(since: str | None = None, until: str | None = None,
                  days: int = 30) -> tuple[date, date]:
    end = date.fromisoformat(until) if until else date.today()
    start = date.fromisoformat(since) if since else end - timedelta(days=max(days, 1) - 1)
    if start > end:
        raise ValueError("起始日期晚于结束日期：%s > %s" % (start, end))
    return start, end


def window_bounds(start_day: date, end_day: date) -> tuple[int, int]:
    tz = datetime.now().astimezone().tzinfo
    start = datetime.combine(start_day, dt_time.min, tzinfo=tz)
    end = datetime.combine(end_day, dt_time.max, tzinfo=tz)
    return int(start.timestamp()), int(end.timestamp())


def chunk_windows(start_ts: int, end_ts: int, days: int = CHUNK_DAYS) -> list[tuple[int, int]]:
    if end_ts < start_ts:
        return []
    step = max(days, 1) * 86400
    windows = []
    cursor = end_ts
    while cursor >= start_ts:
        begin = max(start_ts, cursor - step + 1)
        windows.append((begin, cursor))
        cursor = begin - 1
    return list(reversed(windows))


def local_day(ts: float) -> str:
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d")


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def normalize_session(item) -> tuple[TraeSessionUsage | None, str | None]:
    if not isinstance(item, dict):
        return None, "shape"
    session_id = item.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        return None, "session"
    raw_ts = item.get("usage_time")
    ts = _number(raw_ts)
    if ts is None or ts <= 0:
        return None, "ts"
    if ts > 100_000_000_000:
        ts /= 1000.0
    credits = _number(item.get("credits_float"))
    if credits is None:
        credits = _number(item.get("amount_float"))
    if credits is None:
        return None, "credits"
    model = item.get("model_name")
    if not isinstance(model, str) or not model.strip():
        model = "unknown"
    mode = item.get("mode")
    if not isinstance(mode, str):
        mode = ""
    return TraeSessionUsage(session_id=session_id.strip(), ts=ts,
                            credits=credits, model=model.strip(), mode=mode), None


def _merge_rows(rows: list[TraeSessionUsage]) -> list[TraeSessionUsage]:
    merged: dict[str, TraeSessionUsage] = {}
    for row in rows:
        prev = merged.get(row.session_id)
        if prev is None or row.ts > prev.ts:
            merged[row.session_id] = row
    return sorted(merged.values(), key=lambda row: (row.ts, row.session_id))


class TraeCreditsClient:
    def __init__(self, jwt: str, *, url: str = API_URL, transport=None,
                 sleep=time.sleep, timeout: float = REQUEST_TIMEOUT,
                 page_delay: float = PAGE_DELAY):
        self._jwt = jwt
        self.url = url
        self.transport = transport or http_post_json
        self.sleep = sleep
        self.timeout = timeout
        self.page_delay = page_delay
        self.request_count = 0

    def _headers(self) -> dict:
        return {
            "authorization": "Cloud-IDE-JWT " + self._jwt,
            "content-type": "application/json",
            "accept": "application/json, text/plain, */*",
            "user-agent": USER_AGENT,
            "origin": "https://www.trae.cn",
            "referer": "https://www.trae.cn/",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }

    def _request(self, start_ts: int, end_ts: int, page: int) -> dict:
        payload = {"start_time": int(start_ts), "end_time": int(end_ts),
                   "page_size": PAGE_SIZE, "page_num": page, "usage_type": [7]}
        attempts = 0
        while True:
            attempts += 1
            self.request_count += 1
            status, raw = self.transport(self.url, self._headers(), payload, self.timeout)
            if (status == 429 or status >= 500) and attempts == 1:
                self.sleep(RETRY_DELAY)
                continue
            break
        if status in (401, 403):
            raise TraeCreditsError(
                "API 认证失败（HTTP %d）：凭证已失效或不被该接口接受；"
                "请重新登录 Trae CN 后重试" % status, status=status)
        if status < 200 or status >= 300:
            raise TraeCreditsError(
                "API 请求失败（HTTP %d）" % status, status=status)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise TraeCreditsError("API 响应不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise TraeCreditsError("API 响应结构异常")
        code = data.get("code")
        if code not in (None, 0, "0"):
            raise TraeCreditsError("API 错误码 %s" % code)
        nested = data.get("data")
        return nested if isinstance(nested, dict) else data

    def fetch_window(self, start_ts: int, end_ts: int) -> TraeFetchResult:
        before = self.request_count
        rows: list[TraeSessionUsage] = []
        skipped = 0
        total = None
        seen = 0
        page = 1
        pages = 0
        while page <= MAX_PAGES:
            data = self._request(start_ts, end_ts, page)
            items = data.get("user_usage_group_by_sessions")
            if items is None:
                items = []
            if not isinstance(items, list):
                raise TraeCreditsError("API 响应结构异常：user_usage_group_by_sessions")
            pages += 1
            seen += len(items)
            for item in items:
                row, _reason = normalize_session(item)
                if row is None:
                    skipped += 1
                else:
                    rows.append(row)
            raw_total = data.get("total")
            try:
                parsed_total = int(raw_total) if raw_total is not None else None
            except (TypeError, ValueError):
                parsed_total = None
            if parsed_total is not None:
                total = parsed_total
                if total > PAGE_SIZE * MAX_PAGES:
                    raise WindowTooLarge("窗口超过 %d 条" % total)
            if len(items) < PAGE_SIZE:
                break
            if total is not None and seen >= total:
                break
            if page == MAX_PAGES:
                raise WindowTooLarge("窗口超过 %d 页" % MAX_PAGES)
            page += 1
            self.sleep(self.page_delay)
        return TraeFetchResult(rows=_merge_rows(rows), total=total or seen,
                               pages=pages, requests=self.request_count - before,
                               skipped=skipped, start_ts=start_ts, end_ts=end_ts)

    def _fetch_split(self, start_ts: int, end_ts: int, depth: int = 0) -> TraeFetchResult:
        try:
            return self.fetch_window(start_ts, end_ts)
        except WindowTooLarge:
            if depth >= MAX_SPLIT_DEPTH or end_ts - start_ts <= 1:
                raise TraeCreditsError("窗口数据量超限，请缩短 --days 或缩小日期范围")
            mid = (start_ts + end_ts) // 2
            left = self._fetch_split(start_ts, mid, depth + 1)
            right = self._fetch_split(mid + 1, end_ts, depth + 1)
            return TraeFetchResult(
                rows=left.rows + right.rows,
                total=left.total + right.total,
                pages=left.pages + right.pages,
                requests=left.requests + right.requests,
                skipped=left.skipped + right.skipped,
                windows=left.windows + right.windows,
                start_ts=start_ts, end_ts=end_ts)

    def fetch_range(self, start_ts: int, end_ts: int) -> TraeFetchResult:
        before = self.request_count
        rows: list[TraeSessionUsage] = []
        total = pages = skipped = windows = 0
        for start, end in chunk_windows(start_ts, end_ts):
            result = self._fetch_split(start, end)
            rows.extend(result.rows)
            total += result.total
            pages += result.pages
            skipped += result.skipped
            windows += 1
        merged = _merge_rows(rows)
        return TraeFetchResult(
            rows=merged, total=total, pages=pages,
            requests=self.request_count - before, skipped=skipped,
            windows=windows, start_ts=start_ts, end_ts=end_ts)


def _safe_error(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    text = re.sub(r"(?i)(cloud-ide-jwt|bearer)\s+\S+", r"\1 <redacted>", text)
    text = re.sub(r"eyJ[\w\-.]{10,}", "<redacted>", text)
    return text[:300]


def sync_trae_credits(store, since_day: str, until_day: str,
                      jwt_file: str | None = None, transport=None,
                      sleep=time.sleep, client_cls=None) -> TraeSyncResult:
    attempted_at = datetime.now(timezone.utc).isoformat()
    try:
        start = date.fromisoformat(since_day)
        end = date.fromisoformat(until_day)
        start_ts, end_ts = window_bounds(start, end)
        credential = resolve_jwt(jwt_file)
        client = (client_cls or TraeCreditsClient)(
            credential.token, transport=transport, sleep=sleep)
        result = client.fetch_range(start_ts, end_ts)
        projects = store.est_session_projects(TRAE_EST_SOURCE)
        credits = [
            Credit(request_id="trae-cn:%s" % row.session_id, ts=row.ts,
                   day=local_day(row.ts), project=projects.get(row.session_id, ""),
                   model=row.model, session=row.session_id, credits=row.credits,
                   billable=True, source="trae-cn")
            for row in result.rows
        ]
        store.upsert_credits(credits, [])
        cached = store.credit_count("trae-cn")
        store.update_source_state(
            TRAE_CREDITS_SOURCE, files=0, records=cached,
            status="ok" if cached else "empty",
            last_ts=max((row.ts for row in result.rows), default=None))
        store.set_meta("trae_credits_last_window", json.dumps({
            "since": since_day, "until": until_day,
            "start_ts": start_ts, "end_ts": end_ts}, separators=(",", ":")))
        store.set_meta("trae_credits_last_attempt", attempted_at)
        return TraeSyncResult(
            sessions=len(result.rows), credits=result.credits,
            cached_sessions=cached, skipped=result.skipped, pages=result.pages,
            requests=result.requests, since=since_day, until=until_day,
            jwt_warning=credential.warning)
    except Exception as exc:
        store.mark_source_error(TRAE_CREDITS_SOURCE, _safe_error(exc))
        store.set_meta("trae_credits_last_attempt", attempted_at)
        raise


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def can_reuse_last_sync(store, since_day: str, until_day: str,
                        max_age: int, now: datetime | None = None) -> bool:
    if max_age <= 0:
        return False
    now = now or datetime.now(timezone.utc)
    state = store.source_state(TRAE_CREDITS_SOURCE)
    if not state or state.get("status") not in ("ok", "empty"):
        return False
    last_sync = _parse_iso(state.get("last_sync_at"))
    if last_sync is None or now - last_sync > timedelta(seconds=max_age):
        return False
    try:
        window = json.loads(store.get_meta("trae_credits_last_window") or "{}")
    except ValueError:
        return False
    return (window.get("since") or "9999") <= since_day and \
        (window.get("until") or "") >= until_day


def credits_coverage(store, mode: str, refresh_error: str | None,
                     requested_since: str, requested_until: str,
                     now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if store is None:
        return {
            "available": False, "last_sync_at": None, "last_attempt_at": None,
            "since": requested_since, "until": requested_until, "sessions": 0,
            "status": "empty", "refresh_mode": mode,
            "refresh_error": refresh_error, "stale": True,
            "error": refresh_error,
        }
    state = store.source_state(TRAE_CREDITS_SOURCE) or {}
    sessions = store.credit_count("trae-cn")
    last_sync_at = state.get("last_sync_at")
    attempted_at = store.get_meta("trae_credits_last_attempt")
    try:
        window = json.loads(store.get_meta("trae_credits_last_window") or "{}")
    except ValueError:
        window = {}
    last_sync = _parse_iso(last_sync_at)
    stale = (refresh_error is not None or last_sync is None or
             now - last_sync > STALE_AFTER)
    return {
        "available": sessions > 0,
        "last_sync_at": last_sync_at,
        "last_attempt_at": attempted_at,
        "since": window.get("since") or requested_since,
        "until": window.get("until") or requested_until,
        "sessions": sessions,
        "status": state.get("status") or "empty",
        "refresh_mode": mode,
        "refresh_error": refresh_error,
        "stale": stale,
        "error": state.get("last_error"),
    }
