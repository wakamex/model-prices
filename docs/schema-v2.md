# Prices planned for snapshot schema 2

[models.dev](https://models.dev)'s schema 2 model files record prices that model-prices' snapshot does not carry yet: service tiers, regions, dates, and hours as conditions on a price, cache write prices by lifetime, and tool fees. model-prices reads those files through a translation in `src/model_prices/backfill.py`, a port of the one models.dev uses to publish its data in schema 1, which keeps text prices, cache read and write prices, long-prompt tiers, reasoning prices, and modes.

From 0.0.6 the package reads the schema 2 snapshot under `v2/` on the `data` branch and ignores rate fields it does not know, so each price below can be added to that snapshot on its own. Releases up to 0.0.5 raise on an unknown field, so `v1/` keeps being published with only the fields they know. Each model's history stays a timeline that clients look up by time: model-prices compiles conditions into the timeline and into fields, and does not ask clients to evaluate models.dev's condition language, which combines conditions with `any`, `all`, and `not` over hours, weekdays, holidays, dates, regions, and service tiers.

Two of those prices are carried, as the README describes: dated price changes, which models.dev records as a multiplier from a date, are history entries labeled `scheduled`, and prices by modality are the `modalities` field. Explicit cache hits were the first new price field: `cache_read_explicit` carries models.dev's `cache.explicit.read` where it differs from the cache read price, and the check compares models.dev's time-of-day multipliers and cache write prices by lifetime with `schedules.toml` and `cache_writes.toml`. The order below puts first the prices that are wrong today in ways callers cannot see.

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
