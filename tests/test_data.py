from datetime import datetime
from pathlib import Path
import tomllib
import unittest

DATA = Path(__file__).resolve().parent.parent / "data"
FILES = ("corrections.toml", "research_corrections.toml")


def _corrections(name):
    return tomllib.loads((DATA / name).read_text())["correction"]


def _time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class CorrectionDataTests(unittest.TestCase):
    """Invariants that a sourced price cannot break, to catch fields assembled wrongly."""

    def each(self):
        for name in FILES:
            for item in _corrections(name):
                with self.subTest(file=name, model=item["model"], valid_from=item["valid_from"]):
                    yield item

    def test_periods_are_well_formed(self):
        for item in self.each():
            self.assertTrue(item["source"])
            if "valid_until" in item:
                self.assertLess(_time(item["valid_from"]), _time(item["valid_until"]))
            else:
                # An open-ended correction must stop once models.dev records anything else.
                self.assertIn("replaces", item)

    def test_tiers_cost_at_least_the_base_price(self):
        for item in self.each():
            for tier in item.get("tiers", []):
                for field in ("input", "output", "cache_read", "cache_write"):
                    if tier.get(field) is not None and item.get(field) is not None:
                        self.assertGreaterEqual(tier[field], item[field], field)

    def test_cache_prices_bracket_the_input_price(self):
        for item in self.each():
            if item.get("cache_read") is not None:
                self.assertLessEqual(item["cache_read"], item["input"])
            # Anthropic prices cache writes at 1.25x input and reads at 0.1x, except Claude 3
            # Haiku (1.2x and 0.12x), Opus 5.5 (reads at 0.05x), and Fable 5.1 and Mythos 5.1
            # (reads at 0.025x).
            if item["provider"] == "anthropic":
                if item.get("cache_write") is not None:
                    self.assertIn(round(item["cache_write"] / item["input"], 3), {1.25, 1.2})
                if item.get("cache_read") is not None:
                    self.assertIn(round(item["cache_read"] / item["input"], 3),
                                  {0.1, 0.12, 0.05, 0.025})

    def test_corrections_in_one_file_do_not_overlap(self):
        for name in FILES:
            periods = {}
            for item in _corrections(name):
                end = _time(item["valid_until"]) if "valid_until" in item else datetime.max.replace(
                    tzinfo=_time(item["valid_from"]).tzinfo)
                periods.setdefault((item["provider"], item["model"]), []).append(
                    (_time(item["valid_from"]), end))
            for key, spans in periods.items():
                spans.sort()
                for (_, first_end), (second_start, _) in zip(spans, spans[1:]):
                    with self.subTest(file=name, model=key):
                        self.assertLessEqual(first_end, second_start)


if __name__ == "__main__":
    unittest.main()
