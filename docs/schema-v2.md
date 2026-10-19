# Deferred to snapshot schema v2

These changes need a field the v1 snapshot does not have. A release builds each compiled rate entry into a `Rates` object directly, so an unknown field in a published snapshot raises `TypeError` in 0.0.4 and every earlier release, instead of being ignored. Adding a field therefore means publishing a v2 snapshot beside v1, under `v2/` on the `data` branch, while v1 keeps being published without the field for existing installs, and a release that reads v2.

Trigger: do these together when a change needs schema v2 anyway, or when a caller needs one of them priced exactly. Until then, the approximations below stay.

## Alibaba explicit cache hits

Alibaba bills an implicit cache hit, which needs no setup, at 20% of input, and an explicit cache hit, from a request with `cache_control` markers, at 10% of input; a request uses one mode or the other ([context cache](https://www.alibabacloud.com/help/en/model-studio/context-cache)). Each model has one cache-read price, so a model with implicit caching prices every hit at 20%, and an explicit hit on it costs twice what Alibaba charges, such as $0.08 instead of $0.04 per million cached tokens on `qwen-plus`. Models with only explicit caching price their hits at 10%, which is exact.

Plan: follow the one-hour cache write precedent. A per-provider multiple of input for explicit hits, recorded beside `cache_write_1h` in `data/cache_writes.toml` and compiled into each rate entry, and a `cache_read_explicit_tokens` argument to `cost()` and `breakdown()`. A caller can tell explicit hits apart, since it sent the markers and only explicit caching reports `cache_creation_input_tokens`.

## Perplexity tool fees

Perplexity's Agent API, which replaced Sonar Chat Completions on 2026-09-27, bills tool calls, such as web search, beside tokens ([models](https://docs.perplexity.ai/docs/agent-api/models)). Sonar Chat Completions added a per-request fee that depended on the search context size, and Sonar Deep Research also billed citation tokens, reasoning tokens, and search queries. model-prices prices input and output tokens only.

Plan: per-call tool prices on the rate entry, and matching arguments to `cost()`.

## Prices by modality

Google prices input and output tokens by modality: Gemini 3.1 Flash Image charges $3 per million text and thinking output tokens and $60 per million image tokens, and Gemini 3.8 Live charges $0.75 for text input and $3.00 for audio input ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). Each model has one input and one output price, chosen as models.dev chooses them: the text price, except that an image or video generation model's output is the price of what it generates, and a cell without a text price gives its one price. A request that mixes modalities is priced at that one rate, so an image model's text and thinking output costs the image price, and a Live model's audio costs the text price.

Plan: optional per-modality prices on the rate entry, such as `output_image` and `input_audio`, which models.dev already records for some models, and matching token arguments to `cost()`, with the current single prices kept as the default for tokens given without a modality.

## Unknown fields

A v2 release should build `Rates` from the fields it knows and ignore the rest, so a later field that only adds information does not need another schema version.
