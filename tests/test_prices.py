import json
from pathlib import Path
import subprocess
import sys

import pytest

import llm_prices
from llm_prices import Rates, Tier, cost, main, rates, rates_between, resolve
from llm_prices.backfill import build, parse_rates, write


@pytest.mark.parametrize(
    ("name", "provider", "expected"),
    [
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
        ("grok-build-0.1", None, ("xai", "grok-build-0.1")),
        ("codex-auto-review", None, None),
    ],
)
def test_resolves_log_and_harness_model_names(name, provider, expected):
    assert resolve(name, provider) == expected


def test_prices_follow_models_dev_history_with_corrections():
    before = rates("gpt-5.6-sol", at="2026-08-21T12:00:00Z")
    corrected = rates("gpt-5.6-sol", at="2026-08-23T12:00:00Z")
    after = rates("gpt-5.6-sol", at="2026-09-01T00:00:00Z")

    assert (before.input, before.output) == (5.0, 30.0)
    assert (corrected.input, corrected.output) == (4.0, 20.0)
    assert corrected.source == "https://github.com/sst/models.dev/pull/5375"
    assert (after.input, after.output) == (4.0, 20.0)
    assert after.source.startswith("https://github.com/sst/models.dev/commit/")


def test_usage_before_first_recorded_price_uses_that_price():
    early = rates("claude-opus-5-5", at="2026-01-01")

    assert (early.input, early.output, early.cache_read, early.cache_write) == (4, 20, 0.2, 5)


def test_long_context_tier_applies_per_request_prompt_size():
    # 310,000 prompt tokens exceed Astra's 272,000-token tier.
    assert cost("gpt-6-astra", input_tokens=10_000, cache_read_tokens=300_000,
                output_tokens=1_000, at="2026-09-20") == pytest.approx(
        (10_000 * 20 + 300_000 * 2 + 1_000 * 75) / 1e6
    )
    assert cost("gpt-6-astra", input_tokens=10_000, output_tokens=1_000,
                at="2026-09-20") == pytest.approx((10_000 * 10 + 1_000 * 50) / 1e6)


def test_missing_cache_prices_fall_back_to_input_price():
    price = Rates(provider="p", model="m", valid_from="", source="", input=2.0, output=8.0,
                  tiers=(Tier(above=100, input=4.0),))

    assert price.cost(input_tokens=10, cache_read_tokens=20, cache_write_tokens=30) == (
        pytest.approx((10 + 20 + 30) * 2.0 / 1e6)
    )
    assert price.cost(input_tokens=100, cache_read_tokens=1) == pytest.approx(101 * 4.0 / 1e6)


def test_alternate_mode_prices():
    fast = rates("claude-opus-5-5", at="2026-09-25", mode="fast")

    assert (fast.input, fast.output) == (8, 40)
    assert rates("claude-opus-5-5", mode="missing-mode") is None


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


def test_backfill_replays_price_changes_and_symlinks(tmp_path):
    repo = tmp_path / "models.dev"
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
    # A first-party id serving a lab model, a deprecated id serving the same model, and
    # a deleted id, to check which id a lab model name resolves to.
    (models / "legacy.toml").write_text(
        'base_model = "openai/gpt-6-astra-lab"\nstatus = "deprecated"\n'
    )
    (models / "removed.toml").write_text('base_model = "openai/gpt-6-other"\n')
    _commit(repo, "add ids", "2026-09-11T10:00:00+00:00")
    (models / "removed.toml").unlink()
    (models / "gpt-6-astra.toml").write_text(
        'base_model = "openai/gpt-6-astra-lab"\n' + ASTRA.format(input="9.00").split("\n", 1)[1]
    )
    _commit(repo, "serve lab model", "2026-09-12T10:00:00+00:00")

    data = build(repo, ("openai",))

    entries = data["providers"]["openai"]["gpt-6-astra"]
    assert [(item["valid_from"], item["rates"]["input"]) for item in entries] == [
        ("2026-09-04T15:00:00Z", 10.0), ("2026-09-10T10:00:00Z", 9.0),
    ]
    assert entries[0]["rates"]["tiers"] == [{"above": 272_000, "input": 20.0, "output": 75.0}]
    assert entries[0]["rates"]["modes"] == {"fast": {"input": 20.0, "output": 100.0}}
    assert data["links"] == {"openai": {"astra-latest": "gpt-6-astra"}}
    assert data["bases"] == {"openai": {"gpt-6-astra-lab": "gpt-6-astra"}}

    output = tmp_path / "prices.json"
    assert write(data, output)
    unchanged = {**data, "source_commit": "later"}
    assert not write(unchanged, output)
    assert json.loads(output.read_text())["source_commit"] == data["source_commit"]


def test_parse_rates_reads_legacy_long_context_prices():
    parsed = parse_rates({"cost": {"input": 1, "output": 2, "context_over_200k": {"input": 3}}})

    assert parsed == {"input": 1.0, "output": 2.0, "tiers": [{"above": 200_000, "input": 3.0}]}
    assert parse_rates({"cost": {"output": 2}}) is None
    assert parse_rates({"name": "no cost"}) is None


def test_shipped_data_identifies_its_source():
    basis = llm_prices.pricing_basis()

    assert basis.startswith("llm-prices-")
    assert "+models.dev@" in basis


def test_cli_prints_rates(capsys):
    assert main(["rate", "claude-opus-5-5", "--at", "2026-09-25", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["cache_read"] == 0.2
    assert main(["rate", "codex-auto-review"]) == 1


def test_module_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "llm_prices", "--version"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0"


@pytest.mark.parametrize(
    ("at", "period", "input_price"),
    [
        ("2026-08-10T02:00:00Z", None, 0.14),        # flat pricing before 2026-08-16T16:00Z
        ("2026-08-17T02:00:00Z", "peak", 0.44),      # Monday peak hour
        ("2026-08-17T05:00:00Z", "off_peak", 0.22),  # between the two peak windows
        ("2026-08-22T02:00:00Z", "off_peak", 0.22),  # Saturday: the current rule applies from the start
        ("2026-09-10T08:00:00Z", "peak", 0.30),      # V4.1 Flash price before models.dev caught up
        ("2026-09-25T02:00:00Z", "off_peak", 0.15),  # Mid-Autumn Festival holiday
        ("2026-09-28T02:00:00Z", "peak", 0.30),
    ],
)
def test_deepseek_time_of_day_prices(at, period, input_price):
    found = rates("deepseek-v4-flash", at=at)

    assert found.period == period
    assert found.input == pytest.approx(input_price)


def test_peak_multiplier_scales_every_rate():
    off_peak = rates("deepseek-v4-pro", at="2026-09-30T13:00:00Z")
    peak = rates("deepseek-v4-pro", at="2026-09-30T02:00:00Z")

    assert (off_peak.input, off_peak.cache_read, off_peak.output) == (0.66, 0.022, 1.98)
    assert (peak.input, peak.cache_read, peak.output) == pytest.approx((1.32, 0.044, 3.96))
    assert rates("claude-opus-5-5", at="2026-09-30T02:00:00Z").period is None


def test_strict_resolution_keeps_suffixes():
    assert resolve("gpt-3.5-turbo-1106") == ("openai", "gpt-3.5-turbo")
    assert resolve("gpt-3.5-turbo-1106", strict=True) is None


def test_current_price_list_keeps_the_request_time_of_day():
    # A V4 Flash peak hour in August, priced from the September price list.
    then = rates("deepseek-v4-flash", at="2026-08-17T02:00:00Z")
    now = rates("deepseek-v4-flash", at="2026-08-17T02:00:00Z", prices_at="2026-09-30T00:00:00Z")
    off_peak_now = rates("deepseek-v4-flash", at="2026-08-17T05:00:00Z",
                         prices_at="2026-09-30T00:00:00Z")

    assert (then.input, then.period) == (0.44, "peak")
    assert (now.input, now.period) == (pytest.approx(0.30), "peak")
    assert (off_peak_now.input, off_peak_now.period) == (0.15, "off_peak")


def test_plan_prices():
    assert llm_prices.plan("anthropic", "max_20x").usd_per_month == 200
    assert llm_prices.plan("zai", "lite").usd_per_month == 18
    # Google AI Ultra was one plan until 2026-05-19, then two price-tagged tiers.
    assert llm_prices.plan("google", "ultra", at="2026-05-01").usd_per_month == 249.99
    assert llm_prices.plan("google", "ultra", at="2026-06-01") is None
    assert llm_prices.plan("google", "ultra_100").name == "Google AI Ultra $100"
    assert llm_prices.plan("google", "ultra_200").usd_per_month == 199.99
    assert llm_prices.plan("google", "ultra_200", at="2026-05-01") is None
    assert llm_prices.plan("openai", "pro_500").usd_per_month == 500
    assert llm_prices.plan_ids("google") == ["pro", "ultra_100", "ultra_200"]
    assert "ultra" in llm_prices.plan_ids("google", at="2026-05-01")


def test_rates_report_the_suffix_removed_to_find_the_model():
    assert rates("kimi-k3-max").removed_suffix == "-max"
    assert rates("gpt-5.5-2026-04-23").removed_suffix == "-2026-04-23"
    assert rates("claude-opus-5[1m]").removed_suffix == "[1m]"
    assert rates("grok-4.6-build").removed_suffix == "-build"
    assert rates("claude-opus-5-5").removed_suffix == ""
    assert rates("deepseek-v4.1-flash").removed_suffix == ""


def test_price_key_ignores_provenance():
    corrected = rates("gpt-5.6-sol", at="2026-08-23T00:00:00Z")
    recorded = rates("gpt-5.6-sol", at="2026-09-01T00:00:00Z")

    assert corrected.source != recorded.source
    assert corrected.price_key() == recorded.price_key()


def test_rates_between_returns_each_distinct_price():
    # A Monday 00:00-12:00 UTC span crosses DeepSeek's two peak windows.
    segments = rates_between("deepseek-flash", "2026-09-28T00:00:00Z", "2026-09-28T12:00:00Z")

    assert [(when.isoformat(), found.period) for when, found in segments] == [
        ("2026-09-28T00:00:00+00:00", "off_peak"),
        ("2026-09-28T01:00:00+00:00", "peak"),
        ("2026-09-28T04:00:00+00:00", "off_peak"),
        ("2026-09-28T06:00:00+00:00", "peak"),
        ("2026-09-28T10:00:00+00:00", "off_peak"),
    ]
    # One price across a correction ending with identical rates.
    assert len(rates_between("gpt-5.6-sol", "2026-08-24T00:00:00Z", "2026-08-26T00:00:00Z")) == 1
    # A price change inside the span.
    changes = rates_between("gpt-5.6-sol", "2026-08-21T00:00:00Z", "2026-08-23T00:00:00Z")
    assert [(found.input, found.output) for _, found in changes] == [(5.0, 30.0), (4.0, 20.0)]
    # A Chinese holiday weekday has no peak hours.
    assert len(rates_between("deepseek-flash", "2026-10-01T00:00:00Z", "2026-10-01T23:00:00Z")) == 1
    assert rates_between("codex-auto-review", "2026-09-01", "2026-09-02") == []
