"""Chinese markdown / text sections for the daily review."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from review.metrics import INDEX_UNIVERSE, _num

SHANGHAI = ZoneInfo("Asia/Shanghai")


def fmt_yi(value: float | int | None) -> str:
    n = float(value or 0)
    if abs(n) >= 1e12:
        return f"{n / 1e12:.2f}万亿"
    if abs(n) >= 1e8:
        return f"{n / 1e8:.0f}亿"
    if abs(n) >= 1e4:
        return f"{n / 1e4:.0f}万"
    return f"{n:.0f}"


def fmt_pct(value: float | int | None, digits: int = 2) -> str:
    n = float(value or 0)
    sign = "+" if n > 0 else ""
    return f"{sign}{n:.{digits}f}%"


def fmt_seal_money(value: float | int | None) -> str:
    n = float(value or 0)
    if n >= 1e8:
        return f"{n / 1e8:.1f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.0f}万"
    return f"{n:.0f}"


def iso_shanghai(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(SHANGHAI)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI)
    return dt.astimezone(SHANGHAI).isoformat(timespec="seconds")


def ms_to_iso(ms: Any) -> str | None:
    try:
        value = int(ms)
    except (TypeError, ValueError):
        return None
    dt = datetime.fromtimestamp(value / 1000, tz=SHANGHAI)
    return iso_shanghai(dt)


def _index_line(index_items: list[dict[str, Any]]) -> str:
    by_code = {str(x.get("thscode") or ""): x for x in index_items}
    parts = []
    for code, label in INDEX_UNIVERSE:
        row = by_code.get(code)
        if not row:
            continue
        parts.append(f"{label} {fmt_pct(row.get('price_change_ratio_pct'))}")
    return "，".join(parts) if parts else "指数行情暂缺"


def build_summary(
    date: str,
    core: dict[str, Any],
    prev: dict[str, Any],
    index_items: list[dict[str, Any]],
    yesterday_themes: list[dict[str, Any]],
    sectors: list[dict[str, Any]],
) -> str:
    idx = _index_line(index_items)
    to_today = core.get("turnover") or 0
    to_y = prev.get("turnover") or 0
    to_bit = f"两市成交{fmt_yi(to_today)}"
    if to_y:
        delta = to_today - to_y
        to_bit += f"（{fmt_pct(100.0 * delta / to_y if to_y else 0, 1)}）"
    lead = sectors[0]["name"] if sectors else "题材"
    theme_fail = [t["name"] for t in yesterday_themes if t.get("status") in {"证伪", "走弱"}]
    theme_ok = [t["name"] for t in yesterday_themes if t.get("status") == "加强"]
    height = f"名义{core.get('nominal_height') or 0}板/真实{core.get('true_height') or 0}板"
    mood = []
    if theme_ok:
        mood.append("、".join(theme_ok[:2]) + "加强")
    if theme_fail:
        fail_status = "证伪" if all(
            t.get("status") == "证伪"
            for t in yesterday_themes
            if t.get("name") in theme_fail[:2]
        ) else "走弱"
        mood.append("、".join(theme_fail[:2]) + fail_status)
    mood_txt = "，".join(mood) if mood else "主线尚未完全收敛"
    return (
        f"{date} {idx}；{to_bit}；涨停{core.get('limit_up', 0)}、炸板{core.get('limit_break', 0)}、"
        f"跌停{core.get('limit_down', 0)}，封板率{core.get('seal_rate', 0):.1f}%；"
        f"连板{height}；盘面以{lead}为前排，{mood_txt}。"
    )


def build_core_conflict(
    core: dict[str, Any],
    prev: dict[str, Any],
    index_items: list[dict[str, Any]],
    yesterday_themes: list[dict[str, Any]],
    sectors: list[dict[str, Any]],
) -> str:
    by_code = {str(x.get("thscode") or ""): x for x in index_items}
    sh = _num((by_code.get("000001.SH") or {}).get("price_change_ratio_pct"))
    cyb = _num((by_code.get("399006.SZ") or {}).get("price_change_ratio_pct"))
    up = core.get("up") or 0
    down = core.get("down") or 0
    parts = []
    if sh * cyb < 0 or abs(sh - cyb) >= 0.6:
        parts.append("指数结构分化（权重与中小盘不同步）")
    if down > up * 1.2 and up:
        parts.append("跌多涨少，赚钱效应不足")
    if (core.get("true_height") or 0) < (core.get("nominal_height") or 0):
        parts.append("连板名义高度高于真实高度，高位成色打折")
    if (core.get("true_height") or 0) < (prev.get("true_height") or 0):
        parts.append("情绪高度回落")
    strengthened = [t["name"] for t in yesterday_themes if t.get("status") == "加强"]
    faded = [t["name"] for t in yesterday_themes if t.get("status") in {"走弱", "证伪"}]
    if strengthened and faded:
        parts.append(f"昨主线{('、'.join(faded[:2]))}退潮，资金切向{('、'.join(strengthened[:2]))}")
    elif faded and not strengthened:
        parts.append("昨主线今日结账偏弱，新方向尚未完全接管")
    elif not faded and strengthened:
        parts.append("昨主线仍在，但需要成交与高度同步确认")
    lead = sectors[0]["name"] if sectors else "题材"
    if (core.get("seal_rate") or 0) < 55:
        parts.append(f"封板率偏低，{lead}接力稳定性存疑")
    if not parts:
        parts.append("指数、成交与连板高度能否同时维持，是短线情绪的核心矛盾")
    return "；".join(parts[:3]) + "。"


def build_market_switches(
    core: dict[str, Any],
    prev: dict[str, Any],
    index_items: list[dict[str, Any]],
) -> list[str]:
    switches: list[str] = []
    by_code = {str(x.get("thscode") or ""): x for x in index_items}
    labels = {code: name for code, name in INDEX_UNIVERSE}
    signed = []
    for code, name in INDEX_UNIVERSE:
        row = by_code.get(code)
        if not row:
            continue
        pct = _num(row.get("price_change_ratio_pct"))
        signed.append((name, pct))
        switches.append(f"{name} {fmt_pct(pct)}")
    if signed:
        ups = [n for n, p in signed if p > 0]
        dns = [n for n, p in signed if p < 0]
        if ups and dns:
            switches.append(f"指数分化：{('、'.join(ups))}上涨，{('、'.join(dns))}下跌")
    to_t = _num(core.get("turnover"))
    to_y = _num(prev.get("turnover"))
    if to_t and to_y:
        rel = (to_t - to_y) / to_y
        if rel <= -0.08:
            switches.append(f"成交额萎缩至{fmt_yi(to_t)}（昨日{fmt_yi(to_y)}）")
        elif rel >= 0.08:
            switches.append(f"成交额放大至{fmt_yi(to_t)}（昨日{fmt_yi(to_y)}）")
        else:
            switches.append(f"成交额{fmt_yi(to_t)}，较昨日大致持平")
    elif to_t:
        switches.append(f"成交额{fmt_yi(to_t)}")
    up, down, flat = core.get("up") or 0, core.get("down") or 0, core.get("flat") or 0
    if up or down:
        bit = f"涨跌家数 {up}/{down}/{flat}，中位涨跌幅 {fmt_pct(core.get('median_pct'))}"
        if down > up:
            bit += "（跌多涨少）"
        elif up > down * 1.2:
            bit += "（涨多跌少）"
        switches.append(bit)
    lu, lb, ld = core.get("limit_up") or 0, core.get("limit_break") or 0, core.get("limit_down") or 0
    switches.append(
        f"涨停{lu} / 炸板{lb} / 跌停{ld}，封板率{core.get('seal_rate', 0):.1f}%"
    )
    nh, th = core.get("nominal_height") or 0, core.get("true_height") or 0
    ynh, yth = prev.get("nominal_height") or 0, prev.get("true_height") or 0
    height = f"名义连板高度{nh}板，真实高度{th}板"
    if ynh or yth:
        height += f"（昨名义{ynh}/真实{yth}）"
    if th < nh:
        height += "，高位有水分"
    if yth and th < yth:
        height += "，高度回落"
    elif yth and th > yth:
        height += "，高度上移"
    switches.append(height)
    # drop raw per-index duplicates if too long — keep structured switches
    # First four may be raw index lines; that's intended for 盘面开关.
    _ = labels
    return switches


def build_risks(
    core: dict[str, Any],
    prev: dict[str, Any],
    yesterday_themes: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    true_excluded: list[str],
) -> list[str]:
    risks: list[str] = []
    if (core.get("limit_down") or 0) >= 3:
        risks.append(f"跌停{core['limit_down']}只，冰点风险上升。")
    elif (core.get("limit_down") or 0) > 0:
        risks.append(f"出现{core['limit_down']}只跌停，注意情绪回流失败时的杀跌。")
    if (core.get("seal_rate") or 0) < 50:
        risks.append(f"封板率仅{core.get('seal_rate', 0):.1f}%，炸板回封质量差，高位接力风险大。")
    if (core.get("true_height") or 0) < (prev.get("true_height") or 0):
        risks.append("真实连板高度回落，昨日高位股今日容易变成核按钮。")
    faded = [t for t in yesterday_themes if t.get("status") in {"证伪", "走弱"}]
    if faded:
        risks.append(
            "昨主线"
            + "、".join(t["name"] for t in faded[:3])
            + "结账偏弱，惯性追涨容易接飞刀。"
        )
    to_t, to_y = _num(core.get("turnover")), _num(prev.get("turnover"))
    if to_y and to_t < to_y * 0.85:
        risks.append("成交额明显萎缩，容量不足以同时支撑高低位题材。")
    if true_excluded:
        risks.append("名义高度代表（" + "、".join(true_excluded[:3]) + "）因ST/高换手或多次开板不计入真实高度。")
    st_hits = [
        str(x.get("stock_name") or "")
        for x in anomalies
        if "ST" in str(x.get("stock_name") or "") or str(x.get("tag_name") or "") == "跌停"
    ]
    st_hits = [x for x in st_hits if x][:3]
    if st_hits:
        risks.append("异动/跌停侧：" + "、".join(st_hits) + "，避免风险股外溢。")
    if not risks:
        risks.append("若次日高开低走且连板晋级失败，短线情绪可能快速降温。")
    return risks[:6]


def build_scenarios(
    core: dict[str, Any],
    yesterday_themes: list[dict[str, Any]],
    sectors: list[dict[str, Any]],
) -> list[dict[str, str]]:
    lead = sectors[0]["name"] if sectors else "当日最强方向"
    second = sectors[1]["name"] if len(sectors) > 1 else "低位补涨方向"
    faded = [t["name"] for t in yesterday_themes if t.get("status") in {"走弱", "证伪"}]
    strong = [t["name"] for t in yesterday_themes if t.get("status") == "加强"]
    hold = strong[0] if strong else lead
    fade = faded[0] if faded else "昨日高位"
    scenarios = [
        {
            "name": "情形A",
            "condition": f"竞价或早盘{hold}继续高开高走，连板晋级不掉队，成交不显著萎缩。",
            "action": (
                f"只做最强方向确认单，{hold}回封或中军加速再参与，不追杂毛。"
                if hold == lead
                else f"只做最强方向确认单，{hold}/{lead}回封或中军加速再参与，不追杂毛。"
            ),
        },
        {
            "name": "情形B",
            "condition": f"{hold}高开低走或中军炸板，资金明显切向{second}等低位方向。",
            "action": f"承认高低切换：高位只出不接，低位首板/{second}看竞价溢价与封单质量。",
        },
        {
            "name": "情形C",
            "condition": f"指数跳水、封板率继续下行，{fade}与{lead}同时退潮。",
            "action": "按情绪退潮处理：空仓或只留隔夜最强，不抄底跌停板与高位核按钮。",
        },
    ]
    if (core.get("true_height") or 0) <= 2:
        scenarios[0]["condition"] = f"情绪仍在地板附近但{lead}能走出一致涨停潮。"
        scenarios[0]["action"] = "按反弹试错，仓位克制，只做空间板与板块中军。"
    return scenarios


def _md_theme_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "昨日主线样本不足，无法结账。"
    lines = [
        "| 主线 | 状态 | 涨跌 | 备注 |",
        "| --- | --- | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('name','')} | {row.get('status','')} | {fmt_pct(row.get('change_pct'))} | {row.get('note','')} |"
        )
    return "\n".join(lines)


def _md_sector_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "今日涨停原因尚未形成稳定概念簇。"
    lines = [
        "| 方向 | 热度 | 涨跌 | 状态 | 备注 |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('name','')} | {row.get('heat',0):.0f} | {fmt_pct(row.get('change_pct'))} | {row.get('status','')} | {row.get('note','')} |"
        )
    return "\n".join(lines)


def _md_ladder(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"- {title}：暂无"
    bits = []
    for row in rows:
        reason = row.get("reason") or ""
        extra = f"（{reason}）" if reason else ""
        bits.append(f"{row.get('name')} {row.get('board')}板{extra}")
    return f"- {title}：" + "；".join(bits)


def render_markdown(item: dict[str, Any], *, index_items: list[dict[str, Any]]) -> str:
    date = item["date"]
    core = item["core_metrics"]["today"]
    prev = item["core_metrics"]["yesterday"]
    lines: list[str] = [
        f"# {date} 主线热度复盘",
        "",
        f"> {item.get('summary') or ''}",
        "",
        f"**核心矛盾：** {item.get('core_conflict') or ''}",
        "",
        "## 一、盘面开关",
        "",
    ]
    for sw in item.get("market_switches") or []:
        lines.append(f"- {sw}")
    if not item.get("market_switches"):
        lines.append("- 盘面开关数据不足")
    lines += [
        "",
        "## 二、昨主线今日结账",
        "",
        _md_theme_table(item.get("yesterday_themes") or []),
        "",
        "## 三、连板生死簿",
        "",
    ]
    ladder = item.get("ladder") or {}
    lines.append(_md_ladder("名义高度代表", ladder.get("nominal") or []))
    lines.append(_md_ladder("真实高度代表", ladder.get("true") or []))
    firsts = ladder.get("strong_first_boards") or []
    if firsts:
        bits = []
        for row in firsts:
            reason = row.get("reason") or ""
            extra = f"（{reason}）" if reason else ""
            bits.append(f"{row.get('name')}{extra}")
        lines.append("- 低位强首板：" + "；".join(bits))
    else:
        lines.append("- 低位强首板：暂无足够封单样本")
    lines += [
        "",
        "## 四、行业 / 概念切换",
        "",
        _md_sector_table(item.get("sector_rotation") or []),
        "",
        "## 五、风险警示",
        "",
    ]
    for risk in item.get("risks") or []:
        lines.append(f"- {risk}")
    lines += ["", "## 六、次日互斥情形", ""]
    for sc in item.get("next_day_scenarios") or []:
        lines.append(f"**{sc.get('name')}**")
        lines.append(f"- 条件：{sc.get('condition')}")
        lines.append(f"- 动作：{sc.get('action')}")
        lines.append("")
    audit = item.get("audit") or {}
    lines += [
        "## 数据审计",
        "",
        f"- 交易日：{date}（Asia/Shanghai）",
        f"- 数据截止：{item.get('cutoff_at') or audit.get('data_as_of') or ''}",
        f"- 生成时间：{item.get('generated_at') or audit.get('generated_at') or ''}",
        f"- 来源：{', '.join(audit.get('sources') or ['HiThink Financial-API'])}",
        f"- 涨停{core.get('limit_up',0)} / 炸板{core.get('limit_break',0)} / 跌停{core.get('limit_down',0)}；"
        f"昨涨停{prev.get('limit_up',0)} / 炸板{prev.get('limit_break',0)} / 跌停{prev.get('limit_down',0)}",
        "",
    ]
    _ = index_items
    return "\n".join(lines).rstrip() + "\n"
