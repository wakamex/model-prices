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
import html
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


ALIBABA_CACHE = "https://www.alibabacloud.com/help/en/model-studio/context-cache.md"
_ALIBABA_ID = r"(?:qwen|deepseek|glm|kimi)[a-z0-9.-]*[a-z0-9]"


def _markdown(page: str) -> str:
    """An HTML docs page as the Markdown its .md address used to serve: headings as #
    lines, list items as - lines, code in backticks, and <strong> kept. Code samples are
    left out, since their comments would read as headings."""
    page = re.sub(r"<(script|style|pre)\b.*?</\1>", "", page, flags=re.S)
    page = re.sub(r"<h([1-6])\b[^>]*>(.*?)</h\1>",
                  lambda found: "\n" + "#" * int(found.group(1)) + " " + found.group(2) + "\n",
                  page, flags=re.S)
    page = re.sub(r"<li\b[^>]*>", "\n- ", page)
    page = re.sub(r"</?code\b[^>]*>", "`", page)
    page = re.sub(r"</?(p|div|section|tr|br|ul|ol|table)\b[^>]*>", "\n", page)
    page = re.sub(r"<(?!/?strong>)[^>]+>", "", page)
    lines = (" ".join(html.unescape(line).split()) for line in page.splitlines())
    return "\n".join(line for line in lines if line)


def _alibaba_cache_section(page: str, title: str) -> tuple[str, str]:
    """A cache mode's Singapore supported-model list and its billing text. The page marks
    regions with <Tab title=...> in Markdown and #### headings in converted HTML."""
    if re.match(r"\s*<(!doctype|html)", page, re.I):
        page = _markdown(page)
    section = re.search(rf"^## {title}\b(.*?)(?=^## |\Z)", page, re.M | re.S)
    tab = section and re.search(r'### Supported models.*?(?:<Tab title="Singapore">(.*?)</Tab>'
                                r'|^#### Singapore\n(.*?)(?=^#{3,4} |\Z))',
                                section.group(1), re.S | re.M)
    billing = section and re.search(r"^### Billing(.*?)(?=^### |\Z)", section.group(1),
                                    re.M | re.S)
    if not tab or not billing:
        raise ValueError(f"alibaba: no {title} models or billing in {ALIBABA_CACHE}; "
                         "the page format changed")
    return tab.group(1) or tab.group(2), billing.group(1)


def parse_alibaba_cache(page: str) -> tuple[set[str], set[str]]:
    """The Singapore models with implicit caching, and those with explicit caching.

    Alibaba bills implicit cache hits, which need no setup, at 20% of input, and explicit
    cache hits at 10% and writes at 125%; it lists exceptions, whose prices only its
    console shows. A request uses one mode, so a model with implicit caching prices its
    one cache-read price as an implicit hit, and a model with only explicit caching as an
    explicit hit.
    """
    implicit, implicit_billing = _alibaba_cache_section(page, "Implicit cache")
    explicit, explicit_billing = _alibaba_cache_section(page, "Explicit cache")
    others = re.search(r"For models other than (.*?): The unit price of `cached_token` is "
                       r"<strong>20%</strong> of the `input_token` unit price", implicit_billing)
    # Exceptions are a sentence, "The explicit cache hit price for ... is not 10%", or a
    # bullet per group of models whose hit or creation price is "not 10%" or "not 125%".
    exceptions = [names for names in re.findall(
        r"The explicit cache hit price for (.*?) is not 10%", explicit_billing)] + [
        names for names, rule in re.findall(r"^\s*- ([^:\n]+): (.*)$", explicit_billing, re.M)
        if re.search(r"not (?:10|125)%", rule)]
    if (not others or not exceptions or "billed at 125% of the standard input token price"
            not in explicit_billing or "Billed at 10% of the standard input token price"
            not in explicit_billing):
        raise ValueError(f"alibaba: cache billing rules changed in {ALIBABA_CACHE}")
    excluded = set(re.findall(_ALIBABA_ID, others.group(1) + " " + " ".join(exceptions)))
    return (set(re.findall(_ALIBABA_ID, implicit)) - excluded,
            set(re.findall(_ALIBABA_ID, explicit)) - excluded)


def _with_alibaba_cache(found: dict[str, dict[str, Any]], page: str) -> None:
    implicit, explicit = parse_alibaba_cache(page)
    for model, rates in found.items():
        for prices in (rates, *rates.get("tiers", [])):
            # A model without implicit caching has only explicit hits, at 10% of input.
            share = 0.2 if model in implicit else 0.1 if model in explicit else None
            if share and "input" in prices:
                prices["cache_read"] = round(prices["input"] * share, 6)
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
