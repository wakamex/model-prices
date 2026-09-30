"""Effective-dated LLM API prices from models.dev history, with sourced corrections."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import cache
from importlib.metadata import version
from importlib.resources import files
import json
from pathlib import Path
import re
import sys
import tomllib
from typing import Any

# Search order for model names given without a known provider.
LAB_PROVIDERS = (
    "anthropic", "openai", "google", "zai", "deepseek", "xai", "moonshotai", "alibaba",
)

_EFFORT_SUFFIX = re.compile(r"-(minimal|low|medium|high|xhigh|max|thinking)$")
_DATE_SUFFIX = re.compile(r"-(\d{8}|\d{4})$")


@dataclass(frozen=True)
class Tier:
    above: int
    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None


@dataclass(frozen=True)
class Rates:
    """USD per million tokens in effect for one model at one time."""

    provider: str
    model: str
    valid_from: str
    source: str
    input: float
    output: float
    cache_read: float | None = None
    cache_write: float | None = None
    tiers: tuple[Tier, ...] = ()
    # "peak" or "off_peak" for providers with time-of-day pricing, else None.
    period: str | None = None
    # The default-model alias this model was inferred from, such as "gemini-default".
    inferred_from: str | None = None

    def cost(self, input_tokens: int = 0, output_tokens: int = 0,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> float:
        """Price one request; input_tokens excludes cache reads and writes.

        Long-context tiers apply when the request's whole prompt exceeds the tier size.
        Missing cache prices fall back to the input price.
        """
        prompt = input_tokens + cache_read_tokens + cache_write_tokens
        rates: dict[str, float | None] = {
            "input": self.input, "output": self.output,
            "cache_read": self.cache_read, "cache_write": self.cache_write,
        }
        for tier in self.tiers:
            if prompt > tier.above:
                rates.update({
                    key: value for key, value in asdict(tier).items()
                    if key != "above" and value is not None
                })
        input_rate = rates["input"]
        cache_read = rates["cache_read"] if rates["cache_read"] is not None else input_rate
        cache_write = rates["cache_write"] if rates["cache_write"] is not None else input_rate
        return (
            input_tokens * input_rate
            + output_tokens * rates["output"]
            + cache_read_tokens * cache_read
            + cache_write_tokens * cache_write
        ) / 1e6


@cache
def _prices() -> dict[str, Any]:
    return json.loads(files(__package__).joinpath("data/prices.json").read_text())


@cache
def _config(name: str) -> dict[str, Any]:
    return tomllib.loads(files(__package__).joinpath(f"data/{name}").read_text())


def _parse_time(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = (
        value if isinstance(value, datetime)
        else datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def pricing_basis() -> str:
    """Identify the price data, for recording alongside computed costs."""
    return f"llm-prices-{version('llm-prices')}+models.dev@{_prices()['source_commit'][:12]}"


def _known(provider: str, model: str) -> bool:
    data = _prices()
    return (model in data["providers"].get(provider, {})
            or model in data["links"].get(provider, {}))


@cache
def resolve(model: str, provider: str | None = None,
            strict: bool = False) -> tuple[str, str] | None:
    """Map a log or harness model name to a models.dev (provider, model) pair.

    strict=True skips removing effort and date suffixes, for names that must match exactly.
    """
    aliases = _config("aliases.toml")
    name = re.sub(r"[\s_]+", "-", re.sub(r"[()]", "", model.strip().lower())).strip("-")
    if "/" in name:
        prefix, name = name.split("/", 1)
        provider = provider or prefix
    hint = aliases["providers"].get((provider or "").lower(), (provider or "").lower())

    candidates = [name]
    for pattern in () if strict else (_EFFORT_SUFFIX, _DATE_SUFFIX):
        candidates += [pattern.sub("", candidate) for candidate in candidates]
    order = ([hint] if hint in _prices()["providers"] else []) + [
        lab for lab in LAB_PROVIDERS if lab != hint
    ]
    candidates = list(dict.fromkeys(candidates))
    for candidate in candidates:
        if candidate in aliases["models"]:
            target_provider, target_model = aliases["models"][candidate].split("/", 1)
            return target_provider, target_model
    # Prefer the model's own lab over another lab that also serves a variant of it.
    # A lab model name resolves to the first-party id that serves and prices it.
    bases = _prices()["bases"]
    for lab in order:
        for candidate in candidates:
            if _known(lab, candidate):
                return lab, candidate
            if candidate in bases.get(lab, {}):
                return lab, bases[lab][candidate]
    return None


def _tiers(raw: list[dict[str, Any]] | None) -> tuple[Tier, ...]:
    return tuple(Tier(**tier) for tier in raw or ())


@cache
def _corrections(provider: str, model: str) -> tuple[tuple[datetime, datetime | None, dict], ...]:
    return tuple(
        (_parse_time(item["valid_from"]),
         _parse_time(item["valid_until"]) if "valid_until" in item else None, item)
        for item in _config("corrections.toml").get("correction", [])
        if item["provider"] == provider and item["model"] == model
    )


@cache
def _entry_times(provider: str, model: str) -> tuple[datetime, ...]:
    entries = _prices()["providers"].get(provider, {}).get(model, [])
    return tuple(_parse_time(entry["valid_from"]) for entry in entries)


def _correction(provider: str, model: str, at: datetime) -> Rates | None:
    for start, end, item in _corrections(provider, model):
        if start <= at and (end is None or at < end):
            return Rates(
                provider=provider, model=model, valid_from=item["valid_from"],
                source=item["source"], input=item["input"], output=item["output"],
                cache_read=item.get("cache_read"), cache_write=item.get("cache_write"),
                tiers=_tiers(item.get("tiers")),
            )
    return None


def _history_rates(provider: str, model: str, at: datetime, mode: str | None) -> Rates | None:
    data = _prices()
    entries = data["providers"].get(provider, {}).get(model, [])
    times = _entry_times(provider, model)
    link = data["links"].get(provider, {}).get(model)
    if link and (not entries or at < times[0]):
        return _history_rates(provider, link, at, mode)
    if not entries:
        return None
    # Usage before a model's first recorded price uses that first price.
    entry = entries[max(bisect_right(times, at) - 1, 0)]
    values = dict(entry["rates"])
    tiers = values.pop("tiers", None)
    modes = values.pop("modes", {})
    if mode is not None:
        if mode not in modes:
            return None
        values.update(modes[mode])
        tiers = None
    return Rates(
        provider=provider, model=model, valid_from=entry["valid_from"],
        source=f"{data['source']}/commit/{entry['commit']}",
        input=values["input"], output=values["output"],
        cache_read=values.get("cache_read"), cache_write=values.get("cache_write"),
        tiers=_tiers(tiers),
    )


def _in_window(moment: datetime, window: list[str]) -> bool:
    start, end = (datetime.strptime(value, "%H:%M").time() for value in window)
    return start <= moment.time() < end


@cache
def _schedules(provider: str) -> tuple[tuple[datetime, datetime | None, dict], ...]:
    return tuple(
        (_parse_time(item["valid_from"]),
         _parse_time(item["valid_until"]) if "valid_until" in item else None, item)
        for item in _config("schedules.toml").get("schedule", [])
        if item["provider"] == provider
    )


def _schedule(provider: str, moment: datetime) -> dict[str, Any] | None:
    """Return the provider's time-of-day pricing schedule in effect at `moment`."""
    for start, end, schedule in _schedules(provider):
        if start <= moment and (end is None or moment < end):
            return schedule
    return None


def _period(provider: str, moment: datetime,
            schedule_at: datetime | None = None) -> tuple[str, float] | None:
    """Return the time-of-day period and its multiplier on recorded rates, if any.

    schedule_at selects which version of the schedule applies; it defaults to `moment`.
    """
    schedule = _schedule(provider, schedule_at or moment)
    if schedule is None:
        return None
    peak = any(_in_window(moment, window) for window in schedule["peak_hours_utc"])
    if schedule.get("weekdays_only") and moment.weekday() >= 5:
        peak = False
    calendar = _config("schedules.toml").get("holidays", {}).get(schedule.get("holidays", ""))
    if calendar:
        local = moment + timedelta(hours=calendar["utc_offset_hours"])
        peak = peak and local.date().isoformat() not in calendar["dates"]
    return ("peak", schedule["peak_multiplier"]) if peak else ("off_peak", 1.0)


def _scaled(found: Rates, period: str, factor: float) -> Rates:
    def scale(value: float | None) -> float | None:
        return None if value is None else value * factor
    return replace(
        found, period=period, input=found.input * factor, output=found.output * factor,
        cache_read=scale(found.cache_read), cache_write=scale(found.cache_write),
        tiers=tuple(
            replace(tier, input=scale(tier.input), output=scale(tier.output),
                    cache_read=scale(tier.cache_read), cache_write=scale(tier.cache_write))
            for tier in found.tiers
        ),
    )


def default_target(model: str, at: datetime | str | None = None) -> tuple[str, str] | None:
    """Return the (provider, model) a default-model alias named at `at`, if `model` is one.

    Before the first recorded target, the first target applies.
    """
    name = model.strip().lower().split("/")[-1]
    moment = _parse_time(at)
    for alias in _config("defaults.toml").get("alias", []):
        if alias["name"] != name:
            continue
        target = alias["targets"][0]
        for candidate in alias["targets"]:
            if _parse_time(candidate["valid_from"]) <= moment:
                target = candidate
        return alias["provider"], target["model"]
    return None


def rates(model: str, at: datetime | str | None = None, provider: str | None = None,
          mode: str | None = None, corrected: bool = True,
          prices_at: datetime | str | None = None) -> Rates | None:
    """Return the rates for a request made at `at` (default now), or None for an unknown model.

    Time-of-day pricing applies peak rates inside the provider's peak windows.
    prices_at selects a different price list, such as today's, while `at` still decides
    whether the request fell in peak hours; it defaults to `at`.
    corrected=False returns models.dev's recorded rates without local corrections.
    """
    # A default-model alias is resolved by when the request ran, even when pricing it
    # from another date's price list.
    inferred = default_target(model, at)
    if inferred is not None:
        found = rates(inferred[1], at=at, provider=inferred[0], mode=mode,
                      corrected=corrected, prices_at=prices_at)
        name = model.strip().lower().split("/")[-1]
        return replace(found, inferred_from=name) if found else None
    resolved = resolve(model, provider)
    if resolved is None:
        return None
    moment = _parse_time(at)
    listed = _parse_time(prices_at) if prices_at is not None else moment
    found = _correction(*resolved, listed) if mode is None and corrected else None
    found = found or _history_rates(*resolved, listed, mode)
    if found is None:
        return None
    period = _period(resolved[0], moment, schedule_at=listed)
    return _scaled(found, *period) if period else found


def cost(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
         cache_read_tokens: int = 0, cache_write_tokens: int = 0,
         at: datetime | str | None = None, provider: str | None = None,
         mode: str | None = None, prices_at: datetime | str | None = None) -> float | None:
    """Price one request made at `at`; input_tokens excludes cache reads and writes."""
    found = rates(model, at=at, provider=provider, mode=mode, prices_at=prices_at)
    if found is None:
        return None
    return found.cost(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)


@dataclass(frozen=True)
class Plan:
    provider: str
    id: str
    name: str
    usd_per_month: float
    source: str


def plan_ids(provider: str, at: datetime | str | None = None) -> list[str]:
    """Return the provider's plan ids with a price in effect at `at` (default now)."""
    ids = {item["id"] for item in _config("plans.toml").get("plan", [])
           if item["provider"] == provider}
    return sorted(plan_id for plan_id in ids if plan(provider, plan_id, at) is not None)


def plan(provider: str, plan_id: str, at: datetime | str | None = None) -> Plan | None:
    """Return a subscription plan's monthly price in effect at `at` (default now)."""
    moment = _parse_time(at)
    found = None
    for item in _config("plans.toml").get("plan", []):
        if item["provider"] != provider or item["id"] != plan_id:
            continue
        if "valid_from" in item and _parse_time(item["valid_from"]) > moment:
            continue
        if "valid_until" in item and _parse_time(item["valid_until"]) <= moment:
            continue
        found = item
    if found is None:
        return None
    return Plan(provider, plan_id, found["name"], found["usd_per_month"], found["source"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="llm-prices", description=__doc__)
    parser.add_argument("--version", action="version", version=version("llm-prices"))
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("rate", help="Show the rates for a model at a time")
    show.add_argument("model")
    show.add_argument("--provider")
    show.add_argument("--at", help="ISO 8601 time (default: now)")
    show.add_argument("--mode", help="Alternate pricing mode, such as fast")
    show.add_argument("--json", action="store_true")
    update = commands.add_parser(
        "update", help="Rebuild price history from a models.dev git checkout"
    )
    update.add_argument("models_dev", type=Path)
    update.add_argument("--output", type=Path,
                        default=Path("src/llm_prices/data/prices.json"))
    check = commands.add_parser(
        "check", help="Compare effective prices with official provider pricing pages"
    )
    check.add_argument("providers", nargs="*", help="Providers to check (default: all)")
    check.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "check":
        from llm_prices.checks import SOURCES, as_json, report, run
        unknown = sorted(set(args.providers) - set(SOURCES))
        if unknown:
            parser.error(f"no official pricing check for: {', '.join(unknown)}")
        results = run(args.providers or None)
        print(json.dumps(as_json(results), indent=2) if args.json else report(results))
        return 1 if any(result.status == "mismatch" for result in results) else 0

    if args.command == "update":
        from llm_prices.backfill import build, write
        changed = write(build(args.models_dev), args.output)
        print(f"Updated {args.output}" if changed else "No tracked price changes.")
        return 0

    found = rates(args.model, at=args.at, provider=args.provider, mode=args.mode)
    if found is None:
        print(f"No price found for {args.model}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(found), indent=2))
        return 0
    period = f", {found.period.replace('_', '-')} rate" if found.period else ""
    print(f"{found.provider}/{found.model} from {found.valid_from}{period} ({found.source})")
    print(f"input ${found.input}  output ${found.output}  "
          f"cache read ${found.cache_read}  cache write ${found.cache_write}  per 1M tokens")
    for tier in found.tiers:
        print(f"above {tier.above:,} prompt tokens: input ${tier.input}  output ${tier.output}  "
              f"cache read ${tier.cache_read}  cache write ${tier.cache_write}")
    return 0
