from datetime import datetime, timedelta, timezone
import hashlib
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings

import model_prices
from model_prices import Rates, Tier, compiler, cost, main, rates, rates_between, resolve
from model_prices.backfill import _date_rules, _tracked, build, changed_providers, hold, parse_rates, schema1, write

DATA = Path(__file__).resolve().parent.parent / "data"

MODEL_NAMES = [
    ("claude-opus-5-5", None, ("anthropic", "claude-opus-5-5")),
    ("claude-opus-4-6-thinking", None, ("anthropic", "claude-opus-4-6")),
    ("gemini-3.8-flash-medium", None, ("google", "gemini-3.8-flash")),
    ("Gemini 3.5 Flash (High)", None, ("google", "gemini-3.5-flash")),
    ("zai/glm-5.3", None, ("zai", "glm-5.3")),
    ("GLM-5.3", "zcode", ("zai", "glm-5.3")),
    ("muse-wonder-1.0", "muse", ("meta", "muse-wonder-1.0")),
    ("opencode/grok-4.7", None, ("xai", "grok-4.7")),
    ("deepseek/deepseek-v4-flash-0731", None, ("deepseek", "deepseek-v4-flash")),
    ("grok-4-6-xhigh", None, ("xai", "grok-4.6")),
    ("opencode/deepseek-v4.1-flash", None, ("deepseek", "deepseek-flash")),
    # A named provider that prices the exact name keeps it ahead of the alias.
    ("deepseek-v4.1-flash", "sensenova", ("sensenova", "deepseek-v4.1-flash")),
    ("sensenova/deepseek-v4.1-flash", None, ("sensenova", "deepseek-v4.1-flash")),
    # An alias within the named provider still wins: "inkling" is Inkling's renamed id.
    ("inkling", "thinkingmachines", ("thinkingmachines", "thinkingmachines/Inkling")),
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


def _use(snapshot: dict, updated_at: str = "2026-10-01T00:00:00Z") -> bytes:
    """Make `snapshot` the active price data and return its published bytes."""
    text = compiler.serialize({**snapshot, "updated_at": updated_at})
    model_prices._activate((json.loads(text), hashlib.sha256(text).hexdigest(),
                            model_prices._parse_time(updated_at)))
    return text


class PriceTests(unittest.TestCase):
    def tearDown(self):
        model_prices._activate(model_prices._bundled())

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

    def test_estimates_price_models_without_a_per_token_price_only_on_request(self):
        self.assertIsNone(rates("muse-wonder-full-1.0"))
        self.assertIsNone(cost("muse-wonder-full-1.0", input_tokens=1_000_000))
        wonder = rates("muse-wonder-1.0", at="2026-10-20")
        full = rates("muse-wonder-full-1.0", at="2026-10-20", provider="muse", estimate=True)
        self.assertEqual((full.provider, full.model, full.estimated_from),
                         ("meta", "muse-wonder-full-1.0", "meta/muse-wonder-1.0"))
        self.assertEqual((full.input, full.cache_read, full.output),
                         (wonder.input, wonder.cache_read, wonder.output))
        self.assertEqual(cost("muse-wonder-full-1.0", output_tokens=1_000_000, estimate=True), 20.0)
        # A priced model is never an estimate, and another provider's hint finds none.
        self.assertIsNone(rates("muse-wonder-1.0", estimate=True).estimated_from)
        self.assertIsNone(rates("muse-wonder-full-1.0", provider="openai", estimate=True))

    def test_batch_mode_discounts_standard_prices(self):
        standard = rates("claude-opus-5-5", at="2026-10-20")
        batch = rates("claude-opus-5-5", at="2026-10-20", mode="batch")
        self.assertEqual((batch.input, batch.output, batch.cache_read, batch.cache_write),
                         (standard.input / 2, standard.output / 2, standard.cache_read / 2,
                          standard.cache_write / 2))
        # Older Gemini models charge batch cache reads at the standard price.
        flash = rates("gemini-2.5-flash", at="2026-10-20", mode="batch")
        self.assertEqual(flash.cache_read, rates("gemini-2.5-flash", at="2026-10-20").cache_read)
        # Batch Mode started on 2025-07-07, and xAI discounts only some models.
        self.assertIsNone(rates("gemini-2.5-flash", at="2025-07-01", mode="batch"))
        self.assertEqual(rates("gemini-2.5-flash", at="2025-07-08", mode="batch").valid_from,
                         "2025-07-07T00:00:00Z")
        self.assertIsNone(rates("grok-4", provider="xai", mode="batch"))
        # Live and native-audio models have no batch API, under either Google rule.
        self.assertIsNone(rates("gemini-2.5-flash-native-audio-preview-12-2025", mode="batch"))
        self.assertIsNone(rates("deepseek-v4-flash", provider="deepseek", mode="batch"))

    def test_rate_fields_this_release_does_not_know_are_ignored(self):
        snapshot = json.loads(compiler.serialize(model_prices._data()))
        interval = snapshot["prices"]["anthropic"]["claude-haiku-5-5"]["standard"][-1]
        interval["rates"]["cache_read_explicit"] = 0.01
        interval["rates"]["tiers"][0]["output_image"] = 30.0
        _use(snapshot)

        found = rates("claude-haiku-5-5")
        self.assertEqual((found.input, found.tiers[0].above), (0.1, 100_000))

    def test_schema_1_copy_keeps_only_the_fields_older_releases_know(self):
        snapshot = json.loads(compiler.serialize(model_prices._data()))
        interval = snapshot["prices"]["anthropic"]["claude-haiku-5-5"]["standard"][-1]
        interval["rates"]["cache_read_explicit"] = 0.01
        interval["rates"]["tiers"][0]["output_image"] = 30.0

        v1 = compiler.as_v1(snapshot)
        kept = v1["prices"]["anthropic"]["claude-haiku-5-5"]["standard"][-1]["rates"]
        self.assertEqual((v1["schema"], snapshot["schema"]), (1, 2))
        self.assertNotIn("cache_read_explicit", kept)
        self.assertNotIn("output_image", kept["tiers"][0])
        self.assertEqual(kept["input"], interval["rates"]["input"])
        # A release up to 0.0.5 builds Rates from every field it is given.
        Rates(provider="anthropic", model="claude-haiku-5-5",
              **{**kept, "tiers": tuple(Tier(**tier) for tier in kept["tiers"])})

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

    def test_explicit_cache_hits_cost_their_own_price(self):
        qwen = rates("qwen-plus", provider="alibaba", at="2026-10-29")

        self.assertEqual((qwen.cache_read, qwen.cache_read_explicit), (0.08, 0.04))
        self.assertAlmostEqual(cost("qwen-plus", provider="alibaba", at="2026-10-29",
                                    cache_read_tokens=100_000,
                                    cache_read_explicit_tokens=100_000), 0.012)
        # Explicit hits count toward the prompt, so they reach the 256K tier.
        self.assertAlmostEqual(qwen.breakdown(cache_read_explicit_tokens=300_000).cache_read_explicit,
                               300_000 * 0.12 / 1e6)
        # Without an explicit price, an explicit hit costs a cache read, including a tier's.
        price = Rates(provider="p", model="m", valid_from="", source="", input=1.0, output=2.0,
                      cache_read=0.2, cache_read_explicit=0.1,
                      tiers=(Tier(above=100, input=3.0, cache_read=0.6),))
        self.assertAlmostEqual(price.breakdown(cache_read_explicit_tokens=101).cache_read_explicit,
                               101 * 0.6 / 1e6)
        opus = rates("claude-opus-5-5", at="2026-10-29")
        self.assertEqual(opus.breakdown(cache_read_explicit_tokens=1_000_000).total, opus.cache_read)

    def test_one_hour_cache_writes_cost_twice_the_input_price_at_anthropic(self):
        opus = rates("claude-opus-5-5", at="2026-09-25")
        long_cache = opus.breakdown(cache_write_tokens=1_000_000, cache_write_1h_tokens=1_000_000)

        self.assertEqual((long_cache.cache_write, long_cache.cache_write_1h), (5.0, 8.0))
        self.assertAlmostEqual(cost("claude-opus-5-5", cache_write_1h_tokens=1_000_000,
                                    at="2026-09-25"), 8.0)
        # OpenAI prices its 12-hour writes at 2.5x input.
        astra = rates("gpt-6-astra", at="2026-10-21")
        self.assertEqual(astra.cache_write_1h_multiple, 2.5)
        # Other providers price longer-lived writes like any cache write.
        grok = rates("grok-4.6", at="2026-09-20")
        self.assertIsNone(grok.cache_write_1h_multiple)
        self.assertAlmostEqual(grok.breakdown(cache_write_1h_tokens=100_000).cache_write_1h,
                               100_000 * (grok.cache_write or grok.input) / 1e6)

    def test_alternate_mode_prices(self):
        fast = rates("claude-opus-5-5", at="2026-09-25", mode="fast")

        self.assertEqual((fast.input, fast.output), (8, 40))
        self.assertIsNone(rates("claude-opus-5-5", mode="missing-mode"))

    def test_thinking_mode_prices_alibaba_hybrid_output(self):
        thinking = rates("qwen-plus", at="2026-10-08", mode="thinking")

        # A correction states the thinking price of each long-context tier.
        self.assertEqual((thinking.input, thinking.output), (0.4, 4.0))
        self.assertEqual([(tier.above, tier.input, tier.output) for tier in thinking.tiers],
                         [(256_000, 1.2, 12.0)])
        # Other models bill thinking as output.
        self.assertEqual(rates("claude-opus-5-5", at="2026-10-08", mode="thinking"),
                         rates("claude-opus-5-5", at="2026-10-08"))

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
            self.assertEqual(changed_providers(output, data), ["openai"])
            self.assertTrue(write(data, output))
            unchanged = {**data, "source_commit": "later"}
            self.assertFalse(write(unchanged, output))
            self.assertEqual(json.loads(output.read_text())["source_commit"], data["source_commit"])

            # A held provider keeps its current history while another's change goes ahead.
            cut = json.loads(json.dumps(data))
            cut["providers"]["openai"]["gpt-6-astra"][-1]["rates"]["input"] = 8.0
            cut["providers"]["xai"] = {"grok-9": entries[:1]}
            held = hold(cut, output, {"openai"})
            self.assertEqual(held["providers"]["openai"], data["providers"]["openai"])
            self.assertEqual(changed_providers(output, held), ["xai"])

    def test_backfill_follows_links_into_another_provider(self):
        # StepFun's global models link to the files of its China provider.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            china = repo / "providers" / "stepfun" / "models"
            world = repo / "providers" / "stepfun-ai" / "models"
            china.mkdir(parents=True)
            world.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            (china / "step-9.toml").write_text('[cost]\ninput = 1.0\noutput = 2.0\n')
            (world / "step-9.toml").symlink_to("../../stepfun/models/step-9.toml")
            _commit(repo, "add step-9", "2026-09-04T10:00:00+00:00")

            data = build(repo, ("stepfun-ai",))

        self.assertEqual(data["links"], {})
        self.assertEqual(data["providers"]["stepfun-ai"]["step-9"][0]["rates"],
                         {"input": 1.0, "output": 2.0})

    def test_schema_2_files_read_as_models_dev_publishes_them_in_schema_1(self):
        document = {
            "schema": 2,
            "cost": {
                "text": {
                    "input": {"price": 1, "cache": {"read": 0.1, "write": {"5m": 1.25, "1h": 2}},
                              "overrides": [{"when": {"context": {"gt": 272_000}}, "price": 2,
                                             "cache": {"read": 0.2}},
                                            {"when": {"region": {"equals": "us"}}, "price": 9}]},
                    "output": {"price": 5, "reasoning": 6,
                               "overrides": [{"when": {"context": {"gt": 272_000}}, "price": 7.5}]},
                },
                "multipliers": [{"when": {"service_tier": {"equals": "priority"}}, "factor": {"text": 2}}],
            },
            "experimental": {"modes": {"fast": {"service_tier": "priority"},
                                       "pro": {"body": {"reasoning": {"mode": "pro"}}}}},
        }

        self.assertEqual(parse_rates(schema1(document), "alibaba"), {
            "input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25,
            "tiers": [{"above": 272_000, "input": 2.0, "output": 7.5, "cache_read": 0.2}],
            # The priority tier's factor scales long prompts too, and the tier is a mode of
            # its own name beside the declared fast mode that serves it.
            "modes": {name: {"input": 2.0, "output": 10.0, "cache_read": 0.2, "cache_write": 2.5,
                             "tiers": [{"above": 272_000, "input": 4.0, "output": 15.0,
                                        "cache_read": 0.4}]} for name in ("fast", "priority")}
            | {"thinking": {"output": 6.0}},
        })
        # A service tier no mode declares, as on Google's models, is a mode of its own name,
        # and a factor that names some prices leaves the others as they are.
        flex = {**document, "experimental": {}, "cost": {**document["cost"], "multipliers": [
            {"when": {"service_tier": {"equals": "flex"}},
             "factor": {"text": {"input": {"price": 0.5}, "output": {"price": 0.5}}}}]}}
        self.assertEqual(parse_rates(schema1(flex))["modes"]["flex"], {
            "input": 0.5, "output": 2.5, "cache_read": 0.1, "cache_write": 1.25,
            "tiers": [{"above": 272_000, "input": 1.0, "output": 3.75, "cache_read": 0.2}]})
        # A model priced per second has no per-token price, and an unknown schema stops the build.
        media = {"schema": 2, "cost": {"text": {"input": {"price": 1},
                                                "output": {"price": 2, "unit": "second"}}}}
        self.assertIsNone(parse_rates(schema1(media)))
        with self.assertRaisesRegex(ValueError, "schema 3"):
            schema1({"schema": 3})

    def test_explicit_cache_hits_keep_their_own_price_from_schema_2(self):
        def document(cache, tier_cache):
            return {"schema": 2, "cost": {"text": {
                "input": {"price": 0.4, "cache": cache,
                          "overrides": [{"when": {"context": {"gt": 256_000}}, "price": 1.2,
                                         "cache": tier_cache}]},
                "output": {"price": 1.2}}}}

        both = document({"read": 0.08, "explicit": {"read": 0.04, "write": 0.5}},
                        {"read": 0.24, "explicit": {"read": 0.12, "write": 1.5}})
        self.assertEqual(parse_rates(schema1(both)), {
            "input": 0.4, "output": 1.2, "cache_read": 0.08, "cache_read_explicit": 0.04,
            "cache_write": 0.5, "tiers": [{"above": 256_000, "input": 1.2, "output": 1.2,
                                           "cache_read": 0.24, "cache_read_explicit": 0.12,
                                           "cache_write": 1.5}]})
        # Without an explicit hit price, or with the cache read price, hits cost cache_read.
        for explicit in ({"write": 0.5}, {"read": 0.08, "write": 0.5}):
            rates = parse_rates(schema1(document({"read": 0.08, "explicit": explicit}, None)))
            self.assertNotIn("cache_read_explicit", rates)

    def test_backfill_dates_announced_price_changes(self):
        dated = ('[[cost.multipliers]]\nwhen = {{ date = {{ gte = "{date}" }} }}\n'
                 'factor = {{ text = {{ input = {{ price = 2 }}, output = {{ price = 2 }} }} }}\n')
        base = ('schema = 2\n[cost.text.input]\nprice = {input}\ncache = {{ read = 0.1 }}\n'
                '[cost.text.output]\nprice = {output}\n')
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            models = repo / "providers" / "google" / "models"
            models.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            argon = models / "gemini-9.toml"
            moved = models / "gemini-8.toml"
            argon.write_text(base.format(input=2, output=10) + dated.format(date="2026-12-01"))
            moved.write_text(base.format(input=1, output=5) + dated.format(date="2026-11-01"))
            _commit(repo, "announce", "2026-10-20T10:00:00+00:00")
            # One announcement moves before its date; the other is folded into the base
            # prices after its date.
            moved.write_text(base.format(input=1, output=5) + dated.format(date="2027-02-01"))
            _commit(repo, "move", "2026-10-25T10:00:00+00:00")
            argon.write_text(base.format(input=4, output=20))
            _commit(repo, "fold in", "2026-12-03T10:00:00+00:00")

            data = build(repo, ("google",))

        history = data["providers"]["google"]
        # Prices the factor names double at 00:00 UTC; the cache price it does not name stays.
        self.assertEqual([(e["valid_from"], e.get("scheduled"), e["rates"]) for e in history["gemini-9"]], [
            ("2026-10-20T10:00:00Z", None, {"input": 2.0, "output": 10.0, "cache_read": 0.1}),
            ("2026-12-01T00:00:00Z", True, {"input": 4.0, "output": 20.0, "cache_read": 0.1})])
        # A change moved before its date takes effect only on the new date.
        self.assertEqual([e["valid_from"] for e in history["gemini-8"]],
                         ["2026-10-20T10:00:00Z", "2027-02-01T00:00:00Z"])
        # Any other date condition stops the build until it is handled.
        window = {"schema": 2, "cost": {"multipliers": [
            {"when": {"date": {"lt": "2027-01-01"}}, "factor": 2}]}}
        with self.assertRaisesRegex(ValueError, "unsupported date condition"):
            _date_rules(window, "x")
        # The snapshot labels a scheduled change, and prices requests by it from its date.
        argon = rates("gemini-4-argon", at="2026-12-02")
        self.assertEqual((argon.input, argon.valid_from_basis), (4.0, "scheduled"))
        self.assertEqual(rates("gemini-4-argon", at="2026-11-30T23:59:59Z").input, 2.0)

    def test_prices_by_modality_come_from_schema_2_and_schema_1(self):
        realtime = {"schema": 2, "cost": {
            "text": {"input": {"price": 4, "cache": {"read": 0.4}}, "output": {"price": 16}},
            "audio": {"input": {"price": 32, "cache": {"read": 0.4}}, "output": {"price": 64}},
            "image": {"input": {"price": 5, "cache": {"read": 0.5}}},
            "video": {"input": {"price": 0.005, "unit": "minute"}}}}
        # Every modality the provider prices is listed with every price it states, text
        # included; a price per minute is not a token price.
        self.assertEqual(parse_rates(schema1(realtime))["modalities"], {
            "text": {"input": 4.0, "output": 16.0, "cache_read": 0.4},
            "audio": {"input": 32.0, "cache_read": 0.4, "output": 64.0},
            "image": {"input": 5.0, "cache_read": 0.5}})
        # A modality priced like text adds nothing, and schema 1 gives audio prices.
        same = {"schema": 2, "cost": {"text": {"input": {"price": 1}, "output": {"price": 2}},
                                      "image": {"input": {"price": 1}}}}
        self.assertNotIn("modalities", parse_rates(schema1(same)))
        self.assertEqual(parse_rates({"cost": {"input": 0.3, "output": 2.5, "input_audio": 1.0}}),
                         {"input": 0.3, "output": 2.5, "modalities": {
                             "audio": {"input": 1.0}, "text": {"input": 0.3, "output": 2.5}}})
        # Long-context tiers and modality prices together are left out of the rates.
        tiered = {"schema": 2, "cost": {
            "text": {"input": {"price": 1, "overrides": [{"when": {"context": {"gt": 200_000}},
                                                           "price": 2}]},
                     "output": {"price": 2}},
            "audio": {"input": {"price": 3}}}}
        self.assertNotIn("modalities", parse_rates(schema1(tiered)))

    def test_backfill_carries_cached_audio_back_over_schema_1(self):
        schema_1 = '[cost]\ninput = 4\noutput = 16\ncache_read = 0.4\ninput_audio = 32\noutput_audio = 64\n'
        schema_2 = ('schema = 2\n[cost.text.input]\nprice = 4\ncache = { read = 0.4 }\n'
                    '[cost.text.output]\nprice = 16\n'
                    '[cost.audio.input]\nprice = 32\ncache = { read = 0.4 }\n'
                    '[cost.audio.output]\nprice = 64\n')
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            models = repo / "providers" / "openai" / "models"
            models.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            (models / "gpt-realtime-9.toml").write_text(schema_1)
            _commit(repo, "add", "2026-07-01T10:00:00+00:00")
            (models / "gpt-realtime-9.toml").write_text(schema_2)
            _commit(repo, "schema 2", "2026-10-20T10:00:00+00:00")

            data = build(repo, ("openai",))

        # Schema 1 had no cached audio price; schema 2's applies from the first record, so
        # the switch to schema 2 is no price change.
        entries = data["providers"]["openai"]["gpt-realtime-9"]
        self.assertEqual([entry["valid_from"] for entry in entries], ["2026-07-01T10:00:00Z"])
        self.assertEqual(entries[0]["rates"]["modalities"]["audio"],
                         {"input": 32.0, "output": 64.0, "cache_read": 0.4})

    def test_tokens_by_modality_cost_their_own_prices(self):
        split = {"text": {"input": 800, "cache_read": 100, "output": 200},
                 "audio": {"input": 2500, "cache_read": 1000, "output": 2500},
                 "image": {"input": 500}}
        # OpenAI's prices: $4/$0.40/$16 text, $32/$0.40/$64 audio, $5 image input.
        self.assertAlmostEqual(cost("gpt-realtime-1.5", at="2026-10-29", modality_tokens=split),
                               (800 * 4 + 100 * 0.4 + 200 * 16 + 2500 * 32 + 1000 * 0.4
                                + 2500 * 64 + 500 * 5) / 1e6)
        parts = rates("gpt-realtime-1.5", at="2026-10-29").breakdown(modality_tokens=split)
        self.assertAlmostEqual(parts.input, (800 * 4 + 2500 * 32 + 500 * 5) / 1e6)
        # A modality without a cache price charges cached tokens its own input price; text on
        # an image model costs its text price; PDF tokens cost the image price.
        live = rates("gemini-3.8-live", at="2026-10-29")
        self.assertEqual(live.breakdown(modality_tokens={"audio": {"cache_read": 1_000_000}}).cache_read, 3.0)
        image = rates("gemini-3.1-flash-image", at="2026-10-29")
        self.assertEqual(image.breakdown(modality_tokens={"text": {"output": 1_000_000}}).output, 3.0)
        self.assertEqual(image.breakdown(output_tokens=1_000_000).output, 60.0)
        self.assertEqual(image.breakdown(modality_tokens={"document": {"input": 1_000_000}}).input, 0.5)
        # A model priced only by text prices any modality at its plain prices.
        opus = rates("claude-opus-5-5", at="2026-10-29")
        self.assertEqual(opus.cost(modality_tokens={"audio": {"input": 1000}}), opus.cost(input_tokens=1000))
        # Modality tokens count toward long-context tiers.
        astra = rates("gpt-6-astra", at="2026-09-20")
        self.assertEqual(astra.breakdown(modality_tokens={"text": {"input": 300_000}}).tier_above, 272_000)
        for wrong in ({"input_tokens": 1, "modality_tokens": {}},
                      {"modality_tokens": {"smell": {"input": 1}}},
                      {"modality_tokens": {"audio": {"write": 1}}},
                      {"modality_tokens": {"audio": {"input": -1}}},
                      {"output_tokens": -1}):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                opus.cost(**wrong)
        # Cache writes may be passed beside a split.
        self.assertAlmostEqual(opus.cost(cache_write_tokens=1000, modality_tokens={"text": {"input": 1000}}),
                               opus.cost(input_tokens=1000, cache_write_tokens=1000))

    def test_backfill_records_the_rules_models_dev_now_gives(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            deepseek = repo / "providers" / "deepseek" / "models"
            anthropic = repo / "providers" / "anthropic" / "models"
            deepseek.mkdir(parents=True)
            anthropic.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            text = 'schema = 2\n[cost.text.input]\nprice = 1\n[cost.text.output]\nprice = 2\n'
            (deepseek / "deepseek-v9.toml").write_text(
                text + '[[cost.multipliers]]\nwhen = { utc_hours = { gte = "01:00" } }\nfactor = 2\n'
                '[[cost.multipliers]]\nwhen = { service_tier = { equals = "flex" } }\nfactor = 0.5\n')
            (anthropic / "claude-9.toml").write_text(text.replace(
                "price = 1\n", 'price = 1\ncache = { read = 0.1, write = { "5m" = 1.25, "1h" = 2 } }\n', 1))
            (anthropic / "claude-8.toml").write_text(text)
            _commit(repo, "add", "2026-10-21T10:00:00+00:00")

            data = build(repo, ("anthropic", "deepseek"))

        # Time-of-day multipliers and cache writes by lifetime, and nothing else.
        self.assertEqual(data["rules"], {
            "anthropic": {"claude-9": {"input": 1, "cache_write": {"5m": 1.25, "1h": 2}}},
            "deepseek": {"deepseek-v9": {"multipliers": [
                {"when": {"utc_hours": {"gte": "01:00"}}, "factor": 2}]}}})

    def test_backfill_reads_a_link_that_became_a_file(self):
        # StepFun's global files linked to its China ones until schema 2 made them files.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            china = repo / "providers" / "stepfun" / "models"
            world = repo / "providers" / "stepfun-ai" / "models"
            china.mkdir(parents=True)
            world.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            (china / "step-9.toml").write_text('[cost]\ninput = 1.0\noutput = 2.0\n')
            (world / "step-9.toml").symlink_to("../../stepfun/models/step-9.toml")
            _commit(repo, "add step-9", "2026-09-04T10:00:00+00:00")
            (china / "step-9.toml").write_text('[cost]\ninput = 1.1\noutput = 2.2\n')
            (world / "step-9.toml").unlink()
            (world / "step-9.toml").write_text(
                'schema = 2\n[cost.text.input]\nprice = 1.0\n[cost.text.output]\nprice = 2.0\n')
            _commit(repo, "own file", "2026-09-05T10:00:00+00:00")

            data = build(repo, ("stepfun-ai",))

        # The China file's later yuan-converted price does not replace the file's own price.
        self.assertEqual([(entry["valid_from"], entry["rates"]) for entry in
                          data["providers"]["stepfun-ai"]["step-9"]],
                         [("2026-09-04T10:00:00Z", {"input": 1.0, "output": 2.0})])

    def test_backfill_trims_spaces_from_model_ids(self):
        # models.dev added Cohere's model with a trailing space and renamed it the next day.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            models = repo / "providers" / "cohere" / "models"
            models.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            (models / "command-z .toml").write_text('[cost]\ninput = 1.0\noutput = 2.0\n')
            _commit(repo, "add command-z", "2026-09-04T10:00:00+00:00")
            (models / "command-z .toml").rename(models / "command-z.toml")
            _commit(repo, "rename command-z", "2026-09-05T10:00:00+00:00")

            data = build(repo, ("cohere",))

        self.assertEqual(list(data["providers"]["cohere"]), ["command-z"])
        self.assertEqual(data["providers"]["cohere"]["command-z"][0]["valid_from"],
                         "2026-09-04T10:00:00Z")

    def test_backfill_records_deprecated_and_removed_models(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "models.dev"
            models = repo / "providers" / "openai" / "models"
            models.mkdir(parents=True)
            _git(repo, "init", "-q", "-b", "main")
            for model in ("old", "gone", "back", "current"):
                (models / f"{model}.toml").write_text('[cost]\ninput = 1.0\noutput = 2.0\n')
            _commit(repo, "add models", "2026-09-04T10:00:00+00:00")
            for model in ("old", "back"):
                (models / f"{model}.toml").write_text(
                    'status = "deprecated"\n[cost]\ninput = 1.0\noutput = 2.0\n')
            (models / "gone.toml").unlink()
            _commit(repo, "retire models", "2026-09-05T10:00:00+00:00")
            (models / "back.toml").write_text('[cost]\ninput = 1.0\noutput = 2.0\n')
            _commit(repo, "restore back", "2026-09-06T10:00:00+00:00")

            data = build(repo, ("openai",))

        self.assertEqual(data["status"], {"openai": {"gone": "removed", "old": "deprecated"}})

    def test_backfill_skips_models_not_billed_per_token(self):
        self.assertFalse(_tracked("providers/google/models/lyria-3-pro-preview.toml"))
        self.assertTrue(_tracked("providers/google/models/gemini-3.8-flash.toml"))
        self.assertTrue(_tracked("providers/amazon-bedrock/models/amazon.nova-pro-v1:0.toml"))
        self.assertFalse(_tracked("providers/amazon-bedrock/models/anthropic.claude-opus-5.toml"))

    def test_ids_match_regardless_of_case(self):
        self.assertEqual(resolve("minimax-m2.7"), ("minimax", "MiniMax-M2.7"))
        self.assertEqual(resolve("MiniMax-M2.7-high"), ("minimax", "MiniMax-M2.7"))

    def test_parse_rates_reads_legacy_long_context_prices(self):
        parsed = parse_rates({"cost": {"input": 1, "output": 2, "context_over_200k": {"input": 3}}})

        self.assertEqual(parsed, {"input": 1.0, "output": 2.0,
                                  "tiers": [{"above": 200_000, "input": 3.0}]})
        self.assertIsNone(parse_rates({"cost": {"output": 2}}))
        self.assertIsNone(parse_rates({"name": "no cost"}))

    def test_parse_rates_reads_alibaba_reasoning_as_thinking_output(self):
        cost = {"cost": {"input": 0.4, "output": 1.2, "reasoning": 4}}

        self.assertEqual(parse_rates(cost, "alibaba")["modes"], {"thinking": {"output": 4.0}})
        # Perplexity's reasoning price is a separate charge, not thinking-mode output.
        self.assertNotIn("modes", parse_rates(cost, "perplexity"))

    def test_shipped_data_identifies_its_source(self):
        basis = model_prices.pricing_basis()

        self.assertTrue(basis.startswith("model-prices-"))
        self.assertIn("+models.dev@", basis)

    def test_cli_prints_rates(self):
        with (tempfile.TemporaryDirectory() as directory,
              mock.patch.dict(os.environ, {"MODEL_PRICES_CACHE": directory}),
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(main(["rate", "claude-opus-5-5", "--at", "2026-09-25", "--json"]), 0)
            self.assertEqual(json.loads(stdout.getvalue())["cache_read"], 0.2)
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
        self.assertEqual(resolve("gpt-3.5-turbo-0613"), ("openai", "gpt-3.5-turbo"))
        self.assertIsNone(resolve("gpt-3.5-turbo-0613", strict=True))

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

        with tempfile.TemporaryDirectory() as directory:
            inputs = Path(shutil.copytree(DATA, Path(directory) / "data"))
            data = json.loads((inputs / "prices.json").read_text())
            entries = data["providers"]["deepseek"]["deepseek-v4-pro"]
            entry = [item for item in entries if item["valid_from"] < "2026-09-29"][-1]
            entries.append({"valid_from": "2026-09-29T00:00:00Z", "commit": "fixed",
                            "rates": {**entry["rates"], "input": 0.70}})
            entries.sort(key=lambda item: item["valid_from"])
            (inputs / "prices.json").write_text(json.dumps(data))
            _use(compiler.build(inputs))
        fixed = rates("deepseek-v4-pro", at="2026-09-30T13:00:00Z")
        self.assertEqual((fixed.input, fixed.valid_from_basis), (0.70, "models.dev commit"))

    def test_bundled_snapshot_is_compiled_from_the_inputs(self):
        bundled = json.loads(Path(model_prices.__file__).with_name("snapshot.json").read_text())
        del bundled["updated_at"]
        self.assertEqual(bundled, compiler.build(DATA), "run model-prices compile")

    def test_compiling_unchanged_inputs_keeps_the_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "snapshot.json"
            self.assertTrue(compiler.write(DATA, output, datetime(2026, 10, 1, tzinfo=timezone.utc)))
            first = output.read_bytes()
            self.assertFalse(compiler.write(DATA, output))
            self.assertEqual(output.read_bytes(), first)
            self.assertEqual(json.loads(first)["updated_at"], "2026-10-01T00:00:00Z")

    def test_aliases_take_the_corrections_of_their_model(self):
        # claude-haiku-4-5 links to claude-haiku-4-5-20251001, which models.dev first
        # listed at Sonnet's $3/$15 for 27 minutes.
        alias = rates("claude-haiku-4-5", at="2025-10-15T17:30:00Z")
        dated = rates("claude-haiku-4-5-20251001", at="2025-10-15T17:30:00Z")

        self.assertEqual((alias.input, alias.output, alias.valid_from_basis),
                         (dated.input, dated.output, "documented"))
        # The corrected first price also covers requests before models.dev's first record,
        # so the hour around it has one price.
        segments = rates_between("claude-haiku-4-5", "2025-10-15T17:00:00Z", "2025-10-15T18:00:00Z")
        self.assertEqual([(found.input, found.output) for _, found in segments], [(1.0, 5.0)])

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



class RefreshTests(unittest.TestCase):
    """refresh() against a fake publisher serving latest.json and snapshots by hash."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = Path(directory.name)
        environment = mock.patch.dict(os.environ, {"MODEL_PRICES_CACHE": directory.name})
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(lambda: model_prices._activate(model_prices._bundled()))
        self.published: dict[str, bytes] = {}
        self.requests: list[str] = []
        download = mock.patch.object(model_prices, "_download", self.download)
        download.start()
        self.addCleanup(download.stop)

    def download(self, url: str, timeout: float) -> bytes:
        self.requests.append(url.removeprefix(model_prices.SNAPSHOT_URL))
        if url.removeprefix(model_prices.SNAPSHOT_URL) not in self.published:
            raise OSError("404")
        return self.published[url.removeprefix(model_prices.SNAPSHOT_URL)]

    def publish(self, text: bytes, published_at: str = "2026-10-02T06:30:00Z",
                name: str | None = None) -> str:
        digest = hashlib.sha256(text).hexdigest()
        self.published[name or f"{digest}.json"] = text
        self.published["latest.json"] = json.dumps(
            {"sha256": digest, "published_at": published_at}).encode()
        return digest

    def cheaper(self, updated_at: str = "2099-01-01T00:00:00Z") -> bytes:
        """The bundled data with a later Opus 5.5 price cut."""
        snapshot = json.loads(Path(model_prices.__file__).with_name("snapshot.json").read_text())
        timeline = snapshot["prices"]["anthropic"]["claude-opus-5-5"]["standard"]
        timeline.append({"start": "2026-10-02T00:00:00Z", "rates": {
            **timeline[-1]["rates"], "input": 3.0, "valid_from": "2026-10-02T00:00:00Z"}})
        return compiler.serialize({**snapshot, "updated_at": updated_at})

    def test_refresh_uses_the_published_snapshot_and_records_its_basis(self):
        bundled_basis = model_prices.pricing_basis()
        digest = self.publish(self.cheaper())

        status = model_prices.refresh()

        self.assertIsNone(status.error)
        self.assertEqual(status.published_at, datetime(2026, 10, 2, 6, 30, tzinfo=timezone.utc))
        self.assertTrue(status.basis.endswith(f"+data@{digest[:12]}"))
        self.assertNotEqual(status.basis, bundled_basis)
        self.assertEqual(rates("claude-opus-5-5", at="2026-10-03").input, 3.0)
        self.assertEqual(rates("claude-opus-5-5", at="2026-09-25").input, 4.0)

    def test_a_fresh_cache_is_used_without_downloading(self):
        self.publish(self.cheaper())
        model_prices.refresh()
        self.requests.clear()
        model_prices._activate(model_prices._bundled())

        model_prices.refresh(max_age=timedelta(hours=1))
        self.assertEqual(self.requests, [])
        self.assertEqual(rates("claude-opus-5-5", at="2026-10-03").input, 3.0)
        model_prices.refresh(max_age=timedelta(0))
        self.assertEqual(self.requests, ["latest.json"])  # the snapshot is already cached

    def test_a_failed_download_keeps_the_newest_local_data(self):
        self.publish(self.cheaper())
        model_prices.refresh()
        self.published.clear()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            status = model_prices.refresh(max_age=timedelta(0))
        self.assertIn("404", status.error)
        self.assertEqual(len(caught), 1)
        self.assertEqual(rates("claude-opus-5-5", at="2026-10-03").input, 3.0)

    def test_snapshots_that_fail_their_hash_or_schema_are_rejected(self):
        bundled_basis = model_prices.pricing_basis()
        digest = self.publish(self.cheaper())
        self.published[f"{digest}.json"] = b"tampered"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.assertIn("does not match", model_prices.refresh().error)
            self.assertEqual(model_prices.pricing_basis(), bundled_basis)

            future = json.loads(self.cheaper())
            self.publish(compiler.serialize({**future, "schema": model_prices.SCHEMA + 1}))
            self.assertIn("schema", model_prices.refresh().error)
            self.assertEqual(model_prices.pricing_basis(), bundled_basis)
        self.assertFalse(any(self.cache.rglob("*.json")))

    def test_bundled_data_newer_than_the_cache_wins(self):
        # As after upgrading the package while offline.
        self.publish(self.cheaper(updated_at="2000-01-01T00:00:00Z"))
        status = model_prices.refresh()

        self.assertEqual(rates("claude-opus-5-5", at="2026-10-03").input, 4.0)
        self.assertEqual(status.basis, model_prices.pricing_basis())
        self.assertEqual(status.published_at, model_prices._bundled()[2])

    def test_without_a_refresh_prices_come_from_the_bundled_data(self):
        self.publish(self.cheaper())
        model_prices.refresh()
        model_prices._activate(model_prices._bundled())

        self.assertEqual(rates("claude-opus-5-5", at="2026-10-03").input, 4.0)
        model_prices.refresh(max_age=None)
        self.assertEqual(rates("claude-opus-5-5", at="2026-10-03").input, 3.0)

    def test_cli_refresh(self):
        self.publish(self.cheaper())
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(main(["refresh"]), 0)
        self.assertIn("published 2026-10-02T06:30:00+00:00", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
