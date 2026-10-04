from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from model_prices import observe, rates, resolve

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = (FIXTURES / "cursor.html").read_text()
INDEX = """# Cursor Docs
  - https://cursor.com/docs/models/claude-opus-5-5.md
  - https://cursor.com/docs/models/cursor-composer-2-5.md
"""


def _site(page):
    def get(url):
        return {observe.CURSOR_INDEX: INDEX,
                "https://cursor.com/docs/models/cursor-composer-2-5": page}[url]
    return get


class ObserveTests(unittest.TestCase):
    def test_cursor_rate_table_gives_rates_and_the_fast_mode(self):
        self.assertEqual(observe.parse_cursor(PAGE), {"composer-2.5": {
            "input": 0.5, "cache_read": 0.2, "output": 2.5,
            "modes": {"fast": {"input": 3.0, "cache_read": 0.5, "output": 15.0}}}})

    def test_only_cursor_model_pages_are_read(self):
        self.assertEqual(observe.cursor_pages(INDEX),
                         ["https://cursor.com/docs/models/cursor-composer-2-5"])

    def test_a_changed_layout_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "page format changed"):
            observe.parse_cursor(PAGE.replace("<span>Cache Read</span>", "<span>Cached</span>"))
        with self.assertRaisesRegex(ValueError, "page format changed"):
            observe.parse_cursor("<p>Pricing moved.</p>")

    def test_an_entry_is_added_only_when_the_price_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observed.json"
            first = datetime(2026, 10, 4, tzinfo=timezone.utc)
            self.assertEqual(observe.observe(output, _site(PAGE), first), ["cursor"])
            self.assertEqual(observe.observe(output, _site(PAGE), datetime(2026, 10, 5,
                                                                         tzinfo=timezone.utc)), [])
            cut = PAGE.replace("$<!-- -->2.5<", "$<!-- -->2<")
            self.assertEqual(observe.observe(output, _site(cut), datetime(2026, 10, 6,
                                                                        tzinfo=timezone.utc)), ["cursor"])
            entries = json.loads(output.read_text())["providers"]["cursor"]["composer-2.5"]
        self.assertEqual([(entry["valid_from"], entry["rates"]["output"]) for entry in entries],
                         [("2026-10-04T00:00:00Z", 2.5), ("2026-10-06T00:00:00Z", 2.0)])
        self.assertEqual(entries[0]["source"], "https://cursor.com/docs/models/cursor-composer-2-5")

    def test_observed_prices_are_priced_with_their_page_and_date_basis(self):
        self.assertEqual(resolve("composer-2.5"), ("cursor", "composer-2.5"))
        found = rates("composer-2.5", at="2026-09-01")
        fast = rates("composer-2.5", at="2026-09-01", mode="fast")

        self.assertEqual((found.input, found.output, found.valid_from_basis),
                         (0.5, 2.5, "first observed"))
        self.assertIn("cursor.com/docs/models/cursor-composer-2-5", found.source)
        self.assertEqual((fast.input, fast.output), (3.0, 15.0))


if __name__ == "__main__":
    unittest.main()
