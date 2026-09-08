import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from review.build import build_item
from review.metrics import (
    break_rate,
    is_st_stock,
    promotion_stats,
    qualifies_true_height,
    volume_expansion_day,
)
from review.narrative import render_markdown
from review.sectors import is_event_token, match_index
from review.themes import incremental_branch, select_industry_lines


def _bar(date_ms: int, turnover: float) -> dict:
    return {"date_ms": date_ms, "turnover": turnover}


def _ms(yyyy_mm_dd: str) -> int:
    # Asia/Shanghai 00:00 of the date as ms. 2026-09-07 = Monday.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    dt = datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return int(dt.timestamp() * 1000)


class ReviewMetricsTests(unittest.TestCase):
    def test_st_detection(self):
        self.assertTrue(is_st_stock({"is_st": True, "name": "富煌钢构"}))
        self.assertTrue(is_st_stock({"name": "*ST广糖"}))
        self.assertFalse(is_st_stock({"name": "爱仕达", "is_st": False}))

    def test_promotion_rate(self):
        yday = [
            {"thscode": "000001.SZ", "name": "A", "continue_day_cnt": 1},
            {"thscode": "000002.SZ", "name": "B", "continue_day_cnt": 2},
            {"thscode": "000003.SZ", "name": "ST假", "continue_day_cnt": 1, "is_st": True},
        ]
        today = [
            {"thscode": "000001.SZ", "name": "A", "continue_day_cnt": 2},
            {"thscode": "000002.SZ", "name": "B", "continue_day_cnt": 2},
        ]
        stats = promotion_stats(yday, today)
        self.assertEqual(stats["eligible"], 2)
        self.assertEqual(stats["promoted"], 1)
        self.assertEqual(stats["rate"], 50.0)

    def test_break_rate_non_st_seal(self):
        self.assertEqual(break_rate(82, 16), 16.3)

    def test_true_height_drops_low_seal_high_open(self):
        item = {
            "name": "深中华A",
            "is_st": False,
            "continue_day_cnt": 7,
            "open_times": 24,
            "seal_ratio_pct": 0.8,
            "turnover": 1.25e9,
        }
        self.assertFalse(qualifies_true_height(item))

    def test_volume_expansion_day(self):
        sh = [
            _bar(_ms("2026-09-04"), 100e8),
            _bar(_ms("2026-09-07"), 117.5e8),
            _bar(_ms("2026-09-08"), 116e8),
        ]
        sz = [
            _bar(_ms("2026-09-04"), 100e8),
            _bar(_ms("2026-09-07"), 117.5e8),
            _bar(_ms("2026-09-08"), 116e8),
        ]
        out = volume_expansion_day(sh, sz, "2026-09-08", threshold=0.08)
        self.assertEqual(out["expansion"]["date"], "2026-09-07")
        self.assertAlmostEqual(out["expansion"]["change_pct"], 17.5, places=1)
        self.assertEqual(out["today_date"], "2026-09-08")

    def test_event_token_and_index_match(self):
        self.assertTrue(is_event_token("中报增长"))
        self.assertFalse(is_event_token("人形机器人"))
        catalog = [
            {"thscode": "886001.TI", "name": "人工智能"},
            {"thscode": "886002.TI", "name": "机器人概念"},
        ]
        hit = match_index("AI应用", catalog)
        self.assertEqual(hit["thscode"], "886001.TI")
        self.assertIsNone(match_index("不存在的主题xyz", catalog))


class IndustryLineTests(unittest.TestCase):
    def test_selects_lead_and_incremental_not_padded(self):
        y_themes = [
            {"name": "资源金属", "status": "走弱", "change_pct": 0.9, "note": ""},
            {"name": "AI硬件", "status": "证伪", "change_pct": -1.3, "note": ""},
        ]
        y_clusters = [{"name": "资源金属", "heat": 8, "count": 4, "stocks": ["紫金矿业"]}]
        t_clusters = [
            {"name": "软件开发", "heat": 6, "count": 5, "change_pct": 0.8, "stocks": ["鼎捷数智"]},
            {"name": "资源金属", "heat": 5, "count": 3, "change_pct": 0.7, "stocks": ["紫金矿业"]},
            {"name": "中报增长", "heat": 10, "count": 11, "change_pct": 9.9, "stocks": ["红棉股份"]},
        ]
        pool = [
            {
                "name": "鼎捷数智",
                "thscode": "300378.SZ",
                "continue_day_cnt": 1,
                "limit_up_reason": "AI智能体+软件开发",
                "turnover": 5.2e8,
            },
            {
                "name": "久其软件",
                "thscode": "002279.SZ",
                "continue_day_cnt": 1,
                "limit_up_reason": "AI智能体+软件开发",
                "turnover": 3.2e8,
            },
            {
                "name": "紫金矿业",
                "thscode": "601899.SH",
                "continue_day_cnt": 1,
                "limit_up_reason": "资源金属+黄金",
                "turnover": 40e8,
            },
        ]
        inc = incremental_branch(t_clusters, y_clusters, pool)
        self.assertIsNotNone(inc)
        self.assertEqual(inc["name"], "软件开发")
        lines = select_industry_lines(
            yesterday_themes=y_themes,
            yesterday_clusters=y_clusters,
            today_clusters=t_clusters,
            incremental=inc,
            today_pool=pool,
            true_leaders=[],
        )
        roles = {x["role"] for x in lines}
        names = [x["name"] for x in lines]
        self.assertEqual(len(lines), 2)
        self.assertIn("次主线候选", roles)
        self.assertIn("新方向候选", roles)
        self.assertEqual(names, ["资源金属", "软件开发"])
        self.assertNotIn("中报增长", names)

    def test_does_not_pad_when_all_falsified(self):
        y_themes = [{"name": "AI硬件", "status": "证伪", "change_pct": -1.3, "note": ""}]
        lines = select_industry_lines(
            yesterday_themes=y_themes,
            yesterday_clusters=[{"name": "AI硬件", "heat": 10, "count": 5, "stocks": []}],
            today_clusters=[{"name": "环氧丙烷", "heat": 1, "count": 1, "change_pct": 2.7, "stocks": []}],
            incremental=None,
            today_pool=[],
            true_leaders=[],
        )
        self.assertEqual(lines, [])

    def test_merges_when_incremental_is_the_lead(self):
        y_themes = [{"name": "软件开发", "status": "加强", "change_pct": 0.8, "note": ""}]
        clusters = [{"name": "软件开发", "heat": 8, "count": 5, "change_pct": 0.8, "stocks": ["鼎捷数智"]}]
        pool = [
            {
                "name": "鼎捷数智",
                "thscode": "1.SZ",
                "continue_day_cnt": 1,
                "limit_up_reason": "软件开发",
            },
            {
                "name": "久其软件",
                "thscode": "2.SZ",
                "continue_day_cnt": 1,
                "limit_up_reason": "软件开发",
            },
        ]
        inc = incremental_branch(clusters, [{"name": "软件开发", "heat": 2, "count": 1, "stocks": []}], pool)
        lines = select_industry_lines(
            yesterday_themes=y_themes,
            yesterday_clusters=[{"name": "软件开发", "heat": 2, "count": 1, "stocks": []}],
            today_clusters=clusters,
            incremental=inc,
            today_pool=pool,
            true_leaders=[],
        )
        self.assertEqual(len(lines), 1)
        self.assertIn("兼", lines[0]["role"])


class MarkdownContractTests(unittest.TestCase):
    def test_build_item_omits_deferred_and_dropped_sections(self):
        today_up = [
            {
                "thscode": "300378.SZ",
                "ticker": "300378",
                "name": "鼎捷数智",
                "is_st": False,
                "continue_day_cnt": 1,
                "limit_up_reason": "AI智能体+软件开发",
                "price_change_ratio_pct": 10.0,
                "seal_money": 1e8,
                "turnover": 5.2e8,
            },
            {
                "thscode": "002279.SZ",
                "ticker": "002279",
                "name": "久其软件",
                "is_st": False,
                "continue_day_cnt": 1,
                "limit_up_reason": "AI智能体+软件开发",
                "price_change_ratio_pct": 10.0,
                "seal_money": 1.2e8,
                "turnover": 3.2e8,
            },
        ]
        yday_up = [
            {
                "thscode": "000651.SZ",
                "ticker": "000651",
                "name": "格力电器",
                "is_st": False,
                "continue_day_cnt": 2,
                "limit_up_reason": "资源金属",
                "price_change_ratio_pct": 10.0,
            }
        ]
        item = build_item(
            date="2026-09-08",
            prev_date="2026-09-07",
            today_pools={"limit_up": today_up, "limit_down": [], "limit_break": []},
            yday_pools={"limit_up": yday_up, "limit_down": [], "limit_break": []},
            snapshot=[],
            index_items=[
                {"thscode": "000001.SH", "price_change_ratio_pct": -0.4, "turnover": 1e12}
            ],
            anomalies=[],
            prev_item=None,
            y_turnover=2.14e12,
            t_turnover_fallback=2.11e12,
            generated_at="2026-09-08T17:05:00+08:00",
            data_as_of="2026-09-08T17:00:00+08:00",
        )
        md = item["markdown"]
        self.assertIn("## 一、盘面全貌", md)
        self.assertIn("## 八、产业线深拆", md)
        self.assertIn("## 十一、风险警示", md)
        self.assertNotIn("盘前预判", md)
        self.assertNotIn("次日互斥", md)
        self.assertNotIn("数据审计", md)
        self.assertNotIn("next_day_scenarios", item)
        self.assertIn("gaps", item["audit"])
        self.assertTrue(any("盘前预判" in g for g in item["audit"]["gaps"]))

    def test_render_skips_audit_heading_even_if_legacy_fields_present(self):
        item = {
            "date": "2026-09-08",
            "summary": "测试",
            "core_conflict": "测试矛盾",
            "market_switches": ["上证指数 -1.0%"],
            "core_metrics": {
                "today": {
                    "turnover": 1e12,
                    "up": 10,
                    "down": 5,
                    "flat": 1,
                    "median_pct": 0.1,
                    "limit_up": 2,
                    "limit_down": 0,
                    "limit_break": 1,
                    "seal_rate": 66.7,
                    "break_rate": 33.3,
                    "nominal_height": 2,
                    "true_height": 2,
                    "non_st_limit_up": 2,
                    "non_st_limit_down": 0,
                    "non_st_limit_break": 1,
                    "promotion_rate": 20.0,
                    "promotion_eligible": 5,
                    "promotion_count": 1,
                    "index_avg_pct": -1.0,
                },
                "yesterday": {
                    "turnover": 1.1e12,
                    "up": 0,
                    "down": 0,
                    "flat": 0,
                    "median_pct": 0,
                    "limit_up": 3,
                    "limit_down": 0,
                    "limit_break": 1,
                    "seal_rate": 75,
                    "break_rate": 25,
                    "nominal_height": 3,
                    "true_height": 3,
                    "non_st_limit_up": 3,
                    "non_st_limit_down": 0,
                    "non_st_limit_break": 1,
                    "promotion_rate": 30,
                    "index_avg_pct": 1.7,
                },
            },
            "yesterday_themes": [],
            "ladder": {"nominal": [], "true": [], "strong_first_boards": []},
            "sector_rotation": [],
            "risks": ["测试风险"],
            "industry_lines": [],
            "audit": {"sources": ["HiThink Financial-API"], "generated_at": "x", "data_as_of": "y"},
        }
        md = render_markdown(item, index_items=[])
        self.assertNotIn("## 数据审计", md)
        self.assertNotIn("次日互斥", md)


if __name__ == "__main__":
    unittest.main()
