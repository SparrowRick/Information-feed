"""HiThink Financial-API client. Auth via X-api-key (not Bearer)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

BASE_URL = "https://fuyao.aicubes.cn"
SHANGHAI = ZoneInfo("Asia/Shanghai")
_SECRET_PATHS = (
    "/home/box/agent-data/box-secrets.json",
    "/home/box/sand-data/box-secrets.json",
)


class APIError(RuntimeError):
    def __init__(self, message: str, code: int | None = None, path: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def load_api_key() -> str:
    env = os.environ.get("HITHINK_FINANCE_API_KEY")
    if env and env.strip():
        return env.strip()
    for path in _SECRET_PATHS:
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except FileNotFoundError:
            continue
        except (OSError, json.JSONDecodeError):
            continue
        secrets = payload.get("secrets") if isinstance(payload, dict) else None
        if isinstance(secrets, dict):
            key = secrets.get("HITHINK_FINANCE_API_KEY")
            if isinstance(key, str) and key.strip():
                return key.strip()
    raise APIError(
        "HITHINK_FINANCE_API_KEY not found in env or box-secrets.json"
    )


def date_to_ms(date_str: str) -> int:
    """Asia/Shanghai 00:00:00 of YYYY-MM-DD as unix milliseconds."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=SHANGHAI)
    return int(dt.timestamp() * 1000)


def _items(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    inner = data.get("data") if "data" in data else data
    if not isinstance(inner, dict):
        return []
    items = inner.get("item") or inner.get("items") or []
    return [x for x in items if isinstance(x, dict)]


class HiThinkClient:
    def __init__(
        self,
        *,
        min_interval: float = 1.2,
        timeout: int = 90,
        max_retries: int = 6,
    ) -> None:
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self._key = load_api_key()
        self._last_call = 0.0

    def _throttle(self) -> None:
        now = time.monotonic()
        wait = self.min_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = ""
        if params:
            cleaned = {k: v for k, v in params.items() if v is not None}
            if cleaned:
                query = "?" + urllib.parse.urlencode(cleaned)
        url = f"{BASE_URL}{path}{query}"
        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            self._throttle()
            req = urllib.request.Request(url, headers={"X-api-key": self._key})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    self._last_call = time.monotonic()
                    payload = json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                self._last_call = time.monotonic()
                body = exc.read()
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    payload = {"code": exc.code, "message": "http_error"}
                if exc.code == 429 or payload.get("code") == 429:
                    last_err = APIError("rate limited", code=429, path=path)
                    time.sleep(min(30.0, 2.0 * (attempt + 1) + 1.0))
                    continue
                raise APIError(
                    f"HTTP {exc.code} for {path}: {payload.get('message')}",
                    code=exc.code,
                    path=path,
                ) from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                self._last_call = time.monotonic()
                last_err = exc
                time.sleep(min(20.0, 1.5 * (attempt + 1)))
                continue

            code = payload.get("code")
            if code == 429:
                last_err = APIError("rate limited", code=429, path=path)
                time.sleep(min(30.0, 2.0 * (attempt + 1) + 1.0))
                continue
            if code in (3002,):
                return payload if isinstance(payload, dict) else {"code": code, "data": {}}
            if code not in (0, None):
                raise APIError(
                    f"API code={code} {path}: {payload.get('message')}",
                    code=int(code) if isinstance(code, int) else None,
                    path=path,
                )
            return payload
        raise APIError(f"failed after retries: {path}: {last_err}", path=path)

    def _paginated_pool(
        self,
        path: str,
        *,
        trade_date: str,
        extra: dict[str, Any] | None = None,
        page_size: int = 200,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            params: dict[str, Any] = {
                "date_ms": date_to_ms(trade_date),
                "page": page,
                "size": page_size,
            }
            if extra:
                params.update(extra)
            payload = self.get(path, params)
            chunk = _items(payload)
            items.extend(chunk)
            pagination = (payload.get("data") or {}).get("pagination") or {}
            pages = int(pagination.get("pages") or 1)
            total = int(pagination.get("total") or 0)
            if page >= pages or not chunk:
                break
            if total and len(items) >= total:
                break
            page += 1
        return items

    def trading_days(self) -> list[dict[str, Any]]:
        payload = self.get("/api/a-share/calendar/trading-days")
        return _items(payload)

    def limit_up_pool(self, trade_date: str) -> list[dict[str, Any]]:
        return self._paginated_pool(
            "/api/a-share/special-data/limit-up-pool",
            trade_date=trade_date,
            extra={"sort_field": "continue_day_cnt", "sort_dir": "desc"},
        )

    def limit_down_pool(self, trade_date: str) -> list[dict[str, Any]]:
        return self._paginated_pool(
            "/api/a-share/special-data/limit-down-pool",
            trade_date=trade_date,
        )

    def limit_break_pool(self, trade_date: str) -> list[dict[str, Any]]:
        return self._paginated_pool(
            "/api/a-share/special-data/limit-break-pool",
            trade_date=trade_date,
            extra={"sort_field": "open_times", "sort_dir": "desc"},
        )

    def limit_up_ladder(self) -> dict[str, Any]:
        payload = self.get("/api/a-share/special-data/limit-up-ladder")
        data = payload.get("data") or {}
        return data if isinstance(data, dict) else {}

    def anomaly_analysis_list(self, trade_date: str) -> list[dict[str, Any]]:
        # Official API is same-day snapshot; date_ms is sent for consistency.
        payload = self.get(
            "/api/a-share/special-data/anomaly-analysis-list",
            {"date_ms": date_to_ms(trade_date)},
        )
        return _items(payload)

    def prices_snapshot(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        limit = 1000
        total: int | None = None
        while True:
            payload = self.get(
                "/api/a-share/prices/snapshot",
                {"limit": limit, "offset": offset},
            )
            data = payload.get("data") or {}
            chunk = data.get("item") or []
            if total is None:
                try:
                    total = int(data.get("total") or 0)
                except (TypeError, ValueError):
                    total = 0
            items.extend([x for x in chunk if isinstance(x, dict)])
            if not chunk:
                break
            offset += limit
            if total and offset >= total:
                break
            if len(chunk) < limit:
                break
        return items

    def index_snapshot(self, thscodes: list[str]) -> list[dict[str, Any]]:
        payload = self.get(
            "/api/a-share-index/prices/snapshot",
            {"thscodes": ",".join(thscodes)},
        )
        return _items(payload)

    def index_historical(
        self, thscode: str, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        start_ms = date_to_ms(start_date)
        end_ms = date_to_ms(end_date) + 86400000 - 1
        payload = self.get(
            "/api/a-share-index/prices/historical",
            {
                "thscode": thscode,
                "interval": "1d",
                "start": start_ms,
                "end": end_ms,
            },
        )
        return _items(payload)
