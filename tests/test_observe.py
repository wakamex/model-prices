from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from model_prices import checks, compiler, observe, rates, resolve

FIXTURES = Path(__file__).parent / "fixtures"
DATA = Path(__file__).parent.parent / "data"
TODAY = datetime(2026, 10, 8, tzinfo=timezone.utc)
PAGE = (FIXTURES / "cursor.html").read_text()
DEVIN = (FIXTURES / "devin.html").read_text()
INDEX = """# Cursor Docs
  - https://cursor.com/docs/models/claude-opus-5-5.md
  - https://cursor.com/docs/models/cursor-composer-2-5.md
"""

# Cursor's and Devin's pages, without the checked pricing pages.
OWN_PAGES = ["cognition", "cursor"]


def _site(page, devin=DEVIN):
    def get(url):
        return {observe.CURSOR_INDEX: INDEX, observe.DEVIN_MODELS: devin,
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
            self.assertEqual(observe.observe(output, _site(PAGE), first, OWN_PAGES), ["cognition", "cursor"])
            self.assertEqual(observe.observe(output, _site(PAGE), datetime(2026, 10, 5,
                                                                         tzinfo=timezone.utc), OWN_PAGES), [])
            cut = PAGE.replace("$<!-- -->2.5<", "$<!-- -->2<")
            self.assertEqual(observe.observe(output, _site(cut), datetime(2026, 10, 6,
                                                                        tzinfo=timezone.utc), OWN_PAGES), ["cursor"])
            entries = json.loads(output.read_text())["providers"]["cursor"]["composer-2.5"]
        self.assertEqual([(entry["valid_from"], entry["rates"]["output"]) for entry in entries],
                         [("2026-10-04T00:00:00Z", 2.5), ("2026-10-06T00:00:00Z", 2.0)])
        self.assertEqual(entries[0]["source"], "https://cursor.com/docs/models/cursor-composer-2-5")

    def test_devin_price_list_gives_cognition_models_at_enterprise_prices(self):
        # Self-serve plans list SWE-2 at no charge; Enterprise plans pay per token.
        self.assertEqual(observe.parse_devin(DEVIN), {
            "swe-2-medium": {"input": 0.75, "output": 3.75, "cache_read": 0.075, "cache_write": 0.0},
            "swe-1-7": {"input": 0.5, "output": 2.5, "cache_read": 0.2, "cache_write": 0.0}})

    def test_one_unreadable_page_does_not_stop_the_others(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observed.json"
            with self.assertRaisesRegex(ValueError, "cognition: .*page format changed"):
                observe.observe(output, _site(PAGE, devin="<p>Moved.</p>"), providers=OWN_PAGES)
            recorded = json.loads(output.read_text())["providers"]
        self.assertIn("composer-2.5", recorded["cursor"])
        self.assertNotIn("cognition", recorded)

    def test_byteplus_table_gives_seed_models_with_their_long_context_tier(self):
        # Resold models are left out, and the Flex table gives no standard prices.
        self.assertEqual(observe.parse_byteplus((FIXTURES / "byteplus.html").read_text()), {
            "dola-seed-2-1-turbo": {"input": 0.5, "cache_read": 0.1, "output": 2.5},
            "seed-2-0-lite-260428": {"input": 0.25, "cache_read": 0.05, "output": 2.0, "tiers": [
                {"above": 128_000, "input": 0.5, "cache_read": 0.1, "output": 4.0}]}})
        with self.assertRaisesRegex(ValueError, "page format changed"):
            observe.parse_byteplus("<p>Pricing moved.</p>")

    def test_checked_pages_give_own_models_that_models_dev_lacks(self):
        # Renamed so models.dev lacks it: an own model with long-context tiers, beside a
        # model models.dev lists and a DeepSeek model Alibaba resells.
        page = (FIXTURES / "alibaba.md").read_text().replace(
            "qwen3-coder-480b-a35b-instruct", "qwen3-coder-unlisted")
        url = checks.SOURCES["alibaba"][0]

        cache_page = (FIXTURES / "alibaba-cache.md").read_text()
        found = observe.read_checked("alibaba", DATA, TODAY,
                                     {url: page, observe.ALIBABA_CACHE: cache_page}.__getitem__)

        self.assertEqual(found, {"qwen3-coder-unlisted": (url, {
            "input": 1.5, "output": 7.5,
            "tiers": [{"above": 32000, "input": 2.7, "output": 13.5},
                      {"above": 128000, "input": 4.5, "output": 22.5}]})})

    def test_alibaba_cache_rules_give_implicit_reads_and_explicit_writes(self):
        implicit, explicit = observe.parse_alibaba_cache(
            (FIXTURES / "alibaba-cache.md").read_text())

        # qwen3.8-max is an exception, and the China tab's models are another deployment.
        self.assertEqual(implicit, {"qwen3.7-max", "qwen3-max-preview", "qwen3.7-plus-2026-05-26"})
        self.assertEqual(explicit, {"qwen3.7-max", "qwen3.5-plus-2026-04-20",
                                    "qwen3.7-plus-2026-05-26"})
        with self.assertRaisesRegex(ValueError, "cache billing rules changed"):
            observe.parse_alibaba_cache((FIXTURES / "alibaba-cache.md").read_text()
                                        .replace("<strong>20%</strong>", "<strong>15%</strong>"))

    def test_models_dev_history_takes_over_from_its_first_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for name in DATA.glob("*.toml"):
                (data / name.name).write_text(name.read_text())
            entry = {"commit": "abc", "valid_from": "2026-10-05T00:00:00Z",
                     "rates": {"input": 1.0, "output": 2.0}}
            prices = json.loads((DATA / "prices.json").read_text())
            prices["providers"]["alibaba"]["qwen3-coder-unlisted"] = [entry]
            (data / "prices.json").write_text(json.dumps(prices))
            (data / "observed.json").write_text(json.dumps({"providers": {"alibaba": {
                "qwen3-coder-unlisted": [
                    {"valid_from": "2026-10-01T00:00:00Z", "source": "page",
                     "rates": {"input": 1.5, "output": 7.5}},
                    {"valid_from": "2026-10-06T00:00:00Z", "source": "page",
                     "rates": {"input": 9.0, "output": 9.0}}]}}}))

            timeline = compiler.build(data)["prices"]["alibaba"]["qwen3-coder-unlisted"]["standard"]

        self.assertEqual([(item["rates"]["valid_from"], item["rates"]["input"]) for item in timeline],
                         [("2026-10-01T00:00:00Z", 1.5), ("2026-10-05T00:00:00Z", 1.0)])

    def test_observed_prices_are_priced_with_their_page_and_date_basis(self):
        self.assertEqual(resolve("composer-2.5"), ("cursor", "composer-2.5"))
        found = rates("composer-2.5", at="2026-09-01")
        fast = rates("composer-2.5", at="2026-09-01", mode="fast")

        self.assertEqual((found.input, found.output, found.valid_from_basis),
                         (0.5, 2.5, "first observed"))
        self.assertIn("cursor.com/docs/models/cursor-composer-2-5", found.source)
        self.assertEqual((fast.input, fast.output), (3.0, 15.0))

    def test_logged_cognition_and_inkling_names_resolve(self):
        # Devin listed SWE-1.7 at no charge until its 2026-09-12 price list.
        self.assertEqual(rates("swe-1-7", at="2026-08-20").output, 0.0)
        self.assertEqual(rates("swe-1-7", at="2026-09-20").output, 2.5)
        self.assertEqual(resolve("inkling-xhigh"), ("thinkingmachines", "thinkingmachines/Inkling"))


if __name__ == "__main__":
    unittest.main()
