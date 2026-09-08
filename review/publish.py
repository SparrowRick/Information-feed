"""Write review-feed.json, archive snapshot, and markdown sample."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
KEEP_ITEMS = 30
TIMEZONE = "Asia/Shanghai"


def empty_feed() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "timezone": TIMEZONE,
        "updated_at": None,
        "latest_review_id": None,
        "items": [],
    }


def load_feed(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_feed()
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return empty_feed()
    if not isinstance(data, dict):
        return empty_feed()
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("timezone", TIMEZONE)
    data.setdefault("items", [])
    if not isinstance(data["items"], list):
        data["items"] = []
    return data


def upsert_item(feed: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    items = [x for x in feed.get("items") or [] if isinstance(x, dict) and x.get("id") != item.get("id")]
    items.insert(0, item)
    feed["items"] = items[:KEEP_ITEMS]
    feed["schema_version"] = SCHEMA_VERSION
    feed["timezone"] = TIMEZONE
    feed["updated_at"] = item.get("generated_at")
    feed["latest_review_id"] = item.get("id")
    return feed


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def publish(
    item: dict[str, Any],
    out_dir: Path,
    *,
    dry_run: bool = False,
) -> dict[str, Path]:
    """Write feed + archive + markdown sample under out_dir."""
    out_dir = Path(out_dir)
    feed_path = out_dir / "review-feed.json"
    date = item["date"]
    archive_path = out_dir / "archive" / "review" / f"{date}.json"
    sample_path = out_dir / "samples" / "review" / f"{date}.md"
    paths = {"feed": feed_path, "archive": archive_path, "sample": sample_path}
    if dry_run:
        return paths
    feed = upsert_item(load_feed(feed_path), item)
    write_json(feed_path, feed)
    write_json(archive_path, item)
    write_text(sample_path, item.get("markdown") or "")
    return paths
