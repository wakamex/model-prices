import json
from pathlib import Path
import subprocess
import sys

import pytest

import llm_prices
from llm_prices import Rates, Tier, cost, main, rates, resolve
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
