"""Compile the input data into the price snapshot that model_prices reads.

The inputs in data/ are models.dev price history, prices observed on official pages for
models models.dev does not list (observed.json), and the files that adjust them: corrections,
one-hour cache-write multiples, time-of-day schedules, name aliases, and plans. Combining
them happens here, once, rather than in every client: each model's snapshot entry is its
final timeline, a list of intervals that each give the rates from their start. A client
looks rates up by time, so a client release prices any later snapshot of the same schema
correctly.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, replace
from datetime import datetime, timezone
from functools import cache
import json
from pathlib import Path
import tomllib
from typing import Any

from model_prices import SCHEMA, THINKING, Rates, _parse_time, _tiers

# Evaluated for usage before every recorded change, which takes a model's first price.
_EARLIEST = datetime.min.replace(tzinfo=timezone.utc)


class _Inputs:
    """The merge rules over one set of input files."""

    def __init__(self, data: Path):
        self.prices = json.loads((data / "prices.json").read_text())
        observed = data / "observed.json"
        for provider, models in (json.loads(observed.read_text())["providers"].items()
                                 if observed.exists() else ()):
            listed = self.prices["providers"].setdefault(provider, {})
            for model, entries in models.items():
                # Once models.dev lists an observed model, its history takes over from its
                # first entry.
                start = _parse_time(listed[model][0]["valid_from"]) if model in listed else None
                listed[model] = [entry for entry in entries if start is None
                                 or _parse_time(entry["valid_from"]) < start] + listed.get(model, [])
        self.config = {name: tomllib.loads((data / name).read_text()) for name in (
            "aliases.toml", "cache_writes.toml", "corrections.toml", "plans.toml",
            "research_corrections.toml", "schedules.toml")}
        self.cache_write_1h = {item["provider"]: item["multiple"]
                               for item in self.config["cache_writes.toml"]["cache_write_1h"]}
        self.entry_times = cache(self._entry_times)
        self.corrections = cache(self._corrections)

    def _corrections(self, provider: str, model: str):
        return tuple(
            (_parse_time(item["valid_from"]),
             _parse_time(item["valid_until"]) if "valid_until" in item else None, item)
            # Hand corrections first, so they take precedence over researched ones.
            for name in ("corrections.toml", "research_corrections.toml")
            for item in self.config[name].get("correction", [])
            if item["provider"] == provider and item["model"] == model
        )

    def _entry_times(self, provider: str, model: str) -> tuple[datetime, ...]:
        entries = self.prices["providers"].get(provider, {}).get(model, [])
        return tuple(_parse_time(entry["valid_from"]) for entry in entries)

    def link(self, provider: str, model: str, at: datetime) -> str | None:
        """The model an alias points to at `at`, when the alias has no price of its own then."""
        link = self.prices["links"].get(provider, {}).get(model)
        times = self.entry_times(provider, model)
        return link if link and (not times or at < times[0]) else None

    def correction(self, provider: str, model: str, at: datetime,
                   mode: str | None = None) -> Rates | None:
        """The corrected rates at `at`; in a mode, only when the correction states that
        mode's prices."""
        for start, end, item in self.corrections(provider, model):
            if start <= at and (end is None or at < end):
                if "replaces" in item:
                    # An open-ended correction stops once models.dev records anything else.
                    recorded = self.history(provider, model, at, None)
                    if recorded is None or any(getattr(recorded, key) != value
                                               for key, value in item["replaces"].items()):
                        continue
                values = {key: item.get(key) for key in (
                    "input", "output", "cache_read", "cache_write")}
                tiers = item.get("tiers")
                if mode is not None:
                    if mode not in item.get("modes", {}):
                        return None
                    values, tiers = _in_stated_mode(values, tiers, item["modes"][mode])
                return Rates(
                    provider=provider, model=model, valid_from=item["valid_from"],
                    source=item["source"], **values, tiers=_tiers(tiers),
                    valid_from_basis="documented",
                )
        # An alias without its own history at this time takes the corrections of the model
        # it points to, just as it takes that model's price history.
        link = self.link(provider, model, at)
        return self.correction(provider, link, at, mode) if link else None

    def history(self, provider: str, model: str, at: datetime, mode: str | None) -> Rates | None:
        link = self.link(provider, model, at)
        if link:
            return self.history(provider, link, at, mode)
        entries = self.prices["providers"].get(provider, {}).get(model, [])
        if not entries:
            return None
        # Usage before a model's first recorded price uses that first price.
        entry = entries[max(bisect_right(self.entry_times(provider, model), at) - 1, 0)]
        values = dict(entry["rates"])
        tiers = values.pop("tiers", None)
        modes = values.pop("modes", {})
        if mode is not None and mode not in modes and mode != THINKING:
            return None
        if mode in modes:
            values, tiers = _in_stated_mode(values, tiers, modes[mode])
        # An observed entry names its page, and is dated by the run that first saw it.
        return Rates(
            provider=provider, model=model, valid_from=entry["valid_from"],
            source=entry.get("source") or f"{self.prices['source']}/commit/{entry['commit']}",
            input=values["input"], output=values["output"],
            cache_read=values.get("cache_read"), cache_write=values.get("cache_write"),
            tiers=_tiers(tiers),
            valid_from_basis="first observed" if "source" in entry else "models.dev commit",
        )

    def rates(self, provider: str, model: str, at: datetime, mode: str | None,
              corrected: bool) -> Rates | None:
        found = self.correction(provider, model, at) if corrected else None
        stated = self.correction(provider, model, at, mode) if found and mode else None
        if stated is not None:
            found = stated
        elif found is not None and mode is not None:
            # A correction without the mode's prices gives standard rates; the mode keeps its
            # models.dev ratio to them.
            standard, moded = (self.history(provider, model, at, name) for name in (None, mode))
            found = _in_mode(found, standard, moded) if moded is not None and standard else None
            if moded is None:
                return None
        found = found or self.history(provider, model, at, mode)
        if found is not None and provider in self.cache_write_1h:
            found = replace(found, cache_write_1h_multiple=self.cache_write_1h[provider])
        return found

    def change_times(self, provider: str, model: str) -> list[datetime]:
        """Every time at which the model's rates can change."""
        times: set[datetime] = set()
        for name in (model, self.prices["links"].get(provider, {}).get(model)):
            if name:
                times |= set(self.entry_times(provider, name))
                for start, end, _ in self.corrections(provider, name):
                    times |= {start} | ({end} if end else set())
        return sorted(times)

    def modes(self, provider: str, model: str) -> list[str]:
        found: set[str] = set()
        for name in (model, self.prices["links"].get(provider, {}).get(model)):
            for entry in self.prices["providers"].get(provider, {}).get(name or "", []):
                found |= set(entry["rates"].get("modes", {}))
        return sorted(found)


def _in_stated_mode(values: dict[str, Any], tiers: list[dict] | None,
                    mode: dict[str, Any]) -> tuple[dict[str, Any], list[dict] | None]:
    """Standard rates with a mode's stated prices. The mode's tiers replace the fields they
    give in the standard tier of the same size, and a mode without tiers has none."""
    mode_tiers = {tier["above"]: tier for tier in mode.get("tiers", [])}
    values = {**values, **{key: value for key, value in mode.items() if key != "tiers"}}
    return values, [{**tier, **mode_tiers[tier["above"]]} for tier in tiers or []
                    if tier["above"] in mode_tiers] or None


def _in_mode(corrected: Rates, standard: Rates, moded: Rates) -> Rates:
    """Corrected rates in a mode, scaled by the mode's ratio to models.dev's standard rates."""
    def scaled(field: str) -> float | None:
        value, base, mode_value = (getattr(item, field) for item in (corrected, standard, moded))
        if value is None or not base or mode_value is None:
            return value
        return value * mode_value / base
    return replace(corrected, input=scaled("input"), output=scaled("output"),
                   cache_read=scaled("cache_read"), cache_write=scaled("cache_write"), tiers=())


def _stored(found: Rates | None, model: str) -> dict[str, Any] | None:
    """Rates as a snapshot stores them: without the provider, which the key gives, without
    fields a lookup fills in, and without unset values."""
    if found is None:
        return None
    stored = {key: value for key, value in asdict(found).items()
              if key not in {"provider", "period", "removed_suffix"}
              and value is not None and value != ()}
    if found.model == model:
        del stored["model"]
    if "tiers" in stored:
        stored["tiers"] = [{key: value for key, value in tier.items() if value is not None}
                           for tier in stored["tiers"]]
    return stored


def _timeline(inputs: _Inputs, provider: str, model: str, mode: str | None) -> list[dict]:
    """The intervals of one model's rates: each applies from its start until the next, and
    the first, with no start, also to every earlier time. An interval's rates are null when
    the model is not offered in that mode then. `recorded`, present only when it differs,
    is what models.dev alone listed."""
    intervals: list[dict] = []
    for at in (_EARLIEST, *inputs.change_times(provider, model)):
        effective = _stored(inputs.rates(provider, model, at, mode, True), model)
        recorded = _stored(inputs.rates(provider, model, at, mode, False), model)
        interval: dict[str, Any] = {"start": None if at is _EARLIEST else
                                    at.isoformat().replace("+00:00", "Z"), "rates": effective}
        if recorded != effective:
            interval["recorded"] = recorded
        if intervals and {**intervals[-1], "start": None} == {**interval, "start": None}:
            continue
        intervals.append(interval)
    return intervals


def build(data: Path) -> dict[str, Any]:
    """The snapshot content of the inputs in `data`, without its updated_at time."""
    inputs = _Inputs(data)
    prices: dict[str, dict[str, dict[str, list]]] = {}
    for provider in sorted({*inputs.prices["providers"], *inputs.prices["links"]}):
        models = {*inputs.prices["providers"].get(provider, {}),
                  *inputs.prices["links"].get(provider, {})}
        prices[provider] = {
            model: {mode or "standard": _timeline(inputs, provider, model, mode)
                    for mode in (None, *inputs.modes(provider, model))}
            for model in sorted(models)
        }
    return {
        "schema": SCHEMA,
        "models_dev": {"source": inputs.prices["source"],
                       "commit": inputs.prices["source_commit"],
                       "committed_at": inputs.prices["source_committed_at"]},
        "prices": prices,
        "bases": inputs.prices["bases"],
        "aliases": inputs.config["aliases.toml"],
        "schedules": inputs.config["schedules.toml"],
        "plans": inputs.config["plans.toml"].get("plan", []),
    }


def serialize(snapshot: dict[str, Any]) -> bytes:
    return (json.dumps(snapshot, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode()


def write(data: Path, output: Path, now: datetime | None = None) -> bool:
    """Compile `data` into `output`; return whether its content changed.

    updated_at records when the content last changed, so recompiling unchanged inputs
    leaves the file, and its hash, as they were.
    """
    content = build(data)
    if output.exists():
        current = json.loads(output.read_text())
        if {key: value for key, value in current.items() if key != "updated_at"} == content:
            return False
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    content["updated_at"] = stamp.isoformat().replace("+00:00", "Z")
    output.write_bytes(serialize(content))
    return True
