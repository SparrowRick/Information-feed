#!/usr/bin/env python3
"""Validate and merge the public premarket feed; Python 3.10+, standard library."""
import argparse
import json
import math
import os
import re
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

SH = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[1]
LEGACY_CUTOFF = date(2026, 9, 4)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp(value):
    require(isinstance(value, str), "timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.utcoffset() == timedelta(hours=8), "timestamp must use +08:00")
    return parsed


def text_fields(obj, *keys):
    require(isinstance(obj, dict), "expected object")
    for key in keys:
        require(isinstance(obj.get(key), str) and obj[key].strip(), f"missing text: {key}")


def array(obj, key, maximum):
    value = obj.get(key)
    require(isinstance(value, list) and len(value) <= maximum, f"invalid list: {key}")
    return value


def trading_day(day, calendar_dir=None):
    calendar_dir = Path(calendar_dir or ROOT / "calendar")
    path = calendar_dir / f"{day.year}.json"
    require(path.exists(), f"official trading calendar missing for {day.year}")
    cal = json.loads(path.read_text(encoding="utf-8"))
    require(cal["valid_from"] <= day.isoformat() <= cal["valid_through"], "calendar out of coverage")
    return day.weekday() < 5 and not any(start <= day.isoformat() <= end for start, end in cal["closed_ranges"])


def next_sessions(day, n, calendar_dir=None):
    result = []
    while len(result) < n:
        day += timedelta(days=1)
        if trading_day(day, calendar_dir):
            result.append(day)
    return result


def timely(source, cutoff):
    if source.get("published_at"):
        return stamp(source["published_at"]) <= cutoff
    if source.get("published_date"):
        return date.fromisoformat(source["published_date"]) < cutoff.date() or stamp(source["retrieved_at"]) <= cutoff
    return stamp(source["retrieved_at"]) <= cutoff


def validate_item(item, calendar_dir=None):
    text_fields(item, "id", "title", "date", "timezone", "overnight", "market_note", "review_note")
    day = date.fromisoformat(item["date"])
    require(item.get("version") == 2 and item.get("type") == "premarket", "expected version 2 premarket")
    require(item["id"] == f"premarket-{day}", "report id/date mismatch")
    require(item["timezone"] == "Asia/Shanghai", "wrong timezone")
    require(item.get("is_trading_day") is True and trading_day(day, calendar_dir), "not an exchange trading day")
    generated, cutoff, target = (stamp(item[k]) for k in ("generated_at", "cutoff_at", "target_publish_at"))
    require(cutoff.date() == day and cutoff.time() <= time(8, 20), "cutoff must be on report date, no later than 08:20")
    require(generated >= cutoff, "generated before cutoff")
    require(target == datetime.combine(day, time(8, 30), SH), "wrong target publish time")
    require(item.get("edition") in ("live", "retrospective"), "invalid edition")
    if item["edition"] == "live":
        require(generated.date() == day and generated.time() < time(9), "live report completed after 09:00")
    else:
        require("回溯" in item["title"] and "回溯" in item["overnight"], "retrospective must be visibly labelled")
    coverage = item.get("coverage", {})
    require(coverage.get("status") in ("complete", "partial"), "invalid coverage status")
    gaps = array(coverage, "gaps", 30)
    require(all(isinstance(x, str) and x.strip() for x in gaps), "invalid coverage gaps")
    require((coverage["status"] == "partial") == bool(gaps), "coverage status/gaps mismatch")
    require(stamp(coverage["from"]) <= cutoff and stamp(coverage["to"]) == cutoff, "invalid coverage window")
    sources = {}
    for source in array(item, "sources", 40):
        text_fields(source, "id", "title", "url", "publisher", "timing_note")
        require(source["id"] not in sources, "duplicate source id")
        url = urlparse(source["url"])
        require(url.scheme == "https" and url.hostname and not url.username, "invalid source URL")
        require(source.get("source_type") in ("official", "company", "media", "data"), "invalid source type")
        require(source.get("time_precision") in ("minute", "day", "unknown"), "invalid source time precision")
        retrieved = stamp(source["retrieved_at"])
        require(retrieved <= generated, "source retrieved after report generated")
        precision = source["time_precision"]
        if precision == "minute":
            published = stamp(source["published_at"])
            require(published <= retrieved and source.get("published_date") == published.date().isoformat(), "invalid source publication time")
        elif precision == "day":
            require(source.get("published_at") is None, "date-only source has invented time")
            require(date.fromisoformat(source["published_date"]) <= retrieved.date(), "future publication date")
        else:
            require(source.get("published_at") is None and source.get("published_date") is None, "unknown precision must have null publication times")
        require(timely(source, cutoff) or source.get("reference_only") is True, "source not demonstrably public before cutoff")
        sources[source["id"]] = source
    require(sources, "no sources")

    def refs(obj, key="source_ids", allow_empty=False):
        values = array(obj, key, 15)
        require(all(isinstance(v, str) and v in sources for v in values), f"dangling {key}")
        require(len(set(values)) == len(values), f"duplicate {key}")
        if not allow_empty or values:
            require(values and any(timely(sources[v], cutoff) and not sources[v].get("reference_only") for v in values), "claim needs a source available by cutoff")

    refs(item, "overview_source_ids")
    for metric in array(item, "market_snapshot", 12):
        text_fields(metric, "name", "unit", "session")
        require(type(metric.get("value")) in (int, float) and math.isfinite(metric["value"]), "invalid market value")
        change = metric.get("change_pct")
        require(change is None or (type(change) in (int, float) and math.isfinite(change)), "invalid percentage")
        require(metric["session"] in ("close", "snapshot"), "invalid market session")
        require(stamp(metric["as_of"]) <= cutoff, "market quote after cutoff")
        refs(metric)
    future = next_sessions(day, 5, calendar_dir)
    ids = set()
    for event in array(item, "today", 5):
        text_fields(event, "id", "title", "why", "what_changed", "priced_in", "watch", "invalidates")
        require(re.fullmatch(r"[a-z0-9][a-z0-9-]{1,100}", event["id"]) and event["id"] not in ids, "invalid/duplicate event id")
        ids.add(event["id"])
        require(event.get("kind") in ("catalyst", "risk"), "invalid event kind")
        require(event.get("novelty") in ("new", "update", "known"), "invalid novelty")
        require(event.get("follow_until") == future[-1].isoformat(), "follow_until must be fifth subsequent trading day")
        require(all(isinstance(v, str) and v for v in array(event, "sectors", 6)), "invalid sectors")
        for company in array(event, "companies", 3):
            text_fields(company, "name", "code", "exchange", "relation")
            require(re.fullmatch(r"\d{6}", company["code"]) and company["exchange"] in ("SSE", "SZSE", "BSE"), "invalid A-share code/exchange")
            refs(company)
        refs(event)
    for review in array(item, "review", 2):
        text_fields(review, "original_report_id", "original_event_id", "original_view", "what_happened")
        require(review.get("day_offset") in (1, 3, 5), "invalid review interval")
        require(review.get("status") in ("supported", "weakened", "pending", "unverifiable"), "invalid review status")
        refs(review, allow_empty=review["status"] == "unverifiable")
    for event in array(item, "calendar", 3):
        text_fields(event, "title", "date", "why")
        event_day = date.fromisoformat(event["date"])
        require(day <= event_day <= future[-1], "event outside five-session horizon")
        require(event.get("time_precision") in ("minute", "day"), "invalid calendar precision")
        if event["time_precision"] == "minute":
            scheduled = stamp(event["scheduled_at"])
            require(scheduled.date() == event_day and scheduled >= cutoff, "invalid scheduled time")
        else:
            require(event.get("scheduled_at") is None, "day-only event cannot invent a time")
        refs(event)
    return item


def validate_feed(feed, calendar_dir=None):
    require(isinstance(feed, dict) and feed.get("schema_version") == "2.0", "feed schema_version must be 2.0")
    require(feed.get("timezone") == "Asia/Shanghai", "wrong feed timezone")
    updated = stamp(feed["updated_at"])
    items = array(feed, "items", 100000)
    require(items, "feed cannot be empty")
    seen, latest = set(), None
    previous_date = date.max
    for item in items:
        text_fields(item, "id", "type")
        require(item["id"] not in seen, "duplicate report id")
        seen.add(item["id"])
        if item.get("version") == 2:
            validate_item(item, calendar_dir)
            day = date.fromisoformat(item["date"])
            require(stamp(item["generated_at"]) <= updated, "feed timestamp before item generation")
            if latest is None:
                latest = item["id"]
        else:
            match = re.fullmatch(r"(premarket|patrol)-(\d{4}-\d{2}-\d{2})", item["id"])
            require(match and item["type"] == match[1], "invalid legacy item")
            day = date.fromisoformat(match[2])
            require(day <= LEGACY_CUTOFF, "new reports must use version 2")
        require(day <= previous_date, "items must be newest first")
        previous_date = day
    require(latest is not None and feed.get("latest_premarket_id") == latest, "invalid latest_premarket_id")
    return feed


def validate_reviews(item, archive_dir):
    for review in item["review"]:
        report_id = review["original_report_id"]
        require(re.fullmatch(r"premarket-\d{4}-\d{2}-\d{2}", report_id), "invalid original report id")
        path = Path(archive_dir) / f"{report_id.removeprefix('premarket-')}.json"
        require(path.exists(), "original review archive missing")
        original = json.loads(path.read_text(encoding="utf-8"))
        require(original.get("edition") == "live", "cannot score a retrospective sample")
        matches = [e for e in original["today"] if e["id"] == review["original_event_id"]]
        require(len(matches) == 1 and matches[0]["why"] == review["original_view"], "original judgment has been changed")
        source_day = date.fromisoformat(original["date"])
        require(next_sessions(source_day, review["day_offset"])[-1].isoformat() == item["date"], "review trading-day offset mismatch")


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def merged(feed, item, calendar_dir=None):
    validate_item(item, calendar_dir)
    existing = [old for old in feed["items"] if old["id"] == item["id"]]
    require(not existing or existing == [item], "report already published with different contents; original is immutable")
    if existing:
        return validate_feed(feed, calendar_dir)
    # A late historical repair cannot roll the latest live feed backwards.
    require(all(old["id"][-10:] <= item["date"] for old in feed["items"]), "cannot prepend older report")
    now = datetime.now(SH)
    require(stamp(feed["updated_at"]) <= now and stamp(item["generated_at"]) <= now, "cannot publish future timestamps")
    updated = now.isoformat(timespec="seconds")
    result = {**feed, "schema_version": "2.0", "timezone": "Asia/Shanghai", "updated_at": updated,
              "latest_premarket_id": item["id"], "items": [item, *feed["items"]]}
    return validate_feed(result, calendar_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("path", type=Path)
    merge = sub.add_parser("merge")
    merge.add_argument("item", type=Path)
    merge.add_argument("--feed", type=Path, default=ROOT / "feed.json")
    merge.add_argument("--archive-dir", type=Path, default=ROOT / "archive")
    merge.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "validate":
            value = json.loads(args.path.read_text(encoding="utf-8"))
            (validate_feed if "items" in value else validate_item)(value)
        else:
            item = json.loads(args.item.read_text(encoding="utf-8"))
            feed = json.loads(args.feed.read_text(encoding="utf-8"))
            result = merged(feed, item)
            validate_reviews(item, args.archive_dir)
            path = args.archive_dir / f"{item['date']}.json"
            if path.exists():
                require(json.loads(path.read_text(encoding="utf-8")) == item, "archive is immutable")
            if not args.check:
                if not path.exists():
                    atomic_write(path, dumps(item))
                atomic_write(args.feed, dumps(result))
        print("OK")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
