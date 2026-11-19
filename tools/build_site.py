"""Write the website's generated content from the bundled price snapshot.

    uv run --locked python tools/build_site.py [--check-results CHECK_JSON]
    zola --root site build

Writes the overview table, one section per provider, one page per model, the subscription
plans page, the navigation, and the calculator's data under site/. These paths are generated and not committed; the
calculator, the about page, and the templates are. CHECK_JSON is the output of
`model-prices check --json`, which adds each model's official-page status.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import tomllib
from urllib.parse import urlencode, urlparse
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import model_prices  # noqa: E402
from model_prices import checks, observe  # noqa: E402

SITE = ROOT / "site"
CONTENT = SITE / "content"
REPOSITORY = "https://github.com/wakamex/model-prices"
GENERATED = (CONTENT / "_index.md", CONTENT / "providers", CONTENT / "corrections.md", CONTENT / "plans.md",
             CONTENT / "benchmarks.md",
             SITE / "data" / "navigation.json",
             SITE / "static" / "snapshot.json", SITE / "static" / "calculator-models.json")

PROVIDER_NAMES = {
    "ai21": "AI21 Labs", "alibaba": "Alibaba", "amazon-bedrock": "Amazon Bedrock",
    "anthropic": "Anthropic", "arcee": "Arcee", "bailing": "Ant Group (Bailing)",
    "byteplus": "ByteDance (BytePlus)", "cognition": "Cognition", "cohere": "Cohere",
    "cursor": "Cursor", "deepseek": "DeepSeek", "google": "Google", "inception": "Inception",
    "longcat": "Meituan (LongCat)", "meta": "Meta", "minimax": "MiniMax", "mistral": "Mistral",
    "moonshotai": "Moonshot AI", "nova": "Amazon Nova", "openai": "OpenAI",
    "perplexity": "Perplexity", "poolside": "Poolside", "sakana": "Sakana AI",
    "sensenova": "SenseTime (SenseNova)", "stepfun-ai": "StepFun",
    "tencent-tokenhub": "Tencent (TokenHub)", "thinkingmachines": "Thinking Machines",
    "upstage": "Upstage", "volcengine": "ByteDance (Volcengine)", "xai": "xAI",
    "xiaomi": "Xiaomi", "zai": "Z.ai",
}
MODE_NAMES = {"standard": "Standard", "fast": "Fast mode", "ultrafast": "Ultrafast mode",
              "flex": "Flex tier", "priority": "Priority tier", "thinking": "Thinking mode",
              "batch": "Batch API"}
STATUS_TEXT = {
    "ok": "Matches {page}, checked {ran}.",
    "corrected": ("Matches {page}, checked {ran}. models.dev lists a different price, which "
                  "model-prices corrects; the history shows both."),
    "mismatch": ("Differs from {page}, checked {ran}, so this price may be out of date until "
                 "a correction lands."),
}


def name(provider: str) -> str:
    return PROVIDER_NAMES.get(provider, provider)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", text.lower()).strip("-")


def escape(text: str) -> str:
    """Text for a Markdown table cell or link label."""
    return re.sub(r"([\\`*_\[\]|<>])", r"\\\1", text)


def price(value: float | None) -> str:
    if value is None:
        return ""
    if value == 0:
        return "free"
    text = f"{value:.10f}".rstrip("0")
    whole, _, fraction = text.partition(".")
    return f"${whole}.{fraction.ljust(2, '0')}"


def day(value: str | None) -> str:
    return value[:10] if value else ""


def cached(rates: dict) -> str:
    """The cached input cell, with the explicit cache hit price where one differs."""
    explicit = rates.get("cache_read_explicit")
    return price(rates.get("cache_read")) + (f", explicit {price(explicit)}" if explicit is not None else "")


def by_modality(rates: dict) -> str:
    """The prices a model states for each modality, such as "audio: in $32.00, out $64.00"."""
    return "; ".join(
        f"{name}: " + ", ".join(f"{label} {price(prices[field])}" for field, label in (
            ("input", "in"), ("cache_read", "cached"), ("output", "out")) if field in prices)
        for name, prices in sorted(rates.get("modalities", {}).items()))


def tiers(rates: dict) -> str:
    return "; ".join(
        f"above {tier['above'] // 1000:,}K: " + ", ".join(
            f"{label} {price(tier[field])}" for field, label in (
                ("input", "in"), ("cache_read", "cached"),
                ("cache_read_explicit", "explicit cached"), ("cache_write", "write"),
                ("output", "out")) if tier.get(field) is not None)
        for tier in rates.get("tiers", []))


def current(timeline: list[dict], now: datetime) -> dict | None:
    """The price change in effect now: the last whose start has passed."""
    timeline = changes(timeline)
    found = timeline[0]
    for interval in timeline[1:]:
        if model_prices._parse_time(interval["start"]) <= now:
            found = interval
    return found


def statuses(path: Path | None) -> tuple[dict, str | None]:
    """Each checked model's statuses from `model-prices check --json`, and when it ran."""
    if path is None:
        return {}, None
    found: dict[str, set[str]] = {}
    for result in json.loads(path.read_text()):
        # Comparisons with models.dev's rules say nothing about the pricing page.
        if ("/" in result["model"] and result["status"] in STATUS_TEXT
                and not result["field"].startswith("rule:")):
            found.setdefault(result["model"], set()).add(result["status"])
    ran = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return found, ran


def unlisted(path: Path | None) -> set[tuple[str, str]]:
    """Models priced from their provider's page that the page no longer lists, which the check
    names, one result per provider, as unchecked parsed prices."""
    if path is None:
        return set()
    return {(result["provider"], model) for result in json.loads(path.read_text())
            if result["field"] == "parsed prices" for model in result["official"].split(", ")}


def official_page(provider: str) -> str | None:
    """The provider's pricing page for readers: the check reads Markdown copies, and
    Volcengine's document through the API its page loads."""
    url = checks.SOURCES.get(provider, (None,))[0]
    if url is None:
        return None
    if provider == "volcengine":
        return "https://www.volcengine.com/docs/82379/1544106"
    return re.sub(r"(index)?\.md(\.txt)?$", "", url)


# Providers that set prices in Chinese yuan, which models.dev converts to US dollars.
YUAN_NOTES = {
    "volcengine": "at 6.737 yuan per dollar, the exchange rate on 2026-08-26",
    "tencent-tokenhub": f"at about {1 / checks.YUAN_TO_USD['tencent-tokenhub']:.2f} yuan per dollar",
}


def yuan_note(provider: str) -> str:
    rate = YUAN_NOTES.get(provider)
    return (f" {name(provider)} sets its prices in Chinese yuan, which models.dev converts to US "
            f"dollars {rate}, so a bill in yuan can differ slightly." if rate else "")


# "unlisted" is a model priced from its provider's page that the page no longer lists.
STATUS_LABELS = {"deprecated": "deprecated", "removed": "delisted", "unlisted": "delisted"}
STATUS_TEXT_MODEL = {
    "deprecated": "models.dev marks this model deprecated: the provider plans to retire it or has.",
    "removed": "models.dev no longer lists this model, usually because the provider retired it; "
               "its history ends with the last price models.dev recorded.",
    "unlisted": "Its provider's pricing page no longer lists this model, usually because the "
                "provider retired it; its history ends with the last price that page stated.",
}


def check_line(provider: str, model: str, found: dict, ran: str | None) -> str:
    page = official_page(provider)
    if page is None:
        return f"{name(provider)} has no official pricing page that model-prices checks."
    if ran is None:
        return f"Checked daily against [{name(provider)}'s pricing page]({page})."
    seen = found.get(f"{provider}/{model}")
    if not seen:
        return f"{name(provider)}'s [pricing page]({page}) does not list this model under this id."
    status = "mismatch" if "mismatch" in seen else "corrected" if "corrected" in seen else "ok"
    link = f"[{name(provider)}'s pricing page]({page})"
    return STATUS_TEXT[status].format(page=link, ran=ran)


def schedule_line(provider: str, model: str, now: datetime) -> str | None:
    """The time-of-day rule in effect now for the model, if any."""
    data = model_prices._data()["schedules"]
    for schedule in data.get("schedule", []):
        until = schedule.get("valid_until")
        if schedule["provider"] != provider or (until and model_prices._parse_time(until) <= now):
            continue
        if "peak_hours_utc" in schedule:
            hours = ", ".join("-".join(window) for window in schedule["peak_hours_utc"])
            days = " on weekdays" if schedule.get("weekdays_only") else ""
            holidays = " other than Chinese public holidays" if schedule.get("holidays") == "cn" else ""
            return (f"Since {day(schedule['valid_from'])}, requests during peak hours, {hours} UTC"
                    f"{days}{holidays}, cost {schedule['peak_multiplier']:g} times the prices below, "
                    "which are the off-peak prices.")
        factor = schedule["off_peak_multiplier"].get(model)
        if factor is not None:
            hours = ", ".join("-".join(window) for window in schedule["off_peak_hours_utc"])
            return (f"Since {day(schedule['valid_from'])}, requests during off-peak hours, {hours} UTC, "
                    f"cost {factor:g} times the prices below.")
    return None


PRICE_KEYS = ("input", "output", "cache_read", "cache_read_explicit", "cache_write", "tiers",
              "cache_write_1h_multiple", "modalities", "regions")


def changes(timeline: list[dict]) -> list[dict]:
    """The timeline's intervals where the price changed, each with the provenance of its first
    interval; consecutive intervals that differ only in source or dating are merged."""
    merged: list[dict] = []
    for interval in timeline:
        rates = interval["rates"]
        key = None if rates is None else tuple(json.dumps(rates.get(k)) for k in PRICE_KEYS)
        if merged and merged[-1]["key"] == key:
            continue
        merged.append({**interval, "key": key})
    return merged


def first_start(timeline: list[dict]) -> str:
    """The first price's date: it also applies to every earlier request. A model not sold
    at first, such as before a batch discount began, is not sold until the next change."""
    rates = timeline[0]["rates"] or {}
    first = day(rates.get("valid_from"))
    following = day(timeline[1]["start"]) if len(timeline) > 1 else None
    if not rates:
        return f"before {following}"
    return f"before {first}" if first and first == following else f"{first} or earlier"


def source_name(url: str) -> str:
    commit = re.search(r"models\.dev/commit/([0-9a-f]{7})", url)
    if commit:
        return f"models.dev {commit.group(1)}"
    archived = re.match(r"https?://web\.archive\.org/web/([0-9]{8})[^/]*/(?:https?://)?([^/]+)", url)
    if archived:
        date = archived.group(1)
        return f"{archived.group(2).removeprefix('www.')}, archived {date[:4]}-{date[4:6]}-{date[6:]}"
    return urlparse(url).netloc.removeprefix("www.")


FIELD_NAMES = (("input", "input"), ("cache_read", "cached input"),
               ("cache_read_explicit", "explicit cache hits"), ("cache_write", "cache write"),
               ("output", "output"))


def dated_by(interval: dict) -> str:
    """How the row's start date is known, linked to its source, and the models.dev price a
    correction replaces."""
    rates = interval["rates"]
    basis = rates.get("valid_from_basis", "")
    url = rates.get("source")
    label = {"models.dev commit": basis, "scheduled": "scheduled in models.dev"}.get(
        basis, f"{basis}, {source_name(url or '')}")
    cell = f"[{escape(label)}]({url})" if url else escape(basis)
    recorded = interval.get("recorded") or {}
    replaced = [f"{label} {price(recorded.get(field))}" for field, label in FIELD_NAMES
                if field in recorded and recorded.get(field) != rates.get(field)]
    if recorded and recorded.get("tiers") != rates.get("tiers"):
        replaced.append(f"longer prompts {escape(tiers(recorded))}" if recorded.get("tiers")
                        else "no longer-prompt prices")
    return cell + (f"; models.dev lists {', '.join(replaced)}" if replaced else "")


def history(timeline: list[dict]) -> list[str]:
    timeline = changes(timeline)
    # Models priced by modality show those prices in their own column.
    modal = any((interval["rates"] or {}).get("modalities") for interval in timeline)
    regional = any((interval["rates"] or {}).get("regions") for interval in timeline)
    titles = ["From", "Input", "Cached input", "Cache write", "Output", "Longer prompts",
              *(["By modality"] if modal else []), *(["By region"] if regional else []), "Dated by"]
    lines = ["| " + " | ".join(titles) + " |", "|" + " --- |" * len(titles)]
    for interval in reversed(timeline):
        rates = interval["rates"]
        start = day(interval["start"]) or first_start(timeline)
        if rates is None:
            lines.append(f"| {start} | not sold |" + "  |" * (len(titles) - 2))
            continue
        lines.append(" | ".join((
            f"| {start}", price(rates["input"]), cached(rates),
            price(rates.get("cache_write")), price(rates["output"]), tiers(rates),
            *([by_modality(rates)] if modal else []),
            *([", ".join(f"{name} {factor:g}x" for name, factor in sorted(rates.get("regions", {}).items()))]
              if regional else []), dated_by(interval))) + " |")
    return lines


def model_page(provider: str, model: str, timelines: dict, found: dict, ran: str | None,
               now: datetime, state: str | None = None) -> str:
    standard = timelines.get("standard", [])
    latest = current(standard, now) if standard else None
    rates = latest["rates"] if latest else None
    front = {
        "title": model,
        "description": f"{model} per-token prices from {name(provider)}, with dated price history.",
        "extra": {
            "breadcrumbs": [{"title": "Providers", "path": "providers/"},
                            {"title": name(provider), "path": f"providers/{slug(provider)}/"}],
            "navigation_group": "providers",
            "navigation_branch": f"providers/{slug(provider)}/",
            "page_navigation": False,
            "toc": len(timelines) > 1,
            # Prefill the price report form.
            "provider": provider,
            "model": model,
        },
    }
    intro = [f"{name(provider)} model `{model}`. Prices are in US dollars per million tokens."
             + yuan_note(provider)]
    if rates:
        intro[0] += " " + (
            f"Current price, since {day(latest['start']) or first_start(changes(standard))}: "
            f"input {price(rates['input'])}, output {price(rates['output'])}"
            + (f", cached input {price(rates['cache_read'])}" if rates.get("cache_read") is not None else "")
            + (f", explicit cache hits {price(rates['cache_read_explicit'])}"
               if rates.get("cache_read_explicit") is not None else "")
            + (f", cache write {price(rates['cache_write'])}" if rates.get("cache_write") is not None else "")
            + ".")
    if rates and rates.get("regions"):
        intro.append("Requests served in a region cost more: " + ", ".join(
            f"`{name}` {factor:g} times these prices" for name, factor in sorted(rates["regions"].items()))
            + ". Pass `region` to price them.")
    if rates and rates.get("modalities"):
        intro.append(f"Prices by modality: {by_modality(rates)}. Tokens without a modality cost "
                     "the prices above.")
    upcoming = [interval for interval in changes(standard)
                if interval["start"] and model_prices._parse_time(interval["start"]) > now
                and interval["rates"]]
    for interval in upcoming:
        intro.append(f"Scheduled from {day(interval['start'])}: input {price(interval['rates']['input'])}, "
                     f"output {price(interval['rates']['output'])}"
                     + (f", cached input {price(interval['rates']['cache_read'])}"
                        if interval["rates"].get("cache_read") is not None else "") + ".")
    if state:
        intro.append(STATUS_TEXT_MODEL[state])
    intro.append(check_line(provider, model, found, ran))
    rule = schedule_line(provider, model, now)
    if rule:
        intro.append(rule)
    intro.append(f"[Price a request with this model](../../../calculator/?{urlencode({'provider': provider, 'model': model})}).")
    body = []
    for mode in ("standard", *sorted(mode for mode in timelines if mode != "standard")):
        body += ["", f"## {MODE_NAMES.get(mode, mode.title())} price history", "", *history(timelines[mode])]
    body += ["", "A blank cache price is charged at the input price. Longer prompts list the prices for "
             "requests whose whole prompt exceeds the size given. Dated by says how a row's start "
             "is known: from the models.dev commit that recorded it, which can lag the provider's "
             "change by days; documented by the provider; first observed on the provider's "
             "pricing page by the daily check; or scheduled, a change the provider announced ahead, "
             "which models.dev recorded and which takes effect at 00:00 UTC on its date. The first price also applies to every earlier "
             "request. [About the data](../../../about/) explains each source.", "",
             "Price usage in Python with the [model-prices package](https://pypi.org/project/model-prices/):", "",
             "```sh", "pip install model-prices", "```", "",
             "```python", "import model_prices", "",
             f"model_prices.rates({json.dumps(model)}, provider={json.dumps(provider)})", "```"]
    return "+++\n" + toml(front) + "+++\n\n" + "\n\n".join(intro) + "\n" + "\n".join(body) + "\n"


def toml(value: dict, prefix: str = "") -> str:
    """Front matter as TOML; values are strings, booleans, and lists of tables."""
    lines, tables = [], []
    for key, item in value.items():
        if isinstance(item, dict):
            tables.append((key, item))
        else:
            lines.append(f"{key} = {json.dumps(item) if not isinstance(item, bool) else str(item).lower()}")
    for key, item in tables:
        lines.append(f"\n[{prefix}{key}]")
        for name_, entry in item.items():
            if isinstance(entry, list):
                lines.append(f"{name_} = [" + ", ".join(
                    "{ " + ", ".join(f"{k} = {json.dumps(v)}" for k, v in row.items()) + " }"
                    for row in entry) + "]")
            else:
                lines.append(f"{name_} = {json.dumps(entry) if not isinstance(entry, bool) else str(entry).lower()}")
    return "\n".join(lines) + "\n"


def price_row(provider: str | None, model: str, rates: dict, start: str, link: str,
              note: str = "") -> str:
    """A table row; a provider names the Provider column, which provider pages omit."""
    longer = min((tier["above"] for tier in rates.get("tiers", [])), default=None)
    return " | ".join((
        f"| [{escape(model)}]({link}){note}", *([name(provider)] if provider else []),
        price(rates["input"]), cached(rates), price(rates.get("cache_write")),
        price(rates["output"]), f"above {longer // 1000:,}K" if longer else "", start)) + " |"


def table_head(with_provider: bool) -> list[str]:
    titles = ["Model", *(["Provider"] if with_provider else []), "Input", "Cached input",
              "Cache write", "Output", "Longer prompts", "Since"]
    return ["| " + " | ".join(titles) + " |", "|" + " --- |" * len(titles)]


def price_filter(placeholder: str) -> str:
    return ('<label class="price-filter">Filter <input id="price-filter" type="search" '
            f'placeholder="{placeholder}" autocomplete="off"></label>')


def build(check_results: Path | None) -> None:
    data = model_prices._data()
    now = datetime.now(timezone.utc)
    found, ran = statuses(check_results)
    delisted = unlisted(check_results)
    for path in GENERATED:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    providers = CONTENT / "providers"
    providers.mkdir(parents=True)
    overview, calculator, navigation = [], [], []
    pages: dict[tuple[str, str], str] = {}
    for provider in sorted(data["prices"], key=name):
        section = providers / slug(provider)
        section.mkdir()
        rows, used = [], set()
        for model in sorted(data["prices"][provider], key=str.lower):
            timelines = data["prices"][provider][model]
            page = slug(model)
            while page in used:
                page += "-"
            used.add(page)
            state = data["status"].get(provider, {}).get(model) or (
                "unlisted" if (provider, model) in delisted else None)
            (section / f"{page}.md").write_text(model_page(provider, model, timelines, found, ran, now, state))
            pages[(provider, model)] = f"../providers/{slug(provider)}/{page}/"
            resolved = model_prices.resolve_details(model, provider)
            if resolved and resolved[:3] == (provider, model, ""):
                calculator.append({"provider": provider, "provider_name": name(provider),
                                   "model": model, "modes": sorted(timelines)})
            latest = current(timelines["standard"], now) if timelines.get("standard") else None
            if latest and latest["rates"]:
                start = day(latest["start"]) or first_start(changes(timelines["standard"]))
                rule = schedule_line(provider, model, now)
                note = (" (off-peak)" if rule and "peak hours" in rule else
                        " (time of day)" if rule else "")
                note += f" ({STATUS_LABELS[state]})" if state else ""
                # Deprecated and delisted models follow the current ones.
                order = (state is not None, model.lower())
                rows.append((order, price_row(None, model, latest["rates"], start, f"{page}/", note)))
                # The front page leaves out delisted models, which their provider pages keep.
                if state not in {"removed", "unlisted"}:
                    overview.append((order, price_row(provider, model, latest["rates"], start,
                                                      f"providers/{slug(provider)}/{page}/", note)))
        page_url = official_page(provider)
        observed = provider in observe.SOURCES
        intro = (f"model-prices checks these prices daily against [{name(provider)}'s pricing page]({page_url})."
                 if page_url else
                 f"model-prices reads these prices from {name(provider)}'s own pages daily." if observed else
                 f"These prices come from [models.dev](https://models.dev); {name(provider)} has no "
                 "official pricing page that model-prices checks.")
        (section / "_index.md").write_text(
            "+++\n" + toml({"title": name(provider), "sort_by": "title", "template": "provider.html",
                            "description": f"{name(provider)} per-token prices with dated price history.",
                            "extra": {"breadcrumbs": [{"title": "Providers", "path": "providers/"}],
                                      "provider": provider,
                                      "navigation_group": "providers",
                                      "navigation_branch": f"providers/{slug(provider)}/"}})
            + "+++\n\n" + intro + " Prices are in US dollars per million tokens." + yuan_note(provider)
            + "\n\n"
            + price_filter("Model") + "\n\n" + "\n".join(table_head(False) + [row for _, row in sorted(rows)]) + "\n")
        navigation.append({"title": name(provider), "path": f"providers/{slug(provider)}/",
                           "sidebar_children": False})
    (providers / "_index.md").write_text(
        "+++\n" + toml({"title": "Providers", "template": "prices.html",
                        "description": "Every provider model-prices tracks.",
                        "extra": {"navigation_group": "providers", "navigation_branch": "providers/"}})
        + "+++\n\n" + "\n".join(
            f"- [{name(provider)}]({slug(provider)}/): {len(data['prices'][provider])} models"
            for provider in sorted(data["prices"], key=name)) + "\n")
    (CONTENT / "_index.md").write_text(
        "+++\n" + toml({"title": "LLM token prices with dated history", "template": "prices.html",
                        "description": "Current and historical per-token prices for LLMs, checked against "
                                       "each provider's own pricing page."})
        + "+++\n\n"
        "What each LLM cost per token on any date: every model's page lists each past price with when it "
        "took effect, how that date is known, and its source. Prices come from the history of "
        "[models.dev](https://models.dev), corrected where a provider's own pricing page differs, "
        "and are checked against those pages daily. Price past usage at the rates in effect when it "
        "ran, whether you pay per token or want to see what a subscription's usage would cost at "
        "those rates, with the [calculator](calculator/), or in Python with the [model-prices package]"
        "(https://pypi.org/project/model-prices/): `pip install model-prices`. The code is on "
        "[GitHub](https://github.com/wakamex/model-prices), and the data is published as a [JSON "
        "snapshot](https://github.com/wakamex/model-prices/tree/data/v1).\n\n"
        f"Current prices for {len(overview)} models from {len(data['prices'])} providers, in US "
        "dollars per million tokens, as of "
        f"{data['updated_at'][:10]}. A blank cache price is charged at the input price, and free "
        "means the provider charges nothing for that token type. Longer "
        "prompts gives the prompt size above which a model costs more. A Since date ending in "
        "\"or earlier\" is when tracking began. Models marked off-peak cost more at peak hours, and "
        "those marked time of day cost less off-peak; their pages give the hours. Deprecated "
        "models follow the current ones. Delisted models, which models.dev or their provider's "
        "pricing page no longer lists, usually because they were retired, appear only on their "
        "provider's page. "
        "[Corrections](corrections/) lists every price that differs from models.dev, and why.\n\n"
        + price_filter("Model or provider") + "\n\n" + "\n".join(table_head(True) + [row for _, row in sorted(overview)]) + "\n")
    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "data" / "navigation.json").write_text(json.dumps({"groups": [
        {"id": "prices", "title": "Prices", "items": [
            {"title": "All models", "path": ""},
            {"title": "Calculator", "path": "calculator/"},
            {"title": "Plans", "path": "plans/"},
            {"title": "Benchmarks in plan dollars", "path": "benchmarks/"},
            {"title": "Corrections", "path": "corrections/"},
            {"title": "About the data", "path": "about/"}]},
        # The group heading links to the list of providers, so the count covers providers only.
        {"id": "providers", "title": "Providers", "path": "providers/", "items": navigation},
    ]}, indent=1) + "\n")
    (CONTENT / "corrections.md").write_text(corrections_page(pages))
    (CONTENT / "plans.md").write_text(plans_page(check_results, ran, now))
    (CONTENT / "benchmarks.md").write_text(benchmarks_page(data["plans"], now))
    shutil.copyfile(ROOT / "src" / "model_prices" / "snapshot.json", SITE / "static" / "snapshot.json")
    (SITE / "static" / "calculator-models.json").write_text(json.dumps(calculator))


def correction_note(note: str) -> str:
    """A correction's note as table text, with research findings linked."""
    note = escape(re.sub(r"\s+", " ", re.sub(r"^[a-z_]+: ", "", note.strip())))
    return re.sub(r"research/price-dates/findings/[A-Za-z0-9.\\_-]+",
                  lambda found: f"[{found.group(0)}]({REPOSITORY}/tree/main/{found.group(0).replace(chr(92), '')})",
                  note)


def corrections_page(pages: dict[tuple[str, str], str]) -> str:
    """Every correction to models.dev's prices, with its period, price, source, and reason."""
    data = ROOT / "data"
    items = [item for file in ("corrections.toml", "research_corrections.toml")
             for item in tomllib.loads((data / file).read_text())["correction"]]
    items.sort(key=lambda item: (name(item["provider"]).lower(), item["model"].lower(), item["valid_from"]))
    rows = ["| Model | Period | Corrected price | Source and reason |", "| --- | --- | --- | --- |"]
    for item in items:
        page = pages.get((item["provider"], item["model"]))
        label = f"{name(item['provider'])} {escape(item['model'])}"
        until = f"to {day(item['valid_until'])}" if "valid_until" in item else "until models.dev agrees"
        prices = ", ".join(f"{label_} {price(item[field])}" for field, label_ in FIELD_NAMES if field in item)
        if item.get("tiers"):
            prices += "; " + tiers(item)
        rows.append(" | ".join((
            f"| [{label}]({page})" if page else f"| {label}", f"{day(item['valid_from'])} {until}",
            prices, f"[{escape(source_name(item['source']))}]({item['source']}): "
            + correction_note(item.get("note", "")))) + " |")
    front = toml({"title": "Corrections", "description": "Where model-prices replaces models.dev's prices, and why.",
                  "extra": {"navigation_group": "prices", "toc": False}})
    return ("+++\n" + front + "+++\n\n"
            "model-prices takes prices from models.dev's history and replaces them where a provider's own "
            "documents show a different price or an earlier date. Each correction below gives the period it "
            "covers, the price it sets, and its source. A correction without an end date stops applying "
            "once models.dev records anything other than the price it replaced. Prices are in US dollars "
            "per million tokens. The corrections live in "
            f"[data/corrections.toml]({REPOSITORY}/blob/main/data/corrections.toml) and, for those "
            f"found by dating research, [data/research_corrections.toml]({REPOSITORY}/blob/main/data/research_corrections.toml).\n\n"
            + '<div class="wrapping">\n\n' + "\n".join(rows) + "\n\n</div>\n")


def plan_checks(path: Path | None) -> dict[str, str]:
    """Each plan's status in `model-prices check --json`, by "provider/id"."""
    if path is None:
        return {}
    return {result["model"]: result["status"] for result in json.loads(path.read_text())
            if result["field"] == "plan"}


def plans_page(check_results: Path | None, ran: str | None, now: datetime) -> str:
    """Every subscription plan's monthly price, by lab, with its check status, and the prices
    plans had before."""
    plans = tomllib.loads((ROOT / "data" / "plans.toml").read_text())["plan"]
    checked = plan_checks(check_results)

    def ended(plan: dict) -> bool:
        return "valid_until" in plan and model_prices._parse_time(plan["valid_until"]) <= now

    def started(plan: dict) -> bool:
        return "valid_from" not in plan or model_prices._parse_time(plan["valid_from"]) <= now

    def status(plan: dict) -> str:
        found = checked.get(f"{plan['provider']}/{plan['id']}")
        if found == "ok":
            return f"matches, {ran}"
        if found in {"mismatch", "error"}:
            return f"differs or unreadable, {ran}"
        if found == "unchecked" or "checked" in plan:
            return f"read by hand{', ' + day(plan['checked']) if 'checked' in plan else ''}"
        return ""

    lines = []
    for provider in sorted({plan["provider"] for plan in plans}, key=name):
        current = sorted((plan for plan in plans if plan["provider"] == provider
                          and started(plan) and not ended(plan)),
                         key=lambda plan: (plan["usd_per_month"], plan["name"]))
        if not current:
            continue
        lines += [f"## {name(provider)}", "", "| Plan | Per month | Since | Checked against the page | Plan id |",
                  "| --- | --- | --- | --- | --- |"]
        for plan in current:
            since = day(plan.get("valid_from")) or "tracking began"
            lines.append(f"| [{escape(plan['name'])}]({plan['source']}) | {price(plan['usd_per_month'])} | "
                         f"{since} | {status(plan)} | `{plan['id']}` |")
        lines.append("")
    earlier = sorted((plan for plan in plans if ended(plan)),
                     key=lambda plan: (name(plan["provider"]).lower(), plan["name"], plan["valid_until"]))
    if earlier:
        lines += ["## Earlier prices", "", "| Plan | Per month | Period | Plan id |", "| --- | --- | --- | --- |"]
        for plan in earlier:
            period = f"{day(plan.get('valid_from')) or 'tracking began'} to {day(plan['valid_until'])}"
            lines.append(f"| {name(plan['provider'])} [{escape(plan['name'])}]({plan['source']}) | "
                         f"{price(plan['usd_per_month'])} | {period} | `{plan['id']}` |")
        lines.append("")
    lines += quota_value(plans, now)
    front = toml({"title": "Subscription plans",
                  "description": "Monthly prices of the subscriptions each lab sells to individuals and teams.",
                  "extra": {"navigation_group": "prices", "toc": False}})
    return ("+++\n" + front + "+++\n\n"
            "The monthly price of every subscription plan each lab sells to individuals and teams, billed "
            "monthly, in US dollars, per seat for team plans. Each price is checked daily against the "
            "lab's pricing page, or the price feed the page loads; a plan whose page an automated "
            "check cannot read, such as one shown only after signing in or only in the reader's local "
            "currency, is checked by hand, on the date given. A change is dated by the lab's "
            "announcement, or by the first check that read the new price. Plans sold only in yuan, priced "
            "only by quote, or billed only annually are not listed. The plan id is the name the lab's "
            "usage tools report, which `model_prices.plan(provider, plan_id)` takes. The prices live in "
            f"[data/plans.toml]({REPOSITORY}/blob/main/data/plans.toml).\n\n" + "\n".join(lines))


def quota_value(plans: list[dict], now: datetime) -> list[str]:
    """What a plan's weekly quota is worth at API prices, from data/quota_rates.toml, with a
    converter from an API cost per task to plan dollars and tasks a week."""
    current = {(plan["provider"], plan["id"]): plan for plan in plans
               if "valid_until" not in plan or model_prices._parse_time(plan["valid_until"]) > now}
    rates = tomllib.loads((ROOT / "data" / "quota_rates.toml").read_text())["rate"]
    lines = ["## What a plan's quota is worth", "",
             "A subscription's weekly limit is a quota of percentage points, and each point is worth "
             "some amount of usage at API prices. The table gives that amount as measured on one "
             "user's accounts, with the date and method of each measurement in "
             f"[data/quota_rates.toml]({REPOSITORY}/blob/main/data/quota_rates.toml); the labs publish "
             "no such figures, and they vary with how a plan is used. A plan dollar buys a week's "
             "share of the monthly price, so API dollars per plan dollar is the API value of a full "
             "week divided by the plan's monthly price over 4.348 weeks. Enter a task's cost at API "
             "prices, such as a benchmark's cost per task, to see what it costs in plan dollars and "
             "how many such tasks fit in a week's limit.", "",
             '<label class="plan-value-cost">API cost per task, US dollars '
             '<input id="task-cost" type="number" min="0" step="0.01" value="1"></label>', "",
             "| Plan | Pool | Models | API $ per weekly point | API $ per plan $ | Plan $ per task | "
             "Tasks a week | Measured |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    measured = set()
    for rate in rates:
        plan = current.get((rate["provider"], rate["plan"]))
        if plan is None:
            continue
        measured.add((rate["provider"], rate["plan"]))
        point = plan["usd_per_month"] / 434.8
        lines.append(
            f'| {escape(plan["name"])} | {escape(rate["pool"])} | {escape(rate["models"])} | '
            f'${rate["usd_per_point"]:,.2f} | {rate["usd_per_point"] / point:,.1f} | '
            f'<span class="plan-task" data-rate="{rate["usd_per_point"]}" data-point="{point}"></span> | '
            f'<span class="plan-tasks" data-rate="{rate["usd_per_point"]}"></span> | {rate["measured"]} |')
    unmeasured = sorted({plan["name"] for key, plan in current.items() if key not in measured})
    lines += ["", f"Not yet measured: {', '.join(escape(name) for name in unmeasured)}.", "",
              '<script type="module" src="../plan-value.js"></script>', ""]
    return lines


# Lab colors as the FrontierCode leaderboard draws them.
LAB_COLORS = {"anthropic": "#FF5833", "google": "#D1A700", "openai": "#10B552", "meta": "#2050CF"}


def plan_rates(plans: list[dict], now: datetime) -> list[tuple[re.Pattern, dict, dict]]:
    """Each measured quota rate that names the benchmark models it prices, with its plan."""
    current = {(plan["provider"], plan["id"]): plan for plan in plans
               if "valid_until" not in plan or model_prices._parse_time(plan["valid_until"]) > now}
    rates = tomllib.loads((ROOT / "data" / "quota_rates.toml").read_text())["rate"]
    return [(re.compile(rate["match"]), rate, current[(rate["provider"], rate["plan"])])
            for rate in rates if "match" in rate and (rate["provider"], rate["plan"]) in current]


# Harnesses by the name a benchmark gives them, with their display name and chart marker.
HARNESSES = {"claude-code": ("Claude Code", "triangle"), "Claude Code": ("Claude Code", "triangle"),
             "antigravity-cli": ("Antigravity CLI", "star"), "Antigravity CLI": ("Antigravity CLI", "star"),
             "codex": ("Codex", "circle"), "devin-cli": ("Devin CLI", "square"), "Cursor": ("Cursor", "diamond"),
             "muse": ("Muse Code", "circle"), "proximus": ("proximus", "circle")}


def _version(model: str) -> tuple[str, tuple[int, ...]]:
    """A model's line and version, as ("GPT- Sol", (6, 2)) for GPT-6.2 Sol."""
    found = re.search(r"\d+(?:\.\d+)*", model)
    if found is None:
        return model, ()
    return model[:found.start()] + model[found.end():], tuple(int(part) for part in found.group().split("."))


def superseded(model: str, results: list[dict]) -> bool:
    """Whether any benchmark lists a newer version of the model's line, as GPT-6.2 Sol is of
    GPT-6.1 Sol."""
    line, version = _version(model)
    return any(other_line == line and other > version
               for other_line, other in (_version(item["model"]) for item in results))


# Usage multiples a lab's plan names state, against its smallest plan.
STATED_MULTIPLES = {("anthropic", "pro"): 1, ("anthropic", "max_5x"): 5, ("anthropic", "max_20x"): 20}
LAB_NAMES = {"anthropic": "Anthropic", "google": "Google", "openai": "OpenAI", "meta": "Meta"}


def plan_choices(plans: list[dict], measured: dict[str, str], now: datetime) -> list[dict]:
    """Each lab with a measured plan: its current plans, with their monthly price and usage
    multiple, a stated multiple where the plan's name gives one, otherwise one in proportion to
    price against the lab's cheapest plan."""
    labs = []
    for provider, plan_id in sorted(measured.items(), key=lambda item: LAB_NAMES.get(item[0], item[0])):
        current = sorted((plan for plan in plans if plan["provider"] == provider and (
            "valid_until" not in plan or model_prices._parse_time(plan["valid_until"]) > now)),
            key=lambda plan: plan["usd_per_month"])
        cheapest = current[0]["usd_per_month"]
        labs.append({"lab": provider, "name": LAB_NAMES.get(provider, provider), "measured": plan_id, "plans": [
            {"id": plan["id"], "name": plan["name"], "price": plan["usd_per_month"],
             "multiple": STATED_MULTIPLES.get((provider, plan["id"]), round(plan["usd_per_month"] / cheapest, 2)),
             "stated": (provider, plan["id"]) in STATED_MULTIPLES} for plan in current]})
    return labs


def benchmarks_page(plans: list[dict], now: datetime) -> str:
    """Each benchmark's results against their cost per task at API prices, and in plan dollars
    at the measured rate of the plan that runs the model."""
    data = tomllib.loads((ROOT / "data" / "benchmarks.toml").read_text())
    rates = plan_rates(plans, now)
    measured: dict[str, str] = {}
    sections = []
    for source in data["source"]:
        results, rows = [], []
        listed = [item for item in data["result"] if item["source"] == source["id"]]
        for result in (item for item in listed if not superseded(item["model"], data["result"])):
            found = next(((rate, owner) for pattern, rate, owner in rates if pattern.match(result["model"])), None)
            if found is None:
                continue
            rate, owner = found
            per_plan = result["cost"] / rate["usd_per_point"] * owner["usd_per_month"] / 434.8
            label = f'{result["model"]} {result["effort"]}'.strip()
            color = LAB_COLORS.get(rate["provider"], "#777")
            harness = HARNESSES.get(result["harness"], (result["harness"], "circle"))[0]
            results.append({"model": result["model"], "effort": result["effort"], "harness": harness,
                            "score": result["score"], "api": result["cost"], "plan": round(per_plan, 6),
                            "tokens": result.get("tokens"), "color": color, "lab": rate["provider"],
                            "rate": rate["usd_per_point"]})
            measured[rate["provider"]] = owner["id"]
            rows.append(f'| {escape(label)} | {result["score"]:g} | ${result["cost"]:,.2f} | {escape(owner["name"])}, '
                        f'{escape(rate["pool"])} | ${per_plan:,.3f} | {math.floor(100 * rate["usd_per_point"] / result["cost"]):,} |')
        if not results:
            continue
        sections += [f'## {escape(source["name"])}', "",
                     f'[{escape(source["name"])}]({source["url"]}), read {source["retrieved"]}: {escape(source["note"])}', "",
                     '<div class="bench"><script type="application/json">' + json.dumps({
                         "name": source["name"], "results": results,
                         "harnesses": {name: shape for name, shape in HARNESSES.values()
                                       if any(item["harness"] == name for item in results)},
                     }).replace("</", "<\\/") + "</script><noscript>The chart needs JavaScript; the table below "
                     "lists every result.</noscript></div>", "",
                     # The table of every result starts folded under the chart.
                     f"<details><summary>All {len(rows)} results</summary>", "",
                     "| Model and effort | Score | API $ per task | Plan and pool | Plan $ per task | Tasks a week |",
                     "| --- | --- | --- | --- | --- | --- |", *rows, "", "</details>", ""]
    settings = '<div class="bench-plans"><script type="application/json">' + json.dumps(
        plan_choices(plans, measured, now)).replace("</", "<\\/") + "</script></div>"
    front = toml({"title": "Benchmarks in plan dollars",
                  "description": "Benchmark scores against cost per task at API prices and in subscription plan dollars.",
                  "extra": {"navigation_group": "prices", "toc": False}})
    return ("+++\n" + front + "+++\n\n"
            "Benchmarks report what a task costs at API prices. Run on a subscription, the same task "
            "costs a share of the plan's weekly limit instead, and plans value their quota very "
            "differently, so the ranking by cost can change. Each chart below plots score against a "
            "cost you choose: the published cost per task in API dollars, or what the task costs in "
            "plan dollars, at the measured rate of the plan that runs the model, or output tokens "
            "where a benchmark gives them. A line joins each model's effort levels, the marker shows "
            "the harness it ran in, and each model is named at its best score. A cost in plan "
            "dollars is the API cost divided by the API "
            "dollars a weekly quota point buys, times the plan's price per point (its monthly price "
            "over 434.8). Tasks a week is how many such tasks a full week's limit holds. The rates "
            "are measurements of one user's accounts, dated on the [Plans](../plans/) page, where a "
            "converter takes any cost per task; only models whose plan rate has been measured are "
            "shown, a model superseded by a newer version of its line that any benchmark here "
            "lists, such as GPT-6.1 Sol by GPT-6.2 Sol, is left out, and a folded table under each "
            "chart lists the rest. A benchmark run in another harness, such as Cursor, is priced as if run in the "
            "lab's own. Artificial Analysis's figures are quoted, with attribution, from the text of "
            "its public post; the other benchmarks publish their cost per task openly.\n\n"
            "Choose each lab's plan below. A plan's usage multiple is the size of its weekly limit "
            "against the lab's other plans: Anthropic's plan names state theirs, as Max 5x and 20x "
            "Pro, and any other plan starts in proportion to its price, so you can change it. A "
            "plan's rate is the measured plan's rate times the ratio of their multiples, so a plan "
            "whose multiple grows faster than its price gives more per dollar. The folded tables "
            "keep the measured plans.\n\n" + settings + "\n\n"
            + "\n".join(sections) + '\n<script type="module" src="../bench-chart.js"></script>\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-results", type=Path,
                        help="Output of `model-prices check --json` for official-page status")
    build(parser.parse_args().check_results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
