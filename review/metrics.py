"""Market statistics: breadth, limit pools, seal rate, nominal/true height."""

from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

# True-height MVP: drop ST / unopened IPOs; demote if the stock opened too
# many times or printed extremely high turnover (fields used when present).
TRUE_HEIGHT_OPEN_TIMES = 3
TRUE_HEIGHT_TURNOVER_RATIO = 30.0
TRUE_HEIGHT_HIGH_TURNOVER_YUAN = 2_000_000_000  # 20亿, only with high boards
TRUE_HEIGHT_HIGH_TURNOVER_BOARDS = 5
TRUE_HEIGHT_SEAL_RATIO = 1.0  # 封单/成交额 < 1% 且多次开板 → 伪强势
TRUE_HEIGHT_SEAL_OPEN_TIMES = 3
VOLUME_EXPANSION_THRESHOLD = 0.08

INDEX_UNIVERSE = [
    ("000001.SH", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("399006.SZ", "创业板指"),
    ("000688.SH", "科创50"),
    ("899050.BJ", "北证50"),
]
CORE_INDEX_CODES = [code for code, _ in INDEX_UNIVERSE]
# 指数快照文档只保证 .SH/.SZ/.TI；北证50 单独请求，失败不影响前四个。
SAFE_INDEX_CODES = [code for code, _ in INDEX_UNIVERSE if not code.endswith(".BJ")]


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def is_st_stock(item: dict[str, Any]) -> bool:
    if item.get("is_st") is True:
        return True
    name = str(item.get("name") or item.get("stock_name") or "")
    compact = name.upper().replace(" ", "")
    return compact.startswith("ST") or compact.startswith("*ST") or "ST" in compact[:4]


def is_new_stock(item: dict[str, Any]) -> bool:
    return item.get("is_new") is True


def empty_core_metrics() -> dict[str, Any]:
    return {
        "turnover": 0.0,
        "up": 0,
        "down": 0,
        "flat": 0,
        "median_pct": 0.0,
        "limit_up": 0,
        "limit_down": 0,
        "limit_break": 0,
        "seal_rate": 0.0,
        "break_rate": 0.0,
        "nominal_height": 0,
        "true_height": 0,
        "non_st_limit_up": 0,
        "non_st_limit_down": 0,
        "non_st_limit_break": 0,
        "promotion_rate": 0.0,
        "promotion_eligible": 0,
        "promotion_count": 0,
        "index_avg_pct": 0.0,
    }


def snapshot_breadth(snapshot: list[dict[str, Any]]) -> dict[str, Any]:
    """Turnover / up / down / flat / median from a full-market snapshot."""
    active: list[dict[str, Any]] = []
    turnover = 0.0
    for row in snapshot:
        to = _num(row.get("turnover"))
        vol = _num(row.get("volume"))
        turnover += to
        if to <= 0 and vol <= 0:
            continue
        if row.get("last_price") in (None, "", 0, 0.0):
            continue
        active.append(row)
    up = down = flat = 0
    pcts: list[float] = []
    for row in active:
        pct = _num(row.get("price_change_ratio_pct"))
        pcts.append(pct)
        if pct > 0.0001:
            up += 1
        elif pct < -0.0001:
            down += 1
        else:
            flat += 1
    median = float(statistics.median(pcts)) if pcts else 0.0
    return {
        "turnover": round(turnover, 2),
        "up": up,
        "down": down,
        "flat": flat,
        "median_pct": round(median, 4),
    }


def seal_rate(limit_up: int, limit_break: int) -> float:
    denom = limit_up + limit_break
    if denom <= 0:
        return 0.0
    return round(100.0 * limit_up / denom, 2)


def break_rate(limit_up: int, limit_break: int) -> float:
    """炸板率 = 炸板 / (涨停 + 炸板)，与样例口径一致。"""
    denom = limit_up + limit_break
    if denom <= 0:
        return 0.0
    return round(100.0 * limit_break / denom, 1)


def code_key(item: dict[str, Any]) -> str:
    return str(item.get("thscode") or item.get("ticker") or "")


def non_st_items(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for x in pool if not is_st_stock(x)]


def seal_ratio_pct(
    item: dict[str, Any], snap: dict[str, Any] | None = None
) -> float | None:
    seal = _num(item.get("seal_money"))
    turnover = _num(item.get("turnover"))
    if snap and turnover <= 0:
        turnover = _num(snap.get("turnover"))
    if seal <= 0 or turnover <= 0:
        return None
    return round(100.0 * seal / turnover, 2)


def _break_lookup(break_pool: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in break_pool:
        key = str(row.get("thscode") or row.get("ticker") or row.get("name") or "")
        if key:
            out[key] = row
        ticker = str(row.get("ticker") or "")
        if ticker:
            out[ticker] = row
    return out


def _snapshot_lookup(snapshot: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in snapshot:
        thscode = str(row.get("thscode") or "")
        ticker = str(row.get("ticker") or "")
        if thscode:
            out[thscode] = row
        if ticker:
            out[ticker] = row
    return out


def qualifies_true_height(
    item: dict[str, Any],
    *,
    break_by_code: dict[str, dict[str, Any]] | None = None,
    snapshot_by_code: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Return False if the name should be excluded from true height."""
    if is_st_stock(item) or is_new_stock(item):
        return False
    open_times = item.get("open_times")
    turnover_ratio = item.get("turnover_ratio_pct")
    thscode = str(item.get("thscode") or "")
    ticker = str(item.get("ticker") or "")
    extra = None
    if break_by_code:
        extra = break_by_code.get(thscode) or break_by_code.get(ticker)
    if extra:
        if open_times is None:
            open_times = extra.get("open_times")
        if turnover_ratio is None:
            turnover_ratio = extra.get("turnover_ratio_pct")
    if _int(open_times) >= TRUE_HEIGHT_OPEN_TIMES:
        return False
    if turnover_ratio is not None and _num(turnover_ratio) >= TRUE_HEIGHT_TURNOVER_RATIO:
        return False
    snap = None
    if snapshot_by_code:
        snap = snapshot_by_code.get(thscode) or snapshot_by_code.get(ticker)
    turnover = _num(item.get("turnover"))
    if snap and turnover <= 0:
        turnover = _num(snap.get("turnover"))
    boards = _int(item.get("continue_day_cnt") or item.get("board") or item.get("board_num"))
    if (
        boards >= TRUE_HEIGHT_HIGH_TURNOVER_BOARDS
        and turnover >= TRUE_HEIGHT_HIGH_TURNOVER_YUAN
    ):
        return False
    ratio = item.get("seal_ratio_pct")
    if ratio is None:
        ratio = seal_ratio_pct(item, snap)
    if (
        ratio is not None
        and _num(ratio) < TRUE_HEIGHT_SEAL_RATIO
        and (_int(open_times) >= TRUE_HEIGHT_SEAL_OPEN_TIMES or boards >= 5)
    ):
        return False
    return True


def board_count(item: dict[str, Any]) -> int:
    return _int(item.get("continue_day_cnt") or item.get("board") or item.get("board_num"))


def height_from_pool(
    pool: list[dict[str, Any]],
    *,
    break_pool: list[dict[str, Any]] | None = None,
    snapshot: list[dict[str, Any]] | None = None,
) -> tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (nominal, true, nominal_leaders, true_leaders)."""
    if not pool:
        return 0, 0, [], []
    break_by = _break_lookup(break_pool or [])
    snap_by = _snapshot_lookup(snapshot or [])
    ranked = sorted(pool, key=board_count, reverse=True)
    nominal = board_count(ranked[0])
    nominal_leaders = [x for x in ranked if board_count(x) == nominal][:6]
    true_candidates = [
        x
        for x in ranked
        if qualifies_true_height(x, break_by_code=break_by, snapshot_by_code=snap_by)
    ]
    if not true_candidates:
        return nominal, 0, nominal_leaders, []
    true_h = board_count(true_candidates[0])
    true_leaders = [x for x in true_candidates if board_count(x) == true_h][:6]
    return nominal, true_h, nominal_leaders, true_leaders


def pool_metrics(
    limit_up: list[dict[str, Any]],
    limit_down: list[dict[str, Any]],
    limit_break: list[dict[str, Any]],
    *,
    snapshot: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    nominal, true_h, _, _ = height_from_pool(
        limit_up, break_pool=limit_break, snapshot=snapshot
    )
    up_n = len(limit_up)
    down_n = len(limit_down)
    break_n = len(limit_break)
    ns_up = len(non_st_items(limit_up))
    ns_down = len(non_st_items(limit_down))
    ns_break = len(non_st_items(limit_break))
    return {
        "limit_up": up_n,
        "limit_down": down_n,
        "limit_break": break_n,
        "seal_rate": seal_rate(ns_up, ns_break),
        "break_rate": break_rate(ns_up, ns_break),
        "nominal_height": nominal,
        "true_height": true_h,
        "non_st_limit_up": ns_up,
        "non_st_limit_down": ns_down,
        "non_st_limit_break": ns_break,
    }


def merge_core_metrics(
    *,
    breadth: dict[str, Any] | None = None,
    pools: dict[str, Any] | None = None,
    turnover_override: float | None = None,
) -> dict[str, Any]:
    out = empty_core_metrics()
    if breadth:
        out.update({k: breadth[k] for k in ("turnover", "up", "down", "flat", "median_pct") if k in breadth})
    if pools:
        out.update(
            {
                k: pools[k]
                for k in (
                    "limit_up",
                    "limit_down",
                    "limit_break",
                    "seal_rate",
                    "break_rate",
                    "nominal_height",
                    "true_height",
                    "non_st_limit_up",
                    "non_st_limit_down",
                    "non_st_limit_break",
                )
                if k in pools
            }
        )
    if turnover_override is not None and (not breadth or not breadth.get("turnover")):
        out["turnover"] = round(float(turnover_override), 2)
    return out


def index_map(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in items:
        code = str(row.get("thscode") or "")
        if code:
            out[code] = row
    return out


def index_bar_for_date(bars: list[dict[str, Any]], date_str: str) -> dict[str, Any] | None:
    want = date_str.replace("-", "")
    for row in bars:
        ms = row.get("date_ms")
        if ms is None:
            continue
        try:
            got = datetime.fromtimestamp(int(ms) / 1000, tz=SHANGHAI).strftime("%Y%m%d")
        except (TypeError, ValueError, OSError):
            continue
        if got == want:
            return row
    return None


def two_market_turnover(
    sh_bars: list[dict[str, Any]],
    sz_bars: list[dict[str, Any]],
    date_str: str,
) -> float:
    sh = index_bar_for_date(sh_bars, date_str)
    sz = index_bar_for_date(sz_bars, date_str)
    return _num(sh.get("turnover") if sh else 0) + _num(sz.get("turnover") if sz else 0)


def enrich_limit_items(
    pool: list[dict[str, Any]],
    *,
    snapshot: list[dict[str, Any]] | None = None,
    break_pool: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach turnover / open_times / seal_ratio from snapshot and 炸板池."""
    snap_by = _snapshot_lookup(snapshot or [])
    break_by = _break_lookup(break_pool or [])
    out: list[dict[str, Any]] = []
    for item in pool:
        row = dict(item)
        ths = str(item.get("thscode") or "")
        ticker = str(item.get("ticker") or "")
        snap = snap_by.get(ths) or snap_by.get(ticker)
        brk = break_by.get(ths) or break_by.get(ticker)
        if snap and not _num(row.get("turnover")):
            row["turnover"] = snap.get("turnover")
        if brk:
            if row.get("open_times") is None:
                row["open_times"] = brk.get("open_times")
            if row.get("turnover_ratio_pct") is None:
                row["turnover_ratio_pct"] = brk.get("turnover_ratio_pct")
            if not _num(row.get("turnover")):
                row["turnover"] = brk.get("turnover")
        ratio = seal_ratio_pct(row, snap)
        if ratio is not None:
            row["seal_ratio_pct"] = ratio
        out.append(row)
    return out


def promotion_stats(
    yesterday_up: list[dict[str, Any]],
    today_up: list[dict[str, Any]],
) -> dict[str, Any]:
    """晋级率：昨日非 ST 涨停中，今日连板天数增加的比例。"""
    yday = non_st_items(yesterday_up)
    today_by = {code_key(x): x for x in today_up if code_key(x)}
    if not yday:
        return {"eligible": 0, "promoted": 0, "rate": 0.0}
    promoted = 0
    for item in yday:
        key = code_key(item)
        today = today_by.get(key)
        if today and board_count(today) > board_count(item):
            promoted += 1
    return {
        "eligible": len(yday),
        "promoted": promoted,
        "rate": round(100.0 * promoted / len(yday), 1),
    }


def _bar_date(row: dict[str, Any]) -> str | None:
    ms = row.get("date_ms")
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=SHANGHAI).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def turnover_series(
    sh_bars: list[dict[str, Any]], sz_bars: list[dict[str, Any]]
) -> list[tuple[str, float]]:
    by_date: dict[str, float] = {}
    for row in list(sh_bars) + list(sz_bars):
        day = _bar_date(row)
        if not day:
            continue
        by_date[day] = by_date.get(day, 0.0) + _num(row.get("turnover"))
    return sorted(by_date.items())


def volume_expansion_day(
    sh_bars: list[dict[str, Any]],
    sz_bars: list[dict[str, Any]],
    date_str: str,
    *,
    threshold: float = VOLUME_EXPANSION_THRESHOLD,
) -> dict[str, Any]:
    """最近一次两市成交额环比达到 threshold 的交易日（含当日）。"""
    series = [(d, v) for d, v in turnover_series(sh_bars, sz_bars) if d <= date_str]
    expansion: dict[str, Any] | None = None
    for i in range(1, len(series)):
        prev_date, prev_v = series[i - 1]
        cur_date, cur_v = series[i]
        if prev_v <= 0:
            continue
        rel = (cur_v - prev_v) / prev_v
        if rel >= threshold:
            expansion = {
                "date": cur_date,
                "turnover": round(cur_v, 2),
                "prev_date": prev_date,
                "prev_turnover": round(prev_v, 2),
                "change_pct": round(rel * 100.0, 1),
            }
    today_v = next((v for d, v in series if d == date_str), 0.0)
    prev_v = 0.0
    prev_date = None
    for d, v in series:
        if d < date_str:
            prev_date, prev_v = d, v
    today_vs_prev = None
    if prev_v:
        today_vs_prev = round(100.0 * (today_v - prev_v) / prev_v, 1)
    return {
        "expansion": expansion,
        "today_date": date_str,
        "today_turnover": round(today_v, 2),
        "prev_date": prev_date,
        "prev_turnover": round(prev_v, 2),
        "today_vs_prev_pct": today_vs_prev,
    }


def index_avg_change(index_items: list[dict[str, Any]]) -> float | None:
    pcts = []
    by_code = index_map(index_items)
    for code, _ in INDEX_UNIVERSE:
        row = by_code.get(code)
        if row and row.get("price_change_ratio_pct") is not None:
            pcts.append(_num(row.get("price_change_ratio_pct")))
    if not pcts:
        return None
    return round(sum(pcts) / len(pcts), 3)


def summarize_dragon_tiger(data: dict[str, Any], limit: int = 6) -> dict[str, Any]:
    stocks = [x for x in (data.get("stock_items") or []) if isinstance(x, dict)]
    ranked = sorted(stocks, key=lambda x: abs(_num(x.get("net_value"))), reverse=True)
    rows = []
    for item in ranked[:limit]:
        rows.append(
            {
                "name": str(item.get("name") or ""),
                "net_value": _num(item.get("net_value")),
                "org_net_value": _num(item.get("org_net_value")),
                "hot_money_net_value": _num(item.get("hot_money_net_value")),
                "change_pct": _num(item.get("change")),
                "reason": str(item.get("limit_reason") or ""),
            }
        )
    hot = [x for x in (data.get("hot_money_items") or []) if isinstance(x, dict)]
    hot_rows = []
    for item in sorted(hot, key=lambda x: abs(_num(x.get("buying"))), reverse=True)[:5]:
        hot_rows.append(
            {
                "name": str(item.get("name") or ""),
                "buying": _num(item.get("buying")),
            }
        )
    return {
        "trade_date": str(data.get("trade_date") or ""),
        "stock_count": int(data.get("stock_count") or len(stocks)),
        "stocks": rows,
        "hot_money": hot_rows,
        "note": "龙虎榜席位净额，不是全市场主力净流入。",
    }
