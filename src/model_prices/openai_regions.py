"""OpenAI's uplift on regional processing endpoints, read from OpenAI's own pages.

OpenAI charges "a 10% uplift" on "Regional processing (data residency) endpoints" "for
models released on or after March 5, 2026, that are eligible for data residency", and
models.dev does not record it. Every part of that rule is read from a page OpenAI keeps
current, so no list needs maintaining: the factor and the cutoff from the pricing page, the
models each region processes from the data residency table in the Your data guide, and a
model's side of the cutoff from its dated snapshot ids, its model page, and the API
changelog. A model whose evidence disagrees is reported, so the check fails instead of
guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Callable

DOCS = "https://developers.openai.com/api/docs"
PRICING = f"{DOCS}/pricing.md"
YOUR_DATA = f"{DOCS}/guides/your-data.md"
CHANGELOG = f"{DOCS}/changelog.md"

_DATED = re.compile(r"-(\d{4}-\d{2}-\d{2})$")
_LONG_DATE = "%B %d, %Y"


def model_page(model: str) -> str:
    return f"{DOCS}/models/{model}.md"


def parse_uplift(page: str) -> tuple[float, date]:
    """The factor regional processing adds to token prices and the release date from
    which it applies, from the pricing page's statement of the rule."""
    found = re.search(r"Regional processing \(data residency\) endpoints are charged a "
                      r"(\d+)% uplift for models released on or after ([A-Z][a-z]+ \d{1,2}, \d{4})",
                      page)
    if found is None:
        raise ValueError(f"openai: no regional uplift rule in {PRICING}; the page format changed")
    return 1 + int(found.group(1)) / 100, datetime.strptime(found.group(2), _LONG_DATE).date()


def _rows(page: str, heading: str) -> list[list[str]]:
    lines = page.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith(heading)), None)
    if start is None:
        raise ValueError(f"openai: no {heading!r} table in {YOUR_DATA}; the page format changed")
    # A heading that is itself the table's header row starts the table.
    table = lines[start if heading.startswith("|") else start + 1:][:300]
    rows = []
    for line in table:
        if not line.startswith("|"):
            if rows:
                break
            continue
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return [row for row in rows[2:]]


def parse_residency(page: str) -> dict[str, set[str]]:
    """The regions, as domain prefixes such as "us", in which OpenAI processes each model
    or snapshot it lists: a region an endpoint processes in, narrowed to the snapshots its
    exceptions name for that region."""
    regions = {}
    for row in _rows(page, "| Region"):
        prefix = re.match(r"`([a-z]{2})\.api\.openai\.com`", row[1])
        if prefix and row[3] == "Yes":
            regions[re.sub(r"\\?\*", "", row[0]).strip()] = prefix.group(1)
    if not regions:
        raise ValueError(f"openai: no regional processing regions in {YOUR_DATA}")
    processed: dict[str, set[str]] = {}
    for row in _rows(page, "#### API Endpoint, tool and model support"):
        models = re.findall(r"`([a-z0-9][a-z0-9.-]*)`", row[4])
        names = [name.strip() for name in row[3].split(",")]
        # "United Arab Emirates: `gpt-5.6-luna`, ..." limits that region to those snapshots.
        subsets = {name.strip(): set(re.findall(r"`([a-z0-9.-]+)`", listed))
                   for name, listed in re.findall(r"([A-Z][^:`<]*):((?:\s*`[^`]+`,?)+)", row[5])}
        for name in names:
            if name not in regions:
                continue
            for model in subsets.get(name, models):
                processed.setdefault(model, set()).add(regions[name])
    if not processed:
        raise ValueError(f"openai: no models in the data residency table of {YOUR_DATA}")
    return processed


@dataclass(frozen=True)
class ModelPage:
    """What a model page states that dates the model or prices regional processing."""

    uplift: float | None
    knowledge_cutoff: date | None
    snapshots: tuple[str, ...]


def parse_model_page(page: str) -> ModelPage:
    stated = re.search(r"(?i)regional processing[^\n]*?(\d+)% (?:uplift|premium)", page)
    cutoff = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4}) knowledge cutoff", page)
    snapshots = re.search(r"^## Snapshots\n(.*?)(?=^## |\Z)", page, re.M | re.S)
    return ModelPage(
        1 + int(stated.group(1)) / 100 if stated else None,
        datetime.strptime(cutoff.group(1), "%b %d, %Y").date() if cutoff else None,
        tuple(re.findall(r"^- `([a-z0-9.-]+)`", snapshots.group(1), re.M)) if snapshots else ())


def parse_changelog(page: str) -> dict[str, date]:
    """Each model's first release in the API changelog: the earliest dated entry of kind
    Feature that tags the model, such as "Feature · Model: gpt-6.1-terra"."""
    released: dict[str, date] = {}
    year = None
    day = None
    for line in page.splitlines():
        heading = re.match(r"## [A-Z][a-z]+, (\d{4})$", line)
        if heading:
            year = heading.group(1)
            continue
        dated = re.match(r"### ([A-Z][a-z]{2}) (\d{1,2})$", line)
        if dated and year:
            day = datetime.strptime(f"{dated.group(1)} {dated.group(2)} {year}", "%b %d %Y").date()
            continue
        if day and line.startswith("Feature") and "Model: " in line:
            for model in re.findall(r"Model: ([a-z0-9][a-z0-9.-]*)", line):
                released[model] = min(released.get(model, day), day)
    if not released:
        raise ValueError(f"openai: no model releases in {CHANGELOG}; the page format changed")
    return released


def base(model: str) -> str:
    """The model a dated snapshot belongs to, such as gpt-5.5 for gpt-5.5-2026-04-23."""
    return _DATED.sub("", model)


@dataclass(frozen=True)
class Side:
    """A model's side of the uplift's release cutoff, with the evidence for it."""

    after: bool | None
    evidence: tuple[str, ...]
    conflict: bool = False


def side(model: str, cutoff: date, page: ModelPage | None, released: dict[str, date]) -> Side:
    """Whether a model was released on or after the cutoff. A dated snapshot id decides
    either way; otherwise the model page stating the uplift, the changelog's first release
    of the model, or a knowledge cutoff after the cutoff shows a later release. Evidence
    that points both ways is a conflict."""
    after, before = [], []
    snapshot = _DATED.search(model) or next(
        (found for found in map(_DATED.search, page.snapshots if page else ()) if found), None)
    if snapshot:
        (after if date.fromisoformat(snapshot.group(1)) >= cutoff else before).append(
            f"snapshot {snapshot.group(0)[1:]}")
    if page and page.uplift:
        after.append("model page states the uplift")
    first = released.get(model) or released.get(base(model))
    if first:
        (after if first >= cutoff else before).append(f"changelog release {first}")
    if page and page.knowledge_cutoff and page.knowledge_cutoff >= cutoff:
        after.append(f"knowledge cutoff {page.knowledge_cutoff}")
    if after and before:
        return Side(None, tuple(after + before), conflict=True)
    return Side(bool(after), tuple(after or before))


@dataclass(frozen=True)
class Regional:
    """OpenAI's regional factors by model, and the models whose evidence disagrees."""

    factors: dict[str, dict[str, float]]
    conflicts: dict[str, tuple[str, ...]]
    sources: tuple[str, ...]


def read(get: Callable[[str], str]) -> Regional:
    """The regional factor of every model OpenAI processes regionally and released on or
    after the uplift's cutoff, keyed by the ids the data residency table lists and by the
    model each dated snapshot belongs to."""
    factor, cutoff = parse_uplift(get(PRICING))
    processed = parse_residency(get(YOUR_DATA))
    released = parse_changelog(get(CHANGELOG))
    pages: dict[str, ModelPage | None] = {}
    factors: dict[str, dict[str, float]] = {}
    conflicts: dict[str, tuple[str, ...]] = {}
    for model, prefixes in sorted(processed.items()):
        name = base(model)
        if name not in pages:
            try:
                pages[name] = parse_model_page(get(model_page(name)))
            except OSError:
                pages[name] = None
        found = side(model, cutoff, pages[name], released)
        if found.conflict:
            conflicts[model] = found.evidence
        elif found.after:
            for listed in {model, name}:
                factors.setdefault(listed, {}).update(dict.fromkeys(sorted(prefixes), factor))
    return Regional({model: dict(sorted(regions.items())) for model, regions in factors.items()},
                    conflicts, (PRICING, YOUR_DATA, CHANGELOG))
