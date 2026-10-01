"""Read prices from Pydantic's genai-prices, an independent price list, for comparison."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.request

DATA_URL = "https://raw.githubusercontent.com/pydantic/genai-prices/main/prices/data.json"

# model-prices provider ids and the genai-prices ids for the same first-party APIs. Z.ai has
# none: genai-prices' zhipuai is Zhipu's mainland China API, priced from yuan.
PROVIDERS = {"anthropic": "anthropic", "deepseek": "deepseek", "google": "google",
             "moonshotai": "moonshotai", "openai": "openai", "xai": "x-ai"}
FIELDS = {"input": "input_mtok", "output": "output_mtok", "cache_read": "cache_read_mtok",
          "cache_write": "cache_write_mtok"}


def load(source: str) -> list:
    """genai-prices' data.json from a URL, the file itself, or a checkout containing it."""
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "model-prices"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
    path = Path(source)
    if path.is_dir():
        path = path / "prices" / "data.json"
    return json.loads(path.read_text())


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


def _names(rule: dict) -> set[str]:
    """The exact model names a match rule lists."""
    if "equals" in rule:
        return {rule["equals"]}
    return {name for key in ("or", "and") for item in rule.get(key, []) for name in _names(item)}


def model_prices(data: list, provider: str, model: str, at: datetime) -> tuple[str, dict] | None:
    """The genai-prices model that lists a name exactly, and its prices at a moment.

    genai-prices also matches names by prefix, so a model it lacks, such as a newer
    version, can resolve to an older model's prices. Only exact listings count here, so
    a missing model reads as not listed rather than as a wrong price.
    """
    name = model.lower()
    found = next((item for item in data if item["id"] == PROVIDERS.get(provider)), None)
    entry = next((item for item in found["models"]
                  if name == item["id"] or name in _names(item["match"])), None) if found else None
    if entry is None:
        return None
    prices = entry["prices"]
    if isinstance(prices, list):
        dated = [item for item in prices
                 if _time((item.get("constraint") or {}).get("start_date", "1970-01-01")) <= at]
        prices = dated[-1]["prices"] if dated else prices[0]["prices"]
    return entry["id"], prices


def price(data: list, provider: str, model: str, field: str, at: datetime,
          above: int | None = None) -> float | None:
    """One price in USD per million tokens, or None when genai-prices lists none."""
    found = model_prices(data, provider, model, at)
    value = found[1].get(FIELDS[field]) if found else None
    if isinstance(value, dict):
        if above is None:
            return value["base"]
        return next((tier["price"] for tier in value.get("tiers", [])
                     if tier["start"] in (above, above + 1)), None)
    return value if above is None else None


def tier_start(data: list, provider: str, model: str, at: datetime) -> int | None:
    """The smallest prompt size at which genai-prices starts a higher input price."""
    found = model_prices(data, provider, model, at)
    value = found[1].get("input_mtok") if found else None
    starts = [tier["start"] for tier in value.get("tiers", [])] if isinstance(value, dict) else []
    return min(starts) if starts else None
