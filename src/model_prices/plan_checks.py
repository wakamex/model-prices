"""Checks of subscription plan prices against each lab's pricing page.

Each source is read by one reader of its layout: on a page, the plan's name, its monthly
price, and the billing label after it, with only text cells between the name and the price, so
a second price such as a struck-out original fails the match; in a price feed, the field that
holds the regular price, such as originalAmount, rather than a discounted one. A reader returns
every monthly price it finds, keyed by (provider, plan id) as in data/plans.toml, and fails
when a plan has two different prices. PLAN_PAGES names the plans each source is read for, so a
source that stops listing one fails, and a plan it lists that plans.toml lacks is a mismatch.
"""

from __future__ import annotations

from datetime import datetime
import http.client
import json
import re
import time
from typing import Callable, Iterable
import urllib.error
import urllib.request

from model_prices import _data, plan
from model_prices.checks import Result, _html_text

Prices = dict[tuple[str, str], float]


def _collect(page: str, pairs: Iterable[tuple[tuple[str, str], float]]) -> Prices:
    """The prices found, failing when one plan is listed at two prices."""
    found: Prices = {}
    for key, price in pairs:
        if found.setdefault(key, price) != price:
            raise ValueError(f"{page}: {key[0]}/{key[1]} is listed at ${found[key]:g} and ${price:g}")
    return found


def _cells(page: str, text: str, provider: str, patterns: dict[str, str]) -> Prices:
    """Each plan's price from the cell run its pattern spells out, in the page's text."""
    return _collect(page, (((provider, plan_id), float(price)) for plan_id, pattern in patterns.items()
                           for price in re.findall(pattern, text)))


# Up to a few cells of text, such as a tagline or a badge, between a plan's name and its price.
TEXT = r"(?: [^|$]+ \|){0,3}"


def read_anthropic(page: str) -> Prices:
    """A plan's annual price comes first where it has one, then the monthly one."""
    annual = r" \$[0-9]+ \| Per (?:month|seat / month)[^|$]*annual[^|$]*\|(?: \$[0-9,]+ \|[^|$]*\|)?"
    monthly = annual + r" \$([0-9]+) \| if billed monthly\. \|"
    return _cells("anthropic", _html_text(page), "anthropic", {
        "pro": r"\| Pro \|" + TEXT + monthly,
        # Max and Ultra keep the ids Claude Code reports, from before their 2026-10-30 renaming.
        "max_5x": r"\| Max \|" + TEXT + r" \$([0-9]+) \| Per month \|",
        "max_20x": r"\| Ultra \|" + TEXT + r" \$([0-9]+) \| Per month \|",
        "team_standard": r"\| Standard seat \|" + TEXT + monthly,
        "team_premium": r"\| Premium seat \|" + TEXT + monthly})


def read_openai(page: str) -> Prices:
    """The PricingCard components of the ChatGPT pricing page's Markdown copy: a card's own
    price, the Business card's monthly footnote, and the Pro card's list of tiers."""
    cards: dict[str, list[tuple[dict[str, str], str]]] = {}
    for attributes, body in re.findall(r"<PricingCard\s([^>]*)>(.*?)</PricingCard>", page, re.S):
        fields = dict(re.findall(r'(\w+)="([^"]*)"', attributes))
        cards.setdefault(fields["name"], []).append((fields, body))
    pairs = []
    for name in ("Go", "Plus"):
        for fields, _ in cards.get(name, []):
            if fields.get("priceEyebrow") == "From" or fields["interval"] != "/month":
                raise ValueError(f"openai: the {name} card's price is not a single monthly price")
            pairs.append((("openai", name.lower()), float(fields["price"].removeprefix("$"))))
    for fields, _ in cards.get("Business", []):
        pairs += [(("openai", "business"), float(price)) for price in
                  re.findall(r"\$([0-9]+) per user per month when billed monthly", fields.get("footnoteLabel", ""))]
    # A Pro tier is named by its price, so these check that each tier is still sold.
    for _, body in cards.get("Pro", []):
        for tiers in re.findall(r"Plans at ((?:\$[0-9]+,? )+or \$[0-9]+) USD per month", body):
            pairs += [(("openai", f"pro_{price}"), float(price)) for price in re.findall(r"\$([0-9]+)", tiers)]
    return _collect("openai", pairs)


def read_google(page: str) -> Prices:
    text = _html_text(page)
    found = _cells("google", text, "google", {
        name.lower(): rf"\| Google AI {name} \|(?: [^|$]+ \|){{0,6}} \$([0-9.]+) \| / month \|"
        for name in ("Plus", "Pro")})
    # Ultra's tiers are named by their usage, 5x and 20x that of AI Pro.
    ultra = re.findall(r"\| Google AI Ultra \|(?: [^|$]+ \|){0,6} Starting at: \| \$[0-9.]+ \| / month \| "
                       r"\$([0-9.]+) \| / month: 5x [^|$]+ \| \$([0-9.]+) \| / month: 20x [^|$]+ \|", text)
    return found | _collect("google", [pair for low, high in ultra for pair in
                                       ((("google", "ultra_100"), float(low)),
                                        (("google", "ultra_200"), float(high)))])


def read_zai_team(page: str) -> Prices:
    """Z.ai's Team plan seats, from the price feed its subscribe page loads."""
    seats = {"PRO": "team_standard", "MAX": "team_premium"}
    return _collect("zai", ((("zai", seats[product["tier"]]), float(product["originalAmount"]))
                            for product in json.loads(page)["data"]["productList"]
                            if product["subscribePeriod"] == "MONTHLY"))


def read_cursor(page: str) -> Prices:
    return _cells("cursor", _html_text(page), "cursor", {
        name.lower(): rf"\| {name} \|" + TEXT + r" \$([0-9]+) \| /month \|"
        for name in ("Plus", "Premium", "Super", "Ultra")})


def read_cognition(page: str) -> Prices:
    """Devin's plan comparison header, such as "| Pro | $20/month |"."""
    return _cells("cognition", _html_text(page), "cognition", {
        name.lower(): rf"\| {name} \| \$([0-9]+)/month \|" for name in ("Pro", "Max")})


def read_mistral(page: str) -> Prices:
    return _cells("mistral", _html_text(page), "mistral", {
        "pro": r"\| Pro \|" + TEXT + r" \$([0-9.]+) \| /mo \|",
        "team": r"\| Team \|" + TEXT + r" \$([0-9.]+) \| /user/mo \|",
        "student": r"students can get Mistral Pro for \$([0-9.]+) / month"})


def read_meta(page: str) -> Prices:
    return _cells("meta", _html_text(page), "meta", {
        name.lower(): rf"\| {name} Usage \|" + TEXT + r" \$([0-9.]+)/month \|"
        for name in ("Everyday", "High", "Power", "Maximum")})


def read_kimi(page: str) -> Prices:
    """Kimi's overseas subscriptions billed monthly, in cents, from the goods list its pricing
    page loads, which gives each one price and no discounted one."""
    pairs = []
    for goods in json.loads(page)["goods"]:
        if (goods["useRegion"] != "REGION_OVERSEA" or goods["type"] != "GOODS_TYPE_SUBSCRIPTION"
                or goods["billingCycle"] != {"duration": 1, "timeUnit": "TIME_UNIT_MONTH"}
                or goods["membershipLevel"] == "LEVEL_FREE"):
            continue
        usd = [amount["priceInCents"] for amount in goods["amounts"] if amount["currency"] == "USD"]
        if len(usd) != 1:
            raise ValueError(f"moonshotai: {goods['title']} has {len(usd)} USD prices")
        pairs.append((("moonshotai", goods["title"].lower()), int(usd[0]) / 100))
    return _collect("moonshotai", pairs)


def read_minimax(page: str) -> Prices:
    """The M Plan table, whose Regular price column is the price after the first month."""
    if "| Tier | First-month discount | Regular price |" not in page:
        raise ValueError("minimax: the M Plan table's columns changed")
    return _collect("minimax", ((("minimax", name.lower()), float(price)) for name, price in
                                re.findall(r"^\| (\w+) \| [^|]+ \| \\?\$([0-9.]+)/month \|$", page, re.M)))


def _table(page: str, provider: str, label: str) -> tuple[list[str], list[str]]:
    """The column titles and the row whose first cell is `label`, as text, of the one HTML
    table that has such a row."""

    def text(cell: str) -> str:
        return " ".join(re.sub(r"<[^>]+>", " ", cell).replace("\\$", "$").split())

    found = []
    for table in re.findall(r"<table.*?</table>", page, re.S):
        rows = [[text(cell) for cell in re.findall(r"<t[hd][^>]*?(?:/>|>(.*?)</t[hd]>)", row, re.S)]
                for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)]
        found += [(rows[0], row) for row in rows[1:] if row[0] == label]
    if len(found) != 1:
        raise ValueError(f"{provider}: {len(found)} tables have a {label} row; the page format changed")
    return found[0]


def read_alibaba_coding(page: str) -> Prices:
    titles, row = _table(page, "alibaba", "Price")
    prices = [re.fullmatch(r"\$ ?([0-9.]+) ?/month", cell) for cell in row[1:]]
    if len(prices) != len(titles) - 1 or not all(prices):
        raise ValueError(f"alibaba: the Coding Plan price row is {row}")
    return _collect("alibaba", ((("alibaba", f"coding_{title.lower()}"), float(price.group(1)))
                                for title, price in zip(titles[1:], prices)))


def read_alibaba_token(page: str) -> Prices:
    """The Token Plan table: a cell holds the monthly price, and may add a labelled new-user
    price; any other text in it fails, so a discount shown another way is not read as the
    price."""
    titles, row = _table(page, "alibaba", "Pricing")
    cells = row[1:]
    names = [re.fullmatch(r"(\w+) plan", title) for title in titles[1:]]
    prices = [re.fullmatch(r"\$([0-9.]+)/month(?: Limited-time new-user price \$[0-9.]+/month)?", cell)
              for cell in cells]
    if not names or len(cells) != len(names) or not all(names) or not all(prices):
        raise ValueError(f"alibaba: the Token Plan pricing row is {cells}")
    return _collect("alibaba", ((("alibaba", f"token_{name.group(1).lower()}"), float(price.group(1)))
                                for name, price in zip(names, prices)))


def read_xiaomi(page: str) -> Prices:
    """The MiMo Token Plan list its page loads."""
    return _collect("xiaomi", ((("xiaomi", item["planCode"]), float(item["originalPrice"]))
                               for item in json.loads(page)["data"]
                               if item["subscribeType"] == "MONTHLY" and item["periodInterval"] == 1
                               and item["currency"] == "USD"))


# The Step Plan page shows each plan type under this name.
STEPFUN_TYPES = {4: "mini", 1: "plus", 2: "pro", 3: "max"}


def read_stepfun(page: str) -> Prices:
    """Step Plan list prices billed monthly, in cents, from the plan list its page loads."""
    pairs = []
    for item in json.loads(page)["plans"]:
        if item["billing_cycle"] != 1:
            continue
        if item["type"] not in STEPFUN_TYPES:
            raise ValueError(f"stepfun-ai: unknown plan type {item['type']}")
        pairs.append((("stepfun-ai", STEPFUN_TYPES[item["type"]]), int(item["original_price"]) / 100))
    return _collect("stepfun-ai", pairs)


def _plans(provider: str, *ids: str) -> tuple[tuple[str, str], ...]:
    return tuple((provider, plan_id) for plan_id in ids)


# Each source: the page or the price feed it loads, the request body for a feed read by
# POST, its reader, and the plans it is read for.
PLAN_PAGES: dict[str, tuple[str, bytes | None, Callable[[str], Prices], tuple[tuple[str, str], ...]]] = {
    "anthropic": ("https://claude.com/pricing", None, read_anthropic,
                  _plans("anthropic", "pro", "max_5x", "max_20x", "team_standard", "team_premium")),
    "openai": ("https://learn.chatgpt.com/docs/pricing.md", None, read_openai,
               _plans("openai", "go", "plus", "business", "pro_100", "pro_200", "pro_500")),
    "google": ("https://gemini.google/us/subscriptions/?hl=en", None, read_google,
               _plans("google", "plus", "pro", "ultra_100", "ultra_200")),
    "zai-team": ("https://api.z.ai/api/biz/overseas/team/subscribe/product/public_pricing", None,
                 read_zai_team, _plans("zai", "team_standard", "team_premium")),
    "cursor": ("https://cursor.com/pricing", None, read_cursor,
               _plans("cursor", "plus", "premium", "super", "ultra")),
    "cognition": ("https://devin.ai/pricing", None, read_cognition, _plans("cognition", "pro", "max")),
    "mistral": ("https://mistral.ai/pricing", None, read_mistral, _plans("mistral", "pro", "team", "student")),
    "meta": ("https://dev.meta.ai/products/muse-code", None, read_meta,
             _plans("meta", "everyday", "high", "power", "maximum")),
    "moonshotai": ("https://www.kimi.com/apiv2/kimi.gateway.order.v1.GoodsService/ListGoods", b"{}",
                   read_kimi, _plans("moonshotai", "plus", "pro", "max", "ultra")),
    "minimax": ("https://platform.minimax.io/docs/m-plan/monthly-offer.md", None, read_minimax,
                _plans("minimax", "go", "explore", "build")),
    "alibaba-coding": ("https://www.alibabacloud.com/help/en/model-studio/coding-plan.md", None,
                       read_alibaba_coding, _plans("alibaba", "coding_pro")),
    "alibaba-token": ("https://docs.modelstudio.console.alibabacloud.com/en/model-studio/"
                      "token-plan-personal-overview.md", None, read_alibaba_token,
                      _plans("alibaba", "token_lite", "token_essential", "token_standard", "token_pro")),
    "xiaomi": ("https://platform.xiaomimimo.com/api/v1/openTokenPlan/list", None, read_xiaomi,
               _plans("xiaomi", "lite", "standard", "pro", "max")),
    "stepfun-ai": ("https://platform.stepfun.ai/api/step.openapi.devcenter.Dashboard/ListStepPlans",
                   b"{}", read_stepfun, _plans("stepfun-ai", "mini", "plus", "pro", "max")),
}


def _fetch(url: str, body: bytes | None, attempts: int = 3) -> str:
    """The source, retried after a failed or cut-off response, but not after a refusal,
    such as a 403, which a retry would not change."""
    request = urllib.request.Request(url, data=body, headers={
        "User-Agent": "model-prices", **({"Content-Type": "application/json"} if body else {})})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode()
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == attempts:
                raise
            time.sleep(5 * attempt)
        except (OSError, http.client.HTTPException):
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)
    raise AssertionError("unreachable")


def check_plans(today: datetime, pages: dict[str, str] | None = None) -> list[Result]:
    """Compare every plan price in effect today with its source. A source that cannot be read
    is an error that covers its plans; a plan no source is read for is listed as unchecked."""
    results, covered = [], set()
    for key, (url, body, reader, expected) in PLAN_PAGES.items():
        covered.update(expected)
        try:
            stated = reader(pages[key] if pages is not None else _fetch(url, body))
            missing = [f"{provider}/{plan_id}" for provider, plan_id in expected
                       if (provider, plan_id) not in stated]
            if missing:
                raise ValueError(f"no price for {', '.join(missing)}; the page format changed")
        # Any failure to fetch or read a source fails its check, whatever raised it.
        except Exception as error:
            results.append(Result(expected[0][0], key, "plan", None, None, url,
                                  f"{type(error).__name__}: {error}", None, "error"))
            continue
        for (provider, plan_id), price in sorted(stated.items()):
            recorded = plan(provider, plan_id, today)
            status = "ok" if recorded and abs(recorded.usd_per_month - price) < 1e-9 else "mismatch"
            results.append(Result(provider, f"{provider}/{plan_id}", "plan", None, None, price,
                                  recorded.usd_per_month if recorded else None, None, status))
    unread = {(item["provider"], item["id"]) for item in _data()["plans"]} - covered
    for provider, plan_id in sorted(unread):
        recorded = plan(provider, plan_id, today)
        if recorded is not None:
            results.append(Result(provider, f"{provider}/{plan_id}", "plan", None, None,
                                  recorded.source, None, None, "unchecked"))
    return results
