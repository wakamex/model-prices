"""Score how promptly models.dev and genai-prices recorded price changes with known dates.

Each event below is a price change whose time was established from the provider's own
announcements or archived pricing pages (see corrections.toml and the findings). For each,
this reports when models.dev first recorded the new price, when genai-prices first
committed it, and any start date genai-prices assigns, measured against the true time.

    uv run --locked python research/score_dating.py GENAI_PRICES_CHECKOUT
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from functools import cache
import json
from pathlib import Path
import subprocess

from llm_prices import genai_prices

PRICES = Path(__file__).resolve().parent.parent / "src" / "llm_prices" / "data" / "prices.json"
FAR_FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)

# (provider, model, field, new value, true time, how the time is known). A field of
# "tier" with value None means the long-context tier was removed.
EVENTS = [
    ("anthropic", "claude-sonnet-4-6", "tier", None, "2026-03-13T00:00:00Z",
     "Anthropic's 1M context GA post, dated 2026-03-13"),
    ("anthropic", "claude-opus-4-6", "tier", None, "2026-03-13T00:00:00Z",
     "Anthropic's 1M context GA post, dated 2026-03-13"),
    ("openai", "gpt-5.6-luna", "input", 0.2, "2026-07-30T00:00:00Z",
     "OpenAI announcement dated 2026-07-30 (research finding)"),
    ("openai", "gpt-5.6-terra", "input", 2.0, "2026-07-30T00:00:00Z",
     "OpenAI announcement dated 2026-07-30 (research finding)"),
    ("google", "gemini-3.6-flash", "input", 0.75, "2026-08-13T18:11:24Z",
     "first archived pricing page with the promotion; previous copy 2026-08-12T04:23Z"),
    ("deepseek", "deepseek-v4-flash", "input", 0.22, "2026-08-16T16:00:00Z",
     "DeepSeek changelog: effective 2026-08-17 00:00 Beijing time"),
    ("deepseek", "deepseek-v4-pro", "input", 0.66, "2026-08-16T16:00:00Z",
     "DeepSeek changelog: effective 2026-08-17 00:00 Beijing time"),
    ("openai", "gpt-5.6-sol", "input", 4.0, "2026-08-21T00:00:00Z",
     "OpenAI GPT-5.6 post: update on 2026-08-21"),
    ("deepseek", "deepseek-v4-flash", "input", 0.15, "2026-09-10T04:00:00Z",
     "DeepSeek V4.1 Flash release note: 04:00 UTC"),
]


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _shows(prices: dict, field: str, value: float | None) -> bool:
    if field == "tier":
        return not prices.get("tiers")
    return prices.get(field) is not None and abs(prices[field] - value) < 1e-9


def models_dev_first(provider: str, model: str, field: str, value: float | None,
                     since: datetime) -> datetime | None:
    """When models.dev first recorded the new price after the previous one."""
    entries = json.loads(PRICES.read_text())["providers"].get(provider, {}).get(model, [])
    for previous, entry in zip(entries, entries[1:]):
        if (_shows(entry["rates"], field, value) and not _shows(previous["rates"], field, value)
                and _time(entry["valid_from"]) >= since):
            return _time(entry["valid_from"])
    return None


def _genai_view(prices: dict, field: str) -> dict:
    """genai-prices' prices in the shape of a models.dev rates entry."""
    key = genai_prices.FIELDS.get(field, "input_mtok")
    value = prices.get(key)
    if field == "tier":
        return {"tiers": value.get("tiers") if isinstance(value, dict) else None}
    return {field: value["base"] if isinstance(value, dict) else value}


@cache
def _snapshot(checkout: Path, commit: str) -> list:
    return json.loads(subprocess.run(["git", "-C", str(checkout), "show", f"{commit}:prices/data.json"],
                                     check=True, capture_output=True, text=True).stdout)


def genai_first(checkout: Path, provider: str, model: str, field: str, value: float | None,
                since: datetime) -> tuple[datetime | None, str | None]:
    """When genai-prices first committed the new price, and the start date it gives it."""
    log = subprocess.run(["git", "-C", str(checkout), "log", "--reverse", "--format=%H %cI",
                          f"--since={(since - timedelta(days=60)).isoformat()}", "--", "prices/data.json"],
                         check=True, capture_output=True, text=True).stdout
    for commit, when in (line.split() for line in log.splitlines()):
        data = _snapshot(checkout, commit)
        found = genai_prices.model_prices(data, provider, model, FAR_FUTURE)
        if found and _shows(_genai_view(found[1], field), field, value):
            start = _start_date(data, provider, model, field, value)
            return _time(when), start
    return None, None


def _start_date(data: list, provider: str, model: str, field: str, value: float | None) -> str | None:
    """The start_date genai-prices puts on the prices showing the new value, if any."""
    entry = genai_prices.model_prices(data, provider, model, FAR_FUTURE)
    providers = next(item for item in data if item["id"] == genai_prices.PROVIDERS[provider])
    listed = next(item for item in providers["models"] if item["id"] == entry[0])["prices"]
    if not isinstance(listed, list):
        return None
    for item in listed:
        if _shows(_genai_view(item["prices"], field), field, value):
            return (item.get("constraint") or {}).get("start_date")
    return None


def _lag(found: datetime | None, true: datetime) -> str:
    if found is None:
        return "never"
    hours = (found - true).total_seconds() / 3600
    return f"{hours / 24:+.1f} days" if abs(hours) >= 48 else f"{hours:+.0f} h"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checkout", type=Path, help="a git checkout of pydantic/genai-prices")
    checkout = parser.parse_args().checkout
    print("| Change | True time | models.dev recorded | genai-prices committed | genai-prices start date |")
    print("|---|---|---|---|---|")
    for provider, model, field, value, true_time, evidence in EVENTS:
        true = _time(true_time)
        since = true - timedelta(days=30)
        recorded = models_dev_first(provider, model, field, value, since)
        committed, start = genai_first(checkout, provider, model, field, value, since)
        change = f"{model} {'long-context tier removed' if field == 'tier' else f'{field} ${value:g}'}"
        start_text = f"{start} ({_lag(_time(start + 'T00:00:00Z'), true)})" if start else "none"
        print(f"| {change} | {true_time[:16].replace('T', ' ')} UTC | {_lag(recorded, true)} | "
              f"{_lag(committed, true)} | {start_text} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
