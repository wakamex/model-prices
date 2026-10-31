"""Record prices from official pages for models that models.dev does not list.

The daily job reads Cursor's and Devin's pages, and the pricing page of each provider that
`model-prices check` reads, and, when a model's rates differ from the last entry in
data/observed.json, appends an entry dated by that run. Entries have the shape
of models.dev history entries, with the page's URL in place of a commit, so the compiler
merges them into the same timelines. A page whose layout changed fails loudly, as a price
check does, rather than recording a guessed price.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import cache, partial
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterable
import tomllib

from model_prices import checks, openai_regions
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


BYTEPLUS_PRICING = "https://docs.byteplus.com/en/docs/ModelArk/1544106"
_BYTEPLUS_COLUMNS = {"Input": "input", "Cached input": "cache_read", "Output": "output"}


def parse_byteplus(page: str) -> dict[str, dict[str, Any]]:
    """Rates of ByteDance's own Seed models from BytePlus ModelArk's Standard table for
    non-audio input, which the page embeds as Markdown in its router data.

    A "(128, 256]" prompt length row is the tier above 128K tokens. The table also lists
    other labs' models that BytePlus resells, such as DeepSeek's and GLM, which are left out.
    """
    router = re.search(r"window\._ROUTER_DATA = (\{.*?\});?\s*</script>", page, re.S)
    try:
        markdown = next(value["curDoc"]["MDContent"]
                        for value in json.loads(router.group(1))["loaderData"].values()
                        if isinstance(value, dict) and "curDoc" in value)
    except (AttributeError, StopIteration, KeyError, TypeError, ValueError):
        raise ValueError("byteplus: no pricing document; the page format changed") from None
    section = re.search(r"^#### Non\\?-audio input\n.*?\*\*Standard\*\*\n(.*?)(?=^\*\*|^#)",
                        markdown, re.M | re.S)
    rows = [[checks._ark_cell(cell).strip("`") for cell in
             line.strip().removeprefix("|").removesuffix("|").split("|")]
            for line in (section.group(1) if section else "").splitlines() if line.startswith("|")]
    titles = rows[0] if rows else []
    if not {"Provider", "Model ID", "Prompt length", *_BYTEPLUS_COLUMNS} <= set(titles):
        raise ValueError(f"byteplus: Standard table columns are {titles}; the page format changed")
    models: dict[str, dict[str, Any]] = {}
    provider = model = ""
    for cells in rows[2:]:
        row = dict(zip(titles, cells))
        provider = row["Provider"] or provider
        model = row["Model ID"] or model
        if provider != "ByteDance":
            continue
        rates = {field: float(row[title].removeprefix("$")) for title, field in _BYTEPLUS_COLUMNS.items()
                 if row[title] not in {"", "-"}}
        tier = re.fullmatch(r"([\[(])(\d+), (\d+)\]", row["Prompt length"])
        if tier is None:
            raise ValueError(f"byteplus: unknown prompt length {row['Prompt length']!r} for {model}")
        if tier.group(1) == "(":
            models[model].setdefault("tiers", []).append({"above": int(tier.group(2)) * 1000,
                                                          **rates})
        else:
            models[model] = rates
    if not models:
        raise ValueError("byteplus: no Seed prices parsed; the page format changed")
    return models


def read_byteplus(get: Callable[[str], str]) -> dict[str, tuple[str, dict[str, Any]]]:
    # BytePlus serves about one request in 15 an unrendered page shell without its pricing
    # document, so the page is fetched up to three times before its format counts as changed.
    page = get(BYTEPLUS_PRICING)
    for _ in range(2):
        if "_ROUTER_DATA" in page and "MDContent" in page:
            break
        page = get(BYTEPLUS_PRICING)
    return {model: (BYTEPLUS_PRICING, rates) for model, rates in parse_byteplus(page).items()}


SOURCES: dict[str, Callable[[Callable[[str], str]], dict[str, tuple[str, dict[str, Any]]]]] = {
    "byteplus": read_byteplus,
    "cognition": read_cognition,
    "cursor": read_cursor,
}

# The provider's own models on its checked pricing page, where the page also resells other
# labs' models, such as Alibaba's DeepSeek and Kimi models, at its own prices.
OWN_MODELS = {"alibaba": r"qwen.*", "arcee": r"trinity-.*", "mistral": r"(?!zai-).*",
              "thinkingmachines": r"thinkingmachines/.*"}
# Pages priced in yuan are left to models.dev, since their names are not API ids and their
# dollar prices are conversions.
CHECKED = [provider for provider in checks.SOURCES if provider not in checks.YUAN_TO_USD]


@cache
def listed(data: Path) -> dict[str, set[str]]:
    """The lowercase ids that models.dev or an alias already gives each provider."""
    found = {provider: {model.lower() for model in models} for provider, models in
             json.loads((data / "prices.json").read_text())["providers"].items()}
    for name, target in tomllib.loads((data / "aliases.toml").read_text())["models"].items():
        found.setdefault(target.split("/", 1)[0], set()).add(name.lower())
    return found


def read_checked(provider: str, data: Path, now: datetime,
                 get: Callable[[str], str]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Rates of the provider's own models on its checked page that models.dev lacks.

    Prices for a stated time, such as DeepSeek's peak hours or Upstage's promotions, are left
    out, as are models without an input and output price, such as embedding models.
    """
    url = checks.SOURCES[provider][0]
    own = re.compile(OWN_MODELS.get(provider, ".*"))
    known = listed(data).get(provider, set())
    found: dict[str, dict[str, Any]] = {}
    for item in checks.parse(provider, get(url), now, get):
        # Z.ai's page writes ids in capitals, such as GLM-4.5-X; its API ids are lowercase.
        model = item.model.lower() if provider == "zai" else item.model
        if (item.at or item.field not in checks.FIELDS or model.lower() in known
                or not own.fullmatch(model)):
            continue
        rates = found.setdefault(model, {})
        if item.mode:
            rates = rates.setdefault("modes", {}).setdefault(item.mode, {})
        if item.modality:
            # Prices by modality are kept only where one differs from the default, below.
            if item.above:
                continue
            rates = rates.setdefault("modalities", {}).setdefault(item.modality, {})
        if item.above:
            tiers = rates.setdefault("tiers", [])
            tier = next((tier for tier in tiers if tier["above"] == item.above), None)
            if tier is None:
                tiers.append(tier := {"above": item.above})
                tiers.sort(key=lambda tier: tier["above"])
            rates = tier
        if rates.get(item.field, item.value) != item.value:
            raise ValueError(f"{provider}: {model} lists two {item.field} prices")
        rates[item.field] = item.value
    found = {model: rates for model, rates in found.items()
             if "input" in rates and "output" in rates}
    for rates in found.values():
        for prices in (rates, *rates.get("modes", {}).values()):
            _keep_differing_modalities(prices)
    return {model: (url, rates) for model, rates in found.items()}


def _keep_differing_modalities(rates: dict[str, Any]) -> None:
    """Drop a page's prices by modality when every one is the price of a token without a
    modality, as the history keeps them."""
    modalities = rates.get("modalities", {})
    if all(rates.get(key) == value for prices in modalities.values()
           for key, value in prices.items()):
        rates.pop("modalities", None)


def observe(output: Path, get: Callable[[str], str] = fetch, now: datetime | None = None,
            providers: Iterable[str] | None = None) -> list[str]:
    """Append each model whose page rates differ from its last entry; return the providers
    that changed.

    A provider whose pages cannot be read keeps its entries, and the others are still
    recorded before the failures are raised together.
    """
    data = json.loads(output.read_text()) if output.exists() else {"providers": {}}
    stamp = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    readers = {**SOURCES, **{provider: partial(read_checked, provider, output.parent, stamp)
                             for provider in CHECKED}}
    changed, failures = [], []
    for provider, read in readers.items():
        if providers is not None and provider not in providers:
            continue
        try:
            found = read(get)
        except (OSError, ValueError, KeyError) as error:
            failures.append(f"{provider}: {error}")
            continue
        for model, (url, rates) in sorted(found.items()):
            entries = data["providers"].setdefault(provider, {}).setdefault(model, [])
            if entries and entries[-1]["rates"] == rates:
                continue
            entries.append({"valid_from": stamp.isoformat().replace("+00:00", "Z"),
                            "source": url, "rates": rates})
            if provider not in changed:
                changed.append(provider)
    if changed:
        output.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    if providers is None or "openai" in providers:
        try:
            if (observe_regions(output.with_name("observed_regions.json"), get, stamp)
                    and "openai" not in changed):
                changed.append("openai")
        except (OSError, ValueError) as error:
            failures.append(f"openai regions: {error}")
    if failures:
        raise ValueError("; ".join(failures))
    return changed


def observe_regions(output: Path, get: Callable[[str], str], now: datetime) -> bool:
    """Record OpenAI's regional factors by model, each change dated by the first run that
    read it; return whether any changed. A model whose evidence disagrees keeps its entries."""
    data = json.loads(output.read_text()) if output.exists() else {"providers": {}}
    regional = openai_regions.read(get)
    listed = data["providers"].setdefault("openai", {})
    changed = False
    for model in sorted(set(regional.factors) | set(listed)):
        if model in regional.conflicts:
            continue
        regions = regional.factors.get(model, {})
        entries = listed.setdefault(model, [])
        if (entries[-1]["regions"] if entries else {}) == regions:
            continue
        entries.append({"valid_from": now.isoformat().replace("+00:00", "Z"),
                        "source": openai_regions.YOUR_DATA, "regions": regions})
        changed = True
    if changed:
        output.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return changed
