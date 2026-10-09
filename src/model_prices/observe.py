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

from model_prices import checks
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
_BYTEPLUS_COLUMNS = {"Input (non-audio)": "input", "Cache-hit input (non-audio)": "cache_read",
                     "Output": "output"}


def _byteplus_cell(cell: str) -> str:
    """Cell text without Markdown emphasis, escapes, line breaks, or units."""
    text = re.sub(r"\*\*|<br>", " ", cell.replace("\\", ""))
    return " ".join(re.sub(r"\((?:USD|K tokens)[^)]*\)", "", text).split())


def parse_byteplus(page: str) -> dict[str, dict[str, Any]]:
    """Rates of ByteDance's own Seed models from BytePlus ModelArk's standard online
    inference table, which the page embeds as Markdown in its router data.

    A "Prompt length (128, 256]" row is the tier above 128K tokens. BytePlus also resells
    other labs' models, such as DeepSeek's and GLM, which are left out.
    """
    router = re.search(r"window\._ROUTER_DATA = (\{.*?\});?\s*</script>", page, re.S)
    try:
        markdown = next(value["curDoc"]["MDContent"]
                        for value in json.loads(router.group(1))["loaderData"].values()
                        if isinstance(value, dict) and "curDoc" in value)
        section = re.search(r"^## Online inference \(standard\)\n(.*?)(?=^#)", markdown,
                            re.M | re.S).group(1)
    except (AttributeError, StopIteration, KeyError, TypeError, ValueError):
        raise ValueError("byteplus: no standard online inference table; the page format "
                         "changed") from None
    lines = [line for line in section.splitlines() if line.startswith("|")]
    rows = [line.strip().removeprefix("|").removesuffix("|").split("|") for line in lines]
    titles = [_byteplus_cell(cell) for cell in rows[0]] if rows else []
    if not titles or titles[:2] != ["Model ID", "Pricing tiers"] or not set(
            _BYTEPLUS_COLUMNS) <= set(titles):
        raise ValueError(f"byteplus: table columns are {titles}; the page format changed")
    models: dict[str, dict[str, Any]] = {}
    model = ""
    for row in rows[2:]:
        cells = [_byteplus_cell(cell) for cell in row]
        model = cells[0] or model
        if not re.fullmatch(r"(dola-)?seed-[a-z0-9-]+", model):
            continue
        rates = {field: float(cells[titles.index(title)])
                 for title, field in _BYTEPLUS_COLUMNS.items()}
        tier = re.fullmatch(r"Prompt length ([\[(])(\d+), (\d+)\]", cells[1])
        if cells[1] != "-" and tier is None:
            raise ValueError(f"byteplus: unknown pricing tier {cells[1]!r} for {model}")
        if tier and tier.group(1) == "(":
            models[model].setdefault("tiers", []).append({"above": int(tier.group(2)) * 1000,
                                                          **rates})
        else:
            models[model] = rates
    if not models:
        raise ValueError("byteplus: no Seed prices parsed; the page format changed")
    return models


def read_byteplus(get: Callable[[str], str]) -> dict[str, tuple[str, dict[str, Any]]]:
    return {model: (BYTEPLUS_PRICING, rates)
            for model, rates in parse_byteplus(get(BYTEPLUS_PRICING)).items()}


SOURCES: dict[str, Callable[[Callable[[str], str]], dict[str, tuple[str, dict[str, Any]]]]] = {
    "byteplus": read_byteplus,
    "cognition": read_cognition,
    "cursor": read_cursor,
}

# The provider's own models on its checked pricing page, where the page also resells other
# labs' models, such as Alibaba's DeepSeek and Kimi models, at its own prices.
OWN_MODELS = {"alibaba": r"qwen.*", "arcee": r"trinity-.*", "mistral": r"(?!zai-).*",
              "thinkingmachines": r"thinkingmachines/.*"}
# Google's page names models for display, such as "Gemini 3.8 Live", and prices images and
# audio by the unit, so its models are left to models.dev.
CHECKED = [provider for provider in checks.SOURCES if provider != "google"]


ALIBABA_CACHE = "https://www.alibabacloud.com/help/en/model-studio/context-cache.md"
_ALIBABA_ID = r"(?:qwen|deepseek|glm|kimi)[a-z0-9.-]*[a-z0-9]"


def _alibaba_cache_section(page: str, title: str) -> tuple[str, str]:
    """A cache mode's Singapore supported-model list and its billing text."""
    section = re.search(rf"^## {title}\b(.*?)(?=^## |\Z)", page, re.M | re.S)
    tab = section and re.search(r'### Supported models.*?<Tab title="Singapore">(.*?)</Tab>',
                                section.group(1), re.S)
    billing = section and re.search(r"^### Billing(.*?)(?=^### |\Z)", section.group(1),
                                    re.M | re.S)
    if not tab or not billing:
        raise ValueError(f"alibaba: no {title} models or billing in {ALIBABA_CACHE}; "
                         "the page format changed")
    return tab.group(1), billing.group(1)


def parse_alibaba_cache(page: str) -> tuple[set[str], set[str]]:
    """The Singapore models whose implicit cache hits cost 20% of input, and those whose
    explicit cache writes cost 125% of input.

    Alibaba bills implicit cache hits, which need no setup, at 20% of input, and explicit
    cache writes at 125%; it lists exceptions, whose prices only its console shows. One
    cache-read price per model cannot also give explicit hits, at 10% of input, so they
    are priced as implicit hits.
    """
    implicit, implicit_billing = _alibaba_cache_section(page, "Implicit cache")
    explicit, explicit_billing = _alibaba_cache_section(page, "Explicit cache")
    others = re.search(r"For models other than (.*?): The unit price of `cached_token` is "
                       r"<strong>20%</strong> of the `input_token` unit price", implicit_billing)
    exceptions = re.search(r"The explicit cache hit price for (.*?) is not 10%", explicit_billing)
    if (not others or not exceptions or "billed at 125% of the standard input token price"
            not in explicit_billing):
        raise ValueError(f"alibaba: cache billing rules changed in {ALIBABA_CACHE}")
    excluded = set(re.findall(_ALIBABA_ID, others.group(1) + " " + exceptions.group(1)))
    return (set(re.findall(_ALIBABA_ID, implicit)) - excluded,
            set(re.findall(_ALIBABA_ID, explicit)) - excluded)


def _with_alibaba_cache(found: dict[str, dict[str, Any]], page: str) -> None:
    implicit, explicit = parse_alibaba_cache(page)
    for model, rates in found.items():
        for prices in (rates, *rates.get("tiers", [])):
            if model in implicit and "input" in prices:
                prices["cache_read"] = round(prices["input"] * 0.2, 6)
            if model in explicit and "input" in prices:
                prices["cache_write"] = round(prices["input"] * 1.25, 6)


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
    # Alibaba's pricing page states cache prices as rules on its cache page.
    if provider == "alibaba":
        _with_alibaba_cache(found, get(ALIBABA_CACHE))
    return {model: (url, rates) for model, rates in found.items()}


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
    if failures:
        raise ValueError("; ".join(failures))
    return changed
