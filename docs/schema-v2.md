# Prices planned for snapshot schema 2

[models.dev](https://models.dev)'s schema 2 model files record prices that snapshot schema 1 had no field for. Most are now carried, as the third paragraph lists; this page plans the rest: tool fees, and OpenAI's regional uplift, which models.dev does not record. model-prices reads those files through a translation in `src/model_prices/backfill.py`, a port of the one models.dev uses to publish its data in schema 1, which keeps text prices, cache read and write prices, long-prompt tiers, reasoning prices, and modes.

From 0.0.6 the package reads the schema 2 snapshot under `v2/` on the `data` branch and ignores rate fields it does not know, so each price below can be added to that snapshot on its own. Releases up to 0.0.5 raise on an unknown field, so `v1/` keeps being published with only the fields they know. Each model's history stays a timeline that clients look up by time: model-prices compiles conditions into the timeline and into fields, and does not ask clients to evaluate models.dev's condition language, which combines conditions with `any`, `all`, and `not` over hours, weekdays, holidays, dates, regions, and service tiers.

These prices are carried, as the README describes: dated price changes, which models.dev records as a multiplier from a date, are history entries labeled `scheduled`; service tiers are modes named after the tier, such as `flex` and `priority`; prices by modality are the `modalities` field; and regional factors are the `regions` field with a `region` argument. Explicit cache hits were the first new price field: `cache_read_explicit` carries models.dev's `cache.explicit.read` where it differs from the cache read price, and the check compares models.dev's time-of-day multipliers and cache write prices by lifetime with `schedules.toml` and `cache_writes.toml`. The order below puts first the prices that are wrong today in ways callers cannot see.

## OpenAI's regional uplift

OpenAI charges a 10% uplift on data residency endpoints, such as `us.api.openai.com` and `eu.api.openai.com`, for models released on or after 2026-03-05 that are eligible for data residency ([pricing](https://developers.openai.com/api/docs/pricing), [your data](https://developers.openai.com/api/docs/guides/your-data)). models.dev does not record it, and its files give release dates for only some OpenAI models, so the models it covers cannot be read from models.dev. Plan: a hand-kept rule naming those models, from OpenAI's model pages and data residency table, giving each the factor 1.1 for every regional prefix, which `Rates.regions` then carries like Anthropic's and xAI's factors.

## Tool fees

Web search costs $10 per 1,000 calls at OpenAI and Anthropic, $14 at Google, and $5 at xAI, and Perplexity's Agent API, which replaced Sonar Chat Completions on 2026-09-27, bills tool calls beside tokens ([models](https://docs.perplexity.ai/docs/agent-api/models)). These are priced per call, not per million tokens, so pricing them turns `cost()` from a token price into a request's whole bill.

Plan: per-call tool prices on the rate entry, and either call counts per tool in `cost()` or a separate function for tool fees, decided when this is built. It comes last, in its own release.
