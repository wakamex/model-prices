"""Compare llm-prices corrections with Pydantic's genai-prices, an independent price list.

For each correction, takes the middle of its period and prices the model there three ways:
the correction, models.dev's own entry, and genai-prices. genai-prices is read twice: its
current data, which dates a few price changes with start_date, and the data.json committed
on or before that moment, which shows what it listed then. Each corrected field is then
reported as agreeing with the correction, with models.dev, or with neither, or as
missing when genai-prices lists no price for it.

    uv run --no-config python research/crosscheck_genai_prices.py GENAI_PRICES_CHECKOUT
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import cache
import json
from pathlib import Path
import re
import subprocess
import tomllib

import llm_prices

DATA = Path(__file__).resolve().parent.parent / "src" / "llm_prices" / "data"
PROVIDERS = {"anthropic": "anthropic", "deepseek": "deepseek", "google": "google",
             "moonshotai": "moonshotai", "openai": "openai", "xai": "x-ai", "zai": "zhipuai"}
FIELDS = {"input": "input_mtok", "output": "output_mtok", "cache_read": "cache_read_mtok",
          "cache_write": "cache_write_mtok"}


def _time(value: str) -> datetime:
    if len(value) == 10:
        value += "T00:00:00Z"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _matches(rule: dict, name: str) -> bool:
    if "or" in rule:
        return any(_matches(item, name) for item in rule["or"])
    if "and" in rule:
        return all(_matches(item, name) for item in rule["and"])
    if "equals" in rule:
        return name == rule["equals"]
    if "starts_with" in rule:
        return name.startswith(rule["starts_with"])
    if "ends_with" in rule:
        return name.endswith(rule["ends_with"])
    if "contains" in rule:
        return rule["contains"] in name
    if "regex" in rule:
        return re.search(rule["regex"], name) is not None
    return False


def _base(value: object) -> float | None:
    return value["base"] if isinstance(value, dict) else value


def genai_rates(data: list, provider: str, model: str, at: datetime) -> dict | None:
    """The model's prices at a moment, the first matching model winning as in genai-prices."""
    found = next((item for item in data if item["id"] == PROVIDERS.get(provider)), None)
    if found is None:
        return None
    entry = next((item for item in found["models"] if _matches(item["match"], model.lower())), None)
    if entry is None:
        return None
    prices = entry["prices"]
    if isinstance(prices, list):
        dated = [item for item in prices
                 if _time((item.get("constraint") or {}).get("start_date", "1970-01-01")) <= at]
        prices = dated[-1]["prices"] if dated else prices[0]["prices"]
    rates = {field: _base(prices.get(key)) for field, key in FIELDS.items()}
    tiered = prices.get("input_mtok")
    tiers = [item["start"] for item in tiered.get("tiers", [])] if isinstance(tiered, dict) else []
    return {**rates, "tier": min(tiers) if tiers else None, "id": entry["id"]}


@cache
def _snapshot(checkout: Path, commit: str) -> list:
    return json.loads(subprocess.run(["git", "-C", str(checkout), "show", f"{commit}:prices/data.json"],
                                     check=True, capture_output=True, text=True).stdout)


def _commits(checkout: Path) -> list[tuple[datetime, str]]:
    log = subprocess.run(["git", "-C", str(checkout), "log", "--format=%H %cI", "--", "prices/data.json"],
                         check=True, capture_output=True, text=True).stdout
    return sorted((_time(when), commit) for commit, when in (line.split() for line in log.splitlines()))


def _compare(value: object, corrected: object, recorded: object) -> str:
    def same(left: object, right: object) -> bool:
        if left is None or right is None:
            return left is None and right is None
        return abs(float(left) - float(right)) < 1e-9
    if value is None:
        return "missing"  # genai-prices lists no price, which is no evidence either way
    if same(value, corrected):
        return "correction"
    if same(value, recorded):
        return "models.dev"
    return "neither"


def crosscheck(checkout: Path) -> None:
    current = json.loads((checkout / "prices" / "data.json").read_text())
    commits = _commits(checkout)
    totals: Counter[tuple[str, str]] = Counter()
    for name in ("corrections.toml", "research_corrections.toml"):
        for item in tomllib.loads((DATA / name).read_text())["correction"]:
            start = _time(item["valid_from"])
            end = _time(item["valid_until"]) if "valid_until" in item else datetime.now(timezone.utc)
            at = start + (end - start) / 2
            recorded = llm_prices.rates(item["model"], provider=item["provider"], at=at,
                                        corrected=False)
            earlier = [commit for when, commit in commits if when <= at]
            views = {"now": genai_rates(current, item["provider"], item["model"], at),
                     "then": genai_rates(_snapshot(checkout, earlier[-1]), item["provider"],
                                         item["model"], at) if earlier else None}
            changed = [field for field in FIELDS if item.get(field) != getattr(recorded, field)]
            corrected_tier = min((tier["above"] for tier in item.get("tiers", [])), default=None)
            recorded_tier = min((tier.above for tier in recorded.tiers), default=None)
            line = []
            for view, rates in views.items():
                if rates is None:
                    line.append(f"{view}: no data")
                    totals[(view, "no data")] += 1
                    continue
                verdicts = {field: _compare(rates[field], item.get(field), getattr(recorded, field))
                            for field in changed}
                if corrected_tier != recorded_tier:
                    verdicts["tier"] = _compare(rates["tier"], corrected_tier, recorded_tier)
                for verdict in verdicts.values():
                    totals[(view, verdict)] += 1
                line.append(f"{view}: " + (", ".join(f"{field} {verdict}" for field, verdict in
                                                    verdicts.items()) or "no field changed"))
            print(f"{name.split('.')[0]:22} {item['provider']}/{item['model']} "
                  f"{start.date()}..{end.date()} | " + " | ".join(line))
    print()
    for (view, verdict), count in sorted(totals.items()):
        print(f"{view:5} {verdict:11} {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checkout", type=Path, help="a git checkout of pydantic/genai-prices")
    crosscheck(parser.parse_args().checkout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
