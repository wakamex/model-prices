# llm-prices

LLM API prices as they were at any point in time. Pricing past usage at today's rates misstates it whenever a price changed: GPT-5.6 Sol cost $5/$30 per million input/output tokens until August 22, 2026, and $4/$20 after. This package answers "what did this request cost at API prices when it ran?"

```python
import llm_prices

llm_prices.cost(
    "gpt-5.6-sol",
    input_tokens=12_000,        # uncached input only
    cache_read_tokens=180_000,
    output_tokens=900,
    at="2026-08-20T14:00:00Z",
)

llm_prices.rates("claude-opus-5-5")  # current rates, per million tokens
```

```sh
llm-prices rate gpt-5.6-sol --at 2026-08-20
llm-prices rate "Gemini 3.5 Flash (High)" --json
```

## Install

Requires Python 3.12 or newer.

```sh
uv add llm-prices
```

## Where the prices come from

Prices come from the git history of [models.dev](https://github.com/sst/models.dev), an open catalog of model metadata that records each model's price in one TOML file per provider. Every commit on its main branch that changed a tracked model's price becomes an entry effective from that commit's time. The tracked providers are the labs that sell their own models: Alibaba, Anthropic, DeepSeek, Google, Moonshot AI, OpenAI, xAI, and Z.ai.

models.dev sometimes records a change days after the provider made it, or lists a wrong price for a while. `corrections.toml` overrides those periods, and every correction cites its source. A correction without an end date names the models.dev values it replaces and stops applying as soon as models.dev records anything else, so it cannot outlive a later fix or price change.

`Rates.valid_from_basis` says how a start date was found: `models.dev commit` dates usually lag the provider's real change by days, while `documented` dates come from a correction's cited source.

Usage from before a model's first recorded price is priced at that first price, because models.dev often adds a model after its launch. `Rates.valid_from` is then later than the requested time, which a caller can check to reject implausible times, such as a zero timestamp. Usage after the last sync, given by `data_as_of()`, assumes no price changed since.

Pass the time the provider billed the request as `at`. Providers do not document whether a request that spans a peak boundary bills at its start or its end; agent harnesses usually report completion times, which is a reasonable choice.

Each entry keeps input, output, cache read, and cache write rates, long-context tiers, and alternate modes such as fast mode. A tier applies when one request's whole prompt, meaning uncached input plus cache reads and writes, exceeds the tier size. A missing cache price falls back to the input price.

## Time-of-day pricing

Some providers charge more at busy hours. `schedules.toml` records each provider's peak windows, weekday rules, and holiday calendar, with the dates each version of the rules applied. The recorded rate is the off-peak rate, and inside a peak window every rate is multiplied by the schedule's peak multiplier. `Rates.period` says which applied: `"peak"`, `"off_peak"`, or `None` for providers without time-of-day pricing.

Holiday calendars record the last date they cover, and `llm-prices check` fails 45 days before that date so the next year's holidays are added in time. DeepSeek is the one provider with such pricing so far. Since 16:00 UTC on August 16, 2026, its peak hours have been 01:00-04:00 and 06:00-10:00 UTC on weekdays other than Chinese public holidays, at twice the off-peak rate. The pricing page added the weekday and holiday exceptions in late August and mid-September without an announcement; llm-prices applies the current rule from the start of peak pricing. [DeepSeek pricing history](docs/deepseek-pricing-history.md) records the evidence for each date.

## Official price checks

`llm-prices check` fetches each supported provider's official pricing page, reads it with a parser written for that page's table layout, and compares every price with the rate llm-prices uses today. It covers Anthropic, DeepSeek, Google, OpenAI, xAI, and Z.ai. Each price is reported as:

- `ok`: models.dev and the official page agree.
- `corrected`: models.dev differs, but a correction in `corrections.toml` supplies the official price.
- `mismatch`: llm-prices differs from the official page. The command exits with status 1.
- `untracked`: the page lists a model that models.dev does not price.

Page model names must match models.dev ids exactly, with no suffix removal, so a dated model is never compared with a different undated one. For DeepSeek, peak and off-peak prices are checked at the next hours the schedule classifies as each, and the peak-hour rule on both the English and Chinese pricing pages must match the wording recorded in `schedules.toml`, so a change to the hours, multiplier, or exceptions fails the check. Google's dated future prices are read for the check date. A page that yields no prices fails the check, because its format has changed.

## Model names

`resolve()` maps the names that logs and agent harnesses use to models.dev ids. It lowercases the name and normalizes display names such as `Gemini 3.5 Flash (High)` and dotted Claude versions such as `claude-sonnet-4.5`. It reads a `provider/` prefix or the `provider` argument as a hint, and when the full name is unknown it removes context markers such as `[1m]`, the `-build` suffix that xAI's subscription endpoint adds to Grok versions such as `grok-4.6-build`, effort suffixes such as `-high`, and date suffixes such as `-20251001` or `-2026-04-23`. `Rates.removed_suffix` records any text removed this way, and `resolve_details()` returns it, so a caller can tell when a price belongs to a related name: `-max` is both an effort level and part of some model names, such as `qwen3.8-max`. A model is looked up at its own lab before other labs that also serve it. A lab model name resolves to the first-party API id that serves it, using models.dev's `base_model` links and preferring ids that are not deprecated: DeepSeek serves `deepseek-v4.1-flash` as `deepseek-flash`, so that name gets `deepseek-flash`'s price. `aliases.toml` holds the few names that need an explicit mapping. Unknown models return `None` rather than a guessed price.

## Current prices for past requests

`rates()` and `cost()` take `prices_at` to price a request from a different date's price list while `at`, the time the request ran, still decides peak or off-peak. Pricing every past request with `prices_at` set to today compares usage across weeks without price changes appearing as usage changes.

## Prices over a span

`rates_between(model, start, end)` returns each distinct rate in effect over a span with the time it begins. Use it for usage known only to fall within a span, such as a run with a start and finish but no per-request times: a single entry means one price covered the whole span. It finds changes from price history, corrections, and time-of-day schedules exactly, including peak windows and holidays. `Rates.price_key()` compares prices without provenance, so a correction and the models.dev entry that later records the same prices compare equal.

## Subscription plans

`plan(provider, plan_id, at=None)` returns a subscription plan's monthly price from `plans.toml`, keyed by the plan name each lab's usage tools report, such as `max_20x` for Claude or `lite` for the GLM Coding Plan. A plan sold in several price tiers gets one entry per tier, with the price in its id and name, such as `ultra_200` for Google AI Ultra $200 or `pro_500` for ChatGPT Pro $500. When a usage tool reports only the untiered name, that name has no entry, except that ChatGPT's `pro` keeps its original $200 price.

## Recording what was used

`pricing_basis()` returns an identifier such as `llm-prices-0.1.0+models.dev@e2bf2e470a1b+synced@2026-09-30+data@3f1c09a2b7de`, naming the package version, the models.dev commit and sync date its data came from, and a hash of all its data files, so any change to prices, corrections, schedules, or aliases changes it. Store it next to computed costs.

## Updating prices

A daily workflow clones models.dev, rebuilds `src/llm_prices/data/prices.json` with `llm-prices update`, and opens a pull request when a tracked price changed. It then runs `llm-prices check` and fails when an official price disagrees; fix that with a correction, or with a models.dev pull request when models.dev is wrong. Before merging, check each changed model's effective date against the provider's announcement and add a correction when models.dev recorded the change late.

To rebuild locally:

```sh
git clone https://github.com/sst/models.dev.git /tmp/models.dev
uv run --locked llm-prices update /tmp/models.dev
```

## Development

```sh
uv run --locked pytest
```

## License

MIT. Price data is derived from [models.dev](https://github.com/sst/models.dev), which is MIT licensed.
