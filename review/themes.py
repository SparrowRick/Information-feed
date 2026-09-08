"""Yesterday-theme settlement and concept/sector heat clustering."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from review.metrics import _num, board_count, is_st_stock

_SPLIT = re.compile(r"[+＋、,，/|；;]")
_SKIP_TOKENS = {
    "",
    "其他",
    "综合",
    "无",
    "None",
    "null",
}


def split_reason(reason: Any) -> list[str]:
    if reason is None:
        return []
    if isinstance(reason, list):
        tokens: list[str] = []
        for part in reason:
            tokens.extend(split_reason(part))
        return tokens
    text = str(reason).strip()
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in _SPLIT.split(text):
        token = raw.strip()
        if not token or token in _SKIP_TOKENS or token in seen:
            continue
        if len(token) > 24:
            continue
        seen.add(token)
        out.append(token)
    return out


def _code_key(item: dict[str, Any]) -> str:
    return str(item.get("thscode") or item.get("ticker") or item.get("name") or "")


def cluster_limit_up(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for item in pool:
        if is_st_stock(item):
            continue
        tokens = split_reason(item.get("limit_up_reason"))
        if not tokens:
            continue
        weight = max(board_count(item), 1)
        chg = _num(item.get("price_change_ratio_pct"))
        name = str(item.get("name") or "")
        for token in tokens:
            bucket = buckets.setdefault(
                token,
                {
                    "name": token,
                    "weight": 0.0,
                    "count": 0,
                    "change_sum": 0.0,
                    "stocks": [],
                    "max_board": 0,
                    "codes": set(),
                },
            )
            code = _code_key(item)
            if code and code in bucket["codes"]:
                continue
            if code:
                bucket["codes"].add(code)
            bucket["weight"] += weight
            bucket["count"] += 1
            bucket["change_sum"] += chg
            bucket["max_board"] = max(bucket["max_board"], board_count(item))
            if name and name not in bucket["stocks"]:
                bucket["stocks"].append(name)
    clusters = []
    for bucket in buckets.values():
        count = bucket["count"] or 1
        clusters.append(
            {
                "name": bucket["name"],
                "heat": round(float(bucket["weight"]), 2),
                "count": bucket["count"],
                "change_pct": round(bucket["change_sum"] / count, 3),
                "stocks": bucket["stocks"][:8],
                "max_board": bucket["max_board"],
            }
        )
    clusters.sort(key=lambda x: (x["heat"], x["count"], x["max_board"]), reverse=True)
    return clusters


def cluster_anomaly(anomalies: list[dict[str, Any]]) -> dict[str, list[str]]:
    """token -> stock names from keyword_list / tag_name."""
    mapping: dict[str, list[str]] = defaultdict(list)
    for item in anomalies:
        name = str(item.get("stock_name") or item.get("name") or "")
        tokens = split_reason(item.get("keyword_list"))
        tag = str(item.get("tag_name") or "").strip()
        if tag and tag not in {"涨停", "跌停", "大涨", "大跌", "快速拉升", "快速下挫"}:
            tokens.append(tag)
        for token in tokens:
            if name and name not in mapping[token]:
                mapping[token].append(name)
    return dict(mapping)


def _avg_change_for_names(
    names: list[str], snapshot_by_name: dict[str, dict[str, Any]]
) -> float | None:
    pcts: list[float] = []
    for name in names:
        row = snapshot_by_name.get(name)
        if not row:
            continue
        if row.get("price_change_ratio_pct") is None:
            continue
        pcts.append(_num(row.get("price_change_ratio_pct")))
    if not pcts:
        return None
    return round(sum(pcts) / len(pcts), 3)


def snapshot_by_name(
    snapshot: list[dict[str, Any]], limit_up: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in limit_up:
        name = str(row.get("name") or "")
        if name:
            out[name] = row
    # snapshot has no name; skip
    return out


def settle_yesterday_themes(
    yesterday_clusters: list[dict[str, Any]],
    today_clusters: list[dict[str, Any]],
    *,
    yesterday_pool: list[dict[str, Any]],
    today_pool: list[dict[str, Any]],
    snapshot: list[dict[str, Any]] | None = None,
    top_n: int = 6,
) -> list[dict[str, Any]]:
    today_by = {c["name"]: c for c in today_clusters}
    name_to_today_chg: dict[str, float] = {}
    for row in today_pool:
        name = str(row.get("name") or "")
        if name:
            name_to_today_chg[name] = _num(row.get("price_change_ratio_pct"))
    if snapshot:
        for row in snapshot:
            ticker = str(row.get("ticker") or "")
            if ticker:
                name_to_today_chg.setdefault(
                    ticker, _num(row.get("price_change_ratio_pct"))
                )

    snap_by_code: dict[str, dict[str, Any]] = {}
    for row in snapshot or []:
        for key in (row.get("thscode"), row.get("ticker")):
            if key:
                snap_by_code[str(key)] = row
    for row in today_pool:
        for key in (row.get("thscode"), row.get("ticker"), row.get("name")):
            if key:
                snap_by_code.setdefault(str(key), row)

    y_members: dict[str, list[str]] = {}
    y_codes: dict[str, list[str]] = {}
    for item in yesterday_pool:
        tokens = split_reason(item.get("limit_up_reason"))
        name = str(item.get("name") or "")
        codes = [c for c in (item.get("thscode"), item.get("ticker"), name) if c]
        for token in tokens:
            if name and name not in y_members.setdefault(token, []):
                y_members[token].append(name)
            for code in codes:
                if str(code) not in y_codes.setdefault(token, []):
                    y_codes[token].append(str(code))

    settled: list[dict[str, Any]] = []
    for cluster in yesterday_clusters[:top_n]:
        name = cluster["name"]
        today = today_by.get(name)
        members = y_members.get(name) or cluster.get("stocks") or []
        member_chgs = [name_to_today_chg[n] for n in members if n in name_to_today_chg]
        if not member_chgs:
            for code in y_codes.get(name) or []:
                row = snap_by_code.get(code)
                if row and row.get("price_change_ratio_pct") is not None:
                    member_chgs.append(_num(row.get("price_change_ratio_pct")))
        avg = round(sum(member_chgs) / len(member_chgs), 3) if member_chgs else None
        if avg is None and today:
            avg = today.get("change_pct")
        y_count = cluster.get("count") or 0
        t_count = today.get("count") if today else 0
        t_heat = today.get("heat") if today else 0
        y_heat = cluster.get("heat") or 0
        still_limit = t_count or 0
        down_members = sum(1 for c in member_chgs if c < -1)
        up_members = sum(1 for c in member_chgs if c > 3)

        if still_limit >= max(2, int(y_count * 0.7)) and t_heat >= y_heat * 0.8:
            status = "加强"
        elif still_limit == 0 and (avg is not None and avg < 0 or down_members >= 2):
            status = "证伪"
        elif still_limit > 0 and (down_members >= 1 and up_members >= 1 or (avg is not None and -1 <= avg <= 3)):
            status = "分化"
        elif still_limit > 0 and (t_heat < y_heat * 0.8 or (avg is not None and avg < 5)):
            status = "走弱"
        elif still_limit == 0:
            status = "走弱" if (avg is not None and avg >= 0) else "证伪"
        else:
            status = "分化"

        if avg is None:
            avg = 0.0
        leaders = (today.get("stocks") if today else members)[:3]
        note_bits = []
        if still_limit:
            note_bits.append(f"今日涨停{still_limit}只")
        else:
            note_bits.append("今日无涨停接力")
        if leaders:
            note_bits.append("代表：" + "、".join(leaders))
        settled.append(
            {
                "name": name,
                "status": status,
                "change_pct": round(float(avg), 3),
                "note": "；".join(note_bits),
            }
        )
    return settled


def sector_rotation(
    today_clusters: list[dict[str, Any]],
    yesterday_clusters: list[dict[str, Any]],
    *,
    anomalies: list[dict[str, Any]] | None = None,
    top_n: int = 8,
) -> list[dict[str, Any]]:
    y_by = {c["name"]: c for c in yesterday_clusters}
    anomaly_map = cluster_anomaly(anomalies or [])
    rows: list[dict[str, Any]] = []
    for cluster in today_clusters[:top_n]:
        name = cluster["name"]
        prev = y_by.get(name)
        heat = cluster["heat"]
        if prev:
            if heat >= prev["heat"] * 1.1:
                status = "加强"
            elif heat <= prev["heat"] * 0.6:
                status = "退潮"
            else:
                status = "延续"
            note = f"昨热度{prev['heat']:.0f} → 今{heat:.0f}"
        else:
            status = "新方向"
            note = "昨日涨停池未形成该簇"
        extra_names = anomaly_map.get(name) or []
        if extra_names:
            note += "；异动：" + "、".join(extra_names[:3])
        stocks = cluster.get("stocks") or []
        if stocks:
            note += "；" + "、".join(stocks[:3])
        rows.append(
            {
                "name": name,
                "heat": heat,
                "change_pct": cluster.get("change_pct") or 0.0,
                "status": status,
                "note": note,
            }
        )
    return rows


def strong_first_boards(pool: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    first = []
    for item in pool:
        if is_st_stock(item) or item.get("is_new") is True:
            continue
        if board_count(item) != 1:
            continue
        first.append(item)

    def _time_key(item: dict[str, Any]) -> str:
        return str(item.get("limit_up_time") or "99:99")

    first.sort(
        key=lambda x: (-_num(x.get("seal_money")), _time_key(x), -_num(x.get("max_seal_money"))),
    )
    out = []
    for item in first[:limit]:
        out.append(
            {
                "name": str(item.get("name") or ""),
                "reason": str(item.get("limit_up_reason") or ""),
                "seal_money": _num(item.get("seal_money")),
                "limit_up_time": str(item.get("limit_up_time") or ""),
            }
        )
    return out


def ladder_entries(
    leaders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for item in leaders:
        rows.append(
            {
                "name": str(item.get("name") or ""),
                "board": board_count(item),
                "reason": str(item.get("limit_up_reason") or item.get("continue_day_text") or ""),
            }
        )
    return rows
