import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from review.check_polish import check, locked_diff, mark_polished


def _item() -> dict:
    return {
        "id": "review-2026-09-08",
        "type": "review",
        "title": "2026-09-08 主线热度复盘",
        "date": "2026-09-08",
        "timezone": "Asia/Shanghai",
        "generated_at": "2026-09-08T17:05:00+08:00",
        "cutoff_at": "2026-09-08T17:00:00+08:00",
        "is_trading_day": True,
        "summary": "2026-09-08 上证指数 -1.00%；两市成交2.12万亿；非ST涨停82、炸板16、跌停1，封板率83.7%；连板名义7板/真实4板。",
        "core_conflict": "指数下跌与封板改善并存。",
        "market_switches": ["上证指数 -1.00%"],
        "core_metrics": {
            "today": {
                "turnover": 2.12e12,
                "limit_up": 82,
                "non_st_limit_up": 82,
                "limit_break": 16,
                "non_st_limit_break": 16,
                "limit_down": 1,
                "seal_rate": 83.7,
                "break_rate": 16.3,
                "nominal_height": 7,
                "true_height": 4,
            },
            "yesterday": {"turnover": 2.14e12, "limit_up": 77, "seal_rate": 81.9},
        },
        "yesterday_themes": [{"name": "AI硬件", "status": "证伪", "change_pct": -1.3, "note": "x"}],
        "ladder": {"nominal": [{"name": "深中华A", "board": 7}], "true": [], "strong_first_boards": []},
        "industry_lines": [],
        "risks": ["真实高度回落"],
        "markdown": (
            "# 2026-09-08 主线热度复盘\n\n"
            "非ST涨停82，封板率83.7%，名义7板，真实4板。\n"
        ),
        "audit": {"sources": ["HiThink Financial-API"], "generated_at": "t", "data_as_of": "t", "gaps": ["无主力净流入"]},
    }


class CheckPolishTests(unittest.TestCase):
    def test_prose_change_ok(self):
        raw = _item()
        polished = copy.deepcopy(raw)
        polished["summary"] = (
            "2026-09-08 五个核心指数走弱，但非ST涨停82、炸板16，封板率83.7%；"
            "系统高度7板、真实高度4板，指数与短线情绪背离。"
        )
        polished["core_conflict"] = "指数走弱与封板改善并存，当前定为混沌而不是退潮。"
        polished["markdown"] = raw["markdown"] + "\n解释：真实高度回落，不能把7板当情绪。"
        polished["title"] = "主线热度复盘 · 2026-09-08收盘：指数走弱与封板改善并存"
        self.assertEqual(check(raw, polished), [])

    def test_rejects_metric_edit(self):
        raw = _item()
        polished = copy.deepcopy(raw)
        polished["core_metrics"]["today"]["non_st_limit_up"] = 99
        errs = locked_diff(raw, polished)
        self.assertTrue(any("core_metrics" in e for e in errs))

    def test_rejects_markdown_dropping_numbers(self):
        raw = _item()
        polished = copy.deepcopy(raw)
        polished["markdown"] = "今天情绪还可以。"
        errs = check(raw, polished)
        self.assertTrue(any("markdown missing" in e for e in errs))

    def test_mark_polished_does_not_fail_audit_lock(self):
        raw = _item()
        polished = mark_polished(copy.deepcopy(raw))
        # audit.polished is allowed; remaining audit must match
        self.assertEqual(locked_diff(raw, polished), [])


if __name__ == "__main__":
    unittest.main()
