from datetime import datetime, timezone
import io
import json
from pathlib import Path
import unittest
from unittest import mock

from model_prices import checks, main
from model_prices.checks import Observed

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
# Synthetic pages in the layouts of the official pricing pages, with their 2026-09-30 prices.
PAGES = {
    "alibaba": (FIXTURES / "alibaba.md").read_text(),
    "anthropic": (FIXTURES / "anthropic.md").read_text(),
    "deepseek": (FIXTURES / "deepseek.html").read_text(),
    "deepseek:zh": (FIXTURES / "deepseek-zh.html").read_text(),
    "google": (FIXTURES / "google.md").read_text(),
    "moonshotai": (FIXTURES / "moonshot.md").read_text(),
    "openai": (FIXTURES / "openai.md").read_text(),
    "xai": (FIXTURES / "xai.md").read_text(),
    "zai": (FIXTURES / "zai.md").read_text(),
}


def _prices(provider):
    return {(item.model, item.field, item.above, item.at): item.value
            for item in checks.SOURCES[provider][1](PAGES[provider], TODAY)}


def _terms(pages):
    results = checks.run(["deepseek"], today=TODAY, pages=pages)
    return {result.field: result for result in results if result.field.startswith("peak_terms")}


class CheckTests(unittest.TestCase):
    def test_parsers_read_official_tables(self):
        anthropic = _prices("anthropic")
        self.assertEqual(anthropic[("claude-opus-5-5", "input", None, None)], 4)
        self.assertEqual(anthropic[("claude-opus-5-5", "cache_write", None, None)], 5)
        self.assertEqual(anthropic[("claude-opus-5-5", "cache_read", None, None)], 0.2)
        self.assertEqual(anthropic[("claude-opus-5-5", "cache_write_1h", None, None)], 8)

        openai = _prices("openai")
        self.assertEqual(openai[("gpt-6-astra", "output", 272_000, None)], 75)
        self.assertNotIn(("gpt-5.4-mini", "input", 272_000, None), openai)

        self.assertEqual(_prices("zai")[("GLM-5.3", "cache_read", None, None)], 0.26)

        xai = _prices("xai")
        self.assertEqual(xai[("grok-4.6", "input", None, None)], 2)
        self.assertEqual(xai[("grok-4.6", "output", 200_000, None)], 12)

        google = _prices("google")
        self.assertEqual(google[("Gemini 3.8 Flash", "input", None, None)], 0.75)
        self.assertEqual(google[("Gemini 2.5 Pro", "input", 200_000, None)], 2.5)
        self.assertEqual(google[("Gemini 2.5 Flash", "cache_read", None, None)], 0.03)
        self.assertIn(("Gemini 3.8 Flash", "cache_read", None, None), google)
        self.assertNotIn(0.5, {value for (model, field, _, _), value in google.items()
                               if model == "Gemini 3.8 Flash" and field == "cache_read"})

        deepseek = _prices("deepseek")
        self.assertEqual(sorted(value for (model, field, _, _), value in deepseek.items()
                                if model == "deepseek-flash" and field == "input"), [0.15, 0.3])

    def test_moonshot_parser_reads_both_table_layouts(self):
        moonshot = _prices("moonshotai")

        self.assertEqual(moonshot[("kimi-k3", "cache_write_1h", None, None)], 6)
        self.assertEqual(moonshot[("kimi-k3", "cache_read", None, None)], 0.3)
        self.assertEqual(moonshot[("kimi-k2.6", "cache_read", None, None)], 0.16)
        self.assertEqual(moonshot[("kimi-k2.6", "input", None, None)], 0.95)

    def test_alibaba_parser_reads_singapore_text_prices(self):
        alibaba = _prices("alibaba")

        # Merged cells repeat down their rows; a tier starts above its lower bound.
        self.assertEqual(alibaba[("qwen3.7-plus", "input", None, None)], 0.4)
        self.assertEqual(alibaba[("qwen3.7-plus", "output", 256_000, None)], 4.8)
        self.assertEqual(alibaba[("qwen3-coder-480b-a35b-instruct", "input", 32_000, None)], 2.7)
        # Output is the non-thinking price.
        self.assertEqual(alibaba[("qwen-turbo", "output", None, None)], 0.2)
        # Other regions, per-modality tables, busy-hour prices, and images are skipped.
        self.assertNotIn(0.115, alibaba.values())
        models = {model for model, *_ in alibaba}
        self.assertFalse(models & {"qwen3.5-omni-plus", "deepseek-v4-flash-0731", "qwen-image"})

    def test_resold_models_are_not_compared_with_their_lab(self):
        results = checks.run(["alibaba"], pages=PAGES, today=TODAY)
        resold = [r for r in results if r.model == "deepseek-v4-pro"]

        self.assertEqual({r.status for r in resold}, {"untracked"})

    def test_google_section_pricing_several_models_prices_each(self):
        google = _prices("google")
        names = {model for model, *_ in google}

        self.assertLessEqual({"Gemini 3.8 Live", "Gemini 3.8 Live Extended Thinking",
                              "Gemini 3.1 Flash Live Preview"}, names)
        self.assertFalse(any(", " in name or " and Gemini" in name for name in names))
        # "$0.75 (text) $3.00 or $0.005/min (audio)": only the text price counts.
        self.assertEqual(google[("Gemini 3.1 Flash Live Preview", "input", None, None)], 0.75)

    def test_google_dated_prices_follow_the_check_date(self):
        cell = "$0.75 through December 31, 2026. $1.50 starting January 1, 2027."

        self.assertEqual(checks._google_price(cell, TODAY), [(0.75, None)])
        self.assertEqual(checks._google_price(cell, datetime(2027, 1, 2, tzinfo=timezone.utc)),
                         [(1.5, None)])

    def test_official_pages_match_effective_prices(self):
        results = checks.run(pages=PAGES, today=TODAY)
        statuses = {result.status for result in results}

        self.assertNotIn("mismatch", statuses)
        corrected = {(r.model, r.field) for r in results if r.status == "corrected"}
        self.assertIn(("deepseek/deepseek-v4-pro", "input"), corrected)
        self.assertIn(("google/gemini-omni-flash-preview", "output"), corrected)
        one_hour = [r for r in results if r.field == "cache_write_1h"]
        self.assertTrue(one_hour)
        self.assertEqual({r.status for r in one_hour}, {"ok"})

    def test_check_scores_genai_prices_against_official_pages(self):
        # Anthropic and OpenAI entries of genai-prices' data.json at commit 36d4e77c (2026-09-29).
        genai = json.loads((FIXTURES / "genai-prices.json").read_text())
        results = checks.run(["anthropic", "openai"], pages=PAGES, today=TODAY, genai=genai)
        listed = {(r.model, r.field, r.above): r.genai_prices for r in results}

        # genai-prices lacks Opus 5.5; its Opus 5 rule would accept the name only as a prefix.
        self.assertIsNone(listed[("anthropic/claude-opus-5-5", "input", None)])
        # It still lists GPT-5.6 Sol at the price before the 2026-08-21 cut.
        self.assertEqual(listed[("openai/gpt-5.6-sol", "input", None)], 5)
        self.assertEqual(listed[("openai/gpt-5.6-sol", "input", 272000)], 10)
        report = checks.report(results, genai=True)
        self.assertIn("genai     openai/gpt-5.6-sol input: official $4, genai-prices 5", report)
        self.assertIn("in genai-prices: ", report.splitlines()[-1])

    def test_compare_flags_prices_that_differ(self):
        wrong = Observed("anthropic", "claude-opus-5-5", "input", 3.0)
        unknown = Observed("anthropic", "claude-mythos-5-1", "input", 10.0)

        mismatch, untracked = checks.compare([wrong, unknown], TODAY)

        self.assertEqual((mismatch.status, mismatch.effective), ("mismatch", 4.0))
        self.assertEqual(untracked.status, "untracked")

    def test_changed_page_format_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "page format changed"):
            checks.run(["zai"], today=TODAY, pages={"zai": "# Pricing\n"})

    def test_check_command_exit_status(self):
        with (mock.patch.object(checks, "fetch", lambda url: PAGES["zai"]),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(main(["check", "zai"]), 0)
        self.assertIn("0 mismatch", stdout.getvalue())

        changed = PAGES["zai"].replace("\\$1.4", "\\$9.9")
        with (mock.patch.object(checks, "fetch", lambda url: changed),
              mock.patch("sys.stdout", new_callable=io.StringIO)):
            self.assertEqual(main(["check", "zai"]), 1)

    def test_peak_hour_terms_must_match_in_both_languages(self):
        pages = {"deepseek": PAGES["deepseek"], "deepseek:zh": PAGES["deepseek:zh"]}
        self.assertEqual({field: result.status for field, result in _terms(pages).items()},
                         {"peak_terms:en": "ok", "peak_terms:zh": "ok"})

        changed = {**pages,
                   "deepseek:zh": pages["deepseek:zh"].replace("14:00 - 18:00", "14:00 - 19:00")}
        terms = _terms(changed)
        self.assertEqual((terms["peak_terms:en"].status, terms["peak_terms:zh"].status),
                         ("ok", "mismatch"))
        self.assertIn("14:00 - 19:00",
                      checks.report(checks.run(["deepseek"], today=TODAY, pages=changed)))

    def test_holiday_calendar_must_cover_the_coming_weeks(self):
        ok, = checks.check_calendars({"deepseek"}, TODAY)
        late, = checks.check_calendars({"deepseek"}, datetime(2026, 11, 30, tzinfo=timezone.utc))

        self.assertEqual((ok.status, late.status), ("ok", "mismatch"))
        self.assertIn("add the next year's holidays", checks.report([late]))
        self.assertEqual(checks.check_calendars({"anthropic"}, TODAY), [])


if __name__ == "__main__":
    unittest.main()
