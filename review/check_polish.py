"""Guardrail: LLM polish may only change prose fields, not computed data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from review.publish import load_feed, write_json, write_text, upsert_item

POLISHABLE = frozenset(
    {
        "title",
        "summary",
        "core_conflict",
        "markdown",
        "market_switches",
        "risks",
    }
)

# Top-level keys that must stay byte-for-byte equal after polish (JSON equality).
LOCKED_TOP = (
    "id",
    "type",
    "date",
    "timezone",
    "generated_at",
    "cutoff_at",
    "is_trading_day",
    "core_metrics",
    "volume_day",
    "yesterday_themes",
    "incremental_branch",
    "ladder",
    "structure_rows",
    "broken_high_boards",
    "sector_rotation",
    "industry_lines",
    "rotation",
    "event_themes",
    "dragon_tiger",
)


class PolishError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise PolishError(f"not an object: {path}")
    return data


def _item_from_feed(feed: dict[str, Any], review_id: str | None = None) -> dict[str, Any]:
    wanted = review_id or feed.get("latest_review_id")
    for item in feed.get("items") or []:
        if isinstance(item, dict) and item.get("id") == wanted:
            return item
    raise PolishError(f"feed missing item {wanted}")


def locked_diff(raw: dict[str, Any], polished: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in LOCKED_TOP:
        if raw.get(key) != polished.get(key):
            errors.append(f"locked field changed: {key}")
    raw_audit = dict(raw.get("audit") or {})
    pol_audit = dict(polished.get("audit") or {})
    for skip in ("polished",):
        raw_audit.pop(skip, None)
        pol_audit.pop(skip, None)
    if raw_audit != pol_audit:
        errors.append("locked field changed: audit")
    return errors


def _must_appear(md: str, token: str, label: str, errors: list[str]) -> None:
    if token and token not in md:
        errors.append(f"markdown missing {label}: {token}")


def markdown_still_has_numbers(item: dict[str, Any]) -> list[str]:
    md = item.get("markdown") or ""
    core = (item.get("core_metrics") or {}).get("today") or {}
    errors: list[str] = []
    _must_appear(md, str(item.get("date") or ""), "date", errors)
    lu = core.get("non_st_limit_up")
    if lu is None:
        lu = core.get("limit_up")
    if lu is not None:
        _must_appear(md, str(int(lu)), "non-ST/涨停家数", errors)
    if core.get("seal_rate") is not None:
        _must_appear(md, f"{float(core['seal_rate']):.1f}", "封板率", errors)
    if core.get("nominal_height") is not None:
        _must_appear(md, str(int(core["nominal_height"])), "名义高度", errors)
    if core.get("true_height") is not None:
        _must_appear(md, str(int(core["true_height"])), "真实高度", errors)
    return errors


def check(raw: dict[str, Any], polished: dict[str, Any]) -> list[str]:
    errors = locked_diff(raw, polished)
    errors.extend(markdown_still_has_numbers(polished))
    if not (polished.get("summary") or "").strip():
        errors.append("summary empty after polish")
    if not (polished.get("markdown") or "").strip():
        errors.append("markdown empty after polish")
    date = str(raw.get("date") or "")
    title = polished.get("title") or ""
    if date and date not in title and date.replace("-", "/") not in title:
        errors.append("title missing date")
    return errors


def mark_polished(item: dict[str, Any]) -> dict[str, Any]:
    audit = dict(item.get("audit") or {})
    audit["polished"] = True
    item["audit"] = audit
    return item


def sync_outputs(item: dict[str, Any], out_dir: Path) -> None:
    """Write polished item into feed + archive + markdown sample."""
    out_dir = Path(out_dir)
    date = item["date"]
    write_json(out_dir / "archive" / "review" / f"{date}.json", item)
    write_text(out_dir / "samples" / "review" / f"{date}.md", item.get("markdown") or "")
    feed_path = out_dir / "review-feed.json"
    feed = upsert_item(load_feed(feed_path), item)
    write_json(feed_path, feed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验润色未改动锁定字段")
    parser.add_argument("--raw", required=True, type=Path, help="润色前 archive JSON")
    parser.add_argument("--polished", required=True, type=Path, help="润色后 archive JSON")
    parser.add_argument("--feed", type=Path, help="可选：核对 review-feed.json 最新条")
    parser.add_argument("--out", type=Path, help="校验通过后写回 feed/archive/md")
    parser.add_argument("--mark", action="store_true", help="校验通过后打 audit.polished")
    args = parser.parse_args(argv)

    raw = _load(args.raw)
    polished = _load(args.polished)
    errors = check(raw, polished)
    if args.feed and args.feed.exists():
        feed = _load(args.feed)
        try:
            feed_item = _item_from_feed(feed, polished.get("id"))
        except PolishError as exc:
            errors.append(str(exc))
        else:
            errors.extend(locked_diff(raw, feed_item))
    if errors:
        print("polish check FAILED", file=sys.stderr)
        for err in errors:
            print(f"- {err}", file=sys.stderr)
        return 1
    if args.mark:
        polished = mark_polished(polished)
        write_json(args.polished, polished)
    if args.out:
        sync_outputs(polished, args.out)
    print("polish check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
