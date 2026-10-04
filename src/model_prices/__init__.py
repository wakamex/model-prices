"""Effective-dated LLM API prices from models.dev history, with sourced corrections."""

from __future__ import annotations

import argparse
from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import cache
import hashlib
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
import urllib.request
import warnings

# Search order for model names given without a known provider.
LAB_PROVIDERS = (
    "anthropic", "openai", "google", "zai", "deepseek", "xai", "moonshotai", "alibaba",
)

_EFFORT_SUFFIX = re.compile(r"-(minimal|low|medium|high|xhigh|max|thinking)$")
# Dated snapshots: -2026-04-23 (OpenAI), -20251001 (Anthropic), -0731 (DeepSeek).
_DATE_SUFFIX = re.compile(r"-(\d{4}-\d{2}-\d{2}|\d{8}|\d{4})$")
# Context-window markers that tools append, such as Claude Code's "[1m]".
_CONTEXT_MARKER = re.compile(r"\[[^\]]*\]$")
# xAI's subscription endpoint, used by Grok Build, reports grok-4.6 as grok-4.6-build:
# a server-side alias, not a separate model. grok-build-0.1 is a separate model.
_GROK_BUILD_ALIAS = re.compile(r"^(grok-\d+\.\d+)(-build)$")


@dataclass(frozen=True)
class Tier:
    above: int
    input: float | None = None
    output: float | None = None
    cache_read: float | None = None
    cache_write: float | None = None


@dataclass(frozen=True)
class CostBreakdown:
    """USD cost of one request by token type, and the long-context tier applied, if any."""

    tier_above: int | None
    input: float
    output: float
    cache_read: float
    cache_write: float
    cache_write_1h: float = 0.0

    @property
    def total(self) -> float:
        return self.input + self.output + self.cache_read + self.cache_write + self.cache_write_1h


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
    # Suffix text removed from the requested name to find this model, such as "-max".
    removed_suffix: str = ""
    # How valid_from was dated: "models.dev commit", which usually lags the provider's
    # change by days, or "documented", a date from the correction's cited source.
    valid_from_basis: str = "models.dev commit"
    # A one-hour cache write's price as a multiple of the input price, for providers that
    # price it separately from the five-minute cache write; None prices it as cache_write.
    cache_write_1h_multiple: float | None = None

    def price_key(self) -> tuple:
        """The prices alone, without provenance, for comparing rates from different sources."""
        return (self.input, self.output, self.cache_read, self.cache_write, self.tiers,
                self.period, self.cache_write_1h_multiple)

    def breakdown(self, input_tokens: int = 0, output_tokens: int = 0,
                  cache_read_tokens: int = 0, cache_write_tokens: int = 0,
                  cache_write_1h_tokens: int = 0) -> CostBreakdown:
        """Price one request by token type; input_tokens excludes cache reads and writes.

        cache_write_tokens are five-minute cache writes and cache_write_1h_tokens one-hour
        ones. Long-context tiers apply when the request's whole prompt exceeds the tier
        size. Missing cache prices fall back to the input price.
        """
        prompt = input_tokens + cache_read_tokens + cache_write_tokens + cache_write_1h_tokens
        rates: dict[str, float | None] = {
            "input": self.input, "output": self.output,
            "cache_read": self.cache_read, "cache_write": self.cache_write,
        }
        applied = None
        for tier in self.tiers:
            if prompt > tier.above:
                applied = tier.above
                rates.update({
                    key: value for key, value in asdict(tier).items()
                    if key != "above" and value is not None
                })
        input_rate = rates["input"]
        cache_read = rates["cache_read"] if rates["cache_read"] is not None else input_rate
        cache_write = rates["cache_write"] if rates["cache_write"] is not None else input_rate
        cache_write_1h = (input_rate * self.cache_write_1h_multiple
                          if self.cache_write_1h_multiple is not None else cache_write)
        return CostBreakdown(
            tier_above=applied,
            input=input_tokens * input_rate / 1e6,
            output=output_tokens * rates["output"] / 1e6,
            cache_read=cache_read_tokens * cache_read / 1e6,
            cache_write=cache_write_tokens * cache_write / 1e6,
            cache_write_1h=cache_write_1h_tokens * cache_write_1h / 1e6,
        )

    def cost(self, input_tokens: int = 0, output_tokens: int = 0,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0,
             cache_write_1h_tokens: int = 0) -> float:
        """Price one request in USD; input_tokens excludes cache reads and writes."""
        return self.breakdown(input_tokens, output_tokens, cache_read_tokens,
                              cache_write_tokens, cache_write_1h_tokens).total


# The snapshot format this version reads. It changes only when looking up a price changes,
# so a client prices every later snapshot of its schema correctly.
SCHEMA = 1
# Published snapshots: v1/latest.json names the current one, and v1/<sha256>.json holds
# each snapshot ever published, so a recorded pricing basis can be fetched again.
SNAPSHOT_URL = f"https://raw.githubusercontent.com/wakamex/model-prices/data/v{SCHEMA}/"
# Where a checkout keeps the bundled snapshot, relative to its root.
SNAPSHOT_PATH = "src/model_prices/snapshot.json"


@dataclass(frozen=True)
class DataStatus:
    """The price data in use, as refresh() reports it."""

    basis: str
    # When the data was last confirmed current: the time it was published, or for the data
    # bundled with this release, when its content last changed.
    published_at: datetime
    # Why fetching newer data failed, if it did.
    error: str | None = None


_active: tuple[dict[str, Any], str, datetime] | None = None


def _load(text: bytes) -> dict[str, Any]:
    snapshot = json.loads(text)
    if snapshot.get("schema") != SCHEMA:
        raise ValueError(f"snapshot schema {snapshot.get('schema')!r}, not {SCHEMA}")
    return snapshot


def _bundled() -> tuple[dict[str, Any], str, datetime]:
    text = files(__package__).joinpath("snapshot.json").read_bytes()
    snapshot = _load(text)
    return snapshot, hashlib.sha256(text).hexdigest(), _parse_time(snapshot["updated_at"])


def _activate(found: tuple[dict[str, Any], str, datetime]) -> None:
    global _active
    _active = found
    for function in (pricing_basis, resolve_details, _intervals, _schedules):
        function.cache_clear()


def _data() -> dict[str, Any]:
    if _active is None:
        _activate(_bundled())
    return _active[0]


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


def data_as_of() -> datetime:
    """The date of the models.dev commit the price history was built from.

    The history is rebuilt only when a tracked price changes, so this is when models.dev
    last changed a tracked price as of the build. Rates for requests after this time
    assume no price has changed since.
    """
    return _parse_time(_data()["models_dev"]["committed_at"])


@cache
def pricing_basis() -> str:
    """Identify the price data, for recording alongside computed costs.

    Names the package version, the models.dev commit, and a hash of the whole snapshot,
    so a change to corrections, schedules, or aliases also changes the basis.
    """
    commit = _data()["models_dev"]["commit"]
    return (f"model-prices-{_version()}+models.dev@{commit[:12]}"
            f"+synced@{data_as_of().date().isoformat()}+data@{_active[1][:12]}")


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else (
        os.environ.get("XDG_CACHE_HOME"))
    root = os.environ.get("MODEL_PRICES_CACHE") or Path(base or Path.home() / ".cache") / (
        "model-prices")
    return Path(root) / f"v{SCHEMA}"


def _download(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "model-prices"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _save(path: Path, content: bytes) -> None:
    """Write a cache file whole, so a concurrent reader never sees part of it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def _cached() -> tuple[tuple[dict[str, Any], str, datetime] | None, datetime | None]:
    """The cached latest snapshot with its publication time, and when it was fetched."""
    try:
        manifest = json.loads((_cache_dir() / "latest.json").read_text())
        text = (_cache_dir() / f"{manifest['sha256']}.json").read_bytes()
        if hashlib.sha256(text).hexdigest() != manifest["sha256"]:
            return None, None
        return ((_load(text), manifest["sha256"], _parse_time(manifest["published_at"])),
                _parse_time(manifest["fetched_at"]))
    except (OSError, ValueError, KeyError):
        return None, None


def _fetch(timeout: float) -> None:
    """Download the latest published snapshot into the cache, checking its hash and schema."""
    manifest = json.loads(_download(SNAPSHOT_URL + "latest.json", timeout))
    name = f"{manifest['sha256']}.json"
    if not (_cache_dir() / name).exists():
        text = _download(SNAPSHOT_URL + name, timeout)
        if hashlib.sha256(text).hexdigest() != manifest["sha256"]:
            raise ValueError(f"{name} does not match its hash")
        _load(text)
        _save(_cache_dir() / name, text)
    fetched = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    _save(_cache_dir() / "latest.json", json.dumps({**manifest, "fetched_at": fetched}).encode())


def refresh(max_age: timedelta | None = timedelta(days=1), timeout: float = 10) -> DataStatus:
    """Use the newest published price data, downloading it when the cached copy is older
    than max_age.

    Prices change only when this is called: until then, and without a cache, the data
    bundled with the installed release applies. max_age=None never downloads and uses the
    newest copy already cached or bundled. A failed download keeps the newest cached or
    bundled copy, reports why in DataStatus.error, and warns.
    """
    error = None
    cached, fetched_at = _cached()
    if max_age is not None and (fetched_at is None
                                or datetime.now(timezone.utc) - fetched_at > max_age):
        try:
            _fetch(timeout)
            cached, _ = _cached()
        except (OSError, ValueError, KeyError) as failure:
            error = f"could not fetch price data from {SNAPSHOT_URL}: {failure}"
            warnings.warn(f"model-prices: {error}; using the newest local price data",
                          stacklevel=2)
    bundled = _bundled()
    # updated_at orders snapshots by when their content changed, so an upgrade's bundled
    # data replaces an older cached copy.
    newest = (cached if cached and _parse_time(cached[0]["updated_at"])
              >= _parse_time(bundled[0]["updated_at"]) else bundled)
    if _active is None or newest[1] != _active[1]:
        _activate(newest)
    return DataStatus(pricing_basis(), newest[2], error)


def _known(provider: str, model: str) -> bool:
    return model in _data()["prices"].get(provider, {})


def _candidates(name: str, strict: bool) -> list[tuple[str, str]]:
    """Names to look up, with the suffix text removed to reach each, most exact first."""
    found = [(name, "")]
    if strict:
        return found
    marker = _CONTEXT_MARKER.search(name)
    if marker:
        found.append((name[:marker.start()], marker.group(0)))
    # Anthropic ids write versions with hyphens: claude-sonnet-4.5 is claude-sonnet-4-5.
    found += [(candidate.replace(".", "-"), removed) for candidate, removed in found
              if candidate.startswith("claude-") and "." in candidate]
    for pattern in (_EFFORT_SUFFIX, _DATE_SUFFIX):
        for candidate, removed in list(found):
            match = pattern.search(candidate)
            if match:
                found.append((candidate[:match.start()], match.group(0) + removed))
    # After suffix removal, so grok-4.6-build-high reaches grok-4.6 as well.
    found += [(match.group(1), match.group(2) + removed) for candidate, removed in found
              if (match := _GROK_BUILD_ALIAS.match(candidate))]
    unique: dict[str, str] = {}
    for candidate, removed in found:
        unique.setdefault(candidate, removed)
    return list(unique.items())


@cache
def resolve_details(model: str, provider: str | None = None,
                    strict: bool = False) -> tuple[str, str, str] | None:
    """Like resolve, but also return the suffix text removed to find the model.

    The removed text is "" for an exact, alias, or first-party match, and otherwise
    names what was dropped, such as "-max" or "-2026-04-23", so callers can record
    that the price belongs to a related name.
    """
    aliases = _data()["aliases"]
    name = re.sub(r"[\s_]+", "-", re.sub(r"[()]", "", model.strip().lower())).strip("-")
    if "/" in name:
        prefix, name = name.split("/", 1)
        provider = provider or prefix
    hint = aliases["providers"].get((provider or "").lower(), (provider or "").lower())

    candidates = _candidates(name, strict)
    for candidate, removed in candidates:
        if candidate in aliases["models"]:
            target_provider, target_model = aliases["models"][candidate].split("/", 1)
            return target_provider, target_model, removed
    order = ([hint] if hint in _data()["prices"] else []) + [
        lab for lab in LAB_PROVIDERS if lab != hint
    ]
    # Prefer the model's own lab over another lab that also serves a variant of it.
    # A lab model name resolves to the first-party id that serves and prices it.
    bases = _data()["bases"]
    for lab in order:
        for candidate, removed in candidates:
            if _known(lab, candidate):
                return lab, candidate, removed
            if candidate in bases.get(lab, {}):
                return lab, bases[lab][candidate], removed
    return None


def resolve(model: str, provider: str | None = None,
            strict: bool = False) -> tuple[str, str] | None:
    """Map a log or harness model name to a models.dev (provider, model) pair.

    strict=True skips removing effort, date, and context suffixes, for names that must
    match exactly.
    """
    found = resolve_details(model, provider, strict)
    return found[:2] if found else None


def _tiers(raw: list[dict[str, Any]] | None) -> tuple[Tier, ...]:
    return tuple(Tier(**tier) for tier in raw or ())


@cache
def _intervals(provider: str, model: str,
               mode: str | None) -> tuple[tuple[datetime, ...], list[dict[str, Any]]]:
    """A model's compiled intervals in a mode, with their start times for bisection."""
    intervals = _data()["prices"].get(provider, {}).get(model, {}).get(mode or "standard", [])
    starts = tuple(_parse_time(item["start"]) for item in intervals[1:])
    return starts, intervals


def _lookup(provider: str, model: str, at: datetime, mode: str | None,
            corrected: bool) -> Rates | None:
    """The compiled rates in effect at `at`, before any time-of-day rule."""
    starts, intervals = _intervals(provider, model, mode)
    if not intervals:
        return None
    # The first interval also covers every earlier time.
    interval = intervals[bisect_right(starts, at)]
    stored = interval["rates"] if corrected else interval.get("recorded", interval["rates"])
    if stored is None:
        return None
    values = dict(stored)
    values.setdefault("model", model)
    values["tiers"] = _tiers(values.get("tiers"))
    return Rates(provider=provider, **values)


def _in_window(moment: datetime, window: list[str]) -> bool:
    """Whether a UTC time falls in a window; a window may run past midnight."""
    start, end = (datetime.strptime(value, "%H:%M").time() for value in window)
    if start <= end:
        return start <= moment.time() < end
    return moment.time() >= start or moment.time() < end


@cache
def _schedules(provider: str) -> tuple[tuple[datetime, datetime | None, dict], ...]:
    return tuple(
        (_parse_time(item["valid_from"]),
         _parse_time(item["valid_until"]) if "valid_until" in item else None, item)
        for item in _data()["schedules"].get("schedule", [])
        if item["provider"] == provider
    )


def _schedule(provider: str, moment: datetime) -> dict[str, Any] | None:
    """Return the provider's time-of-day pricing schedule in effect at `moment`."""
    for start, end, schedule in _schedules(provider):
        if start <= moment and (end is None or moment < end):
            return schedule
    return None


def _period(provider: str, moment: datetime,
            model: str | None = None) -> tuple[str, float] | None:
    """Return the time-of-day period at `moment` and its multiplier on recorded rates.

    A schedule either raises prices inside peak hours or, like DeepSeek's 2025 discount,
    lowers them for listed models inside off-peak hours; outside those hours the recorded
    price is the standard price.
    """
    schedule = _schedule(provider, moment)
    if schedule is None:
        return None
    if "off_peak_hours_utc" in schedule:
        factor = schedule["off_peak_multiplier"].get(model or "")
        if factor is None:
            return None
        off_peak = any(_in_window(moment, window) for window in schedule["off_peak_hours_utc"])
        return ("off_peak", factor) if off_peak else ("standard", 1.0)
    peak = any(_in_window(moment, window) for window in schedule["peak_hours_utc"])
    if schedule.get("weekdays_only") and moment.weekday() >= 5:
        peak = False
    calendar = _data()["schedules"].get("holidays", {}).get(schedule.get("holidays", ""))
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


def rates(model: str, at: datetime | str | None = None, provider: str | None = None,
          mode: str | None = None, corrected: bool = True,
          prices_at: datetime | str | None = None) -> Rates | None:
    """Return the rates for a request made at `at` (default now), or None for an unknown model.

    Time-of-day pricing applies the provider's peak or off-peak rates for `at`.
    prices_at selects a different price list, such as today's, while the time-of-day rule
    in force at `at` still applies to it; it defaults to `at`.
    corrected=False returns models.dev's recorded rates without local corrections.
    """
    details = resolve_details(model, provider)
    if details is None:
        return None
    resolved, removed = details[:2], details[2]
    moment = _parse_time(at)
    listed = _parse_time(prices_at) if prices_at is not None else moment
    found = _lookup(*resolved, listed, mode, corrected)
    if found is None:
        return None
    found = replace(found, removed_suffix=removed) if removed else found
    # The time-of-day rule in force when the request ran applies to the chosen price list.
    period = _period(resolved[0], moment, resolved[1])
    return _scaled(found, *period) if period else found


def _change_times(provider: str, model: str, start: datetime, end: datetime) -> set[datetime]:
    """Every moment in (start, end) at which the model's rates could change."""
    times: set[datetime] = set(_intervals(provider, model, None)[0])
    for begin, until, _ in _schedules(provider):
        times |= {begin} | ({until} if until else set())
    calendars = _data()["schedules"].get("holidays", {})
    for _, _, schedule in _schedules(provider):
        calendar = calendars.get(schedule.get("holidays", ""))
        day = start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        while day <= end:
            times.add(day)  # weekday rules change at UTC midnight
            for window in schedule.get("peak_hours_utc", schedule.get("off_peak_hours_utc", [])):
                for clock in window:
                    hour, minute = map(int, clock.split(":"))
                    times.add(day.replace(hour=hour, minute=minute))
            if calendar:
                times.add(day - timedelta(hours=calendar["utc_offset_hours"]))
            day += timedelta(days=1)
    return {moment for moment in times if start < moment < end}


def rates_between(model: str, start: datetime | str, end: datetime | str,
                  provider: str | None = None) -> list[tuple[datetime, Rates]]:
    """Return the distinct rates in effect from `start` to `end`, each with the time it begins.

    For usage known only to fall within a span, a single entry means one price covered the
    whole span. Entries differ in price, not only in provenance. An unknown model gives [].
    """
    details = resolve_details(model, provider)
    begin, finish = _parse_time(start), _parse_time(end)
    first = rates(model, at=begin, provider=provider) if details else None
    if first is None:
        return []
    segments = [(begin, first)]
    for moment in sorted(_change_times(*details[:2], begin, finish)):
        found = rates(model, at=moment, provider=provider)
        if found is not None and found.price_key() != segments[-1][1].price_key():
            segments.append((moment, found))
    return segments


def cost(model: str, *, input_tokens: int = 0, output_tokens: int = 0,
         cache_read_tokens: int = 0, cache_write_tokens: int = 0,
         cache_write_1h_tokens: int = 0,
         at: datetime | str | None = None, provider: str | None = None,
         mode: str | None = None, prices_at: datetime | str | None = None) -> float | None:
    """Price one request made at `at`; input_tokens excludes cache reads and writes.

    cache_write_tokens are five-minute cache writes and cache_write_1h_tokens one-hour ones.
    """
    found = rates(model, at=at, provider=provider, mode=mode, prices_at=prices_at)
    if found is None:
        return None
    return found.cost(input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                      cache_write_1h_tokens)


@dataclass(frozen=True)
class Plan:
    provider: str
    id: str
    name: str
    usd_per_month: float
    source: str


def plan_ids(provider: str, at: datetime | str | None = None) -> list[str]:
    """Return the provider's plan ids with a price in effect at `at` (default now)."""
    ids = {item["id"] for item in _data()["plans"]
           if item["provider"] == provider}
    return sorted(plan_id for plan_id in ids if plan(provider, plan_id, at) is not None)


def plan(provider: str, plan_id: str, at: datetime | str | None = None) -> Plan | None:
    """Return a subscription plan's monthly price in effect at `at` (default now)."""
    moment = _parse_time(at)
    found = None
    for item in _data()["plans"]:
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


def _version() -> str:
    """The installed version, or "unknown" when run from an uninstalled source tree."""
    try:
        return version("model-prices")
    except PackageNotFoundError:
        return "unknown"


def _cli_time(value: str) -> datetime:
    try:
        return _parse_time(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an ISO 8601 time: {value!r}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="model-prices", description=__doc__)
    parser.add_argument("--version", action="version", version=_version())
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("rate", help="Show the rates for a model at a time")
    show.add_argument("model")
    show.add_argument("--provider")
    show.add_argument("--at", type=_cli_time, help="ISO 8601 time (default: now)")
    show.add_argument("--mode", help="Alternate pricing mode, such as fast")
    show.add_argument("--json", action="store_true")
    fetch = commands.add_parser("refresh", help="Download the latest published price data")
    fetch.add_argument("--max-age", type=float, default=0, metavar="HOURS",
                       help="Download only when the cached copy is older (default: 0)")
    # Maintainer commands, run from a checkout's root.
    update = commands.add_parser(
        "update", help="Rebuild price history from a models.dev git checkout, and compile it"
    )
    update.add_argument("models_dev", type=Path)
    update.add_argument("--hold", nargs="*", default=[], metavar="PROVIDER",
                        help="Keep these providers' current history")
    update.add_argument("--json", action="store_true",
                        help="Print the providers whose history changed as JSON")
    compiler = commands.add_parser(
        "compile", help="Compile the input data into the snapshot model_prices reads"
    )
    for command in (update, compiler):
        command.add_argument("--data", type=Path, default=Path("data"),
                             help="Input data directory (default: data)")
        command.add_argument("--snapshot", type=Path, default=Path(SNAPSHOT_PATH),
                             help=f"Snapshot to write (default: {SNAPSHOT_PATH})")
    check = commands.add_parser(
        "check", help="Compare effective prices with official provider pricing pages"
    )
    check.add_argument("providers", nargs="*", help="Providers to check (default: all)")
    check.add_argument("--json", action="store_true")
    check.add_argument(
        "--genai-prices", nargs="?", const="url", metavar="SOURCE",
        help="Also score Pydantic's genai-prices against the official pages, from its data.json "
             "URL (the default), the file, or a checkout")
    args = parser.parse_args(argv)

    if args.command == "check":
        from model_prices import genai_prices
        from model_prices.checks import SOURCES, as_json, report, run
        unknown = sorted(set(args.providers) - set(SOURCES))
        if unknown:
            parser.error(f"no official pricing check for: {', '.join(unknown)}")
        genai = None
        if args.genai_prices:
            source = genai_prices.DATA_URL if args.genai_prices == "url" else args.genai_prices
            genai = genai_prices.load(source)
        results = run(args.providers or None, genai=genai)
        print(json.dumps(as_json(results), indent=2) if args.json
              else report(results, genai=genai is not None))
        return 1 if any(result.status == "mismatch" for result in results) else 0

    if args.command == "refresh":
        status = refresh(timedelta(hours=args.max_age))
        print(f"{status.basis}, published {status.published_at.isoformat()}")
        return 1 if status.error else 0

    if args.command in {"update", "compile"}:
        from model_prices import backfill, compiler
        if args.command == "update":
            output = args.data / "prices.json"
            data = backfill.hold(backfill.build(args.models_dev), output, set(args.hold))
            changed = backfill.changed_providers(output, data)
            backfill.write(data, output)
            if args.json:
                print(json.dumps({"changed": changed}))
            else:
                print(f"Changed: {', '.join(changed)}" if changed else "No tracked price changes.")
        compiled = compiler.write(args.data, args.snapshot)
        if not getattr(args, "json", False):
            print(f"Compiled {args.snapshot}" if compiled else f"{args.snapshot} is current.")
        return 0

    # The newest data already downloaded, without going online.
    refresh(max_age=None)
    found = rates(args.model, at=args.at, provider=args.provider, mode=args.mode)
    if found is None:
        print(f"No price found for {args.model}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(asdict(found), indent=2))
        return 0
    period = f", {found.period.replace('_', '-')} rate" if found.period else ""
    print(f"{found.provider}/{found.model} from {found.valid_from}{period} ({found.source})")
    def usd(value: float | None) -> str:
        return f"${value:g}" if value is not None else "- (input price)"

    print(f"input {usd(found.input)}  output {usd(found.output)}  "
          f"cache read {usd(found.cache_read)}  cache write {usd(found.cache_write)}  per 1M tokens")
    for tier in found.tiers:
        print(f"above {tier.above:,} prompt tokens: input {usd(tier.input)}  "
              f"output {usd(tier.output)}  cache read {usd(tier.cache_read)}  "
              f"cache write {usd(tier.cache_write)}")
    return 0
