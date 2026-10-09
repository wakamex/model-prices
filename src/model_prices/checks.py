"""Compare effective prices with each provider's official pricing page.

Each parser reads a fixed page format without heuristics beyond its own table layout, so
a changed page fails loudly instead of producing a guessed price.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import gzip
import html
import inspect
import json
import re
from typing import Callable, Iterable
import urllib.request

from model_prices import (_data, _ids, _parse_time, _period, _schedule, genai_prices, rates,
                          resolve)

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
    mode: str | None = None
    # The official price in yuan, when value is its conversion to dollars.
    yuan: float | None = None


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
    genai_prices: float | None = None
    yuan: float | None = None


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
               "1h cache writes": "cache_write_1h",
               "Cache hits and refreshes": "cache_read", "Output tokens": "output"}
    found = []
    for _, header, rows in _markdown_tables(text):
        if header[:2] != ["Model", "Base input tokens"]:
            continue
        for row in rows:
            name = re.sub(r"\s*\(.*\)", "", row[0]).strip()
            model = "-".join(name.lower().replace(".", " ").split())
            # Prices for long prompts: "(for prompts over 100,000 tokens)".
            tier = re.search(r"\(for prompts over ([0-9,]+) tokens\)", row[0])
            for title, field in columns.items():
                value = _price(row[header.index(title)])
                if value is not None:
                    found.append(Observed("anthropic", model, field, value,
                                          above=int(tier.group(1).replace(",", "")) if tier else None))
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


def parse_xai(text: str, today: datetime) -> list[Observed]:
    columns = {"Input / 1M tokens": "input", "Cached input / 1M tokens": "cache_read",
               "Output / 1M tokens": "output"}
    found = []
    for headings, header, rows in _markdown_tables(text):
        if headings.get(3) != "Text API Pricing" or header[0] != "Model":
            continue
        for row in rows:
            model = re.sub(r"\s*\(.*\)", "", row[0]).strip()
            tier = re.search(r"≥\s*([0-9]+)k prompt tokens", row[0])
            for title, field in columns.items():
                value = _price(row[header.index(title)])
                if value is not None:
                    found.append(Observed("xai", model, field, value,
                                          above=int(tier.group(1)) * 1000 if tier else None))
    return found


def parse_moonshot(text: str, today: datetime) -> list[Observed]:
    columns = {"Input Price": "input", "Input Price (Cache Miss)": "input",
               "Cached Input Price": "cache_read", "Input Price (Cache Hit)": "cache_read",
               "Cache Write Price (TTL 5min)": "cache_write",
               "Cache Write Price (TTL 1h)": "cache_write_1h", "Output Price": "output"}
    found = []
    # Each table is a <DocTable columns={[{ title: ... }]} rows={[[...], ...]} /> component,
    # with prices written as <>{"$"}3.00</>.
    for table in re.finditer(r"<DocTable\s+columns=\{\[(.*?)\]\}\s+rows=\{\[(.*?)\]\}\s*/>",
                             text, re.S):
        titles = re.findall(r'title:\s*"([^"]*)"', table.group(1))
        for row in re.findall(r"^\s*\[(.*)\],?\s*$", table.group(2), re.M):
            cells = [cell.replace('{"$"}', "$") for cell in
                     re.findall(r'<>(.*?)</>|"((?:[^"\\]|\\.)*)"', row)
                     for cell in (cell[0] or cell[1],)]
            if len(cells) != len(titles) or titles[0] != "Model":
                continue
            for title, cell in zip(titles, cells):
                value = _price(cell) if title in columns else None
                if value is not None:
                    found.append(Observed("moonshotai", cells[0], columns[title], value))
    return found


def _mdx_cell(cell: str) -> str:
    text = re.sub(r"<[^>]+>", " ", cell.replace("\\", ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _mdx_grid(table: str) -> tuple[list[list[str]], list[list[str]]]:
    """Header rows and body rows of an HTML or MDX <table>, each cell repeated across the
    rows and columns it spans."""
    grids: list[list[list[str]]] = []
    for section in ("thead", "tbody"):
        part = re.search(rf"<{section}[^>]*>(.*?)</{section}>", table, re.S)
        rows: list[list[str]] = []
        spanning: dict[int, tuple[str, int]] = {}
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", part.group(1) if part else "", re.S):
            cells = iter(re.findall(r"<t[hd]([^>]*)>(.*?)</t[hd]>", row, re.S))
            line: list[str] = []
            while True:
                while len(line) in spanning:
                    value, left = spanning.pop(len(line))
                    if left > 1:
                        spanning[len(line)] = (value, left - 1)
                    line.append(value)
                cell = next(cells, None)
                if cell is None:
                    break
                attributes, body = cell
                down, across = (int(next(filter(None, found.groups())) if found else 1)
                                for found in (re.search(rf'{name}=(?:\{{(\d+)\}}|"(\d+)")',
                                                        attributes, re.I)
                                              for name in ("rowspan", "colspan")))
                for _ in range(across):
                    if down > 1:
                        spanning[len(line)] = (_mdx_cell(body), down - 1)
                    line.append(_mdx_cell(body))
            rows.append(line)
        grids.append(rows)
    return grids[0], grids[1]


def _alibaba_tier(cell: str) -> int | None:
    """The tier a row's "Input tokens per request" cell starts above: "32K<Token≤128K" and
    "32K" start above 32,000; "0<Token≤1M", "0", and untiered rows are the base price."""
    match = re.match(r"([0-9]+)\s*([KM]?)", cell)
    if not match or match.group(1) == "0":
        return None
    return int(match.group(1)) * {"": 1, "K": 1_000, "M": 1_000_000}[match.group(2)]


def parse_alibaba(text: str, today: datetime) -> list[Observed]:
    """Read text-generation prices for the Singapore (international) deployment, which
    models.dev's Alibaba provider uses.

    A table that splits input prices by modality is skipped, as is a cell that prices busy
    and idle hours separately. Output is the non-thinking price, or for a thinking-only
    model its thinking price; a hybrid model's thinking price is its `thinking` mode output.
    A limited-time discount gives the price charged while it lasts.
    """
    found = []
    heading = tab = ""
    for match in re.finditer(r'^(##) ([^\n]*)$|<Tab title="([^"]*)"|<table.*?</table>',
                             text, re.M | re.S):
        if match.group(1):
            heading, tab = match.group(2), ""
            continue
        if match.group(3) is not None:
            tab = match.group(3)
            continue
        if not heading.startswith("Text generation") or tab != "Singapore":
            continue
        header, rows = _mdx_grid(match.group(0))
        if not header or header[0][0] != "Model ID":
            continue
        titles = header[0]
        detail = header[1] if len(header) > 1 else titles
        inputs = [index for index, title in enumerate(titles) if title.startswith("Input price")]
        outputs = [index for index, title in enumerate(titles) if title.startswith("Output price")]
        if len(inputs) != 1 or not outputs or (len(outputs) > 1 and not all(
                "Thinking mode" in detail[index] for index in outputs)):
            continue
        tiers = titles.index("Input tokens per request") if (
            "Input tokens per request" in titles) else None
        for row in rows:
            model = row[0].split()[0]
            above = _alibaba_tier(row[tiers]) if tiers is not None else None
            prices = {("input", None): row[inputs[0]],
                      ("output", None): next((row[index] for index in outputs
                                              if _price(row[index]) is not None), "")}
            thinking = [index for index in outputs if detail[index].startswith("Thinking mode")]
            if len(outputs) == 2 and len(thinking) == 1:
                prices["output", "thinking"] = row[thinking[0]]
            for (field, mode), cell in prices.items():
                value = None if "Busy hours" in cell else _price(cell)
                # A list price "(Limited-time 20% off)" is charged at the discount; a
                # night and daytime discount depends on the hour and is not modeled.
                discount = re.search(r"Limited-time (\d+)% off", cell)
                if "night" in cell.lower():
                    value = None
                elif value is not None and discount:
                    value = round(value * (100 - int(discount.group(1))) / 100, 6)
                if value is not None:
                    found.append(Observed("alibaba", model, field, value, above=above,
                                          mode=mode))
    return found


def parse_minimax(text: str, today: datetime) -> list[Observed]:
    """Read MiniMax's pay-as-you-go text model prices. The Priority tab prices a faster
    service tier, which model-prices does not model, so it is skipped. A struck-out price
    is the list price before a discount; the price after it is charged."""
    columns = {"Input": "input", "Output": "output", "Prompt caching Read": "cache_read",
               "Prompt caching Write": "cache_write"}
    text = re.sub(r'<Tab title="Priority[^"]*">.*?</Tab>', "", text, flags=re.S)
    found = []
    for _, header, rows in _markdown_tables(text):
        if header[:2] != ["Model", "Input"]:
            continue
        for row in rows:
            name = re.match(r"\*\*([^*]+)\*\*(.*)", row[0])
            if name is None:
                continue
            tier = re.search(r">\s*([0-9]+)k input tokens", name.group(2))
            for title, field in columns.items():
                if title not in header:
                    continue
                amounts = re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", row[header.index(title)].replace("\\$", "$"))
                if amounts:
                    found.append(Observed("minimax", name.group(1), field, float(amounts[-1]),
                                          above=int(tier.group(1)) * 1000 if tier else None))
    return found


def parse_perplexity(text: str, today: datetime) -> list[Observed]:
    """Read Sonar token prices from the price data Perplexity's pricing page embeds. Its
    per-request search fees and Deep Research's citation and reasoning token prices are
    not modeled."""
    models = re.search(r'"sonar":\s*\{\s*"models":\s*(\[.*?\])\s*\}', text, re.S)
    if models is None:
        return []
    return [Observed("perplexity", model["id"], field, float(model[field]))
            for model in json.loads(models.group(1)) for field in ("input", "output")
            if field in model]


def parse_stepfun(text: str, today: datetime) -> list[Observed]:
    """Read token prices from StepFun's global pricing tables."""
    columns = {"Input (cache miss)": "input", "Input (cache hit)": "cache_read", "Output": "output"}
    found = []
    for _, header, rows in _markdown_tables(text):
        if header[:2] != ["Model", "Billing unit"] or not set(columns) <= set(header):
            continue
        for row in rows:
            if row[header.index("Billing unit")] != "1M tokens":
                continue
            model = row[0].strip("`")
            for title, field in columns.items():
                value = _price(row[header.index(title)])
                if value is not None:
                    found.append(Observed("stepfun-ai", model, field, value))
    return found


def parse_arcee(text: str, today: datetime) -> list[Observed]:
    """Read text model prices from Arcee's pricing page, which lists its own and resold
    models under their Arcee ids."""
    columns = {"Input": "input", "Output": "output", "Cached Input": "cache_read"}
    found = []
    for table in re.findall(r"<table.*?</table>", text, re.S):
        header, rows = _mdx_grid(table)
        titles = header[0] if header else []
        if titles[:1] != ["Model Name"]:
            continue
        for row in rows:
            for title, field in columns.items():
                value = _price(row[titles.index(title)]) if title in titles else None
                if value is not None:
                    found.append(Observed("arcee", row[0], field, value))
    return found


def parse_thinkingmachines(text: str, today: datetime) -> list[Observed]:
    """Read Tinker's sampling prices: prefill is input, with its cached price, and sample is
    output. A struck-out list price is followed by the discounted price charged."""
    found = []
    for _, header, rows in _markdown_tables(text):
        if "Tinker ID" not in header or "Sample" not in header:
            continue
        prefill = next(title for title in header if title.startswith("Prefill"))
        for row in rows:
            model = row[header.index("Tinker ID")]
            cell = re.sub(r"~~[^~]*~~", "", row[header.index(prefill)]).replace("\\$", "$")
            cached = re.search(r"\$([0-9.]+) \(cached\)", cell)
            uncached = re.search(r"\$([0-9.]+)(?! \(cached\))", cell)
            sample = re.findall(r"\$([0-9.]+)", re.sub(r"~~[^~]*~~", "", row[header.index("Sample")]))
            for field, match in (("input", uncached), ("cache_read", cached)):
                if match:
                    found.append(Observed("thinkingmachines", model, field, float(match.group(1))))
            if sample:
                found.append(Observed("thinkingmachines", model, "output", float(sample[-1])))
    return found


def _display_id(provider: str, name: str) -> str:
    """The model id a display name denotes: its slug, such as command-a-plus for
    "Command A+", or the newest id that adds a date or version to the slug, such as
    command-a-plus-05-2026."""
    slug = re.sub(r"[\s_]+", "-", name.strip().lower().replace("+", "-plus")).replace("--", "-")
    ids = _ids(provider)[0]
    # Some labs join a trailing version to the name, such as solar-pro4 for "Solar Pro 4".
    for candidate in (slug, re.sub(r"-(\d+(?:\.\d+)?)$", r"\1", slug)):
        if candidate in ids:
            return ids[candidate]
    dated = [key for key in ids if re.fullmatch(re.escape(slug) + r"-(\d{2})-(\d{4})", key)]
    if dated:
        return ids[max(dated, key=lambda key: (key[-4:], key[-7:-5]))]
    versions = [key for key in ids if re.fullmatch(re.escape(slug) + r"-\d+(-\d+)?", key)]
    return ids[versions[0]] if len(versions) == 1 else slug


def parse_cohere(text: str, today: datetime) -> list[Observed]:
    """Read model prices from the content data Cohere's pricing page embeds, which names
    models for display. A card marked Free, such as an open-weights model's, states no API
    price and is skipped."""
    found = []
    data = text.replace('\\"', '"')
    for record in re.finditer(r'"_type":"model".*?"modelName":"([^"]+)","per":"([^"]*)"', data):
        if record.group(2) == "Free":
            continue
        pricing = re.search(r'"pricings":\[\{[^]]*?"inputPrice":([0-9.]+)[^]]*?"outputPrice":([0-9.]+)',
                            data[record.end():record.end() + 4000])
        following = data.find('"_type":"model"', record.end())
        if pricing is None or (following != -1 and record.end() + pricing.start() > following):
            continue
        model = _display_id("cohere", record.group(1))
        found += [Observed("cohere", model, "input", float(pricing.group(1))),
                  Observed("cohere", model, "output", float(pricing.group(2)))]
    return found


def parse_sakana(text: str, today: datetime) -> list[Observed]:
    """Read Sakana AI's pay-as-you-go tables, each under a heading naming its model."""
    fields = {"Input": "input", "Output": "output", "Cached input": "cache_read"}
    found = []
    for table in re.finditer(r"<table.*?</table>", text, re.S):
        headings = re.findall(r"<h[1-4][^>]*>(.*?)</h[1-4]>", text[:table.start()], re.S)
        header, rows = _mdx_grid(table.group(0))
        titles = header[0] if header else []
        if not headings or titles[:1] != ["Token type"]:
            continue
        name = _mdx_cell(headings[-1])
        model = _display_id("sakana", re.sub(r"-v\d+(\.\d+)?$", "", name))
        for row in rows:
            field = fields.get(row[0])
            for title in titles[1:]:
                tier = re.search(r"> ?([0-9]+)K", title)
                value = _price(row[titles.index(title)])
                if field and value is not None:
                    found.append(Observed("sakana", model, field, value,
                                          above=int(tier.group(1)) * 1000 if tier else None))
    return found


def parse_ai21(text: str, today: datetime) -> list[Observed]:
    """Read Jamba prices, which AI21's pricing page states in prose."""
    found = []
    for name, prompt, completion in re.findall(
            r"\| (Jamba [A-Za-z0-9 .]+?) \|[^$]*?\$([0-9.]+) / 1M input tokens \| \$([0-9.]+) / 1M output tokens",
            _html_text(text)):
        model = _display_id("ai21", name)
        found += [Observed("ai21", model, "input", float(prompt)),
                  Observed("ai21", model, "output", float(completion))]
    return found


def parse_inception(text: str, today: datetime) -> list[Observed]:
    """Read Inception's models table; a struck-out list price is followed by the price
    charged."""
    columns = {"Input Price (1M Tokens)": "input", "Cached Input Price (1M Tokens)": "cache_read",
               "Output Price (1M Tokens)": "output"}
    found = []
    for _, header, rows in _markdown_tables(text):
        if header[:1] != ["Model"] or not set(columns) <= set(header):
            continue
        for row in rows:
            model = _display_id("inception", row[0].strip("*"))
            for title, field in columns.items():
                amounts = re.findall(r"\$([0-9.]+)", re.sub(r"~~[^~]*~~", "", row[header.index(title)].replace("\\$", "$")))
                if amounts:
                    found.append(Observed("inception", model, field, float(amounts[-1])))
    return found


_UPSTAGE_WINDOW = re.compile(
    r"(\d{4}-\d\d-\d\dT[\d:]+Z) \| (\d{4}-\d\d-\d\dT[\d:]+Z) \| "
    r"(free|input=([0-9.]+) \| cached=([0-9.]+) \| output=([0-9.]+))")


def parse_upstage(text: str, today: datetime) -> list[Observed]:
    """Read Upstage's LLM price cards: a list price, and dated promotional windows whose
    prices apply instead within them."""
    found = []
    card = re.compile(
        r"((?:Solar|Syn) [^|]+?) \|(?: New \|)? [^|]+ \|(?: \* End of service[^|]* \|)? "
        r"Input \| ([0-9.]+) \| 1M tokens \| Input\(Cached\) \| ([0-9.]+) \| 1M tokens \| "
        r"Output \| ([0-9.]+) \| 1M tokens(.*)")
    # One chunk per card, so each card's promotional windows stay with it.
    chunks = re.split(r"\| (?=(?:Solar|Syn) )", _html_text(text))
    cards = (match.groups() for match in map(card.match, chunks) if match)
    for name, prompt, cached, completion, windows in cards:
        prices = {"input": float(prompt), "cache_read": float(cached), "output": float(completion)}
        for start, end, kind, w_in, w_cached, w_out in _UPSTAGE_WINDOW.findall(windows):
            if _parse_time(start) <= today < _parse_time(end):
                prices = ({field: 0.0 for field in prices} if kind == "free" else
                          {"input": float(w_in), "cache_read": float(w_cached), "output": float(w_out)})
        model = _display_id("upstage", name)
        found += [Observed("upstage", model, field, value) for field, value in prices.items()]
    return found


def parse_xiaomi(text: str, today: datetime) -> list[Observed]:
    """Read Xiaomi MiMo's overseas real-time API prices; batch prices are not modeled. A
    cell can name several models that share its prices."""
    columns = {"Input (Cache Miss)": "input", "Input (Cache Hit)": "cache_read", "Output": "output"}
    start = text.find("### Overseas Pricing")
    found = []
    for table in re.findall(r"<table.*?</table>", text[start:] if start >= 0 else "", re.S):
        header, rows = _mdx_grid(table)
        titles = [title.strip("* ") for title in header[0]] if header else []
        if "Model Name" not in titles or not set(columns) <= set(titles):
            continue
        for row in rows:
            if titles[0] == "Inference Type" and "Real-time" not in row[0]:
                continue
            for model in re.findall(r"`([^`]+)`", row[titles.index("Model Name")]):
                for title, field in columns.items():
                    value = _price(row[titles.index(title)])
                    if value is not None:
                        found.append(Observed("xiaomi", model.strip(), field, value))
    return found


META_SITE = "https://dev.meta.ai"


def parse_meta(text: str, today: datetime, get: Callable[[str], str]) -> list[Observed]:
    """Read the "Models and pricing" grid on each Muse model page the Meta developer site
    links: model id, description, context window, then input, cached input, and output."""
    found = []
    for path in sorted(set(re.findall(r'href="(/models/muse-[a-z0-9-]+/)"', text))):
        page = _html_text(get(META_SITE + path))
        if "| Input (Mtok) | Cached input (Mtok) | Output (Mtok) |" not in page:
            continue
        for model, prompt, cached, completion in re.findall(
                r"\| (muse-[a-z0-9.-]+) \| [^|]+ \| [^|]+ \| \$([0-9.]+) \| \$([0-9.]+) \| \$([0-9.]+)",
                page):
            found += [Observed("meta", model, "input", float(prompt)),
                      Observed("meta", model, "cache_read", float(cached)),
                      Observed("meta", model, "output", float(completion))]
    return found


BEDROCK_PRICES = ("https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrock/USD/current/"
                  "bedrock.json")
_BEDROCK_REGION = "US East (N. Virginia)"
_BEDROCK_FIELDS = {"Price per 1M input tokens": "input",
                   "Price per 1M input tokens (cache read)": "cache_read",
                   "Price per 1M output tokens": "output"}


def parse_bedrock(text: str, today: datetime, get: Callable[[str], str]) -> list[Observed]:
    """Read Amazon Nova's on-demand prices on Amazon Bedrock, in US East (N. Virginia).

    The pricing page's tables are templates whose cells name a price in AWS's published
    price data. A table under "Global Cross-region Inference" prices the global. ids, and
    one under "Geo Cross-region inference and in-region" the unprefixed and us. ids. A
    separate table adds cache-read prices, which apply to whichever of those routes its
    input price matches.
    """
    prices = json.loads(get(BEDROCK_PRICES))["regions"][_BEDROCK_REGION]
    routes = {"Global Cross-region Inference": ("global.",),
              "Geo Cross-region inference and in-region": ("", "us.")}
    standard: dict[tuple[str, str], dict[str, float]] = {}
    cached: dict[str, dict[str, float]] = {}
    for match in re.finditer(r'data-pricing-markup="([^"]*)"', text):
        table = re.sub(r"(\s*\|\s*)+", " | ",
                       re.sub(r"<[^>]+>", " | ", html.unescape(match.group(1))))
        if "Amazon Nova" not in table:
            continue
        titles = [title.strip() for title in
                  re.findall(r"Price per 1M [a-z ]+(?:\([a-z ]+\))?", table)]
        if not titles or not set(titles) <= set(_BEDROCK_FIELDS):
            continue
        before = text[:match.start()]
        route = max(routes, key=before.rfind)
        on_demand = "| On Demand Inference |" in table
        if not on_demand and ("| Standard Tier |" not in table or before.rfind(route) < 0):
            continue
        rows = (re.match(r"(?:([0-9.]+) )?([A-Za-z]+) \|((?: \{priceOf![^}]+\} \|?)+)", row)
                for row in table.split("| Amazon Nova ")[1:])
        for version, family, cells in (row.groups() for row in rows if row):
            slug = f"nova-{version.removesuffix('.0') + '-' if version else ''}{family.lower()}"
            values = {}
            for title, (code, scale) in zip(titles, re.findall(
                    r"\{priceOf!bedrock/bedrock!([^!}]+)!\*!(\d+)", cells)):
                if code in prices:
                    values[_BEDROCK_FIELDS[title]] = round(float(prices[code]["price"]) * int(scale), 10)
            if on_demand:
                cached[slug] = values
            else:
                standard[(route, slug)] = values
    found = []
    for (route, slug), values in standard.items():
        extra = cached.get(slug, {})
        if "cache_read" in extra and extra.get("input") == values.get("input"):
            values = {**values, "cache_read": extra["cache_read"]}
        for prefix in routes[route]:
            found += [Observed("amazon-bedrock", f"{prefix}amazon.{slug}-v1:0", field, value)
                      for field, value in values.items()]
    return found


MISTRAL_DOCS = "https://docs.mistral.ai"


def _mistral_ids(page: str) -> list[str]:
    """Every API name a Mistral docs model page lists for its model, such as
    ["mistral-medium-3-5", "mistral-medium-3", "mistral-medium-latest"]."""
    names = re.search(r'"names":\[((?:"[a-z0-9.-]+",?)+)\]', page.replace('\\"', '"'))
    if names is None:
        raise ValueError("mistral: no model ids on a docs model page; the page format changed")
    return re.findall(r'"([a-z0-9.-]+)"', names.group(1))


def parse_mistral(text: str, today: datetime, get: Callable[[str], str]) -> list[Observed]:
    """Read token prices from Mistral's API pricing tables. Rows name models by display
    name and link to a docs page that gives the API id. A sale price is the price charged."""
    columns = {"Input": "input", "Cached input": "cache_read", "Output": "output"}
    found = []
    for table in re.findall(r"<table.*?</table>", text, re.S):
        header, rows = _mdx_grid(table)
        titles = header[0] if header else []
        if titles[:1] != ["Model"] or not set(columns) <= set(titles):
            continue
        body = re.search(r"<tbody[^>]*>(.*?)</tbody>", table, re.S)
        for row_html, row in zip(re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S), rows):
            cells = {title: row[titles.index(title)] for title in columns}
            # Rows priced per page, minute, or character are not token prices.
            if any(re.search(r"/\s*(1000 Pages|Min|M Chars)", cell) for cell in cells.values()):
                continue
            link = re.search(r'href="(/models/[^"]+)"', row_html)
            if link is None:
                continue
            models = _mistral_ids(get(MISTRAL_DOCS + link.group(1)))
            for title, field in columns.items():
                amounts = re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", cells[title])
                value = float(amounts[-1]) if amounts else (0.0 if cells[title] == "Free" else None)
                if value is not None:
                    found.extend(Observed("mistral", model, field, value) for model in models)
    return found


_GOOGLE_DATE = r"([A-Z][a-z]+ [0-9]{1,2}, [0-9]{4})"


def _google_price(cell: str, today: datetime) -> list[tuple[float, int | None]]:
    """Return (price, tier size) pairs for text tokens in effect today from a Paid Tier cell.

    Each dollar amount is read with the qualifier text that follows it: a date range,
    a modality list such as "(text / image)", or a prompt-size tier such as "prompts > 200k".
    """
    cell = cell.replace("\\<", "<").replace("\\>", ">")
    # A per-minute alternative sits between an amount and its modality: "$3.00 or $0.005/min
    # (audio)". Dropping it leaves each amount next to its own modality.
    cell = re.sub(r"\s+or\s+\$[0-9]+(?:\.[0-9]+)?/min", "", cell)
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
        heading = headings.get(2, "")
        if (not heading.startswith("Gemini") or headings.get(3) != "Standard"
                or header[-1] != "Paid Tier, per 1M tokens in USD"):
            continue
        # One section can price several models: "Gemini A, Gemini B, and Gemini C".
        models = re.split(r",\s*(?:and\s+)?|\s+and\s+(?=Gemini)", heading)
        for row in table:
            field = next((value for key, value in rows.items() if row[0].startswith(key)), None)
            if field is None:
                continue
            for value, above in _google_price(row[-1], today):
                found.extend(Observed("google", model, field, value, above=above)
                             for model in models)
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
        "en": ("https://api-docs.deepseek.com/quick_start/pricing/",
               r"Off-peak rates are half of the peak rates\. Peak hours are .*? in full\."),
        "zh": ("https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
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
    config = _data()["schedules"]
    results = []
    for name in sorted({schedule["holidays"] for schedule in config.get("schedule", [])
                        if schedule["provider"] in providers and "holidays" in schedule}):
        ends = datetime.fromisoformat(config["holidays"][name]["covers_through"]).date()
        remaining = (ends - today.date()).days
        status = "ok" if remaining > CALENDAR_WARNING_DAYS else "mismatch"
        results.append(Result("holidays", name, "holiday_calendar", None, None,
                              f"covers through {ends}", f"{remaining} days left", None, status))
    return results


def _ark_cell(cell: str) -> str:
    """A ModelArk docs table cell without Markdown emphasis, escapes, line breaks, or
    units, which BytePlus writes in English and Volcengine in Chinese."""
    text = re.sub(r"\*\*|<br>", " ", cell.replace("\\", ""))
    text = re.sub(r"\((?:USD|K tokens)[^)]*\)|元/百万token\S*|输入长度：千 token", "", text)
    return " ".join(text.split())


def ark_rows(markdown: str, heading: str, provider: str,
             columns: dict[str, str]) -> list[tuple[str, str, dict[str, float | None]]]:
    """The rows of a pricing table on BytePlus's or Volcengine's ModelArk docs, as
    (model, pricing condition, {field: price}); a row that continues a model's tiers
    repeats its name, and "-" is no price."""
    section = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^#)", markdown, re.M | re.S)
    lines = [line for line in (section.group(1) if section else "").splitlines()
             if line.startswith("|")]
    rows = [line.strip().removeprefix("|").removesuffix("|").split("|") for line in lines]
    titles = [_ark_cell(cell) for cell in rows[0]] if rows else []
    if len(titles) < 2 or not set(columns) <= set(titles):
        raise ValueError(f"{provider}: {heading} table columns are {titles}; the page format "
                         "changed")
    found, model = [], ""
    for row in rows[2:]:
        cells = [_ark_cell(cell) for cell in row]
        model = cells[0] or model
        found.append((model, cells[1], {field: None if cells[titles.index(title)] == "-"
                                        else float(cells[titles.index(title)])
                                        for title, field in columns.items()}))
    return found


# Yuan prices are compared in dollars at the rate models.dev converts each provider's prices
# at, within 1%, so a changed official price fails while models.dev's rounding does not.
YUAN_TO_USD = {
    # providers/volcengine/provider.toml: "CNY→USD rate: 6.737012, 2026-08-26".
    "volcengine": 1 / 6.737012,
    # providers/tencent-tokenhub/provider.toml converts list price / tax rate × exchange
    # rate, which gives hy4-preview's 6 yuan as $0.834.
    "tencent-tokenhub": 0.834 / 6,
}
YUAN_TOLERANCE = 0.01


def _yuan(provider: str, model: str, field: str, price: float, above: int | None = None) -> Observed:
    return Observed(provider, model, field, price * YUAN_TO_USD[provider], above=above, yuan=price)


VOLCENGINE_COLUMNS = {"输入(非音频)": "input", "缓存命中(非音频)": "cache_read", "输出": "output"}


def parse_volcengine(page: str, today: datetime) -> list[Observed]:
    """Volcengine Ark's standard online inference prices in yuan, from the document API
    that its pricing page loads.

    The page names model families, such as doubao-seed-2.0-pro, whose API ids add a date,
    such as doubao-seed-2-0-pro-260215; "正式版" (generally available) is the -ga id. An
    "输入长度 (32, 128]" row is the tier above 32K input tokens. Peak and off-peak rows,
    and superseded "调整前价格" rows, are left out.
    """
    try:
        markdown = json.loads(page)["Result"]["MDContent"]
    except (ValueError, KeyError, TypeError):
        raise ValueError("volcengine: no pricing document; the page format changed") from None
    ids = list(_ids("volcengine")[0].values())
    found = []
    for name, condition, prices in ark_rows(markdown, "在线推理（常规）", "volcengine",
                                            VOLCENGINE_COLUMNS):
        if "调整前" in name or condition in {"空闲时段", "高峰时段"}:
            continue
        family = name.split()[0].replace(".", "-").replace("正式版", "-ga").replace(
            "预览版", "-preview")
        tier = re.fullmatch(r"输入长度 ([\[(])(\d+), (\d+)\]", condition)
        if condition != "-" and tier is None:
            raise ValueError(f"volcengine: unknown pricing condition {condition!r} for {name}")
        above = int(tier.group(2)) * 1000 if tier and tier.group(1) == "(" else None
        models = [model for model in ids if re.fullmatch(re.escape(family) + r"(-\d{6})?", model)]
        for model in models or [family]:
            found += [_yuan("volcengine", model, field, price, above)
                      for field, price in prices.items() if price is not None]
    return found


def parse_tencent(page: str, today: datetime) -> list[Observed]:
    """Tencent TokenHub's language-model prices in yuan for its Guangzhou (China) region,
    whose list prices models.dev converts. Display names, such as "Hy4 preview", are
    hy4-preview; a "＞32k" condition is the tier above 32K tokens. Peak and off-peak rows
    are left out."""
    table = re.search(r"<table.*?</table>", page, re.S)
    if table is None:
        raise ValueError("tencent-tokenhub: no price table; the page format changed")
    rows = [[" ".join(html.unescape(re.sub(r"<[^>]+>", " ", cell)).replace("\ufeff", "")
                      .split()) for cell in re.findall(r"<t[hd].*?</t[hd]>", row, re.S)]
            for row in re.findall(r"<tr.*?</tr>", table.group(0), re.S)]
    titles = [re.sub(r"\s|（.*", "", cell) for cell in rows[0]] if rows else []
    columns = {"推理输入": "input", "推理输出": "output", "缓存命中": "cache_read"}
    if titles[:3] != ["模型名称", "条件", "峰谷计费"] or not set(columns) <= set(titles):
        raise ValueError(f"tencent-tokenhub: table columns are {titles}; the page format changed")
    found, name = [], ""
    for cells in rows[1:]:
        if len(cells) != len(titles):
            continue
        name = cells[0] or name
        if cells[2] != "-":
            continue
        tier = re.search(r"[>＞](\d+)k", cells[1])
        model = "-".join(name.lower().split())
        for title, field in columns.items():
            cell = cells[titles.index(title)]
            if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", cell):
                found.append(_yuan("tencent-tokenhub", model, field, float(cell),
                                   int(tier.group(1)) * 1000 if tier else None))
    return found


SOURCES: dict[str, tuple[str, Callable[[str, datetime], list[Observed]]]] = {
    "alibaba": ("https://www.alibabacloud.com/help/en/model-studio/model-pricing.md",
                parse_alibaba),
    "ai21": ("https://www.ai21.com/pricing/", parse_ai21),
    "arcee": ("https://docs.arcee.ai/get-started/pricing.md", parse_arcee),
    "cohere": ("https://cohere.com/pricing", parse_cohere),
    "amazon-bedrock": ("https://aws.amazon.com/bedrock/pricing/", parse_bedrock),
    "anthropic": ("https://platform.claude.com/docs/en/about-claude/pricing.md", parse_anthropic),
    "deepseek": ("https://api-docs.deepseek.com/quick_start/pricing/", parse_deepseek),
    "google": ("https://ai.google.dev/gemini-api/docs/pricing.md.txt", parse_google),
    "inception": ("https://docs.inceptionlabs.ai/get-started/models.md", parse_inception),
    "meta": ("https://dev.meta.ai/models/muse-spark/", parse_meta),
    "minimax": ("https://platform.minimax.io/docs/guides/pricing-paygo.md", parse_minimax),
    "mistral": ("https://mistral.ai/pricing/api", parse_mistral),
    "perplexity": ("https://docs.perplexity.ai/docs/getting-started/pricing.md", parse_perplexity),
    "thinkingmachines": (
        "https://tinker-docs.thinkingmachines.ai/tinker/models/models_and_pricing/index.md",
        parse_thinkingmachines),
    "sakana": ("https://console.sakana.ai/pricing", parse_sakana),
    "xiaomi": ("https://mimo.mi.com/static/docs/price/pay-as-you-go.md", parse_xiaomi),
    "upstage": ("https://www.upstage.ai/pricing", parse_upstage),
    "stepfun-ai": ("https://platform.stepfun.ai/docs/en/guides/pricing/details.md", parse_stepfun),
    "tencent-tokenhub": ("https://cloud.tencent.com/document/product/1823/130055", parse_tencent),
    "volcengine": ("https://www.volcengine.com/api/doc/getDocDetail?LibraryID=82379"
                   "&DocumentID=1544106&type=online", parse_volcengine),
    "moonshotai": ("https://platform.kimi.ai/docs/pricing/chat.md", parse_moonshot),
    "openai": ("https://developers.openai.com/api/docs/pricing.md", parse_openai),
    "xai": ("https://docs.x.ai/developers/pricing.md", parse_xai),
    "zai": ("https://docs.z.ai/guides/overview/pricing.md", parse_zai),
}


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "model-prices"})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        # Some hosts, such as AWS's price data, send gzip whatever the request accepts.
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body.decode()


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
    if field == "cache_write_1h":
        if found.cache_write_1h_multiple is None:
            return None
        return values["input"] * found.cache_write_1h_multiple
    # Missing cache prices are charged at the input price.
    if values[field] is None and field in {"cache_read", "cache_write"}:
        return values["input"]
    return values[field]


def compare(observed: Iterable[Observed], today: datetime,
            genai: list | None = None) -> list[Result]:
    """Classify each official price against model-prices and against models.dev alone, and
    record what genai-prices lists for it when its data is given."""
    results = []
    for item in observed:
        at = item.at or today.isoformat()
        # Official names must match exactly: a fuzzy match such as gpt-3.5-turbo-1106 to
        # gpt-3.5-turbo would compare different models.
        # An exact id comes first: some ids contain a slash, such as Arcee's
        # deepseek/deepseek-v4-flash-latest, which resolve would read as a provider prefix.
        exact = _ids(item.provider)[0].get(item.model.lower())
        resolved = (item.provider, exact) if exact else resolve(item.model, item.provider, strict=True)
        # A page compares only its own provider's prices: Alibaba's page also lists the
        # prices it resells DeepSeek and Kimi models at, which are not DeepSeek's or Moonshot's.
        if resolved and resolved[0] != item.provider:
            resolved = None
        name = "/".join(resolved) if resolved else item.model
        effective = (rates(name, at=at, provider=item.provider, mode=item.mode)
                     if resolved else None)
        raw = (rates(name, at=at, provider=item.provider, mode=item.mode, corrected=False)
               if resolved else None)
        effective_value = _value(effective, item.field, item.above)
        raw_value = _value(raw, item.field, item.above)
        # A price converted from yuan matches within YUAN_TOLERANCE of the conversion.
        margin = item.value * YUAN_TOLERANCE if item.yuan is not None else 1e-9
        if effective is None:
            status = "untracked"
        elif effective_value is not None and abs(effective_value - item.value) <= margin:
            status = ("ok" if raw_value is not None and abs(raw_value - item.value) <= margin
                      else "corrected")
        else:
            status = "mismatch"
        model = f"{effective.provider}/{effective.model}" if effective else item.model
        api_name = resolved[1] if resolved else item.model
        # genai-prices lists no thinking-mode prices.
        listed = (genai_prices.price(genai, item.provider, api_name, item.field,
                                     _parse_time(at), item.above)
                  if genai is not None and not item.mode and item.yuan is None else None)
        field = f"{item.mode} {item.field}" if item.mode else item.field
        results.append(Result(item.provider, model, field, item.above, item.at,
                              item.value, effective_value, raw_value, status, listed, item.yuan))
    return results


def parse(provider: str, page: str, moment: datetime,
          get: Callable[[str], str]) -> list[Observed]:
    """The prices a provider's pricing page states; `get` fetches any further pages."""
    url, parser = SOURCES[provider]
    # A check that reads further pages, such as Mistral's per-model docs, gets a fetcher.
    if len(inspect.signature(parser).parameters) == 3:
        observed = parser(page, moment, get)
    else:
        observed = parser(page, moment)
    if not observed:
        raise ValueError(f"{provider}: no prices parsed from {url}; the page format changed")
    return observed


def _check(provider: str, moment: datetime, pages: dict[str, str] | None,
           genai: list | None) -> list[Result]:
    url = SOURCES[provider][0]
    page = pages[provider] if pages and provider in pages else fetch(url)
    observed = parse(provider, page, moment,
                     lambda other: pages[other] if pages and other in pages else fetch(other))
    results = compare(observed, moment, genai)
    for language, (terms_url, _) in TERMS.get(provider, {}).items():
        key = f"{provider}:{language}"
        if terms_url == url:
            terms_page = page
        else:
            terms_page = pages[key] if pages and key in pages else fetch(terms_url)
        results.append(compare_terms(provider, language, terms_page, moment))
    return results


def run(providers: Iterable[str] | None = None, today: datetime | None = None,
        pages: dict[str, str] | None = None, genai: list | None = None) -> list[Result]:
    moment = today or datetime.now(timezone.utc)
    results = []
    for provider in providers or SOURCES:
        # A page that cannot be fetched or read fails its own provider's check, and the
        # other providers are still checked.
        try:
            results.extend(_check(provider, moment, pages, genai))
        except (OSError, ValueError) as error:
            results.append(Result(provider, provider, "page", None, None, SOURCES[provider][0],
                                  str(error), None, "error"))
    results.extend(check_calendars(set(providers or SOURCES), moment))
    return results


def _score(results: list[Result], field: str) -> str:
    """How many official prices a source lists correctly, lists wrongly, or omits."""
    values = [(result.official, getattr(result, field)) for result in results
              if isinstance(result.official, (int, float))]
    right = sum(value is not None and abs(value - official) < 1e-9 for official, value in values)
    missing = sum(value is None for _, value in values)
    return f"{right} right, {len(values) - right - missing} wrong, {missing} not listed"


def report(results: list[Result], genai: bool = False) -> str:
    lines = []
    for result in results:
        if result.status in {"ok", "untracked"}:
            continue
        if result.status == "error":
            lines.append(f"error     {result.provider} page {result.official}: {result.effective}")
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
        official = (f"¥{result.yuan:g} (${result.official:.4g})" if result.yuan is not None
                    else f"${result.official:g}")
        lines.append(
            f"{result.status:9} {result.model} {result.field}{tier}{when}: "
            f"official {official}, model-prices {result.effective}, "
            f"models.dev {result.models_dev}"
        )
    if genai:
        for result in results:
            if (isinstance(result.official, (int, float)) and result.genai_prices is not None
                    and abs(result.genai_prices - result.official) >= 1e-9):
                tier = f" above {result.above:,}" if result.above else ""
                when = f" at {result.at}" if result.at else ""
                lines.append(f"genai     {result.model} {result.field}{tier}{when}: "
                             f"official ${result.official:g}, genai-prices {result.genai_prices:g}")
    counts = {status: sum(r.status == status for r in results)
              for status in ("ok", "corrected", "mismatch", "untracked", "error")}
    lines.append(", ".join(f"{count} {status}" for status, count in counts.items()))
    if genai:
        lines.append(f"official prices in models.dev: {_score(results, 'models_dev')}; "
                     f"in genai-prices: {_score(results, 'genai_prices')}")
    return "\n".join(lines)


def as_json(results: list[Result]) -> list[dict]:
    return [asdict(result) for result in results]
