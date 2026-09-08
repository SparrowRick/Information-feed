import copy
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from feed_tool import SH, dumps, merged, next_sessions, trading_day, validate_feed, validate_item, validate_reviews
from sync_feed import freshness, sync


class FeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.feed = json.loads((ROOT / "feed.json").read_text(encoding="utf-8"))
        cls.item = cls.feed["items"][0]
        cls.legacy = json.loads((ROOT / "archive/legacy-feed-2026-09-04.json").read_text(encoding="utf-8"))

    def test_sample_validates_and_preserves_history(self):
        validate_feed(self.feed)
        self.assertEqual(self.feed["items"][1:], self.legacy["items"])
        self.assertEqual(merged(self.feed, self.item), self.feed)

    def test_holidays_and_makeup_work_weekends(self):
        self.assertFalse(trading_day(date(2026, 9, 25)))
        self.assertFalse(trading_day(date(2026, 10, 1)))
        self.assertFalse(trading_day(date(2026, 10, 10)))
        self.assertEqual(next_sessions(date(2026, 9, 24), 5), [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 8), date(2026, 10, 9)])
        with self.assertRaisesRegex(ValueError, "calendar missing"):
            trading_day(date(2027, 1, 4))

    def test_rejects_future_news_and_quotes(self):
        item = copy.deepcopy(self.item)
        item["sources"][0].update(published_at="2026-09-08T09:31:00+08:00", published_date="2026-09-08", time_precision="minute")
        with self.assertRaisesRegex(ValueError, "before cutoff"):
            validate_item(item)
        item = copy.deepcopy(self.item)
        item["market_snapshot"][0]["as_of"] = "2026-09-08T15:00:00+08:00"
        with self.assertRaisesRegex(ValueError, "after cutoff"):
            validate_item(item)

    def test_rejects_dangling_sources_and_unknown_same_day_times(self):
        item = copy.deepcopy(self.item)
        item["today"][0]["source_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "dangling"):
            validate_item(item)
        item = copy.deepcopy(self.item)
        item["sources"][0].update(published_at=None, published_date="2026-09-08", time_precision="day")
        with self.assertRaisesRegex(ValueError, "before cutoff"):
            validate_item(item)

    def test_source_chronology_and_live_deadline(self):
        item = copy.deepcopy(self.item)
        item["sources"][0]["retrieved_at"] = "2026-09-09T08:00:00+08:00"
        with self.assertRaisesRegex(ValueError, "after report"):
            validate_item(item)
        item = copy.deepcopy(self.item)
        item["edition"] = "live"
        with self.assertRaisesRegex(ValueError, "after 09:00"):
            validate_item(item)

    def test_immutable_original_and_no_duplicates(self):
        changed = copy.deepcopy(self.item)
        changed["today"][0]["why"] = "修改后的判断"
        with self.assertRaisesRegex(ValueError, "immutable"):
            merged(self.feed, changed)
        feed = copy.deepcopy(self.feed)
        feed["items"].append(feed["items"][0])
        with self.assertRaisesRegex(ValueError, "duplicate report"):
            validate_feed(feed)

    def test_review_cannot_rewrite_original_or_score_sample(self):
        with tempfile.TemporaryDirectory() as temp:
            original = copy.deepcopy(self.item)
            original["edition"] = "live"
            path = Path(temp) / "2026-09-08.json"
            path.write_text(dumps(original), encoding="utf-8")
            review_item = {"date": "2026-09-09", "review": [{
                "original_report_id": original["id"], "original_event_id": original["today"][0]["id"],
                "original_view": original["today"][0]["why"], "day_offset": 1
            }]}
            validate_reviews(review_item, temp)
            review_item["review"][0]["original_view"] = "事后改写"
            with self.assertRaisesRegex(ValueError, "changed"):
                validate_reviews(review_item, temp)
            original["edition"] = "retrospective"
            path.write_text(dumps(original), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "retrospective"):
                validate_reviews(review_item, temp)

    def test_sync_rejects_bad_and_older_feeds_without_destroying_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            output, status = Path(temp) / "feed.json", Path(temp) / "status.json"
            now = datetime(2026, 9, 8, 23, 59, tzinfo=SH)
            state = sync("https://example.invalid/feed.json", output, status, lambda _: self.feed, now)
            self.assertEqual(state, "retrospective")
            before = output.read_bytes()
            for bad in ({"items": []}, {**self.feed, "updated_at": "2026-09-04T08:30:00+08:00"}):
                with self.assertRaises(ValueError):
                    sync("https://example.invalid/feed.json", output, status, lambda _: bad, now)
                self.assertEqual(output.read_bytes(), before)
                self.assertEqual(json.loads(status.read_text())["state"], "sync_error")
            self.assertEqual(freshness(self.feed, datetime(2026, 9, 9, 8, 30, tzinfo=SH))[0], "awaiting_today")


if __name__ == "__main__":
    unittest.main()
