# model-prices

LLM API prices, today's or as they were at any point in time. Pricing past usage at today's rates misstates it whenever a price changed: GPT-5.6 Sol cost $5/$30 per million input/output tokens until August 21, 2026, and $4/$20 for the three months after. This package answers "what did this request cost at API prices when it ran?"

Status: work in progress. Versions before 0.1 may change the data format and API without notice.

```python
import model_prices

model_prices.cost(
    "gpt-5.6-sol",
    input_tokens=12_000,        # uncached input only
    cache_read_tokens=180_000,
    output_tokens=900,
    at="2026-08-20T14:00:00Z",
)

model_prices.rates("claude-opus-5-5")  # current rates, per million tokens
```

```sh
model-prices rate gpt-5.6-sol --at 2026-08-20
model-prices rate "Gemini 3.5 Flash (High)" --json
```

## Install

Requires Python 3.11 or newer.

```sh
uv add model-prices
```

## Keeping prices current

Each release bundles the price data from when it was built. Price data is also published on its own, so new prices reach an installed release without upgrading it:

```python
status = model_prices.refresh()   # downloads when the cached copy is over a day old
status.basis                      # the pricing basis now in use
status.published_at               # when that data was last confirmed current
```

Prices change only when `refresh()` is called; until then, the bundled data applies. `refresh(max_age=...)` sets how old a downloaded copy may get before it downloads again, and `refresh(max_age=None)` never downloads and uses the newest copy already downloaded or bundled. When a download fails, `refresh()` keeps the newest local copy, sets `status.error`, and warns, so a caller can keep working and decide how stale is too stale from `published_at`. `model-prices refresh` downloads from the command line, and `model-prices rate` uses the newest local copy. Downloads are cached in `~/.cache/model-prices`, `%LOCALAPPDATA%\model-prices` on Windows, or the directory in `MODEL_PRICES_CACHE`.

Published data is a single file, the snapshot, holding every model's final price timeline plus the aliases, schedules, and plans. It is served from the repository's [`data` branch](https://github.com/wakamex/model-prices/tree/data): `v1/latest.json` names the current snapshot by its SHA-256 hash, and `v1/<sha256>.json` keeps every snapshot ever published, so the data behind any recorded basis can be fetched again. `refresh()` checks each download's hash and schema version before using it. The `v1` is the schema version, which changes only when looking up a price changes, so a release keeps reading every later snapshot of its schema.

## Where the prices come from

Prices come from the git history of [models.dev](https://github.com/sst/models.dev), an open catalog of model metadata that records each model's price in one TOML file per provider. Every commit on its main branch that changed a tracked model's price becomes an entry effective from that commit's time. The tracked providers are the labs that sell their own models through an API: AI21 Labs, Alibaba, Amazon Nova (its free developer API and its paid models on [Amazon Bedrock](https://aws.amazon.com/bedrock/), under ids such as `us.amazon.nova-pro-v1:0`), Ant Group's Bailing, Anthropic, Arcee, ByteDance's Volcengine, Cohere, DeepSeek, Google, Inception, Meituan's LongCat, Meta, MiniMax, Mistral, Moonshot AI, OpenAI, Perplexity, Poolside, Sakana AI, SenseTime's SenseNova, StepFun, Tencent, Thinking Machines, Upstage, Xiaomi, xAI, and Z.ai. Where models.dev lists a lab's China and global endpoints separately, the global one is tracked. Some models.dev entries list a price of zero, such as free previews; only providers with an official price check have those prices confirmed. Thinking Machines' Inkling is priced at its [Tinker](https://tinker-docs.thinkingmachines.ai/tinker/models/models_and_pricing/) sampling price, which models.dev records.

Models that models.dev does not list are read from their provider's own pricing pages: Cursor's Composer models, from [Cursor's model docs](https://cursor.com/docs/models), with their fast variants as the `fast` mode, and Cognition's SWE models, from the price list on [Devin's models page](https://docs.devin.ai/desktop/models), under the model ids Devin reports, such as `swe-2-medium`. Cognition's prices are the Enterprise plan's, which pays per token; self-serve plans include some of these models at no charge for a period. Devin listed SWE-1.7 at no charge until its 2026-09-12 price list, so earlier SWE-1.7 usage costs nothing. A daily run records a new entry in `data/observed.json` whenever a page's price differs from the last one recorded, dated by the run that first saw it, and fails when a page's layout changes. Composer 2.5's history starts at the first archived copy of its rate table, on 2026-08-23, and Cognition's at the first archived copy of Devin's price list, on 2026-07-30.

The inputs live in [`data/`](https://github.com/wakamex/model-prices/tree/main/data): `prices.json` holds the models.dev history, and the TOML files beside it adjust it. `model-prices compile` combines them into the snapshot that the package reads, applying every rule in this section once, so a client only looks prices up by time.

models.dev sometimes records a change days after the provider made it, or lists a wrong price for a while. `corrections.toml` overrides those periods, and every correction cites its source. `research_corrections.toml` adds corrections generated from agent research into every recorded change, each verified against quotes from its sources (see [research/README.md](https://github.com/wakamex/model-prices/blob/main/research/README.md)); hand corrections take precedence. A correction without an end date names the models.dev values it replaces and stops applying as soon as models.dev records anything else, so it cannot outlive a later fix or price change.

`Rates.valid_from_basis` says how a start date was found: `models.dev commit` dates usually lag the provider's real change by days, `documented` dates come from a correction's cited source, and `first observed` dates are when model-prices first read the price on the provider's page, at most a day after a change.

Usage from before a model's first recorded price is priced at that first price, because models.dev often adds a model after its launch. `Rates.valid_from` is then later than the requested time, which a caller can check to reject implausible times, such as a zero timestamp. Usage after `data_as_of()`, the date of the models.dev commit the data was built from, assumes no price changed since.

Pass the time the provider billed the request as `at`. Providers do not document whether a request that spans a peak boundary bills at its start or its end; agent harnesses usually report completion times, which is a reasonable choice.

Each entry keeps input, output, cache read, and cache write rates, long-context tiers, and alternate modes such as fast mode. `cache_write_tokens` are five-minute cache writes; pass one-hour cache writes as `cache_write_1h_tokens`. `cache_writes.toml` records Anthropic's price for those, twice the input price, which `model-prices check` compares with Anthropic's pricing page; other providers' one-hour writes are priced as cache writes. A tier applies when one request's whole prompt, meaning uncached input plus cache reads and writes, exceeds the tier size. A missing cache price falls back to the input price.

## Time-of-day pricing

Some providers price by time of day. `schedules.toml` records each version of a provider's rules with the dates it applied: either peak windows that multiply the recorded rate, or off-peak windows that discount it for listed models. `Rates.period` says which applied: `"peak"` or `"off_peak"`, `"standard"` outside a discount window, or `None` when no time-of-day rule applies.

Holiday calendars record the last date they cover, and `model-prices check` fails 45 days before that date so the next year's holidays are added in time. DeepSeek is the one provider with such pricing so far. From 16:30 UTC on February 26, 2025 until 16:00 UTC on September 5, 2025, it took 50% off DeepSeek-V3 (`deepseek-chat`) and 75% off DeepSeek-R1 (`deepseek-reasoner`) from 16:30 to 00:30 UTC daily. Since 16:00 UTC on August 16, 2026, its peak hours have been 01:00-04:00 and 06:00-10:00 UTC on weekdays other than Chinese public holidays, at twice the off-peak rate. The pricing page added the weekday and holiday exceptions in late August and mid-September without an announcement; model-prices applies the current rule from the start of peak pricing. [DeepSeek pricing history](https://github.com/wakamex/model-prices/blob/main/docs/deepseek-pricing-history.md) records the evidence for each 2026 date. DeepSeek decides the period by when a request completes, so pass the completion time as `at` where it is known.

## Official price checks

`model-prices check` fetches each supported provider's official pricing page, reads it with a parser written for that page's table layout, and compares every price with the rate model-prices uses today. It covers AI21 Labs, Alibaba, Amazon Bedrock's Nova models, Anthropic, Arcee, Cohere, DeepSeek, Google, Inception, Meta, MiniMax, Mistral, Moonshot AI, OpenAI, Perplexity, Sakana AI, StepFun, Thinking Machines, Upstage, xAI, Xiaomi, and Z.ai. Upstage's page dates each promotional price window, which the check applies on its dates. Bedrock's pricing page fills its tables from AWS's published price data; its US East (N. Virginia) prices are checked for the unprefixed and `us.` ids under geographic cross-region and in-region inference, and for the `global.` ids under global cross-region inference, which costs less for Nova 2 Lite. Mistral's prices are read from [its API pricing page](https://mistral.ai/pricing/api), which names models for display, and each model's id from its docs page, which lists every API name of the model; a sale price is checked as the price charged. Alibaba's page is read for its Singapore (international) deployment, which models.dev's Alibaba prices describe; its page lists cache prices as a rule rather than per model, so only input, output, and long-context tiers are compared there. Each price is reported as:

- `ok`: models.dev and the official page agree.
- `corrected`: models.dev differs, but a correction in `corrections.toml` or `research_corrections.toml` supplies the official price.
- `mismatch`: model-prices differs from the official page. The command exits with status 1.
- `untracked`: the page lists a model that models.dev does not price.

Page model names must match models.dev ids exactly, with no suffix removal, so a dated model is never compared with a different undated one. A page is compared only for its own provider's models: Alibaba's page also lists the prices it resells DeepSeek and Kimi models at, which are not DeepSeek's or Moonshot AI's prices. For DeepSeek, peak and off-peak prices are checked at the next hours the schedule classifies as each, and the peak-hour rule on both the English and Chinese pricing pages must match the wording recorded in `schedules.toml`, so a change to the hours, multiplier, or exceptions fails the check. Google's dated future prices are read for the check date. A page that yields no prices fails the check, because its format has changed.

`model-prices check --genai-prices` also scores [Pydantic's genai-prices](https://github.com/pydantic/genai-prices) against the same official prices, reading its `data.json` from GitHub, or from a file or checkout given as `--genai-prices PATH`. It lists each price genai-prices gets wrong and ends with how many official prices each source lists correctly, wrongly, or not at all. Its disagreements never change the exit status. genai-prices is read by exact model id only: it also matches names by prefix, which would give a model it lacks, such as Claude Opus 5.5, an older model's prices. Z.ai is not compared, because genai-prices' Zhipu entry is the mainland China API. On 2026-10-01, models.dev listed 342 official prices correctly and 7 wrongly; genai-prices listed 173 correctly and 40 wrongly, almost all from missing price cuts such as GPT-5.6's.

## Not modeled

model-prices prices standard synchronous requests. It does not model batch, flex, or priority service tiers; regional or data-residency surcharges; storage charges for cached context; or tool fees such as web search. Modes listed by models.dev, such as fast mode, are available through `mode`. While a correction applies, a mode's price is the corrected price scaled by the mode's ratio to models.dev's standard price at that time, since corrections record standard prices only.

Perplexity's Sonar models add a per-request fee that depends on search context size, and Sonar Deep Research also bills citation tokens, reasoning tokens, and search queries; model-prices prices their input and output tokens. Alibaba prices thinking-mode output separately for hybrid Qwen models, often above the non-thinking price, such as $4 against $1.2 per million output tokens for `qwen-plus`; model-prices uses the non-thinking price. Alibaba's resale of DeepSeek models has busy-hour and idle-hour prices, which are not modeled.

Where a model has no cache-write price, cache writes are priced as input. That matches providers whose caching is automatic and bills the first, cache-filling request as normal input, such as Google's implicit caching, DeepSeek, xAI, and Z.ai. Providers that charge more for writing a cache list a cache-write price in models.dev.

Long-context tiers apply when a request's prompt exceeds the tier size. Providers word the boundary differently, such as Google's "> 200k" and xAI's "≥ 200k", so a prompt of exactly the tier size may price one tier off.

`Rates.breakdown()` returns a request's cost by token type and the tier it reached, for callers that report either.

## Model names

`resolve()` maps the names that logs and agent harnesses use to models.dev ids. It matches ids regardless of case, such as `minimax-m2.7` for `MiniMax-M2.7`, and normalizes display names such as `Gemini 3.5 Flash (High)` and dotted Claude versions such as `claude-sonnet-4.5`. It reads a `provider/` prefix or the `provider` argument as a hint, and when the full name is unknown it removes context markers such as `[1m]`, the `-build` suffix that xAI's subscription endpoint adds to Grok versions such as `grok-4.6-build`, effort suffixes such as `-high`, and date suffixes such as `-20251001` or `-2026-04-23`. `Rates.removed_suffix` records any text removed this way, and `resolve_details()` returns it, so a caller can tell when a price belongs to a related name: `-max` is both an effort level and part of some model names, such as `qwen3.8-max`. A model is looked up at its own lab before other labs that also serve it. A lab model name resolves to the first-party API id that serves it, using models.dev's `base_model` links and preferring ids that are not deprecated: DeepSeek serves `deepseek-v4.1-flash` as `deepseek-flash`, so that name gets `deepseek-flash`'s price. `aliases.toml` holds the few names that need an explicit mapping. Unknown models return `None` rather than a guessed price.

Aliases are part of the published data, while the normalization rules above are code. A name that resolves wrongly or not at all is fixed with an alias where possible, so the fix reaches every installed release on its next `refresh()`. A normalization change covers a whole class of names, such as the `-build` suffix, and reaches only new releases; older releases keep resolving names as before, so a name they could not resolve still returns `None`.

## Current prices for past requests

`rates()` and `cost()` take `prices_at` to price a request from a different date's price list. The time-of-day rule in force at `at`, the time the request ran, still applies: a request made in a 2025 DeepSeek discount hour keeps its discount on today's prices. Pricing every past request with `prices_at` set to today compares usage across weeks without price changes appearing as usage changes.

## Prices over a span

`rates_between(model, start, end)` returns each distinct rate in effect over a span with the time it begins. Use it for usage known only to fall within a span, such as a run with a start and finish but no per-request times: a single entry means one price covered the whole span. It finds changes from price history, corrections, and time-of-day schedules exactly, including peak windows and holidays. `Rates.price_key()` compares prices without provenance, so a correction and the models.dev entry that later records the same prices compare equal.

## Subscription plans

`plan(provider, plan_id, at=None)` returns a subscription plan's monthly price from `plans.toml`, keyed by the plan name each lab's usage tools report, such as `max_20x` for Claude or `lite` for the GLM Coding Plan. A plan sold in several price tiers gets one entry per tier, with the price in its id and name, such as `ultra_200` for Google AI Ultra $200 or `pro_500` for ChatGPT Pro $500. When a usage tool reports only the untiered name, that name has no entry, except that ChatGPT's `pro` keeps its original $200 price.

## Recording what was used

`pricing_basis()` returns an identifier such as `model-prices-0.0.1+models.dev@e2bf2e470a1b+synced@2026-09-30+data@3f1c09a2b7de`, naming the package version, the models.dev commit its data came from and that commit's date, and the start of the SHA-256 hash of the snapshot in use, so any change to prices, corrections, schedules, or aliases changes it. Store it next to computed costs.

## Updating prices

A daily workflow records observed prices with `model-prices observe`, which goes straight to `main` because the page is the source, then clones models.dev and rebuilds `data/prices.json` with `model-prices update`, which also compiles the snapshot. Each provider whose history changed then runs its official price check. A provider that passes goes straight to `main`. A provider that fails its check, or has no check yet, is held at its current history and goes to the `update-prices` pull request for review instead; the workflow fails when a check failed. Fix a failure with a correction, or with a models.dev pull request when models.dev is wrong. Before merging the pull request, check each changed model's effective date against the provider's announcement and add a correction when models.dev recorded the change late. The workflow publishes the snapshot to the `data` branch after every run and after every push that changes the data, such as a merged correction.

Prices that go straight to `main` are dated by their models.dev commit. A correction for a late date arrives in a later snapshot; costs already computed keep the basis that priced them.

To rebuild locally, from the repository root:

```sh
git clone https://github.com/sst/models.dev.git /tmp/models.dev
uv run --locked model-prices update /tmp/models.dev
```

After editing a file in `data/`, run `uv run --locked model-prices compile`. A test fails when the bundled snapshot does not match its inputs.

## Development

```sh
uv run --locked python -m unittest discover -s tests
```

## License

The code and the corrections are MIT licensed. `data/prices.json` and the snapshot compiled from it are derived from [models.dev](https://github.com/sst/models.dev), whose MIT license is in `data/LICENSE.models.dev`. The test fixture `tests/fixtures/genai-prices.json` is an excerpt of [genai-prices](https://github.com/pydantic/genai-prices), whose MIT license is in `tests/fixtures/LICENSE.genai-prices`.
