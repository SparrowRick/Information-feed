#!/usr/bin/env python3
"""Pull a validated feed, atomically replace local JSON, and expose freshness."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

from feed_tool import SH, atomic_write, dumps, require, stamp, trading_day, validate_feed

DEFAULT_URL = "https://raw.githubusercontent.com/SparrowRick/Information-feed/main/feed.json"
MAX_BYTES = 8 * 1024 * 1024


def fetch(url):
    require(url.startswith("https://"), "feed URL must use HTTPS")
    request = Request(url, headers={"User-Agent": "Information-feed/2.0", "Cache-Control": "no-cache"})
    with urlopen(request, timeout=15) as response:
        require(response.geturl().startswith("https://"), "HTTPS downgrade rejected")
        content = response.read(MAX_BYTES + 1)
    require(len(content) <= MAX_BYTES, "feed exceeds 8 MiB")
    return json.loads(content.decode("utf-8"))


def freshness(feed, now):
    latest = next(i for i in feed["items"] if i["id"] == feed["latest_premarket_id"])
    try:
        is_open = trading_day(now.date())
    except (ValueError, OSError):
        return "calendar_unknown", latest["date"]
    if not is_open:
        return "market_closed", latest["date"]
    if latest["date"] != now.date().isoformat():
        return "awaiting_today", latest["date"]
    if latest["edition"] == "retrospective":
        return "retrospective", latest["date"]
    return "ready", latest["date"]


def sync(url, output, status_path, fetcher=fetch, now=None):
    now = now or datetime.now(SH)
    output, status_path = Path(output), Path(status_path)
    require(output.resolve() != status_path.resolve(), "status path cannot equal feed path")
    previous = {}
    if status_path.exists():
        try:
            previous = json.loads(status_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    try:
        candidate = validate_feed(fetcher(url))
        require(stamp(candidate["updated_at"]) <= now, "feed update timestamp is in the future")
        if output.exists():
            current = json.loads(output.read_text(encoding="utf-8"))
            require(stamp(candidate["updated_at"]) >= stamp(current["updated_at"]), "refusing stale remote version")
            if candidate["updated_at"] == current["updated_at"]:
                require(candidate == current, "same timestamp with different content")
        state, latest_date = freshness(candidate, now)
        content = dumps(candidate)
        if not output.exists() or output.read_text(encoding="utf-8") != content:
            atomic_write(output, content)
        atomic_write(status_path, dumps({
            "checked_at": now.isoformat(), "last_success_at": now.isoformat(),
            "state": state, "latest_date": latest_date,
            "source_updated_at": candidate["updated_at"], "error": None
        }))
        return state
    except Exception as exc:
        # Never overwrite an existing feed with an error, an empty object or bad JSON.
        status = {**previous, "checked_at": now.isoformat(), "state": "sync_error", "error": str(exc)}
        atomic_write(status_path, dumps(status))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--status", type=Path)
    args = parser.parse_args()
    status = args.status or args.output.with_name("sync-status.json")
    last = None
    for attempt in range(3):
        try:
            state = sync(args.url, args.output, status)
            print(f"OK: {state}")
            return 0
        except Exception as exc:
            last = exc
    print(f"ERROR: {last}; previous feed retained", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
