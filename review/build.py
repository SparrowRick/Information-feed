"""CLI entry: python -m review.build --date YYYY-MM-DD --out out"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from review.calendar import (
    is_trading_day,
    latest_completed_trading_day,
    load_trading_days,
    previous_trading_day,
)
from review.client import HiThinkClient
from review.metrics import (
    INDEX_UNIVERSE,
    height_from_pool,
    index_map,
    merge_core_metrics,
    pool_metrics,
    qualifies_true_height,
    snapshot_breadth,
    two_market_turnover,
)
from review.narrative import (
    build_core_conflict,
    build_market_switches,
    build_risks,
    build_scenarios,
    build_summary,
    iso_shanghai,
    render_markdown,
)
from review.publish import load_feed, publish
from review.themes import (
    cluster_limit_up,
    ladder_entries,
    sector_rotation,
    settle_yesterday_themes,
    strong_first_boards,
)


def log(msg: str) -> None:
    print(f"[review] {msg}", file=sys.stderr)


def _find_prev_item(out_dir: Path, prev_date: str | None) -> dict[str, Any] | None:
    if not prev_date:
        return None
    wanted = f"review-{prev_date}"
    feed = load_feed(out_dir / "review-feed.json")
    for item in feed.get("items") or []:
        if isinstance(item, dict) and item.get("id") == wanted:
            return item
    archive = out_dir / "archive" / "review" / f"{prev_date}.json"
    if archive.exists():
        try:
            with archive.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            return None
    return None


def _true_excluded_names(
    limit_up: list[dict[str, Any]],
    break_pool: list[dict[str, Any]],
    snapshot: list[dict[str, Any]],
) -> list[str]:
    from review.metrics import board_count

    if not limit_up:
        return []
    max_board = max(board_count(x) for x in limit_up)
    names = []
    for item in limit_up:
        if board_count(item) != max_board:
            continue
        if qualifies_true_height(
            item, break_by_code=None, snapshot_by_code=None
        ):
            continue
        name = str(item.get("name") or "")
        if name:
            names.append(name)
    _ = (break_pool, snapshot)
    return names


def fetch_day_pools(client: HiThinkClient, date: str) -> dict[str, list[dict[str, Any]]]:
    log(f"fetch pools {date}")
    up = client.limit_up_pool(date)
    down = client.limit_down_pool(date)
    brk = client.limit_break_pool(date)
    log(f"  limit-up={len(up)} limit-down={len(down)} limit-break={len(brk)}")
    return {"limit_up": up, "limit_down": down, "limit_break": brk}


def build_item(
    *,
    date: str,
    prev_date: str | None,
    today_pools: dict[str, list[dict[str, Any]]],
    yday_pools: dict[str, list[dict[str, Any]]],
    snapshot: list[dict[str, Any]],
    index_items: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    prev_item: dict[str, Any] | None,
    y_turnover: float,
    t_turnover_fallback: float,
    generated_at: str,
    data_as_of: str | None,
) -> dict[str, Any]:
    today_up = today_pools["limit_up"]
    today_down = today_pools["limit_down"]
    today_break = today_pools["limit_break"]
    yday_up = yday_pools.get("limit_up") or []
    yday_down = yday_pools.get("limit_down") or []
    yday_break = yday_pools.get("limit_break") or []

    breadth = snapshot_breadth(snapshot) if snapshot else None
    today_pool_m = pool_metrics(today_up, today_down, today_break, snapshot=snapshot)
    yday_pool_m = pool_metrics(yday_up, yday_down, yday_break)

    today_core = merge_core_metrics(
        breadth=breadth,
        pools=today_pool_m,
        turnover_override=None if breadth and breadth.get("turnover") else t_turnover_fallback,
    )
    yday_core = merge_core_metrics(
        breadth=None,
        pools=yday_pool_m,
        turnover_override=y_turnover,
    )
    if prev_item:
        prev_today = (prev_item.get("core_metrics") or {}).get("today") or {}
        for key in ("turnover", "up", "down", "flat", "median_pct"):
            if prev_today.get(key):
                yday_core[key] = prev_today[key]

    today_clusters = cluster_limit_up(today_up)
    yday_clusters = cluster_limit_up(yday_up)
    y_themes = settle_yesterday_themes(
        yday_clusters,
        today_clusters,
        yesterday_pool=yday_up,
        today_pool=today_up,
        snapshot=snapshot,
    )
    sectors = sector_rotation(
        today_clusters, yday_clusters, anomalies=anomalies
    )
    nominal_h, true_h, nominal_leaders, true_leaders = height_from_pool(
        today_up, break_pool=today_break, snapshot=snapshot
    )
    today_core["nominal_height"] = nominal_h
    today_core["true_height"] = true_h
    first_boards = strong_first_boards(today_up)
    excluded = _true_excluded_names(today_up, today_break, snapshot)

    switches = build_market_switches(today_core, yday_core, index_items)
    summary = build_summary(date, today_core, yday_core, index_items, y_themes, sectors)
    conflict = build_core_conflict(today_core, yday_core, index_items, y_themes, sectors)
    risks = build_risks(today_core, yday_core, y_themes, anomalies, excluded)
    scenarios = build_scenarios(today_core, y_themes, sectors)

    cutoff_at = f"{date}T17:00:00+08:00"
    review_id = f"review-{date}"
    item: dict[str, Any] = {
        "id": review_id,
        "type": "review",
        "title": f"{date} 主线热度复盘",
        "date": date,
        "timezone": "Asia/Shanghai",
        "generated_at": generated_at,
        "cutoff_at": cutoff_at,
        "is_trading_day": True,
        "summary": summary,
        "core_conflict": conflict,
        "market_switches": switches,
        "core_metrics": {"today": today_core, "yesterday": yday_core},
        "yesterday_themes": y_themes,
        "ladder": {
            "nominal": ladder_entries(nominal_leaders),
            "true": ladder_entries(true_leaders),
            "strong_first_boards": [
                {"name": x["name"], "reason": x.get("reason") or ""} for x in first_boards
            ],
        },
        "sector_rotation": sectors,
        "risks": risks,
        "next_day_scenarios": scenarios,
        "markdown": "",
        "audit": {
            "sources": ["HiThink Financial-API"],
            "generated_at": generated_at,
            "data_as_of": data_as_of or cutoff_at,
            "previous_trading_day": prev_date,
        },
    }
    item["markdown"] = render_markdown(item, index_items=index_items)
    return item


def run(
    *,
    date: str | None,
    out_dir: Path,
    dry_run: bool,
    skip_non_trading: bool,
) -> int:
    client = HiThinkClient()
    trading_days = load_trading_days(client)
    if not trading_days:
        log("trading calendar empty")
        return 1

    if date:
        if not is_trading_day(date, trading_days):
            prev = previous_trading_day(date, trading_days)
            msg = f"非交易日：{date}"
            if skip_non_trading:
                if prev:
                    log(f"{msg}，改用上一交易日 {prev}")
                    date = prev
                else:
                    print(f"{msg}，日历窗口内无上一交易日，跳过生成。")
                    return 0
            else:
                print(f"{msg}，不生成虚假数据。")
                return 0
    else:
        date = latest_completed_trading_day(trading_days)
        if not date:
            print("无法确定最近已完成交易日，跳过生成。")
            return 0
        log(f"default date {date}")

    prev_date = previous_trading_day(date, trading_days)
    latest = trading_days[-1]
    use_snapshot = date == latest
    generated_at = iso_shanghai()

    today_pools = fetch_day_pools(client, date)
    yday_pools: dict[str, list[dict[str, Any]]] = {
        "limit_up": [],
        "limit_down": [],
        "limit_break": [],
    }
    if prev_date:
        yday_pools = fetch_day_pools(client, prev_date)

    snapshot: list[dict[str, Any]] = []
    data_as_of = None
    if use_snapshot:
        log("fetch full-market snapshot")
        snapshot = client.prices_snapshot()
        log(f"  snapshot={len(snapshot)}")
        if snapshot:
            # snapshot payload itself has no per-row timestamp; use now
            data_as_of = generated_at

    log("fetch index snapshot")
    index_items = client.index_snapshot([code for code, _ in INDEX_UNIVERSE])
    anomalies: list[dict[str, Any]] = []
    try:
        log("fetch anomaly-analysis-list")
        anomalies = client.anomaly_analysis_list(date)
        log(f"  anomalies={len(anomalies)}")
    except Exception as exc:  # noqa: BLE001 — anomaly is auxiliary
        log(f"anomaly list skipped: {type(exc).__name__}")

    y_turnover = 0.0
    t_turnover_fb = 0.0
    hist_start = prev_date or date
    try:
        log("fetch index historical SH/SZ")
        sh_bars = client.index_historical("000001.SH", hist_start, date)
        sz_bars = client.index_historical("399001.SZ", hist_start, date)
        if prev_date:
            y_turnover = two_market_turnover(sh_bars, sz_bars, prev_date)
        t_turnover_fb = two_market_turnover(sh_bars, sz_bars, date)
    except Exception as exc:  # noqa: BLE001
        log(f"index historical skipped: {type(exc).__name__}")

    # If snapshot turnover exists, prefer it; still keep index for yesterday.
    if index_items and not t_turnover_fb:
        imap = index_map(index_items)
        sh = imap.get("000001.SH") or {}
        sz = imap.get("399001.SZ") or {}
        t_turnover_fb = float(sh.get("turnover") or 0) + float(sz.get("turnover") or 0)

    prev_item = _find_prev_item(out_dir, prev_date)
    item = build_item(
        date=date,
        prev_date=prev_date,
        today_pools=today_pools,
        yday_pools=yday_pools,
        snapshot=snapshot,
        index_items=index_items,
        anomalies=anomalies,
        prev_item=prev_item,
        y_turnover=y_turnover,
        t_turnover_fallback=t_turnover_fb,
        generated_at=generated_at,
        data_as_of=data_as_of,
    )

    paths = publish(item, out_dir, dry_run=dry_run)
    print(f"date={date} id={item['id']} dry_run={dry_run}")
    print(f"title={item['title']}")
    print(f"summary={item['summary']}")
    if dry_run:
        print("dry-run: not written")
        print(item["markdown"][:1200])
    else:
        for key, path in paths.items():
            print(f"{key}={path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A股每日主线热度复盘")
    parser.add_argument("--date", help="交易日 YYYY-MM-DD；缺省为上海时区最近已收盘交易日")
    parser.add_argument("--out", default="out", help="输出目录（默认 out）")
    parser.add_argument("--dry-run", action="store_true", help="只计算不写文件")
    parser.add_argument(
        "--skip-non-trading",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="非交易日不造假数据（默认 true；若给了 --date 会回退到上一交易日）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    date = args.date
    if date:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            print("日期格式必须是 YYYY-MM-DD", file=sys.stderr)
            return 2
    out_dir = Path(args.out)
    try:
        return run(
            date=date,
            out_dir=out_dir,
            dry_run=bool(args.dry_run),
            skip_non_trading=bool(args.skip_non_trading),
        )
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
