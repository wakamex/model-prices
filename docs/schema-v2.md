# Prices planned for snapshot schema 2

[models.dev](https://models.dev)'s schema 2 model files record prices that model-prices' snapshot does not carry yet: service tiers, regions, dates, and hours as conditions on a price, cache prices by caching mode and lifetime, tool fees, and prices per modality. model-prices reads those files through a translation in `src/model_prices/backfill.py`, a port of the one models.dev uses to publish its data in schema 1, which keeps text prices, cache read and write prices, long-prompt tiers, reasoning prices, and modes.

From 0.0.6 the package reads the schema 2 snapshot under `v2/` on the `data` branch and ignores rate fields it does not know, so each price below can be added to that snapshot on its own. Releases up to 0.0.5 raise on an unknown field, so `v1/` keeps being published with only the fields they know. Each model's history stays a timeline that clients look up by time: model-prices compiles conditions into the timeline and into fields, and does not ask clients to evaluate models.dev's condition language, which combines conditions with `any`, `all`, and `not` over hours, weekdays, holidays, dates, regions, and service tiers.

The order below puts first the prices that are wrong today in ways callers cannot see.

## Checks against models.dev

`schedules.toml` records DeepSeek's peak hours and Alibaba's off-peak discount, with the dates of each version and an exact holiday calendar, and `cache_writes.toml` records one-hour and 12-hour cache write prices as multiples of input. models.dev records the current version of both, as time-of-day multipliers and as write prices by lifetime, such as `write = { "5m" = 6.25, "1h" = 10 }`. `model-prices check` should fail when the current rule in either file differs from models.dev; both files stay the source, since models.dev keeps earlier rules only in its git history.

## Explicit cache hits

Alibaba bills a cache hit 20% of input when the cache was created implicitly, which needs no setup, and 10% when the request marked what to cache ([context cache](https://www.alibabacloud.com/help/en/model-studio/context-cache)); a model can support both. A rate entry has one cache read price, so every hit on a model with implicit caching is priced at 20%, and an explicit hit on `qwen-plus` costs $0.08 instead of $0.04 per million tokens.

Plan: a `cache_read_explicit` rate field, taken from each model's `cache.explicit.read` in models.dev and checked against Alibaba's cache rules, and a `cache_read_explicit_tokens` argument to `cost()` and `breakdown()`. A caller can tell explicit hits apart, since it sent the markers and only explicit caching reports `cache_creation_input_tokens`.

## Prices by modality

Google prices tokens by modality: Gemini 3.1 Flash Image charges $3 per million text and thinking output tokens and $60 per million image tokens, and Gemini 3.8 Live charges $0.75 for text input and $3.00 for audio input ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). A rate entry has one input and one output price, chosen as models.dev's schema 1 chooses them: the text price, except that an image or video generation model's output is the price of what it generates. So an image model's text output costs the image price, and a Live model's audio costs the text price.

Plan: optional per-modality rate fields, such as `input_audio` and `output_image`, from models.dev's `cost.audio`, `cost.image`, and `cost.video`, and token arguments per modality in `cost()`, with the current single prices kept for tokens given without one. A multiplier's factor is keyed by modality, as in `factor = { text = 1.8, audio = 1.8 }`, so modes and dated changes scale each modality's price by its own factor.

## Dated price changes

Google announces some changes ahead of time, and models.dev records them as a multiplier with a lone `date` condition, such as `when = { date = { gte = "2026-12-01" } }` with `factor = { text = 2, audio = 2 }` on Gemini 4 Argon, whose prices double that day. These need no new field; they become history entries.

Rules:

- A date multiplier seen while replaying models.dev's history is a pending change. It becomes a history entry at its date only if the file still carries it at the last commit before that date, so a change models.dev drops or reschedules first never enters the history.
- The entry's prices are the base prices scaled by that multiplier, and each mode's prices by its tier multiplier as well: every factor that applies multiplies, price by price, and tool fees stay unscaled.
- The date takes effect at 00:00 UTC, and the official-page check confirms the price on the day.
- The entry's `valid_from_basis` is `scheduled`, and the website labels such rows. Clients already look prices up by time; a tool reading a timeline's last entry as the current price would need to compare dates.
- Any other date condition, such as `lt` or a bounded window, stops the build until it is handled.

## Service tiers

models.dev records priority and flex tiers as multipliers with a `service_tier` condition, and the schema 1 translation gives a tier a mode only when the file also declares one under `experimental.modes`. So OpenAI's priority tier is the `fast` mode on some models, and Google's priority and flex tiers appear nowhere. These need no new field; they become modes.

Rules:

- Every service-tier multiplier gives a mode named after its tier, such as `priority` and `flex`, the names the providers' APIs use.
- A declared mode for the same tier, such as OpenAI's and Anthropic's `fast`, stays as a second name with the same prices, and the build stops if their prices differ.
- A mode a model does not have returns no price.
- The check compares tier prices with the pages that list them, such as OpenAI's Flex, Fast, and Ultrafast tables and Google's Priority and Flex sections.

## Regions

Anthropic charges 1.1 times for US-only inference on Claude 4.6 and later, xAI charges 1.1 times on its US regional endpoint, and OpenAI charges a 10% uplift on regional processing endpoints for models released on or after 2026-03-05, each on token prices only ([Anthropic](https://platform.claude.com/docs/en/about-claude/pricing), [xAI](https://docs.x.ai/developers/pricing), [OpenAI](https://developers.openai.com/api/docs/pricing)).

Plan: a factor per region on the rate entry, applied to token prices and never to tool fees, and a `region` argument. Region, mode, and dated factors multiply.

## Tool fees

Web search costs $10 per 1,000 calls at OpenAI and Anthropic, $14 at Google, and $5 at xAI, and Perplexity's Agent API, which replaced Sonar Chat Completions on 2026-09-27, bills tool calls beside tokens ([models](https://docs.perplexity.ai/docs/agent-api/models)). These are priced per call, not per million tokens, so pricing them turns `cost()` from a token price into a request's whole bill.

Plan: per-call tool prices on the rate entry, and either call counts per tool in `cost()` or a separate function for tool fees, decided when this is built. It comes last, in its own release.
