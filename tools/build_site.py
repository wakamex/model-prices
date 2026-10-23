"""Write the website's generated content from the bundled price snapshot.

    uv run --locked python tools/build_site.py [--check-results CHECK_JSON]
    zola --root site build

Writes the overview table, one section per provider, one page per model, the navigation,
and the calculator's data under site/. These paths are generated and not committed; the
calculator, the about page, and the templates are. CHECK_JSON is the output of
`model-prices check --json`, which adds each model's official-page status.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlencode, urlparse
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import model_prices  # noqa: E402
from model_prices import checks, observe  # noqa: E402

SITE = ROOT / "site"
CONTENT = SITE / "content"
GENERATED = (CONTENT / "_index.md", CONTENT / "providers", SITE / "data" / "navigation.json",
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
              "flex": "Flex", "thinking": "Thinking mode"}
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
    text = f"{value:.10f}".rstrip("0")
    whole, _, fraction = text.partition(".")
    return f"${whole}.{fraction.ljust(2, '0')}"


def day(value: str | None) -> str:
    return value[:10] if value else ""


def tiers(rates: dict) -> str:
    return "; ".join(
        f"above {tier['above'] // 1000:,}K: " + ", ".join(
            f"{label} {price(tier[field])}" for field, label in (
                ("input", "in"), ("cache_read", "cached"), ("cache_write", "write"),
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
        if "/" in result["model"] and result["status"] in STATUS_TEXT:
            found.setdefault(result["model"], set()).add(result["status"])
    ran = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return found, ran


def official_page(provider: str) -> str | None:
    """The provider's pricing page for readers: the check reads Markdown copies, and
    Volcengine's document through the API its page loads."""
    url = checks.SOURCES.get(provider, (None,))[0]
    if url is None:
        return None
    if provider == "volcengine":
        return "https://www.volcengine.com/docs/82379/1544106"
    return re.sub(r"(index)?\.md(\.txt)?$", "", url)


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


PRICE_KEYS = ("input", "output", "cache_read", "cache_write", "tiers", "cache_write_1h_multiple")


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
    """The first price's date: it also applies to every earlier request."""
    rates = timeline[0]["rates"] or {}
    first = day(rates.get("valid_from"))
    following = day(timeline[1]["start"]) if len(timeline) > 1 else None
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


FIELD_NAMES = (("input", "input"), ("cache_read", "cached input"), ("cache_write", "cache write"),
               ("output", "output"))


def dated_by(interval: dict) -> str:
    """How the row's start date is known, linked to its source, and the models.dev price a
    correction replaces."""
    rates = interval["rates"]
    basis = rates.get("valid_from_basis", "")
    url = rates.get("source")
    label = "models.dev commit" if basis == "models.dev commit" else f"{basis}, {source_name(url or '')}"
    cell = f"[{escape(label)}]({url})" if url else escape(basis)
    recorded = interval.get("recorded") or {}
    replaced = [f"{label} {price(recorded.get(field))}" for field, label in FIELD_NAMES
                if field in recorded and recorded.get(field) != rates.get(field)]
    if recorded and recorded.get("tiers") != rates.get("tiers"):
        replaced.append(f"longer prompts {escape(tiers(recorded))}" if recorded.get("tiers")
                        else "no longer-prompt prices")
    return cell + (f"; models.dev lists {', '.join(replaced)}" if replaced else "")


def history(timeline: list[dict]) -> list[str]:
    lines = ["| From | Input | Cached input | Cache write | Output | Longer prompts | Dated by |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    timeline = changes(timeline)
    for interval in reversed(timeline):
        rates = interval["rates"]
        start = day(interval["start"]) or first_start(timeline)
        if rates is None:
            lines.append(f"| {start} | not sold |  |  |  |  |  |")
            continue
        lines.append(" | ".join((
            f"| {start}", price(rates["input"]), price(rates.get("cache_read")),
            price(rates.get("cache_write")), price(rates["output"]), tiers(rates),
            dated_by(interval))) + " |")
    return lines


def model_page(provider: str, model: str, timelines: dict, found: dict, ran: str | None,
               now: datetime) -> str:
    standard = timelines.get("standard", [])
    latest = current(standard, now) if standard else None
    rates = latest["rates"] if latest else None
    front = {
        "title": model,
        "description": f"{model} API prices from {name(provider)}, with dated price history.",
        "extra": {
            "breadcrumbs": [{"title": "Providers", "path": "providers/"},
                            {"title": name(provider), "path": f"providers/{slug(provider)}/"}],
            "navigation_group": "providers",
            "navigation_branch": f"providers/{slug(provider)}/",
            "page_navigation": False,
            "toc": len(timelines) > 1,
        },
    }
    intro = [f"{name(provider)} model `{model}`. Prices are in US dollars per million tokens."]
    if rates:
        intro[0] += " " + (
            f"Current price, since {day(latest['start']) or first_start(changes(standard))}: "
            f"input {price(rates['input'])}, output {price(rates['output'])}"
            + (f", cached input {price(rates['cache_read'])}" if rates.get("cache_read") is not None else "")
            + (f", cache write {price(rates['cache_write'])}" if rates.get("cache_write") is not None else "")
            + ".")
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
             "change by days; documented by the provider; or first observed on the provider's "
             "pricing page by the daily check. The first price also applies to every earlier "
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
        price(rates["input"]), price(rates.get("cache_read")), price(rates.get("cache_write")),
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
    for path in GENERATED:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    providers = CONTENT / "providers"
    providers.mkdir(parents=True)
    overview, calculator, navigation = [], [], []
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
            (section / f"{page}.md").write_text(model_page(provider, model, timelines, found, ran, now))
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
                rows.append(price_row(None, model, latest["rates"], start, f"{page}/", note))
                overview.append(price_row(provider, model, latest["rates"], start,
                                          f"providers/{slug(provider)}/{page}/", note))
        page_url = official_page(provider)
        observed = provider in observe.SOURCES
        intro = (f"model-prices checks these prices daily against [{name(provider)}'s pricing page]({page_url})."
                 if page_url else
                 f"model-prices reads these prices from {name(provider)}'s own pages daily." if observed else
                 f"These prices come from [models.dev](https://models.dev); {name(provider)} has no "
                 "official pricing page that model-prices checks.")
        (section / "_index.md").write_text(
            "+++\n" + toml({"title": name(provider), "sort_by": "title", "template": "provider.html",
                            "description": f"{name(provider)} API prices with dated price history.",
                            "extra": {"breadcrumbs": [{"title": "Providers", "path": "providers/"}],
                                      "navigation_group": "providers",
                                      "navigation_branch": f"providers/{slug(provider)}/"}})
            + "+++\n\n" + intro + " Prices are in US dollars per million tokens.\n\n"
            + price_filter("Model") + "\n\n" + "\n".join(table_head(False) + rows) + "\n")
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
        "+++\n" + toml({"title": "LLM API prices with dated history", "template": "prices.html",
                        "description": "Current and historical API prices for LLMs, checked against "
                                       "each provider's own pricing page."})
        + "+++\n\n"
        "What each LLM API cost on any date: every model's page lists each past price with when it "
        "took effect, how that date is known, and its source. Prices come from the history of "
        "[models.dev](https://models.dev), corrected where a provider's own pricing page differs, "
        "and are checked against those pages daily. Price past usage at the rates in effect when it "
        "ran with the [calculator](calculator/), or in Python with `pip install model-prices`.\n\n"
        f"Current prices for {len(overview)} models from {len(data['prices'])} providers, in US "
        "dollars per million tokens, as of "
        f"{data['updated_at'][:10]}. A blank cache price is charged at the input price. Longer "
        "prompts gives the prompt size above which a model costs more. A Since date ending in "
        "\"or earlier\" is when tracking began. Models marked off-peak cost more at peak hours, and "
        "those marked time of day cost less off-peak; their pages give the hours.\n\n"
        + price_filter("Model or provider") + "\n\n" + "\n".join(table_head(True) + sorted(overview, key=str.lower)) + "\n")
    (SITE / "data").mkdir(exist_ok=True)
    (SITE / "data" / "navigation.json").write_text(json.dumps({"groups": [
        {"id": "prices", "title": "Prices", "items": [
            {"title": "All models", "path": ""},
            {"title": "Calculator", "path": "calculator/"},
            {"title": "About the data", "path": "about/"}]},
        # The group heading links to the list of providers, so the count covers providers only.
        {"id": "providers", "title": "Providers", "path": "providers/", "items": navigation},
    ]}, indent=1) + "\n")
    shutil.copyfile(ROOT / "src" / "model_prices" / "snapshot.json", SITE / "static" / "snapshot.json")
    (SITE / "static" / "calculator-models.json").write_text(json.dumps(calculator))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check-results", type=Path,
                        help="Output of `model-prices check --json` for official-page status")
    build(parser.parse_args().check_results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
