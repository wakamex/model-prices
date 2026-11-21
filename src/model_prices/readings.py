"""Readings: what each reader read from the pages a run stored, and the page history they add
up to.

A reader reads one source of prices from its pages: a provider's pricing page, through the
parser its official check uses; a page that prices models models.dev lacks; a provider's tool
fees, peak-hour terms, or batch discounts; OpenAI's regional factors; or a lab's subscription
plans. Each returns a list of entries, every one a price with what it prices: the fields that
name it, and its `value`.

A reading is one reader's entries from one run. It is made from the page archive, never from
a live fetch: the reader reads the bytes the run stored, at the time the run fetched them, so
the same pages always give the same reading. Each reading is stored once under the SHA-256
hash of its content, and a log line per run and reader names the reading, or the error that
stopped one, with the time of the fetch and the hash of every page the reader read.
Unchanged prices give the same reading, so most days add only log lines.

The page history dates each price a reader states by the first reading that showed it, with
the last reading that showed the earlier price as its lower bound. `diff` compares every
pricing page's reading with the prices model-prices published for its time, which shows where
a history built from the pages alone would differ from the published one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import tomllib
from typing import Callable, Iterable, Iterator

from model_prices import _parse_time, _stored_rates, compiler, observe, openai_regions, plan_checks
from model_prices.checks import (MINIMUM_MODELS, SOURCES, card_problems, TERMS, TOOL_PAGES, YUAN_TO_USD, Observed,
                                 _moments, compare, fetch, is_whole, parse, peak_terms, tool_prices, xai_batch)

LOG = "readings"
CONTENT = "readings/by-hash"

# A page getter: the body of a URL, fetched with an optional request payload.
Get = Callable[..., str]


class NotStored(OSError):
    """A page the run did not store, which a reader treats as a failed fetch."""


@dataclass(frozen=True)
class Reader:
    """One source of prices: `url` is the page whose fetch in a run makes the run read it,
    and `read` returns its entries from a page getter and the time of that fetch. An hourly
    reader is read by the hourly page watch as well as daily."""

    url: str
    read: Callable[[Get, datetime], list[dict]]
    hourly: bool = True
    payload: bytes | None = None


def _price(item: Observed) -> dict:
    # Only the fields a page stated, so a reading's hash does not change when Observed gains one.
    # A period's next hour depends on when the page was read, not on the page.
    return {key: value for key, value in asdict(item).items()
            if key != "provider" and value is not None and not (key == "at" and item.period)}


def _pricing_page(provider: str) -> Callable[[Get, datetime], list[dict]]:
    def read(get: Get, at: datetime) -> list[dict]:
        url = SOURCES[provider][0]
        observed = parse(provider, get(url), at, get)
        listed = len({item.model for item in observed})
        if listed < MINIMUM_MODELS.get(provider, 0):
            raise ValueError(f"{provider}: only {listed} models parsed from {url}, fewer than "
                             f"{MINIMUM_MODELS[provider]}; the page format changed")
        return [_price(item) for item in observed]
    return read


def _observed_page(provider: str) -> Callable[[Get, datetime], list[dict]]:
    def read(get: Get, at: datetime) -> list[dict]:
        return [{"model": model, "value": rates} for model, (_, rates) in observe.SOURCES[provider](get).items()]
    return read


def _tools(provider: str) -> Callable[[Get, datetime], list[dict]]:
    def read(get: Get, at: datetime) -> list[dict]:
        return [{"field": f"tool:{tool}", "value": sorted(prices)}
                for tool, prices in tool_prices(provider, get(TOOL_PAGES[provider])).items()]
    return read


def _terms(provider: str, language: str) -> Callable[[Get, datetime], list[dict]]:
    def read(get: Get, at: datetime) -> list[dict]:
        return [{"field": f"peak_terms:{language}",
                 "value": peak_terms(provider, language, get(TERMS[provider][language][0]))}]
    return read


def _xai_batch(get: Get, at: datetime) -> list[dict]:
    return [{"model": model, "field": "batch_multiple", "value": multiple}
            for model, multiple in xai_batch(get(SOURCES["xai"][0])).items()]


def _openai_regions(get: Get, at: datetime) -> list[dict]:
    found = openai_regions.read(get)
    return ([{"model": model, "field": "regions", "value": regions} for model, regions in found.factors.items()]
            + [{"model": model, "field": "conflict", "value": list(evidence)}
               for model, evidence in found.conflicts.items()])


def _plans(key: str) -> Callable[[Get, datetime], list[dict]]:
    url, body, reader, expected = plan_checks.PLAN_PAGES[key]

    def read(get: Get, at: datetime) -> list[dict]:
        stated = reader(get(url, body))
        missing = [f"{provider}/{plan}" for provider, plan in expected if (provider, plan) not in stated]
        if missing:
            raise ValueError(f"no price for {', '.join(missing)}; the page format changed")
        return [{"provider": provider, "plan": plan, "value": price}
                for (provider, plan), price in stated.items()]
    return read


# Each reader whose parser has changed what a successful reading gives, with the number of such
# changes: a reading made before the latest is read again from its run's pages, as a failed one
# is. A reader not listed is at version 1.
VERSIONS = {
    "openai": 2,  # OpenAI's Fast section also prices models.dev's fast mode.
    "google": 2,  # A Flex or Priority tab that prices output only per image is left out.
}

READERS: dict[str, Reader] = {
    **{provider: Reader(url, _pricing_page(provider)) for provider, (url, _) in SOURCES.items()},
    **{provider: Reader(observe.SOURCE_PAGES[provider], _observed_page(provider))
       for provider in observe.SOURCES},
    **{f"{provider}:tools": Reader(url, _tools(provider)) for provider, url in TOOL_PAGES.items()},
    **{f"{provider}:terms:{language}": Reader(url, _terms(provider, language))
       for provider, languages in TERMS.items() for language, (url, _) in languages.items()},
    "xai:batch": Reader(SOURCES["xai"][0], _xai_batch),
    # OpenAI's regional factors read every model page OpenAI processes regionally, so daily.
    "openai:regions": Reader(openai_regions.DATA_RESIDENCY, _openai_regions, hourly=False),
    **{f"plan:{key}": Reader(url, _plans(key), hourly=False, payload=body)
       for key, (url, body, _, _) in plan_checks.PLAN_PAGES.items()},
}


def _fetches(archive: Path) -> dict[str, list[dict]]:
    """The archive's fetch log, by run, in fetch order."""
    runs: dict[str, list[dict]] = {}
    for line in (archive / "fetches.jsonl").read_text().splitlines():
        entry = json.loads(line)
        runs.setdefault(str(entry["run"]), []).append(entry)
    return runs


def _blob(archive: Path, digest: str) -> bytes:
    # The workflow's run directory stores blobs as fetched; the local archive gzips them.
    plain = archive / "blobs" / digest
    return plain.read_bytes() if plain.exists() else gzip.decompress((archive / "blobs" / f"{digest}.gz").read_bytes())


def _key(url: str, payload: bytes | str | None) -> tuple[str, str | None]:
    return url, payload.decode() if isinstance(payload, bytes) else payload


def read_run(archive: Path, run: str, log: list[dict]) -> Iterator[tuple[dict, dict | None]]:
    """Each reader's log line and reading for one run, for every reader whose page the run
    tried to fetch. A reader whose pages the run did not all store, or that fails, gets a line
    naming the error and no reading."""
    stored: dict[tuple[str, str | None], dict] = {}
    for entry in log:
        # The last stored copy is the one the run's checks read: a page is fetched again only
        # after a bare shell.
        if entry["status"] == 200 and entry["sha256"]:
            stored[_key(entry["url"], entry.get("payload"))] = entry
    tried = {_key(entry["url"], entry.get("payload")): entry for entry in log}
    for name, reader in READERS.items():
        main = _key(reader.url, reader.payload)
        if main not in tried:
            continue
        inputs: dict[str, str] = {}

        def get(url: str, payload: bytes | None = None) -> str:
            entry = stored.get(_key(url, payload))
            if entry is None:
                failed = tried.get(_key(url, payload))
                raise NotStored(f"{url} was not stored in run {run}"
                                + (f": {failed.get('error') or failed['status']}" if failed else ""))
            inputs[url] = entry["sha256"]
            page = _blob(archive, entry["sha256"]).decode()
            if not is_whole(url, page):
                raise NotStored(f"{url} was stored only as a bare shell in run {run}")
            return page

        read_at = (stored.get(main) or tried[main])["fetched_at"]
        line = {"run": run, "reader": name, "read_at": read_at}
        if VERSIONS.get(name, 1) > 1:
            line["version"] = VERSIONS[name]
        try:
            entries = reader.read(get, _parse_time(read_at))
        # Any failure to read the pages stops this reader's reading alone.
        except Exception as error:
            yield {**line, "inputs": inputs, "error": f"{type(error).__name__}: {error}"}, None
            continue
        reading = {"reader": name, "entries": sorted(entries, key=_sort_key)}
        yield {**line, "inputs": inputs, "reading": _digest(reading)}, reading


def _sort_key(entry: dict) -> str:
    return json.dumps(entry, sort_keys=True)


def _digest(reading: dict) -> str:
    return hashlib.sha256(json.dumps(reading, sort_keys=True).encode()).hexdigest()


def record(archive: Path, out: Path) -> int:
    """Add a reading for every run and reader in the archive that `out` has none for; return
    how many log lines were added."""
    known = {(entry["run"], entry["reader"]) for entry in load_log(out)}
    added = 0
    (out / CONTENT).mkdir(parents=True, exist_ok=True)
    for run, log in _fetches(archive).items():
        for line, reading in read_run(archive, run, log):
            if (run, line["reader"]) in known:
                continue
            if reading is not None:
                path = out / CONTENT / f"{line['reading']}.json"
                if not path.exists():
                    path.write_text(json.dumps(reading, sort_keys=True) + "\n")
            with (out / LOG / f"{line['read_at'][:7]}.jsonl").open("a") as file:
                file.write(json.dumps(line, sort_keys=True) + "\n")
            added += 1
    return added


def retryable(out: Path) -> list[dict]:
    """The log lines of readings a parser change can change: those that failed for any reason
    but a page the run did not store, and those made before their reader's latest version."""
    return [line for line in load_log(out)
            if ("error" in line and not line["error"].startswith("NotStored"))
            or line.get("version", 1) < VERSIONS.get(line["reader"], 1)]


def retry_pages(out: Path, archive: Path) -> set[str]:
    """The hashes of the pages the runs with retryable readings stored, from the archive's
    fetch log, which a retry needs in the archive's blobs."""
    runs = {line["run"] for line in retryable(out)}
    return {entry["sha256"] for run, log in _fetches(archive).items() if run in runs
            for entry in log if entry["status"] == 200 and entry["sha256"]}


def retry(archive: Path, out: Path) -> int:
    """Read again every retryable reading whose run the archive holds, as after a parser fix or
    change, replacing its log line when the result differs; return how many were replaced."""
    failed = {(line["run"], line["reader"]): line for line in retryable(out)}
    runs = _fetches(archive)
    replaced: dict[tuple[str, str], dict] = {}
    for run in sorted({run for run, _ in failed} & runs.keys()):
        for line, reading in read_run(archive, run, runs[run]):
            key = (run, line["reader"])
            if key not in failed or line == failed[key]:
                continue
            if reading is not None:
                path = out / CONTENT / f"{line['reading']}.json"
                if not path.exists():
                    path.write_text(json.dumps(reading, sort_keys=True) + "\n")
            replaced[key] = line
    for path in sorted((out / LOG).glob("*.jsonl")):
        lines = [json.loads(text) for text in path.read_text().splitlines()]
        updated = [replaced.get((line["run"], line["reader"]), line) for line in lines]
        if updated != lines:
            path.write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in updated))
    return len(replaced)


def fetch_pages(hourly: bool = True) -> None:
    """Fetch every page the readers read, or only the hourly readers', into the page archive
    that the MODEL_PRICES_ARCHIVE environment variable names, for `record` to read. A page that
    cannot be fetched or read is left to `record`, which names the error in that reader's line."""
    if not os.environ.get("MODEL_PRICES_ARCHIVE"):
        raise ValueError("MODEL_PRICES_ARCHIVE must name the directory to fetch the pages into")
    now = datetime.now(timezone.utc)

    def get(url: str, payload: bytes | None = None) -> str:
        return fetch(url) if payload is None else plan_checks._fetch(url, payload)

    for reader in READERS.values():
        if reader.hourly or not hourly:
            try:
                reader.read(get, now)
            except Exception:
                pass


def changed(out: Path, run: str) -> list[str]:
    """The readers whose reading in the run differs from their reading before it."""
    last: dict[str, str] = {}
    found = set()
    for line in load_log(out):
        if "reading" not in line:
            continue
        reader = line["reader"]
        if line["run"] == run and reader in last and last[reader] != line["reading"]:
            found.add(reader)
        last[reader] = line["reading"]
    return sorted(found)


def load_log(out: Path) -> list[dict]:
    lines = [json.loads(line) for path in sorted((out / LOG).glob("*.jsonl"))
             for line in path.read_text().splitlines()]
    return sorted(lines, key=lambda line: (line["read_at"], line["reader"]))


def readings(out: Path) -> Iterator[tuple[dict, list[dict]]]:
    """Each log line that has a reading, in time order, with the entries it read."""
    for line in load_log(out):
        if "reading" in line:
            yield line, json.loads((out / CONTENT / f"{line['reading']}.json").read_text())["entries"]


def observed(line: dict, entries: list[dict]) -> list[Observed]:
    """A pricing page reading's entries as the prices its official check compares, each priced
    for a time-of-day period at that period's next hour after the reading."""
    names = {field.name for field in fields(Observed)}
    found = [Observed(provider=line["reader"], **{key: value for key, value in entry.items() if key in names})
             for entry in entries]
    if any(item.period for item in found):
        moments = _moments(line["reader"], _parse_time(line["read_at"]))
        found = [replace(item, at=moments[item.period]) if item.period else item for item in found]
    return found


# Pages that price in yuan give prices models.dev converts at its own rounding, so their
# conversions would differ from models.dev's by rounding alone; they stay models.dev's.
PRICED_IN_DOLLARS = [provider for provider in SOURCES if provider not in YUAN_TO_USD]


def page_entries(out: Path, data: Path) -> dict[tuple[str, str], list[dict]]:
    """For each provider and model a pricing page states token prices for, those prices over
    time: an entry whenever they change, with the time of the first reading that stated them,
    the page as its source, and the rates as a models.dev entry gives them. A model a page
    stops stating keeps the prices it last stated. A name aliases.toml maps to one of the
    provider's own ids takes that id."""
    aliases = tomllib.loads((data / "aliases.toml").read_text())["models"]
    found: dict[tuple[str, str], list[dict]] = {}
    for line, entries in readings(out):
        reader = line["reader"]
        if reader in PRICED_IN_DOLLARS:
            stated = observe.stated_rates(reader, observed(line, entries), complete=False)
            source = SOURCES[reader][0]
        elif reader in observe.SOURCES:
            stated = {entry["model"]: entry["value"] for entry in entries}
            source = observe.SOURCE_PAGES[reader]
        else:
            continue
        for name, rates in stated.items():
            target = aliases.get(name, "").split("/", 1)
            model = target[1] if len(target) == 2 and target[0] == reader else name
            history = found.setdefault((reader, model), [])
            if not history or history[-1]["rates"] != rates:
                history.append({"valid_from": line["read_at"], "source": source, "rates": rates})
    return found


@dataclass(frozen=True)
class Shadow:
    """The snapshot built with the pages' prices, compared with the published one: where they
    differ, rate cards in the build that are impossible, which fail it, and page prices that
    are possible but unlikely, which are reported for a look at the page."""

    differences: list[str]
    impossible: list[str]
    unlikely: list[str]


def shadow(out: Path, data: Path, published: dict) -> Shadow:
    """Build the snapshot with the pages' prices, and compare it with `published` from the
    first reading on."""
    pages = page_entries(out, data)
    built = compiler.build(data, pages)
    start = min(entry["valid_from"] for entries in pages.values() for entry in entries)
    return Shadow(_differences(built, published, start), impossible(built, start), unlikely(pages))


def impossible(built: dict, start: str) -> list[str]:
    """Each model's rate cards in the build that are impossible, at each time from `start`
    that they change: the problems the published check fails."""
    found = []
    for provider, models in sorted(built["prices"].items()):
        for model, modes in sorted(models.items()):
            times = sorted({start} | {interval["start"] for intervals in modes.values()
                                      for interval in intervals if interval["start"] and interval["start"] > start})
            last = None
            for at in times:
                cards = {mode: _stored_rates(provider, model, _at(intervals, at)) for mode, intervals in modes.items()}
                standard = cards.pop("standard", None)
                problems = card_problems(standard, cards) if standard else []
                if problems and problems != last:
                    found.append(f"{provider}/{model} from {at}: {'; '.join(problems)}")
                last = problems
    return found


# A page price outside these bounds, in dollars per million tokens, is unlikely: text input and
# output prices, then every other price.
TEXT_BOUNDS = (0.01, 200.0)
OTHER_BOUNDS = (0.001, 1000.0)
# A change by more than this factor, up or down, is unlikely.
JUMP = 3.0


def _prices(rates: dict, path: str = "") -> dict[str, float]:
    """A rates entry's prices by where they sit, such as "modes.flex.tiers.272000.input"."""
    found = {}
    for key, value in rates.items():
        if key == "tiers":
            for tier in value:
                found |= _prices({k: v for k, v in tier.items() if k != "above"}, f"{path}tiers.{tier['above']}.")
        elif isinstance(value, dict):
            found |= _prices(value, f"{path}{key}.")
        elif isinstance(value, (int, float)):
            found[path + key] = float(value)
    return found


def unlikely(pages: dict[tuple[str, str], list[dict]]) -> list[str]:
    """Page prices that are possible but unlikely, each where a page first stated it: one
    outside the bounds, or one that changed by more than JUMP times, or to or from $0."""
    found = []
    for (provider, model), entries in sorted(pages.items()):
        before: dict[str, float] = {}
        for entry in entries:
            prices = _prices(entry["rates"])
            for path, price in sorted(prices.items()):
                if before.get(path) == price:
                    continue
                name = path.rsplit(".", 1)[-1]
                text = name in {"input", "output"} and ".modalities." not in f".{path}"
                low, high = TEXT_BOUNDS if text else OTHER_BOUNDS
                reasons = []
                if price and not low <= price <= high:
                    reasons.append(f"outside ${low:g} to ${high:g}")
                old = before.get(path)
                if old is not None and (old == 0) != (price == 0):
                    reasons.append(f"from ${old:g}")
                elif old and (price > old * JUMP or price < old / JUMP):
                    reasons.append(f"{price / old:.3g} times ${old:g}")
                if reasons:
                    found.append(f"{provider}/{model} {path} ${price:g} from {entry['valid_from']}: "
                                 + ", ".join(reasons))
            before |= prices
    return found


def _differences(built: dict, published: dict, start: str) -> list[str]:
    """For each model and mode, each time from `start` that the built and published rates
    differ, with the fields that differ."""
    lines = []
    for provider, models in sorted(built["prices"].items()):
        for model, modes in sorted(models.items()):
            for mode, timeline in sorted(modes.items()):
                before = published["prices"].get(provider, {}).get(model, {}).get(mode, [])
                times = sorted({start} | {interval["start"] for interval in (*timeline, *before)
                                          if interval["start"] and interval["start"] > start})
                for at in times:
                    old, new = (_canonical(_at(intervals, at)) for intervals in (before, timeline))
                    fields = sorted(key for key in {*(old or {}), *(new or {})}
                                    if key not in {"valid_from", "source", "valid_from_basis"}
                                    and (old or {}).get(key) != (new or {}).get(key))
                    if fields:
                        lines.append(f"{provider}/{model} {mode} from {at}: " + "; ".join(
                            f"{key} {_shown((old or {}).get(key))} -> {_shown((new or {}).get(key))}"
                            for key in fields))
    return lines


def _at(intervals: list[dict], at: str) -> dict | None:
    """The rates a timeline gives at an ISO time; the first interval also covers every earlier
    time."""
    found = None
    for index, interval in enumerate(intervals):
        if index == 0 or interval["start"] <= at:
            found = interval["rates"]
    return found


def _canonical(rates: dict | None) -> dict | None:
    """Rates without the modality prices that equal the price of a token without a modality,
    which cost the same whether listed or not."""
    if not rates or "modalities" not in rates:
        return rates
    plain = {key: rates.get(key) for key in ("input", "cache_read", "output")}
    modalities = {name: kept for name, prices in rates["modalities"].items()
                  if (kept := {key: value for key, value in prices.items() if value != plain.get(key)})}
    return {**rates, "modalities": modalities} if modalities else {
        key: value for key, value in rates.items() if key != "modalities"}


def _shown(value: object) -> str:
    return "none" if value is None else json.dumps(value, sort_keys=True)


@dataclass(frozen=True)
class Change:
    """A price a reader started stating: first seen in one reading, after the last reading that
    showed the earlier price, if any. `key` is the reader and the fields that name the price."""

    key: tuple
    value: object
    first_seen: str
    last_before: str | None
    previous: object


def history(lines: Iterable[tuple[dict, list[dict]]]) -> list[Change]:
    """Every price each reader stated over time, each change dated by the reading that first
    showed it. A price a reader stops stating keeps its last value."""
    current: dict[tuple, tuple[object, str]] = {}
    changes = []
    for line, entries in lines:
        for entry in entries:
            key = (line["reader"], *sorted((name, json.dumps(value)) for name, value in entry.items()
                                           if name != "value"))
            last = current.get(key)
            if last is None or last[0] != entry["value"]:
                changes.append(Change(key, entry["value"], line["read_at"],
                                      last[1] if last else None, last[0] if last else None))
            current[key] = (entry["value"], line["read_at"])
    return changes


@dataclass(frozen=True)
class Difference:
    """A period in which a page stated a price that differs from the one published."""

    provider: str
    model: str
    field: str
    above: int | None
    official: float
    published: float | str | None
    since: str
    until: str


def diff(lines: Iterable[tuple[dict, list[dict]]]) -> list[Difference]:
    """Compare every pricing page's reading with the prices model-prices publishes for its
    time; consecutive readings that disagree the same way form one period."""
    open_: dict[tuple, Difference] = {}
    closed = []
    for line, entries in lines:
        if line["reader"] not in SOURCES:
            continue
        seen = set()
        for result in compare(observed(line, entries), _parse_time(line["read_at"])):
            # A row no published model matches is a gap in the parser's names, not a price.
            if result.status != "mismatch":
                continue
            key = (result.provider, result.model, result.field, result.above, result.at)
            seen.add(key)
            found = open_.get(key)
            if found and (found.official, found.published) == (result.official, result.effective):
                open_[key] = Difference(**{**asdict(found), "until": line["read_at"]})
                continue
            if found:
                closed.append(found)
            open_[key] = Difference(result.provider, result.model, result.field, result.above,
                                    result.official, result.effective, line["read_at"], line["read_at"])
        # A provider's period ends at its next reading that agrees.
        for key in [key for key in open_ if key[0] == line["reader"] and key not in seen]:
            closed.append(open_.pop(key))
    return sorted(closed + list(open_.values()), key=lambda item: (item.provider, item.model, item.field, item.since))


def report(differences: list[Difference], errors: list[dict]) -> str:
    lines = []
    for item in differences:
        tier = f" above {item.above:,}" if item.above else ""
        published = "nothing" if item.published is None else f"${item.published:g}"
        period = item.since if item.since == item.until else f"{item.since} to {item.until}"
        lines.append(f"{item.model} {item.field}{tier}: page ${item.official:g}, published {published}, {period}")
    for line in errors:
        lines.append(f"no reading  {line['reader']} in run {line['run']} at {line['read_at']}: {line['error']}")
    return "\n".join(lines)
