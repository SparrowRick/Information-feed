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
    SAFE_INDEX_CODES,
    enrich_limit_items,
    height_from_pool,
    index_avg_change,
    index_map,
    merge_core_metrics,
    pool_metrics,
    promotion_stats,
    qualifies_true_height,
    snapshot_breadth,
    summarize_dragon_tiger,
    two_market_turnover,
    volume_expansion_day,
)
from review.narrative import (
    build_core_conflict,
    build_market_switches,
    build_risks,
    build_summary,
    iso_shanghai,
    render_markdown,
)
from review.publish import load_feed, publish
from review.sectors import attach_index_quotes, match_index
from review.themes import (
    broken_high_boards,
    cluster_limit_up,
    event_theme_rows,
    falsified_and_rotation,
    incremental_branch,
    ladder_entries,
    sector_rotation,
    select_industry_lines,
    settle_yesterday_themes,
    strong_first_boards,
    structure_rows,
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
    volume_day: dict[str, Any] | None = None,
    catalog: list[dict[str, Any]] | None = None,
    index_quotes: list[dict[str, Any]] | None = None,
    hist_by_code: dict[str, list[dict[str, Any]]] | None = None,
    dragon_tiger: dict[str, Any] | None = None,
    gaps: list[str] | None = None,
) -> dict[str, Any]:
    today_up = enrich_limit_items(
        today_pools["limit_up"],
        snapshot=snapshot,
        break_pool=today_pools["limit_break"],
    )
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
        for key in (
            "turnover",
            "up",
            "down",
            "flat",
            "median_pct",
            "index_avg_pct",
            "non_st_limit_up",
            "non_st_limit_down",
            "non_st_limit_break",
            "promotion_rate",
        ):
            if prev_today.get(key) not in (None, 0, 0.0):
                yday_core[key] = prev_today[key]

    promo = promotion_stats(yday_up, today_up)
    today_core["promotion_rate"] = promo["rate"]
    today_core["promotion_eligible"] = promo["eligible"]
    today_core["promotion_count"] = promo["promoted"]
    avg = index_avg_change(index_items)
    if avg is not None:
        today_core["index_avg_pct"] = avg

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
    if catalog:
        sectors = attach_index_quotes(
            sectors,
            catalog,
            index_quotes or [],
            hist_by_code=hist_by_code,
            date_str=date,
            prev_date=prev_date,
        )
    nominal_h, true_h, nominal_leaders, true_leaders = height_from_pool(
        today_up, break_pool=today_break, snapshot=snapshot
    )
    today_core["nominal_height"] = nominal_h
    today_core["true_height"] = true_h
    first_boards = strong_first_boards(today_up)
    excluded = _true_excluded_names(today_up, today_break, snapshot)
    inc = incremental_branch(today_clusters, yday_clusters, today_up)
    industry = select_industry_lines(
        yesterday_themes=y_themes,
        yesterday_clusters=yday_clusters,
        today_clusters=today_clusters,
        incremental=inc,
        today_pool=today_up,
        true_leaders=true_leaders,
    )
    rot = falsified_and_rotation(
        y_themes, today_clusters, {x["name"] for x in industry}
    )

    switches = build_market_switches(today_core, yday_core, index_items)
    summary = build_summary(date, today_core, yday_core, index_items, y_themes, sectors)
    conflict = build_core_conflict(today_core, yday_core, index_items, y_themes, sectors)
    risks = build_risks(today_core, yday_core, y_themes, anomalies, excluded)

    cutoff_at = f"{date}T17:00:00+08:00"
    review_id = f"review-{date}"
    gap_list = list(gaps or [])
    gap_list.append("无板块主力净流入/资金强度，价量不代替资金")
    gap_list.append("盘前预判结账待盘前 feed 稳定后接入")
    gap_list.append("无盘中 9:45/10:00 路径记录")
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
        "volume_day": volume_day,
        "yesterday_themes": y_themes,
        "incremental_branch": inc,
        "ladder": {
            "nominal": ladder_entries(nominal_leaders),
            "true": ladder_entries(true_leaders),
            "strong_first_boards": [
                {
                    "name": x["name"],
                    "reason": x.get("reason") or "",
                    "seal_money": x.get("seal_money"),
                    "turnover": x.get("turnover"),
                    "open_times": x.get("open_times"),
                    "seal_ratio_pct": x.get("seal_ratio_pct"),
                }
                for x in first_boards
            ],
        },
        "structure_rows": structure_rows(
            first_boards=first_boards,
            nominal=ladder_entries(nominal_leaders),
            true_leaders=true_leaders,
        ),
        "broken_high_boards": broken_high_boards(
            yday_up, today_up, snapshot=snapshot
        ),
        "sector_rotation": sectors,
        "industry_lines": industry,
        "rotation": rot,
        "event_themes": event_theme_rows(today_clusters),
        "dragon_tiger": dragon_tiger,
        "risks": risks,
        "markdown": "",
        "audit": {
            "sources": ["HiThink Financial-API"],
            "generated_at": generated_at,
            "data_as_of": data_as_of or cutoff_at,
            "previous_trading_day": prev_date,
            "gaps": gap_list,
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

    gaps: list[str] = []
    if not use_snapshot:
        gaps.append("全市场快照仅最新交易日可用，本日涨跌家数/中位涨跌幅可能缺失")

    log("fetch index snapshot")
    index_items: list[dict[str, Any]] = []
    try:
        index_items = client.index_snapshot(SAFE_INDEX_CODES)
    except Exception as exc:  # noqa: BLE001
        log(f"index snapshot skipped: {type(exc).__name__}")
        gaps.append("核心指数快照失败")
    for code, label in INDEX_UNIVERSE:
        if code in SAFE_INDEX_CODES:
            continue
        try:
            extra = client.index_snapshot([code])
            index_items.extend(extra)
        except Exception as exc:  # noqa: BLE001
            log(f"{label} snapshot skipped: {type(exc).__name__}")
            gaps.append(f"{label}行情不可用")

    anomalies: list[dict[str, Any]] = []
    try:
        log("fetch anomaly-analysis-list")
        anomalies = client.anomaly_analysis_list(date)
        log(f"  anomalies={len(anomalies)}")
    except Exception as exc:  # noqa: BLE001 — anomaly is auxiliary
        log(f"anomaly list skipped: {type(exc).__name__}")

    dragon_tiger: dict[str, Any] | None = None
    try:
        log("fetch dragon-tiger-list")
        raw_dt = client.dragon_tiger_list(date)
        if raw_dt:
            dragon_tiger = summarize_dragon_tiger(raw_dt)
    except Exception as exc:  # noqa: BLE001
        log(f"dragon-tiger skipped: {type(exc).__name__}")
        gaps.append("龙虎榜未取到")

    catalog: list[dict[str, Any]] = []
    try:
        log("fetch THS concept/industry catalog")
        catalog = client.ths_index_list("cn_concept") + client.ths_index_list("industry")
        log(f"  catalog={len(catalog)}")
    except Exception as exc:  # noqa: BLE001
        log(f"index catalog skipped: {type(exc).__name__}")
        gaps.append("同花顺板块目录未取到")

    y_turnover = 0.0
    t_turnover_fb = 0.0
    volume_day: dict[str, Any] | None = None
    earlier = [d for d in trading_days if d <= date]
    hist_start = earlier[-12] if len(earlier) >= 12 else (earlier[0] if earlier else date)
    sh_bars: list[dict[str, Any]] = []
    sz_bars: list[dict[str, Any]] = []
    try:
        log("fetch index historical SH/SZ")
        sh_bars = client.index_historical("000001.SH", hist_start, date)
        sz_bars = client.index_historical("399001.SZ", hist_start, date)
        if prev_date:
            y_turnover = two_market_turnover(sh_bars, sz_bars, prev_date)
        t_turnover_fb = two_market_turnover(sh_bars, sz_bars, date)
        volume_day = volume_expansion_day(sh_bars, sz_bars, date)
    except Exception as exc:  # noqa: BLE001
        log(f"index historical skipped: {type(exc).__name__}")

    index_quotes: list[dict[str, Any]] = []
    hist_by_code: dict[str, list[dict[str, Any]]] = {}
    if catalog and use_snapshot:
        today_up_preview = today_pools.get("limit_up") or []
        preview = cluster_limit_up(today_up_preview)[:8]
        codes: list[str] = []
        for cluster in preview:
            matched = match_index(str(cluster.get("name") or ""), catalog)
            if matched and matched.get("thscode"):
                code = str(matched["thscode"])
                if code not in codes:
                    codes.append(code)
        if codes:
            try:
                log(f"fetch {len(codes)} sector index snapshots")
                index_quotes = client.index_snapshot(codes)
            except Exception as exc:  # noqa: BLE001
                log(f"sector snapshot skipped: {type(exc).__name__}")
                gaps.append("板块指数快照未取到")
            for code in codes[:6]:
                try:
                    hist_by_code[code] = client.index_historical(
                        code, prev_date or date, date
                    )
                except Exception as exc:  # noqa: BLE001
                    log(f"sector hist {code} skipped: {type(exc).__name__}")
    elif catalog and not use_snapshot:
        gaps.append("非最新交易日不拉板块快照，避免串到当日价量")

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
        volume_day=volume_day,
        catalog=catalog,
        index_quotes=index_quotes,
        hist_by_code=hist_by_code,
        dragon_tiger=dragon_tiger,
        gaps=gaps,
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
