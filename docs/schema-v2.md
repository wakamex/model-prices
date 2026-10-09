# Deferred to snapshot schema v2

These changes need a field the v1 snapshot does not have. A release builds each compiled rate entry into a `Rates` object directly, so an unknown field in a published snapshot raises `TypeError` in 0.0.4 and every earlier release, instead of being ignored. Adding a field therefore means publishing a v2 snapshot beside v1, under `v2/` on the `data` branch, while v1 keeps being published without the field for existing installs, and a release that reads v2.

Trigger: do these together when a change needs schema v2 anyway, or when a caller needs one of them priced exactly. Until then, the approximations below stay.

## Alibaba explicit cache hits

Alibaba bills an implicit cache hit, which needs no setup, at 20% of input, and an explicit cache hit, from a request with `cache_control` markers, at 10% of input; a request uses one mode or the other ([context cache](https://www.alibabacloud.com/help/en/model-studio/context-cache)). Each model has one cache-read price, so a model with implicit caching prices every hit at 20%, and an explicit hit on it costs twice what Alibaba charges, such as $0.08 instead of $0.04 per million cached tokens on `qwen-plus`. Models with only explicit caching price their hits at 10%, which is exact.

Plan: follow the one-hour cache write precedent. A per-provider multiple of input for explicit hits, recorded beside `cache_write_1h` in `data/cache_writes.toml` and compiled into each rate entry, and a `cache_read_explicit_tokens` argument to `cost()` and `breakdown()`. A caller can tell explicit hits apart, since it sent the markers and only explicit caching reports `cache_creation_input_tokens`.

## Perplexity per-request fees

Perplexity's Sonar models add a per-request fee that depends on the search context size, and Sonar Deep Research also bills citation tokens, reasoning tokens, and search queries. model-prices prices their input and output tokens only.

Plan: per-request and per-query prices on the rate entry, and matching arguments to `cost()`.

## Unknown fields

A v2 release should build `Rates` from the fields it knows and ignore the rest, so a later field that only adds information does not need another schema version.
