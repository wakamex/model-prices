"""Record prices from official pages for models that models.dev does not list.

The daily job reads each provider's pricing pages and, when a model's rates differ from the
last entry in data/observed.json, appends an entry dated by that run. Entries have the shape
of models.dev history entries, with the page's URL in place of a commit, so the compiler
merges them into the same timelines. A page whose layout changed fails loudly, as a price
check does, rather than recording a guessed price.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable

from model_prices.checks import _mdx_grid, _price, fetch

CURSOR_INDEX = "https://cursor.com/llms.txt"
_CURSOR_COLUMNS = {"Input": "input", "Cache Write": "cache_write", "Cache Read": "cache_read",
                   "Output": "output"}


def cursor_pages(index: str) -> list[str]:
    """The HTML pages of Cursor's own models, from its docs index. Their Markdown copies omit
    the rate table."""
    return sorted({url.removesuffix(".md") for url in re.findall(
        r"https://cursor\.com/docs/models/cursor-[a-z0-9-]+\.md", index)})


def parse_cursor(page: str) -> dict[str, dict[str, Any]]:
    """Rates by model id from a Cursor model page: "Composer 2.5" is composer-2.5, and a
    "Composer 2.5 (Fast)" row is that model's fast mode."""
    table = re.search(r"<table.*?</table>", page, re.S)
    if table is None:
        raise ValueError("cursor: no rate table found; the page format changed")
    header, rows = _mdx_grid(table.group(0))
    titles = header[0] if header else []
    if titles != ["Name", *_CURSOR_COLUMNS]:
        raise ValueError(f"cursor: rate table columns are {titles}; the page format changed")
    models: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = re.match(r"(.*?)\s*(?:\((.+)\))?$", row[0])
        model = "-".join(name.group(1).lower().split())
        rates = {field: value for title, field in _CURSOR_COLUMNS.items()
                 if (value := _price(row[titles.index(title)])) is not None}
        if "input" not in rates or "output" not in rates:
            raise ValueError(f"cursor: no input and output price for {row[0]}")
        entry = models.setdefault(model, {})
        if name.group(2):
            entry.setdefault("modes", {})[name.group(2).lower()] = rates
        else:
            entry.update(rates)
    if not models:
        raise ValueError("cursor: no prices parsed; the page format changed")
    return models


def read_cursor(get: Callable[[str], str]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Each Cursor model's page URL and rates."""
    found = {}
    for url in cursor_pages(get(CURSOR_INDEX)):
        for model, rates in parse_cursor(get(url)).items():
            found[model] = (url, rates)
    if not found:
        raise ValueError(f"cursor: no model pages listed in {CURSOR_INDEX}")
    return found


DEVIN_MODELS = "https://docs.devin.ai/desktop/models"
# Enterprise plans are billed these per-token prices directly; self-serve plans include some
# of Cognition's models at no charge for a period, which is no per-token price.
_DEVIN_TIER = "TEAMS_TIER_ENTERPRISE_SAAS"
_DEVIN_FIELDS = {"input_cost_per_million_usd": "input", "output_cost_per_million_usd": "output",
                 "cache_read_cost_per_million_usd": "cache_read",
                 "cache_write_cost_per_million_usd": "cache_write"}


def parse_devin(page: str) -> dict[str, dict[str, Any]]:
    """Rates of Cognition's own models, by the model ids Devin reports, from the price list
    embedded in Devin's models page."""
    models: dict[str, dict[str, Any]] = {}
    for record in re.findall(r'\{[^{}]*"input_cost_per_million_usd"[^{}]*\}',
                             page.replace('\\"', '"')):
        fields = {key: text if text else number for key, text, number in
                  re.findall(r'"(\w+)":(?:`([^`]*)`|([^,}]*))', record)}
        # Records with internal enum ids, such as MODEL_SWE_1_5, name no model Devin reports.
        if (fields.get("tier") != _DEVIN_TIER
                or fields.get("model_provider") != "MODEL_PROVIDER_WINDSURF"
                or not re.fullmatch(r"[a-z0-9.-]+", fields.get("model_uid", ""))):
            continue
        try:
            models[fields["model_uid"]] = {field: float(fields[key])
                                           for key, field in _DEVIN_FIELDS.items()}
        except (KeyError, ValueError):
            raise ValueError(f"cognition: unreadable price record {record[:200]}") from None
    if not models:
        raise ValueError("cognition: no prices parsed; the page format changed")
    return models


def read_cognition(get: Callable[[str], str]) -> dict[str, tuple[str, dict[str, Any]]]:
    return {model: (DEVIN_MODELS, rates) for model, rates in parse_devin(get(DEVIN_MODELS)).items()}


SOURCES: dict[str, Callable[[Callable[[str], str]], dict[str, tuple[str, dict[str, Any]]]]] = {
    "cognition": read_cognition,
    "cursor": read_cursor,
}


def observe(output: Path, get: Callable[[str], str] = fetch,
            now: datetime | None = None) -> list[str]:
    """Append each model whose page rates differ from its last entry; return the providers
    that changed.

    A provider whose pages cannot be read keeps its entries, and the others are still
    recorded before the failures are raised together.
    """
    data = json.loads(output.read_text()) if output.exists() else {"providers": {}}
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    changed, failures = [], []
    for provider, read in SOURCES.items():
        try:
            found = read(get)
        except (OSError, ValueError, KeyError) as error:
            failures.append(f"{provider}: {error}")
            continue
        models = data["providers"].setdefault(provider, {})
        for model, (url, rates) in sorted(found.items()):
            entries = models.setdefault(model, [])
            if entries and entries[-1]["rates"] == rates:
                continue
            entries.append({"valid_from": stamp.isoformat().replace("+00:00", "Z"),
                            "source": url, "rates": rates})
            if provider not in changed:
                changed.append(provider)
    if changed:
        output.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    if failures:
        raise ValueError("; ".join(failures))
    return changed
