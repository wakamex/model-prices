"""Readings: what each provider's parser read from the pages a run stored, and the page
history they add up to.

A reading is the prices a provider's official check parsed from one run's pages. It is made
from the page archive, never from a live fetch: the parser reads the bytes the run stored, at
the time the run fetched them, so the same pages always give the same reading for the same
parser. Each reading is stored once under the SHA-256 hash of its content, and a log line per
run and provider names the reading, or the error that stopped one, with the time of the fetch
and the hash of every page the parser read. Unchanged prices give the same reading, so most
days add only log lines.

The page history dates each price a page states by the first reading that showed it, with the
last reading that showed the earlier price as its lower bound. `diff` compares every reading
with the prices model-prices published for its time, which shows where a history built from
the pages alone would differ from the published one.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import gzip
import hashlib
import json
from pathlib import Path
from typing import Iterable, Iterator

from model_prices import _parse_time
from model_prices.checks import MINIMUM_MODELS, SOURCES, Observed, compare, parse

LOG = "readings"
CONTENT = "readings/by-hash"


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


def read_run(archive: Path, run: str, log: list[dict]) -> Iterator[tuple[dict, dict | None]]:
    """Each provider's log line and reading for one run, for every provider whose pricing page
    the run tried to fetch. A provider whose pages the run did not all fetch, or whose parser
    fails, gets a line naming the error and no reading."""
    stored: dict[str, dict] = {}
    for entry in log:
        # The first stored copy is the one the run's checks read.
        if entry["status"] == 200 and entry["sha256"] and "payload" not in entry:
            stored.setdefault(entry["url"], entry)
    tried = {entry["url"]: entry for entry in log}
    for provider, (url, _) in SOURCES.items():
        if url not in tried:
            continue
        inputs: dict[str, str] = {}

        def get(page_url: str) -> str:
            entry = stored.get(page_url)
            if entry is None:
                failed = tried.get(page_url)
                raise ValueError(f"{page_url} was not stored in run {run}"
                                 + (f": {failed.get('error') or failed['status']}" if failed else ""))
            inputs[page_url] = entry["sha256"]
            return _blob(archive, entry["sha256"]).decode()

        read_at = (stored.get(url) or tried[url])["fetched_at"]
        line = {"run": run, "provider": provider, "read_at": read_at}
        try:
            observed = parse(provider, get(url), _parse_time(read_at), get)
            listed = len({item.model for item in observed})
            if listed < MINIMUM_MODELS.get(provider, 0):
                raise ValueError(f"{provider}: only {listed} models parsed from {url}, fewer than "
                                 f"{MINIMUM_MODELS[provider]}; the page format changed")
        # Any failure to read the pages stops this provider's reading alone.
        except Exception as error:
            yield {**line, "inputs": inputs, "error": f"{type(error).__name__}: {error}"}, None
            continue
        reading = {"provider": provider,
                   "prices": sorted((_price(item) for item in observed), key=_sort_key)}
        yield {**line, "inputs": inputs, "reading": _digest(reading)}, reading


def _price(item: Observed) -> dict:
    # Only the fields a page stated, so a reading's hash does not change when Observed gains one.
    return {key: value for key, value in asdict(item).items() if key != "provider" and value is not None}


def _sort_key(price: dict) -> str:
    return json.dumps(price, sort_keys=True)


def _digest(reading: dict) -> str:
    return hashlib.sha256(json.dumps(reading, sort_keys=True).encode()).hexdigest()


def record(archive: Path, out: Path) -> int:
    """Add a reading for every run and provider in the archive that `out` has none for; return
    how many log lines were added."""
    known = {(entry["run"], entry["provider"]) for entry in load_log(out)}
    added = 0
    (out / CONTENT).mkdir(parents=True, exist_ok=True)
    for run, log in _fetches(archive).items():
        for line, reading in read_run(archive, run, log):
            if (run, line["provider"]) in known:
                continue
            if reading is not None:
                path = out / CONTENT / f"{line['reading']}.json"
                if not path.exists():
                    path.write_text(json.dumps(reading, sort_keys=True) + "\n")
            with (out / LOG / f"{line['read_at'][:7]}.jsonl").open("a") as file:
                file.write(json.dumps(line, sort_keys=True) + "\n")
            added += 1
    return added


def load_log(out: Path) -> list[dict]:
    lines = [json.loads(line) for path in sorted((out / LOG).glob("*.jsonl"))
             for line in path.read_text().splitlines()]
    return sorted(lines, key=lambda line: (line["read_at"], line["provider"]))


def readings(out: Path) -> Iterator[tuple[dict, list[Observed]]]:
    """Each log line that has a reading, in time order, with the prices it read."""
    names = {field.name for field in fields(Observed)}
    for line in load_log(out):
        if "reading" not in line:
            continue
        reading = json.loads((out / CONTENT / f"{line['reading']}.json").read_text())
        yield line, [Observed(provider=reading["provider"],
                              **{key: value for key, value in price.items() if key in names})
                     for price in reading["prices"]]


@dataclass(frozen=True)
class Change:
    """A price a page started stating: first seen in one reading, after the last reading that
    showed the earlier price, if any."""

    key: tuple
    value: float
    first_seen: str
    last_before: str | None
    previous: float | None


def history(lines: Iterable[tuple[dict, list[Observed]]]) -> list[Change]:
    """Every price each page stated over time, each change dated by the reading that first
    showed it. A price a page stops stating keeps its last value."""
    current: dict[tuple, tuple[float, str]] = {}
    changes = []
    for line, observed in lines:
        for item in observed:
            key = (item.provider, item.model, item.mode, item.modality, item.field, item.above, item.at)
            last = current.get(key)
            if last is None or last[0] != item.value:
                changes.append(Change(key, item.value, line["read_at"],
                                      last[1] if last else None, last[0] if last else None))
            current[key] = (item.value, line["read_at"])
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


def diff(lines: Iterable[tuple[dict, list[Observed]]]) -> list[Difference]:
    """Compare every reading with the prices model-prices publishes for its time; consecutive
    readings that disagree the same way form one period."""
    open_: dict[tuple, Difference] = {}
    closed = []
    for line, observed in lines:
        seen = set()
        for result in compare(observed, _parse_time(line["read_at"])):
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
        for key in [key for key in open_ if key[0] == line["provider"] and key not in seen]:
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
        lines.append(f"no reading  {line['provider']} in run {line['run']} at {line['read_at']}: {line['error']}")
    return "\n".join(lines)
