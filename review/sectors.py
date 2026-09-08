"""Map limit-up reason clusters to THS concept/industry indices (price + turnover)."""

from __future__ import annotations

from typing import Any

from review.metrics import _num, index_bar_for_date, index_map

EVENT_TOKENS = frozenset(
    {
        "半年报增长",
        "中报增长",
        "中报扭亏",
        "年报增长",
        "业绩增长",
        "业绩预增",
        "业绩扭亏",
        "高送转",
        "股权激励",
        "回购",
        "增持",
        "减持",
        "重组",
        "资产注入",
    }
)

# 涨停原因常见简称 → 同花顺指数名子串
_ALIASES = {
    "AI应用": "人工智能",
    "AI智能体": "人工智能",
    "AI算力": "人工智能",
    "人形机器人": "机器人",
    "工业机器人": "机器人",
    "软件开发": "软件",
    "软件应用": "软件",
    "资源金属": "贵金属",
    "光伏概念": "光伏",
    "智能电网": "电网",
}


def is_event_token(name: str) -> bool:
    token = (name or "").strip()
    if token in EVENT_TOKENS:
        return True
    if "增长" in token and ("报" in token or "业绩" in token or "扭亏" in token):
        return True
    return False


def _norm(text: str) -> str:
    return (
        (text or "")
        .replace("概念", "")
        .replace("板块", "")
        .replace("行业", "")
        .replace("指数", "")
        .replace(" ", "")
        .strip()
    )


def match_index(
    cluster_name: str, catalog: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Best-effort name match; miss → None, never invent a code."""
    raw = (cluster_name or "").strip()
    if len(raw) < 2:
        return None
    needle = _norm(_ALIASES.get(raw, raw))
    if len(needle) < 2:
        return None
    exact = []
    contain = []
    for row in catalog:
        name = str(row.get("name") or "")
        if not name or not row.get("thscode"):
            continue
        n = _norm(name)
        if n == needle or name == raw:
            exact.append(row)
        elif needle in n or n in needle:
            contain.append(row)
    if exact:
        exact.sort(key=lambda x: len(str(x.get("name") or "")))
        return exact[0]
    if contain:
        contain.sort(key=lambda x: len(str(x.get("name") or "")))
        return contain[0]
    return None


def attach_index_quotes(
    clusters: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    *,
    hist_by_code: dict[str, list[dict[str, Any]]] | None = None,
    date_str: str | None = None,
    prev_date: str | None = None,
) -> list[dict[str, Any]]:
    """Fill index_thscode / index_change_pct / turnover / volume_ratio on copies."""
    qmap = index_map(quotes)
    out: list[dict[str, Any]] = []
    for cluster in clusters:
        row = dict(cluster)
        matched = match_index(str(cluster.get("name") or ""), catalog)
        if not matched:
            out.append(row)
            continue
        code = str(matched.get("thscode") or "")
        row["index_thscode"] = code
        row["index_name"] = str(matched.get("name") or "")
        quote = qmap.get(code)
        if quote:
            if quote.get("price_change_ratio_pct") is not None:
                row["index_change_pct"] = round(_num(quote.get("price_change_ratio_pct")), 3)
            row["index_turnover"] = _num(quote.get("turnover"))
        hist = (hist_by_code or {}).get(code) or []
        if hist and date_str and prev_date:
            today_bar = index_bar_for_date(hist, date_str)
            prev_bar = index_bar_for_date(hist, prev_date)
            t = _num(today_bar.get("turnover") if today_bar else 0)
            p = _num(prev_bar.get("turnover") if prev_bar else 0)
            if t:
                row["index_turnover"] = t
            if p > 0 and t:
                row["volume_ratio"] = round(t / p, 2)
        out.append(row)
    return out
