"""Yesterday-theme settlement and concept/sector heat clustering."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from review.metrics import _num, board_count, code_key, is_st_stock
from review.sectors import is_event_token

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
                "turnover": _num(item.get("turnover")),
                "turnover_ratio_pct": item.get("turnover_ratio_pct"),
                "open_times": item.get("open_times") or 0,
                "seal_ratio_pct": item.get("seal_ratio_pct"),
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
                "open_times": item.get("open_times"),
                "turnover": _num(item.get("turnover")),
                "turnover_ratio_pct": item.get("turnover_ratio_pct"),
                "seal_ratio_pct": item.get("seal_ratio_pct"),
            }
        )
    return rows


def _first_board_members(
    pool: list[dict[str, Any]], token: str
) -> list[dict[str, Any]]:
    rows = []
    for item in pool:
        if is_st_stock(item) or board_count(item) != 1:
            continue
        if token not in split_reason(item.get("limit_up_reason")):
            continue
        rows.append(item)
    return rows


def incremental_branch(
    today_clusters: list[dict[str, Any]],
    yesterday_clusters: list[dict[str, Any]],
    today_pool: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """当日最大增量分支：非事件标签里，热度增量最大的簇。"""
    y_by = {c["name"]: c for c in yesterday_clusters}
    best: dict[str, Any] | None = None
    best_key: tuple[float, int, float] | None = None
    for cluster in today_clusters:
        name = str(cluster.get("name") or "")
        if is_event_token(name):
            continue
        y_heat = float((y_by.get(name) or {}).get("heat") or 0)
        delta = float(cluster.get("heat") or 0) - y_heat
        firsts = _first_board_members(today_pool, name)
        key = (delta, len(firsts), float(cluster.get("heat") or 0))
        if best_key is None or key > best_key:
            best_key = key
            best = {
                "name": name,
                "heat": cluster.get("heat"),
                "yesterday_heat": y_heat,
                "delta_heat": round(delta, 2),
                "count": cluster.get("count") or 0,
                "first_board_count": len(firsts),
                "change_pct": cluster.get("change_pct"),
                "stocks": [
                    {
                        "name": str(x.get("name") or ""),
                        "board": board_count(x),
                        "reason": str(x.get("limit_up_reason") or ""),
                        "turnover": _num(x.get("turnover")),
                        "turnover_ratio_pct": x.get("turnover_ratio_pct"),
                        "open_times": x.get("open_times") or 0,
                        "seal_ratio_pct": x.get("seal_ratio_pct"),
                    }
                    for x in firsts[:6]
                ],
                "note": (
                    f"昨热度{y_heat:.0f} → 今{float(cluster.get('heat') or 0):.0f}，"
                    f"原因匹配首板{len(firsts)}只"
                ),
            }
    if not best or best_key is None:
        return None
    delta, first_n, _heat = best_key
    if delta <= 0 and first_n < 2:
        return None
    return best


def broken_high_boards(
    yesterday_pool: list[dict[str, Any]],
    today_pool: list[dict[str, Any]],
    snapshot: list[dict[str, Any]] | None = None,
    *,
    min_board: int = 2,
) -> list[dict[str, Any]]:
    today_codes = {code_key(x) for x in today_pool if code_key(x)}
    snap_by: dict[str, dict[str, Any]] = {}
    for row in snapshot or []:
        for key in (row.get("thscode"), row.get("ticker")):
            if key:
                snap_by[str(key)] = row
    rows: list[dict[str, Any]] = []
    for item in yesterday_pool:
        if is_st_stock(item) or board_count(item) < min_board:
            continue
        key = code_key(item)
        if key and key in today_codes:
            continue
        snap = snap_by.get(key) if key else None
        chg = None
        if snap and snap.get("price_change_ratio_pct") is not None:
            chg = round(_num(snap.get("price_change_ratio_pct")), 3)
        rows.append(
            {
                "name": str(item.get("name") or ""),
                "board": board_count(item),
                "change_pct": chg,
                "reason": str(item.get("limit_up_reason") or ""),
            }
        )
    rows.sort(key=lambda x: x.get("board") or 0, reverse=True)
    return rows[:6]


def structure_rows(
    *,
    first_boards: list[dict[str, Any]],
    nominal: list[dict[str, Any]],
    true_leaders: list[dict[str, Any]],
    crowded: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """低位强封 vs 高位拥挤，供生死簿表。"""
    rows: list[dict[str, Any]] = []
    for item in first_boards[:4]:
        rows.append(
            {
                "position": "低位强封",
                "name": str(item.get("name") or ""),
                "board": 1,
                "turnover": _num(item.get("turnover") or item.get("seal_money")),
                "turnover_ratio_pct": item.get("turnover_ratio_pct"),
                "open_times": item.get("open_times") or 0,
                "seal_ratio_pct": item.get("seal_ratio_pct"),
                "reason": str(item.get("reason") or item.get("limit_up_reason") or ""),
            }
        )
    high = crowded or nominal
    seen = {r["name"] for r in rows}
    for item in high[:4]:
        name = str(item.get("name") or "")
        if name in seen:
            continue
        rows.append(
            {
                "position": "高位拥挤",
                "name": name,
                "board": item.get("board") or board_count(item),
                "turnover": _num(item.get("turnover")),
                "turnover_ratio_pct": item.get("turnover_ratio_pct"),
                "open_times": item.get("open_times") or 0,
                "seal_ratio_pct": item.get("seal_ratio_pct"),
                "reason": str(item.get("reason") or item.get("limit_up_reason") or ""),
            }
        )
        seen.add(name)
    _ = true_leaders
    return rows


def event_theme_rows(
    today_clusters: list[dict[str, Any]], limit: int = 6
) -> list[dict[str, Any]]:
    rows = []
    for cluster in today_clusters:
        if not is_event_token(str(cluster.get("name") or "")):
            continue
        rows.append(
            {
                "name": cluster["name"],
                "heat": cluster.get("heat"),
                "count": cluster.get("count") or 0,
                "change_pct": cluster.get("change_pct"),
                "stocks": (cluster.get("stocks") or [])[:4],
            }
        )
        if len(rows) >= limit:
            break
    return rows


def falsified_and_rotation(
    yesterday_themes: list[dict[str, Any]],
    today_clusters: list[dict[str, Any]],
    industry_names: set[str],
) -> dict[str, Any]:
    falsified = [t for t in yesterday_themes if t.get("status") == "证伪"]
    faded = [t for t in yesterday_themes if t.get("status") in {"证伪", "走弱"}]
    rotation = None
    for cluster in today_clusters:
        name = str(cluster.get("name") or "")
        if is_event_token(name) or name in industry_names:
            continue
        rotation = {
            "name": name,
            "heat": cluster.get("heat"),
            "change_pct": cluster.get("change_pct"),
            "count": cluster.get("count") or 0,
            "stocks": (cluster.get("stocks") or [])[:4],
            "note": "未进入资格线，只作并行轮动",
        }
        break
    return {"falsified": falsified, "faded": faded, "rotation": rotation}


def select_industry_lines(
    *,
    yesterday_themes: list[dict[str, Any]],
    yesterday_clusters: list[dict[str, Any]],
    today_clusters: list[dict[str, Any]],
    incremental: dict[str, Any] | None,
    today_pool: list[dict[str, Any]],
    true_leaders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """资格线深拆：0–2 条，不硬凑。

    次主线候选：昨日结账不是证伪的最强昨主线，且今日仍有涨停或成员未全面转负。
    新方向候选：当日最大增量分支，且（热度增量>0 且原因匹配首板≥2，或热度增量≥2）。
    两者同名时合并为一条。
    """
    today_by = {c["name"]: c for c in today_clusters}
    y_heat = {c["name"]: c.get("heat") or 0 for c in yesterday_clusters}
    true_names = {str(x.get("name") or "") for x in true_leaders}

    def _detail(name: str, role: str, why: str) -> dict[str, Any]:
        cluster = today_by.get(name) or {}
        firsts = _first_board_members(today_pool, name)
        members = []
        for item in today_pool:
            if name in split_reason(item.get("limit_up_reason")):
                members.append(item)
        height_names = [
            str(x.get("name") or "")
            for x in members
            if str(x.get("name") or "") in true_names
        ]
        anchors = sorted(members, key=lambda x: _num(x.get("turnover")), reverse=True)
        anchor_names = [str(x.get("name") or "") for x in anchors[:3] if x.get("name")]
        still = int(cluster.get("count") or 0)
        if still == 0:
            falsify = "今日无涨停接力则撤销观察"
        elif not firsts and not height_names:
            falsify = "次日价量转负或首板消失则撤销观察"
        else:
            falsify = "价量转负，或首板扩散失败、真实身位掉队"
        return {
            "name": name,
            "role": role,
            "selection_reason": why,
            "heat": cluster.get("heat") or 0,
            "yesterday_heat": y_heat.get(name, 0),
            "count": still,
            "change_pct": cluster.get("change_pct"),
            "height_names": height_names,
            "capacity_anchors": anchor_names,
            "first_boards": [str(x.get("name") or "") for x in firsts[:5]],
            "falsify": falsify,
        }

    lines: list[dict[str, Any]] = []
    lead = None
    for theme in yesterday_themes:
        name = str(theme.get("name") or "")
        if not name or is_event_token(name):
            continue
        if theme.get("status") == "证伪":
            continue
        today = today_by.get(name)
        still = int((today or {}).get("count") or 0)
        if still == 0:
            continue
        lead = name
        why = (
            f"昨日主线结账为{theme.get('status')}，"
            f"今日涨停{still}只，保留为次主线候选"
        )
        lines.append(_detail(name, "次主线候选", why))
        break

    inc = incremental
    if inc:
        name = str(inc.get("name") or "")
        delta = float(inc.get("delta_heat") or 0)
        first_n = int(inc.get("first_board_count") or 0)
        qualifies = (delta > 0 and first_n >= 2) or delta >= 2
        if qualifies and name and not is_event_token(name):
            if lead == name:
                lines[0]["role"] = "次主线候选兼新方向"
                lines[0]["selection_reason"] += "；同时是当日最大增量分支，不重复列"
            else:
                why = (
                    f"当日最大增量分支（热度+{delta:.0f}，"
                    f"原因匹配首板{first_n}只）"
                )
                lines.append(_detail(name, "新方向候选", why))
    return lines[:2]
