"""Compare effective prices with each provider's official pricing page.

Each parser reads a fixed page format without heuristics beyond its own table layout, so
a changed page fails loudly instead of producing a guessed price.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import html
import re
from typing import Callable, Iterable
import urllib.request

from llm_prices import _config, _period, _schedule, rates, resolve

FIELDS = ("input", "cache_write", "cache_read", "output")


@dataclass(frozen=True)
class Observed:
    """One price stated by an official page, in USD per million tokens."""

    provider: str
    model: str
    field: str
    value: float
    above: int | None = None
    at: str | None = None


@dataclass(frozen=True)
class Result:
    provider: str
    model: str
    field: str
    above: int | None
    at: str | None
    official: float | str
    effective: float | str | None
    models_dev: float | None
    status: str


def _price(cell: str) -> float | None:
    cell = cell.replace("\\$", "$")
    if cell.strip().lower() == "free":
        return 0.0
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", cell)
    return float(match.group(1)) if match else None


def _markdown_tables(text: str) -> Iterable[tuple[dict[int, str], list[str], list[list[str]]]]:
    """Yield (enclosing headings by level, header cells, rows) for each Markdown table."""
    headings: dict[int, str] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        heading = re.match(r"(#+)\s+(.*)", line)
        if heading:
            level = len(heading.group(1))
            headings = {key: value for key, value in headings.items() if key < level}
            headings[level] = heading.group(2).strip()
        if line.startswith("|") and index + 1 < len(lines) and re.fullmatch(
            r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?", lines[index + 1].strip()
        ):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            rows = []
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            yield dict(headings), header, rows
            continue
        index += 1


def parse_anthropic(text: str, today: datetime) -> list[Observed]:
    columns = {"Base input tokens": "input", "5m cache writes": "cache_write",
               "Cache hits and refreshes": "cache_read", "Output tokens": "output"}
    found = []
    for _, header, rows in _markdown_tables(text):
        if header[:2] != ["Model", "Base input tokens"]:
            continue
        for row in rows:
            name = re.sub(r"\s*\(.*\)", "", row[0]).strip()
            model = "-".join(name.lower().replace(".", " ").split())
            for title, field in columns.items():
                value = _price(row[header.index(title)])
                if value is not None:
                    found.append(Observed("anthropic", model, field, value))
        break
    return found


def parse_openai(text: str, today: datetime) -> list[Observed]:
    found = []
    for headings, header, rows in _markdown_tables(text):
        if headings.get(3) != "Standard pricing data":
            continue
        for row in rows:
            model = re.sub(r"\s*\(.*\)", "", row[0]).strip()
            for title, value_text in zip(header[1:], row[1:]):
                value = _price(value_text)
                if value is None:
                    continue
                span, _, kind = title.partition(" context ")
                field = {"input": "input", "cached input": "cache_read",
                         "cache writes": "cache_write", "output": "output"}[kind]
                found.append(Observed("openai", model, field, value,
                                      above=272_000 if span == "Long" else None))
        break
    return found


def parse_zai(text: str, today: datetime) -> list[Observed]:
    columns = {"Input": "input", "Cached Input": "cache_read", "Output": "output"}
    found = []
    for headings, header, rows in _markdown_tables(text):
        if headings.get(3) not in {"Latest Models", "Text Models"} or header[0] != "Model":
            continue
        for row in rows:
            for title, field in columns.items():
                value = _price(row[header.index(title)])
                if value is not None:
                    found.append(Observed("zai", row[0], field, value))
    return found


_GOOGLE_DATE = r"([A-Z][a-z]+ [0-9]{1,2}, [0-9]{4})"


def _google_price(cell: str, today: datetime) -> list[tuple[float, int | None]]:
    """Return (price, tier size) pairs for text tokens in effect today from a Paid Tier cell.

    Each dollar amount is read with the qualifier text that follows it: a date range,
    a modality list such as "(text / image)", or a prompt-size tier such as "prompts > 200k".
    """
    cell = cell.replace("\\<", "<").replace("\\>", ">")
    prices = []
    for amount, qualifier in re.findall(r"\$([0-9]+(?:\.[0-9]+)?)([^$]*)", cell):
        if "per hour" in qualifier:
            continue
        until = re.search(r"through " + _GOOGLE_DATE, qualifier)
        start = re.search(r"starting " + _GOOGLE_DATE, qualifier)
        if until and today.date() > datetime.strptime(until.group(1), "%B %d, %Y").date():
            continue
        if start and today.date() < datetime.strptime(start.group(1), "%B %d, %Y").date():
            continue
        modalities = re.search(r"\(([a-z /]+)\)", qualifier)
        if modalities and "text" not in modalities.group(1).split(" / "):
            continue
        above = re.search(r"prompts\s*>\s*([0-9]+)k", qualifier)
        prices.append((float(amount), int(above.group(1)) * 1000 if above else None))
    return prices


def parse_google(text: str, today: datetime) -> list[Observed]:
    rows = {"Input price": "input", "Output price": "output", "Context caching price": "cache_read"}
    found = []
    for headings, header, table in _markdown_tables(text):
        model = headings.get(2, "")
        if (not model.startswith("Gemini") or headings.get(3) != "Standard"
                or header[-1] != "Paid Tier, per 1M tokens in USD"):
            continue
        for row in table:
            field = next((value for key, value in rows.items() if row[0].startswith(key)), None)
            if field is None:
                continue
            for value, above in _google_price(row[-1], today):
                found.append(Observed("google", model, field, value, above=above))
    return found


def _html_text(page: str) -> str:
    page = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " | ", page)).replace("\u200b", "")
    return re.sub(r"(\s*\|\s*)+", " | ", re.sub(r"\s+", " ", text))


def _moments(provider: str, today: datetime) -> dict[str, str]:
    """The first upcoming hours that the provider's schedule treats as peak and off-peak."""
    found: dict[str, str] = {}
    moment = today.replace(minute=0, second=0, microsecond=0)
    for _ in range(24 * 60):
        moment += timedelta(hours=1)
        period = _period(provider, moment)
        label = {"peak": "PEAK", "off_peak": "OFF-PEAK"}.get(period[0] if period else "")
        if label and label not in found:
            found[label] = moment.isoformat().replace("+00:00", "Z")
        if len(found) == 2:
            return found
    raise ValueError(f"{provider}: no upcoming peak and off-peak hours in the schedule")


def parse_deepseek(page: str, today: datetime) -> list[Observed]:
    text = _html_text(page)
    names = re.search(r"\| MODEL \|(.*?)\| BASE URL", text)
    pricing = re.search(r"\| PRICING \|(.*?)\| Concurrency Limit", text)
    if not names or not pricing:
        return []
    models = [cell.strip() for cell in names.group(1).split("|")
              if re.fullmatch(r"deepseek-[a-z0-9.-]+", cell.strip())]
    moments = _moments("deepseek", today)
    found = []
    pattern = (r"1M (INPUT|OUTPUT) TOKENS \|(?: \((CACHE HIT|CACHE MISS)\) \|)?"
               r" (OFF-PEAK) \|((?: \$[0-9.]+ \|)+) (PEAK) \|((?: \$[0-9.]+ \|)+)")
    for match in re.finditer(pattern, pricing.group(1).strip() + " |"):
        kind, cache = match.group(1), match.group(2)
        field = {"CACHE HIT": "cache_read", "CACHE MISS": "input"}.get(cache, "output")
        for period, values in ((match.group(3), match.group(4)), (match.group(5), match.group(6))):
            prices = [float(value) for value in re.findall(r"\$([0-9.]+)", values)]
            for model, value in zip(models, prices):
                found.append(Observed("deepseek", model, field, value, at=moments[period]))
    return found


# Pages that state time-of-day pricing terms, each compared verbatim with the wording in
# schedules.toml: {provider: {language: (url, pattern matching the terms)}}.
TERMS: dict[str, dict[str, tuple[str, str]]] = {
    "deepseek": {
        "en": ("https://api-docs.deepseek.com/quick_start/pricing",
               r"Off-peak rates are half of the peak rates\. Peak hours are .*? in full\."),
        "zh": ("https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
               r"空闲时段价格为高峰时段价格的一半。.*?空闲时段。"),
    },
}


def compare_terms(provider: str, language: str, page: str, today: datetime) -> Result:
    """Check that a page states the same peak-hour terms that schedules.toml records."""
    url, pattern = TERMS[provider][language]
    match = re.search(pattern, _html_text(page))
    if match is None:
        raise ValueError(f"{provider}: no peak-hour terms found in {url}; the page format changed")
    schedule = _schedule(provider, today)
    expected = (schedule or {}).get("terms", {}).get(language)
    return Result(provider, provider, f"peak_terms:{language}", None, None, match.group(0),
                  expected, None, "ok" if match.group(0) == expected else "mismatch")


CALENDAR_WARNING_DAYS = 45


def check_calendars(providers: set[str], today: datetime) -> list[Result]:
    """Fail when a schedule's holiday calendar ends within CALENDAR_WARNING_DAYS."""
    config = _config("schedules.toml")
    results = []
    for name in sorted({schedule["holidays"] for schedule in config.get("schedule", [])
                        if schedule["provider"] in providers and "holidays" in schedule}):
        ends = datetime.fromisoformat(config["holidays"][name]["covers_through"]).date()
        remaining = (ends - today.date()).days
        status = "ok" if remaining > CALENDAR_WARNING_DAYS else "mismatch"
        results.append(Result("holidays", name, "holiday_calendar", None, None,
                              f"covers through {ends}", f"{remaining} days left", None, status))
    return results


SOURCES: dict[str, tuple[str, Callable[[str, datetime], list[Observed]]]] = {
    "anthropic": ("https://platform.claude.com/docs/en/about-claude/pricing.md", parse_anthropic),
    "deepseek": ("https://api-docs.deepseek.com/quick_start/pricing", parse_deepseek),
    "google": ("https://ai.google.dev/gemini-api/docs/pricing.md.txt", parse_google),
    "openai": ("https://developers.openai.com/api/docs/pricing.md", parse_openai),
    "zai": ("https://docs.z.ai/guides/overview/pricing.md", parse_zai),
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "llm-prices"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode()


def _value(found, field: str, above: int | None) -> float | None:
    if found is None:
        return None
    values = {"input": found.input, "output": found.output,
              "cache_read": found.cache_read, "cache_write": found.cache_write}
    if above is not None:
        tier = next((tier for tier in found.tiers if tier.above == above), None)
        if tier is None:
            return None
        values = {key: getattr(tier, key) if getattr(tier, key) is not None else values[key]
                  for key in values}
    # Missing cache prices are charged at the input price.
    if values[field] is None and field in {"cache_read", "cache_write"}:
        return values["input"]
    return values[field]


def compare(observed: Iterable[Observed], today: datetime) -> list[Result]:
    """Classify each official price against llm-prices and against models.dev alone."""
    results = []
    for item in observed:
        at = item.at or today.isoformat()
        # Official names must match exactly: a fuzzy match such as gpt-3.5-turbo-1106 to
        # gpt-3.5-turbo would compare different models.
        resolved = resolve(item.model, item.provider, strict=True)
        name = "/".join(resolved) if resolved else item.model
        effective = rates(name, at=at, provider=item.provider) if resolved else None
        raw = rates(name, at=at, provider=item.provider, corrected=False) if resolved else None
        effective_value = _value(effective, item.field, item.above)
        raw_value = _value(raw, item.field, item.above)
        if effective is None:
            status = "untracked"
        elif effective_value is not None and abs(effective_value - item.value) < 1e-9:
            status = "ok" if raw_value is not None and abs(raw_value - item.value) < 1e-9 else "corrected"
        else:
            status = "mismatch"
        model = f"{effective.provider}/{effective.model}" if effective else item.model
        results.append(Result(item.provider, model, item.field, item.above, item.at,
                              item.value, effective_value, raw_value, status))
    return results


def run(providers: Iterable[str] | None = None, today: datetime | None = None,
        pages: dict[str, str] | None = None) -> list[Result]:
    moment = today or datetime.now(timezone.utc)
    results = []
    for provider in providers or SOURCES:
        url, parser = SOURCES[provider]
        page = pages[provider] if pages and provider in pages else fetch(url)
        observed = parser(page, moment)
        if not observed:
            raise ValueError(f"{provider}: no prices parsed from {url}; the page format changed")
        results.extend(compare(observed, moment))
        for language, (terms_url, _) in TERMS.get(provider, {}).items():
            key = f"{provider}:{language}"
            if terms_url == url:
                terms_page = page
            else:
                terms_page = pages[key] if pages and key in pages else fetch(terms_url)
            results.append(compare_terms(provider, language, terms_page, moment))
    results.extend(check_calendars(set(providers or SOURCES), moment))
    return results


def report(results: list[Result]) -> str:
    lines = []
    for result in results:
        if result.status in {"ok", "untracked"}:
            continue
        if result.field == "holiday_calendar":
            lines.append(f"{result.status:9} {result.model} holiday calendar {result.official}, "
                         f"{result.effective}; add the next year's holidays to schedules.toml")
            continue
        if result.field.startswith("peak_terms:"):
            language = result.field.partition(":")[2]
            lines.append(f"{result.status:9} {result.provider} peak-hour terms ({language}): "
                         f"official {result.official!r}, schedules.toml {result.effective!r}")
            continue
        tier = f" above {result.above:,}" if result.above else ""
        when = f" at {result.at}" if result.at else ""
        lines.append(
            f"{result.status:9} {result.model} {result.field}{tier}{when}: "
            f"official ${result.official:g}, llm-prices {result.effective}, "
            f"models.dev {result.models_dev}"
        )
    counts = {status: sum(r.status == status for r in results)
              for status in ("ok", "corrected", "mismatch", "untracked")}
    lines.append(", ".join(f"{count} {status}" for status, count in counts.items()))
    return "\n".join(lines)


def as_json(results: list[Result]) -> list[dict]:
    return [asdict(result) for result in results]
