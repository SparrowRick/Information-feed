"""Trading-day helpers (Asia/Shanghai)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from review.client import HiThinkClient

SHANGHAI = ZoneInfo("Asia/Shanghai")


def today_shanghai() -> str:
    return datetime.now(SHANGHAI).strftime("%Y-%m-%d")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI)


def normalize_date(value: str | int | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def trading_day_strings(items: list[dict[str, Any]]) -> list[str]:
    dates: list[str] = []
    seen: set[str] = set()
    for item in items:
        raw = item.get("date") or item.get("trade_date")
        norm = normalize_date(raw)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        dates.append(norm)
    dates.sort()
    return dates


def load_trading_days(client: HiThinkClient) -> list[str]:
    return trading_day_strings(client.trading_days())


def is_trading_day(date_str: str, trading_days: list[str]) -> bool:
    return date_str in trading_days


def previous_trading_day(date_str: str, trading_days: list[str]) -> str | None:
    earlier = [d for d in trading_days if d < date_str]
    return earlier[-1] if earlier else None


def latest_on_or_before(date_str: str, trading_days: list[str]) -> str | None:
    eligible = [d for d in trading_days if d <= date_str]
    return eligible[-1] if eligible else None


def latest_completed_trading_day(
    trading_days: list[str],
    *,
    now: datetime | None = None,
    complete_hour: int = 15,
) -> str | None:
    """Latest trading day that has finished regular session (default 15:00)."""
    now = now or now_shanghai()
    today = now.strftime("%Y-%m-%d")
    latest = latest_on_or_before(today, trading_days)
    if latest is None:
        return None
    if latest == today and now.hour < complete_hour:
        return previous_trading_day(today, trading_days)
    return latest
