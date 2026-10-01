import copy
from importlib.metadata import version
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import model_prices
from model_prices import Rates, Tier, cost, main, rates, rates_between, resolve
from model_prices.backfill import build, parse_rates, write

MODEL_NAMES = [
    ("claude-opus-5-5", None, ("anthropic", "claude-opus-5-5")),
    ("claude-opus-4-6-thinking", None, ("anthropic", "claude-opus-4-6")),
    ("gemini-3.8-flash-medium", None, ("google", "gemini-3.8-flash")),
    ("Gemini 3.5 Flash (High)", None, ("google", "gemini-3.5-flash")),
    ("zai/glm-5.3", None, ("zai", "glm-5.3")),
    ("GLM-5.3", "zcode", ("zai", "glm-5.3")),
    ("opencode/grok-4.7", None, ("xai", "grok-4.7")),
    ("deepseek/deepseek-v4-flash-0731", None, ("deepseek", "deepseek-v4-flash")),
    ("grok-4-6-xhigh", None, ("xai", "grok-4.6")),
    ("opencode/deepseek-v4.1-flash", None, ("deepseek", "deepseek-flash")),
    ("gpt-5.5-2026-04-23", None, ("openai", "gpt-5.5")),
    ("claude-opus-5[1m]", None, ("anthropic", "claude-opus-5")),
    ("claude-sonnet-4.5", None, ("anthropic", "claude-sonnet-4-5")),
    ("grok-4.6-build", None, ("xai", "grok-4.6")),
    ("grok-4.7-build", "grok", ("xai", "grok-4.7")),
    ("grok-4.6-build-high", None, ("xai", "grok-4.6")),
    ("grok-4-build", None, None),  # only dotted Grok versions have -build names
    ("grok-build-0.1", None, ("xai", "grok-build-0.1")),
    ("codex-auto-review", None, None),
]

DEEPSEEK_HOURS = [
    ("2026-08-10T02:00:00Z", None, 0.14),        # flat pricing before 2026-08-16T16:00Z
    ("2026-08-17T02:00:00Z", "peak", 0.44),      # Monday peak hour
    ("2026-08-17T05:00:00Z", "off_peak", 0.22),  # between the two peak windows
    ("2026-08-22T02:00:00Z", "off_peak", 0.22),  # Saturday: the current rule applies from the start
    ("2026-09-10T08:00:00Z", "peak", 0.30),      # V4.1 Flash price before models.dev caught up
    ("2026-09-25T02:00:00Z", "off_peak", 0.15),  # Mid-Autumn Festival holiday
    ("2026-09-28T02:00:00Z", "peak", 0.30),
]

ASTRA = """name = "GPT-6 Astra"
reasoning_options = [{{ type = "effort", values = ["low", "high"] }}]

[cost]
input = {input}
output = 50.00
cache_read = 1.00
cache_write = 12.50

[[cost.tiers]]
tier = {{ size = 272_000 }}
input = 20.00
output = 75.00

[experimental.modes.fast]
cost = {{ input = 20.00, output = 100.00 }}
provider = {{ body = {{ service_tier = "priority" }} }}
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo: Path, message: str, when: str) -> None:
    _git(repo, "add", "-A")
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-qm", message],
        check=True, capture_output=True,
        env={"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when, "PATH": "/usr/bin:/bin"},
    )


class PriceTests(unittest.TestCase):
    def test_resolves_log_and_harness_model_names(self):
        for name, provider, expected in MODEL_NAMES:
            with self.subTest(name=name, provider=provider):
                self.assertEqual(resolve(name, provider), expected)

    def test_prices_follow_models_dev_history_with_corrections(self):
        before = rates("gpt-5.6-sol", at="2026-08-20T12:00:00Z")
        corrected = rates("gpt-5.6-sol", at="2026-08-23T12:00:00Z")
        after = rates("gpt-5.6-sol", at="2026-09-01T00:00:00Z")

        self.assertEqual((before.input, before.output), (5.0, 30.0))
        self.assertEqual((corrected.input, corrected.output), (4.0, 20.0))
        self.assertEqual(corrected.source, "https://openai.com/index/gpt-5-6/")
        self.assertEqual((after.input, after.output), (4.0, 20.0))
        self.assertTrue(after.source.startswith("https://github.com/sst/models.dev/commit/"))

    def test_researched_corrections_apply_after_hand_corrections(self):
        # models.dev listed GPT-4o mini's cache read as $0.08 for a year; OpenAI charges $0.075.
        researched = rates("gpt-4o-mini", provider="openai", at="2026-01-01")
        uncorrected = rates("gpt-4o-mini", provider="openai", at="2026-01-01", corrected=False)

        self.assertEqual((researched.cache_read, uncorrected.cache_read), (0.075, 0.08))
        self.assertEqual(researched.valid_from_basis, "documented")
        # Research also dates the Sol cut to August 21; corrections.toml still decides it.
        self.assertEqual(rates("gpt-5.6-sol", at="2026-08-23").source,
                         "https://openai.com/index/gpt-5-6/")

    def test_usage_before_first_recorded_price_uses_that_price(self):
        early = rates("claude-opus-5-5", at="2026-01-01")

        self.assertEqual((early.input, early.output, early.cache_read, early.cache_write),
                         (4, 20, 0.2, 5))

    def test_long_context_tier_applies_per_request_prompt_size(self):
        # 310,000 prompt tokens exceed Astra's 272,000-token tier.
        self.assertAlmostEqual(
            cost("gpt-6-astra", input_tokens=10_000, cache_read_tokens=300_000,
                 output_tokens=1_000, at="2026-09-20"),
            (10_000 * 20 + 300_000 * 2 + 1_000 * 75) / 1e6)
        self.assertAlmostEqual(
            cost("gpt-6-astra", input_tokens=10_000, output_tokens=1_000, at="2026-09-20"),
            (10_000 * 10 + 1_000 * 50) / 1e6)

    def test_missing_cache_prices_fall_back_to_input_price(self):
        price = Rates(provider="p", model="m", valid_from="", source="", input=2.0, output=8.0,
                      tiers=(Tier(above=100, input=4.0),))

        self.assertAlmostEqual(
            price.cost(input_tokens=10, cache_read_tokens=20, cache_write_tokens=30),
            (10 + 20 + 30) * 2.0 / 1e6)
        self.assertAlmostEqual(price.cost(input_tokens=100, cache_read_tokens=1), 101 * 4.0 / 1e6)

    def test_alternate_mode_prices(self):
        fast = rates("claude-opus-5-5", at="2026-09-25", mode="fast")

        self.assertEqual((fast.input, fast.output), (8, 40))
        self.assertIsNone(rates("claude-opus-5-5", mode="missing-mode"))

    def test_backfill_replays_price_changes_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            models = repo / "providers" / "openai" / "models"
            models.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            (models / "gpt-6-astra.toml").write_text(ASTRA.format(input="10.00"))
            (models / "astra-latest.toml").symlink_to("gpt-6-astra.toml")
            _commit(repo, "add astra", "2026-09-04T10:00:00-05:00")
            (models / "gpt-6-astra.toml").write_text(ASTRA.format(input="10.00") + "\n# comment\n")
            _commit(repo, "no price change", "2026-09-05T10:00:00+00:00")
            (models / "gpt-6-astra.toml").write_text(ASTRA.format(input="9.00"))
            _commit(repo, "cut price", "2026-09-10T10:00:00+00:00")
            # A first-party id serving a lab model, a deprecated id serving the same model,
            # and a deleted id, to check which id a lab model name resolves to.
            (models / "legacy.toml").write_text(
                'base_model = "openai/gpt-6-astra-lab"\nstatus = "deprecated"\n'
            )
            (models / "removed.toml").write_text('base_model = "openai/gpt-6-other"\n')
            _commit(repo, "add ids", "2026-09-11T10:00:00+00:00")
            (models / "removed.toml").unlink()
            (models / "gpt-6-astra.toml").write_text(
                'base_model = "openai/gpt-6-astra-lab"\n'
                + ASTRA.format(input="9.00").split("\n", 1)[1]
            )
            _commit(repo, "serve lab model", "2026-09-12T10:00:00+00:00")

            data = build(repo, ("openai",))

            entries = data["providers"]["openai"]["gpt-6-astra"]
            self.assertEqual([(item["valid_from"], item["rates"]["input"]) for item in entries],
                             [("2026-09-04T15:00:00Z", 10.0), ("2026-09-10T10:00:00Z", 9.0)])
            self.assertEqual(entries[0]["rates"]["tiers"],
                             [{"above": 272_000, "input": 20.0, "output": 75.0}])
            self.assertEqual(entries[0]["rates"]["modes"],
                             {"fast": {"input": 20.0, "output": 100.0}})
            self.assertEqual(data["links"], {"openai": {"astra-latest": "gpt-6-astra"}})
            self.assertEqual(data["bases"], {"openai": {"gpt-6-astra-lab": "gpt-6-astra"}})

            output = Path(directory) / "prices.json"
            self.assertTrue(write(data, output))
            unchanged = {**data, "source_commit": "later"}
            self.assertFalse(write(unchanged, output))
            self.assertEqual(json.loads(output.read_text())["source_commit"], data["source_commit"])

    def test_parse_rates_reads_legacy_long_context_prices(self):
        parsed = parse_rates({"cost": {"input": 1, "output": 2, "context_over_200k": {"input": 3}}})

        self.assertEqual(parsed, {"input": 1.0, "output": 2.0,
                                  "tiers": [{"above": 200_000, "input": 3.0}]})
        self.assertIsNone(parse_rates({"cost": {"output": 2}}))
        self.assertIsNone(parse_rates({"name": "no cost"}))

    def test_shipped_data_identifies_its_source(self):
        basis = model_prices.pricing_basis()

        self.assertTrue(basis.startswith("model-prices-"))
        self.assertIn("+models.dev@", basis)

    def test_cli_prints_rates(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(main(["rate", "claude-opus-5-5", "--at", "2026-09-25", "--json"]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["cache_read"], 0.2)
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["rate", "codex-auto-review"]), 1)

    def test_cli_rejects_an_invalid_time(self):
        with (mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
              self.assertRaises(SystemExit) as raised):
            main(["rate", "gpt-5.5", "--at", "garbage"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("not an ISO 8601 time", stderr.getvalue())

    def test_console_entrypoint(self):
        command = Path(sys.executable).with_name("model-prices")
        result = subprocess.run([command, "--version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), version("model-prices"))

    def test_module_entrypoint(self):
        result = subprocess.run(
            [sys.executable, "-m", "model_prices", "--version"], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), version("model-prices"))

    def test_deepseek_time_of_day_prices(self):
        for at, period, input_price in DEEPSEEK_HOURS:
            with self.subTest(at=at):
                found = rates("deepseek-v4-flash", at=at)
                self.assertEqual(found.period, period)
                self.assertAlmostEqual(found.input, input_price)

    def test_deepseek_2025_off_peak_discount(self):
        # 2025-02-26T16:30Z to 2025-09-05T16:00Z: 50% off V3 and 75% off R1, 16:30-00:30 UTC.
        cases = [
            ("deepseek-chat", "2025-03-10T17:00:00Z", "off_peak", 0.135),
            ("deepseek-chat", "2025-03-11T00:15:00Z", "off_peak", 0.135),  # past midnight
            ("deepseek-chat", "2025-03-11T00:45:00Z", "standard", 0.27),
            ("deepseek-reasoner", "2025-03-10T17:00:00Z", "off_peak", 0.55 * 0.25),
            ("deepseek-chat", "2025-02-26T12:00:00Z", None, 0.27),  # announced, not yet started
        ]
        for model, at, period, input_price in cases:
            with self.subTest(model=model, at=at):
                found = rates(model, at=at)
                self.assertEqual(found.period, period)
                self.assertAlmostEqual(found.input, input_price)

    def test_current_price_list_keeps_the_time_of_day_rule_of_the_request(self):
        # A 2025 off-peak request priced from today's list keeps its 75% discount.
        then = rates("deepseek-reasoner", at="2025-03-10T17:00:00Z")
        today = rates("deepseek-reasoner", at="2025-03-10T17:00:00Z",
                      prices_at="2026-09-30T13:00:00Z")
        listed = rates("deepseek-reasoner", at="2026-09-30T13:00:00Z")

        self.assertEqual((then.period, today.period), ("off_peak", "off_peak"))
        self.assertAlmostEqual(today.input, listed.input * 0.25)

    def test_peak_multiplier_scales_every_rate(self):
        off_peak = rates("deepseek-v4-pro", at="2026-09-30T13:00:00Z")
        peak = rates("deepseek-v4-pro", at="2026-09-30T02:00:00Z")

        self.assertEqual((off_peak.input, off_peak.cache_read, off_peak.output), (0.66, 0.022, 1.98))
        for found, expected in zip((peak.input, peak.cache_read, peak.output), (1.32, 0.044, 3.96)):
            self.assertAlmostEqual(found, expected)
        self.assertIsNone(rates("claude-opus-5-5", at="2026-09-30T02:00:00Z").period)

    def test_strict_resolution_keeps_suffixes(self):
        self.assertEqual(resolve("gpt-3.5-turbo-1106"), ("openai", "gpt-3.5-turbo"))
        self.assertIsNone(resolve("gpt-3.5-turbo-1106", strict=True))

    def test_current_price_list_keeps_the_request_time_of_day(self):
        # A V4 Flash peak hour in August, priced from the September price list.
        then = rates("deepseek-v4-flash", at="2026-08-17T02:00:00Z")
        now = rates("deepseek-v4-flash", at="2026-08-17T02:00:00Z",
                    prices_at="2026-09-30T00:00:00Z")
        off_peak_now = rates("deepseek-v4-flash", at="2026-08-17T05:00:00Z",
                             prices_at="2026-09-30T00:00:00Z")

        self.assertEqual((then.input, then.period), (0.44, "peak"))
        self.assertAlmostEqual(now.input, 0.30)
        self.assertEqual(now.period, "peak")
        self.assertEqual((off_peak_now.input, off_peak_now.period), (0.15, "off_peak"))

    def test_plan_prices(self):
        self.assertEqual(model_prices.plan("anthropic", "max_20x").usd_per_month, 200)
        self.assertEqual(model_prices.plan("zai", "lite").usd_per_month, 18)
        # Google AI Ultra was one plan until 2026-05-19, then two price-tagged tiers.
        self.assertEqual(model_prices.plan("google", "ultra", at="2026-05-01").usd_per_month, 249.99)
        self.assertIsNone(model_prices.plan("google", "ultra", at="2026-06-01"))
        self.assertEqual(model_prices.plan("google", "ultra_100").name, "Google AI Ultra $100")
        self.assertEqual(model_prices.plan("google", "ultra_200").usd_per_month, 199.99)
        self.assertIsNone(model_prices.plan("google", "ultra_200", at="2026-05-01"))
        self.assertEqual(model_prices.plan("openai", "pro_500").usd_per_month, 500)
        self.assertEqual(model_prices.plan_ids("google"), ["pro", "ultra_100", "ultra_200"])
        self.assertIn("ultra", model_prices.plan_ids("google", at="2026-05-01"))

    def test_rates_report_the_suffix_removed_to_find_the_model(self):
        self.assertEqual(rates("kimi-k3-max").removed_suffix, "-max")
        self.assertEqual(rates("gpt-5.5-2026-04-23").removed_suffix, "-2026-04-23")
        self.assertEqual(rates("claude-opus-5[1m]").removed_suffix, "[1m]")
        self.assertEqual(rates("grok-4.6-build").removed_suffix, "-build")
        self.assertEqual(rates("claude-opus-5-5").removed_suffix, "")
        self.assertEqual(rates("deepseek-v4.1-flash").removed_suffix, "")

    def test_price_key_ignores_provenance(self):
        corrected = rates("gpt-5.6-sol", at="2026-08-23T00:00:00Z")
        recorded = rates("gpt-5.6-sol", at="2026-09-01T00:00:00Z")

        self.assertNotEqual(corrected.source, recorded.source)
        self.assertEqual(corrected.price_key(), recorded.price_key())

    def test_rates_between_returns_each_distinct_price(self):
        # A Monday 00:00-12:00 UTC span crosses DeepSeek's two peak windows.
        segments = rates_between("deepseek-flash", "2026-09-28T00:00:00Z", "2026-09-28T12:00:00Z")

        self.assertEqual([(when.isoformat(), found.period) for when, found in segments], [
            ("2026-09-28T00:00:00+00:00", "off_peak"),
            ("2026-09-28T01:00:00+00:00", "peak"),
            ("2026-09-28T04:00:00+00:00", "off_peak"),
            ("2026-09-28T06:00:00+00:00", "peak"),
            ("2026-09-28T10:00:00+00:00", "off_peak"),
        ])
        # One price across a correction ending with identical rates.
        self.assertEqual(
            len(rates_between("gpt-5.6-sol", "2026-08-24T00:00:00Z", "2026-08-26T00:00:00Z")), 1)
        # A price change inside the span.
        changes = rates_between("gpt-5.6-sol", "2026-08-20T00:00:00Z", "2026-08-23T00:00:00Z")
        self.assertEqual([(found.input, found.output) for _, found in changes],
                         [(5.0, 30.0), (4.0, 20.0)])
        # A Chinese holiday weekday has no peak hours.
        self.assertEqual(
            len(rates_between("deepseek-flash", "2026-10-01T00:00:00Z", "2026-10-01T23:00:00Z")), 1)
        self.assertEqual(rates_between("codex-auto-review", "2026-09-01", "2026-09-02"), [])

    def test_open_ended_correction_stops_when_models_dev_changes(self):
        found = rates("deepseek-v4-pro", at="2026-09-30T13:00:00Z")
        self.assertEqual((found.input, found.valid_from_basis), (0.66, "documented"))

        data = copy.deepcopy(model_prices._prices())
        entry = data["providers"]["deepseek"]["deepseek-v4-pro"][-1]
        data["providers"]["deepseek"]["deepseek-v4-pro"].append(
            {"valid_from": "2026-09-29T00:00:00Z", "commit": "fixed",
             "rates": {**entry["rates"], "input": 0.70}})
        model_prices._entry_times.cache_clear()
        try:
            with mock.patch.object(model_prices, "_prices", lambda: data):
                fixed = rates("deepseek-v4-pro", at="2026-09-30T13:00:00Z")
            self.assertEqual((fixed.input, fixed.valid_from_basis), (0.70, "models.dev commit"))
        finally:
            model_prices._entry_times.cache_clear()

    def test_aliases_take_the_corrections_of_their_model(self):
        # claude-haiku-4-5 links to claude-haiku-4-5-20251001, which models.dev first
        # listed at Sonnet's $3/$15 for 27 minutes.
        alias = rates("claude-haiku-4-5", at="2025-10-15T17:30:00Z")
        dated = rates("claude-haiku-4-5-20251001", at="2025-10-15T17:30:00Z")

        self.assertEqual((alias.input, alias.output, alias.valid_from_basis),
                         (dated.input, dated.output, "documented"))
        boundaries = [when.isoformat() for when, _ in rates_between(
            "claude-haiku-4-5", "2025-10-15T17:00:00Z", "2025-10-15T18:00:00Z")]
        self.assertIn("2025-10-15T17:24:36+00:00", boundaries)

    def test_modes_follow_corrections(self):
        # Fast mode costs twice the standard rate, before and during the Sol correction.
        corrected = rates("gpt-5.6-sol", at="2026-08-22T12:00:00Z", mode="fast")
        recorded = rates("gpt-5.6-sol", at="2026-08-22T12:00:00Z", mode="fast", corrected=False)

        self.assertEqual((corrected.input, corrected.output), (8.0, 40.0))
        self.assertEqual((recorded.input, recorded.output), (10.0, 60.0))
        self.assertIsNone(rates("gpt-5.6-sol", at="2026-08-22T12:00:00Z", mode="missing"))

    def test_breakdown_reports_the_tier_and_cost_by_token_type(self):
        found = rates("gpt-6-astra", at="2026-09-20")
        long = found.breakdown(input_tokens=10_000, cache_read_tokens=300_000, output_tokens=1_000)
        short = found.breakdown(input_tokens=10_000, output_tokens=1_000)

        self.assertEqual(long.tier_above, 272_000)
        for found_cost, expected in zip((long.input, long.cache_read, long.output),
                                        (0.2, 0.6, 0.075)):
            self.assertAlmostEqual(found_cost, expected)
        self.assertAlmostEqual(long.total, found.cost(10_000, 1_000, 300_000))
        self.assertIsNone(short.tier_above)


if __name__ == "__main__":
    unittest.main()
