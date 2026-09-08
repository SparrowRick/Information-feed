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
    lu = core.get("non_st_limit_up") if core.get("non_st_limit_up") is not None else core.get("limit_up", 0)
    lb = core.get("non_st_limit_break") if core.get("non_st_limit_break") is not None else core.get("limit_break", 0)
    ld = core.get("non_st_limit_down") if core.get("non_st_limit_down") is not None else core.get("limit_down", 0)
    return (
        f"{date} {idx}；{to_bit}；非ST涨停{lu}、炸板{lb}、"
        f"跌停{ld}，封板率{core.get('seal_rate', 0):.1f}%；"
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
    lu = core.get("non_st_limit_up") or core.get("limit_up") or 0
    lb = core.get("non_st_limit_break") or core.get("limit_break") or 0
    ld = core.get("non_st_limit_down") or core.get("limit_down") or 0
    switches.append(
        f"非ST涨停{lu} / 炸板{lb} / 跌停{ld}，封板率{core.get('seal_rate', 0):.1f}%，"
        f"炸板率{core.get('break_rate', 0):.1f}%"
    )
    if core.get("promotion_rate") is not None:
        switches.append(
            f"晋级率{core.get('promotion_rate', 0):.1f}%"
            f"（{core.get('promotion_count', 0)}/{core.get('promotion_eligible', 0)}）"
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
        "| 昨日方向 | 状态 | 涨跌 | 转接关系 |",
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
        "| 方向 | 今日价格 | 容量变化 | 热度 | 状态 | 结构 |",
        "| --- | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        price = row.get("index_change_pct")
        if price is None:
            price = row.get("change_pct")
        vol = row.get("volume_ratio")
        vol_txt = f"{vol:.2f}倍" if vol else "—"
        extra = row.get("index_name") or row.get("note") or ""
        lines.append(
            f"| {row.get('name','')} | {fmt_pct(price)} | {vol_txt} | "
            f"{row.get('heat',0):.0f} | {row.get('status','')} | {extra} |"
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


def _fmt_opt_pct(value: Any, suffix: str = "%") -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):.1f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _md_core_table(today: dict[str, Any], yesterday: dict[str, Any]) -> str:
    def cell(key: str, fmt: str = "num") -> tuple[str, str]:
        a, b = today.get(key), yesterday.get(key)
        if fmt == "pct":
            return fmt_pct(b), fmt_pct(a)
        if fmt == "yi":
            return fmt_yi(b), fmt_yi(a)
        if fmt == "rate":
            return f"{float(b or 0):.1f}%", f"{float(a or 0):.1f}%"
        if a is None:
            a = "—"
        if b is None:
            b = "—"
        return str(b), str(a)

    rows = [
        ("五个核心指数平均涨跌幅", "index_avg_pct", "pct"),
        ("全市场成交额", "turnover", "yi"),
        ("上涨 / 下跌家数", "breadth", "breadth"),
        ("非ST涨停 / 炸板", "ns_up_break", "pair"),
        ("炸板率", "break_rate", "rate"),
        ("晋级率", "promotion_rate", "rate"),
        ("系统高度 / 真实高度", "height", "height"),
        ("非ST跌停", "non_st_limit_down", "num"),
    ]
    lines = [
        "| 指标 | 上一交易日 | 今日 |",
        "| --- | ---: | ---: |",
    ]
    for label, key, fmt in rows:
        if key == "breadth":
            y = f"{yesterday.get('up') or '—'}/{yesterday.get('down') or '—'}"
            t = f"{today.get('up') or '—'}/{today.get('down') or '—'}"
            lines.append(f"| {label} | {y} | {t} |")
            continue
        if key == "ns_up_break":
            y = f"{yesterday.get('non_st_limit_up') or yesterday.get('limit_up') or 0} / {yesterday.get('non_st_limit_break') or yesterday.get('limit_break') or 0}"
            t = f"{today.get('non_st_limit_up') or today.get('limit_up') or 0} / {today.get('non_st_limit_break') or today.get('limit_break') or 0}"
            lines.append(f"| {label} | {y} | {t} |")
            continue
        if key == "height":
            y = f"{yesterday.get('nominal_height') or 0} / {yesterday.get('true_height') or 0}"
            t = f"{today.get('nominal_height') or 0} / {today.get('true_height') or 0}"
            lines.append(f"| {label} | {y} | {t} |")
            continue
        yv, tv = cell(key, fmt)
        lines.append(f"| {label} | {yv} | {tv} |")
    return "\n".join(lines)


def _md_volume_day(volume_day: dict[str, Any] | None, today_core: dict[str, Any]) -> str:
    if not volume_day:
        return "成交额序列不足，无法定位放量日。"
    exp = volume_day.get("expansion")
    lines = [
        "| 交易日 | 全市场成交额 | 环比 | 说明 |",
        "| --- | ---: | ---: | --- |",
    ]
    if exp:
        lines.append(
            f"| {exp.get('date')} | {fmt_yi(exp.get('turnover'))} | "
            f"{fmt_pct(exp.get('change_pct'), 1)} | 最近放量日 |"
        )
        if exp.get("date") != volume_day.get("today_date"):
            rel = volume_day.get("today_vs_prev_pct")
            lines.append(
                f"| {volume_day.get('today_date')} | {fmt_yi(volume_day.get('today_turnover') or today_core.get('turnover'))} | "
                f"{fmt_pct(rel, 1) if rel is not None else '—'} | 本复盘日 |"
            )
    else:
        lines.append(
            f"| {volume_day.get('today_date')} | {fmt_yi(volume_day.get('today_turnover') or today_core.get('turnover'))} | "
            f"{fmt_pct(volume_day.get('today_vs_prev_pct'), 1) if volume_day.get('today_vs_prev_pct') is not None else '—'} | 观察窗口内无放量日 |"
        )
    return "\n".join(lines)


def _md_incremental(branch: dict[str, Any] | None) -> str:
    if not branch:
        return "当日没有满足热度增量或首板扩散门槛的非事件分支。"
    lines = [
        f"{branch.get('name')}：{branch.get('note') or ''}",
        "",
    ]
    stocks = branch.get("stocks") or []
    if stocks:
        lines += [
            "| 代表标的 | 原因标签 | 板位 | 成交额 | 换手 | 开板 | 封单/成交额 |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for row in stocks:
            lines.append(
                f"| {row.get('name','')} | {row.get('reason','')} | "
                f"{'首板' if (row.get('board') or 1) == 1 else str(row.get('board'))+'板'} | "
                f"{fmt_yi(row.get('turnover'))} | {_fmt_opt_pct(row.get('turnover_ratio_pct'))} | "
                f"{row.get('open_times') if row.get('open_times') is not None else '—'} | "
                f"{_fmt_opt_pct(row.get('seal_ratio_pct'))} |"
            )
    return "\n".join(lines)


def _md_structure(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "高低结构样本不足。"
    lines = [
        "| 位置 | 标的 | 板位 | 成交额 | 换手 | 开板 | 封单/成交额 | 归因 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.get('position','')} | {row.get('name','')} | {row.get('board','')} | "
            f"{fmt_yi(row.get('turnover'))} | {_fmt_opt_pct(row.get('turnover_ratio_pct'))} | "
            f"{row.get('open_times') if row.get('open_times') is not None else '—'} | "
            f"{_fmt_opt_pct(row.get('seal_ratio_pct'))} | {row.get('reason','')} |"
        )
    return "\n".join(lines)


def _md_industry_lines(lines_data: list[dict[str, Any]]) -> str:
    if not lines_data:
        return (
            "今日没有方向同时满足资格线条件，故不深拆。"
            "选择规则：次主线候选=昨日未证伪且今日仍有接力的最强昨主线；"
            "新方向候选=当日最大增量分支且热度上升并有首板扩散。同名合并，不硬凑条数。"
        )
    chunks = [
        "选择规则：次主线候选来自昨日未证伪的最强主线；"
        "新方向候选来自当日最大增量分支（需热度上升且原因匹配首板）。"
        "够格才列，不硬凑两条。",
        "",
        "| 产业线 | 资格 | 身位 | 容量锚 | 首板扩散 | 最短证伪条件 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in lines_data:
        height = "、".join(row.get("height_names") or []) or "无真实高度成员"
        anchors = "、".join(row.get("capacity_anchors") or []) or "—"
        firsts = "、".join(row.get("first_boards") or []) or "无原因匹配首板"
        chunks.append(
            f"| {row.get('name','')} | {row.get('role','')} | {height} | "
            f"{anchors} | {firsts} | {row.get('falsify','')} |"
        )
        if row.get("selection_reason"):
            chunks.append("")
            chunks.append(f"- {row.get('name')}：{row.get('selection_reason')}")
    return "\n".join(chunks)


def _md_broken(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "昨日高位连板今日均仍在涨停池，或没有可对照样本。"
    lines = [
        "| 昨日高标 | 昨板位 | 今日涨跌 | 原因 |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in rows:
        chg = row.get("change_pct")
        chg_txt = fmt_pct(chg) if chg is not None else "—"
        lines.append(
            f"| {row.get('name','')} | {row.get('board','')} | {chg_txt} | {row.get('reason','')} |"
        )
    return "\n".join(lines)


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
        "## 一、盘面全貌",
        "",
    ]
    for sw in item.get("market_switches") or []:
        lines.append(f"- {sw}")
    if not item.get("market_switches"):
        lines.append("- 盘面数据不足")
    lines += [
        "",
        "## 二、从上次放量日到今日",
        "",
        _md_volume_day(item.get("volume_day"), core),
        "",
        "## 三、核心指数、成交与情绪",
        "",
        _md_core_table(core, prev),
        "",
        "## 四、昨主线与重点观察结账",
        "",
        _md_theme_table(item.get("yesterday_themes") or []),
        "",
        "## 五、当日最大增量分支",
        "",
        _md_incremental(item.get("incremental_branch")),
        "",
        "## 六、连板生死簿与高低结构",
        "",
    ]
    ladder = item.get("ladder") or {}
    lines.append(_md_ladder("名义高度代表", ladder.get("nominal") or []))
    lines.append(_md_ladder("真实高度代表", ladder.get("true") or []))
    lines.append("")
    lines.append(_md_structure(item.get("structure_rows") or []))
    broken = item.get("broken_high_boards") or []
    if broken:
        lines += ["", "昨日高标断板：", "", _md_broken(broken)]
    lines += [
        "",
        "## 七、行业、概念与相对配置",
        "",
        "板块涨跌与成交额来自同花顺概念/行业指数（能匹配才填）。"
        "没有主力净流入，下表是价量而不是资金强度。",
        "",
        _md_sector_table(item.get("sector_rotation") or []),
        "",
    ]
    dt = item.get("dragon_tiger") or {}
    if dt.get("stocks"):
        lines += [
            "龙虎榜席位净额（不是全市场主力净流入）：",
            "",
            "| 标的 | 净额 | 机构净额 | 游资净额 | 涨跌 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for row in dt.get("stocks") or []:
            lines.append(
                f"| {row.get('name','')} | {fmt_yi(row.get('net_value'))} | "
                f"{fmt_yi(row.get('org_net_value'))} | {fmt_yi(row.get('hot_money_net_value'))} | "
                f"{fmt_pct(row.get('change_pct'))} |"
            )
        lines.append("")
    lines += [
        "## 八、产业线深拆",
        "",
        _md_industry_lines(item.get("industry_lines") or []),
        "",
        "## 九、最大轮动与被证伪方向",
        "",
    ]
    rot = item.get("rotation") or {}
    falsified = rot.get("falsified") or []
    if falsified:
        lines.append(
            "被证伪："
            + "；".join(
                f"{x.get('name')}（{x.get('note') or x.get('status')}）" for x in falsified
            )
        )
        lines.append("")
    if rot.get("rotation"):
        r = rot["rotation"]
        lines.append(
            f"最大并行轮动：{r.get('name')} 热度{r.get('heat')}，"
            f"{fmt_pct(r.get('change_pct'))}。{r.get('note') or ''}"
        )
    elif not falsified:
        lines.append("没有单独列出的并行轮动或证伪方向。")
    lines += [
        "",
        "## 十、其他涨停原因暗线",
        "",
    ]
    events = item.get("event_themes") or []
    if events:
        bits = [
            f"{e.get('name')} {e.get('count')}只"
            for e in events
        ]
        lines.append("事件标签（不升格为主线）：" + "；".join(bits) + "。")
    else:
        lines.append("当日涨停原因里没有形成独立的事件标签暗线。")
    lines += ["", "## 十一、风险警示", ""]
    for risk in item.get("risks") or []:
        lines.append(f"- {risk}")
    if not item.get("risks"):
        lines.append("- 若次日高开低走且连板晋级失败，短线情绪可能快速降温。")
    lines.append("")
    _ = (index_items, date)
    return "\n".join(lines).rstrip() + "\n"
