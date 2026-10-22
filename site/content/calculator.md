+++
title = "Calculator"
description = "Price one LLM API request at the rates in effect at any time."
template = "calculator.html"

[extra]
navigation_group = "prices"
+++

Price one request at the rates in effect when it ran. Pick the model and the request time in UTC, then enter its tokens by type.

Input counts only uncached prompt tokens, so take cache reads and writes out of a provider's prompt total first. Anthropic's `input_tokens` already excludes `cache_read_input_tokens` and `cache_creation_input_tokens`. OpenAI's `prompt_tokens` includes `prompt_tokens_details.cached_tokens`, and Google's `prompt_token_count` includes `cached_content_token_count`, so subtract those. Longer-lived cache writes, shown only for providers that sell them, are one-hour writes for Anthropic and Moonshot AI and 12-hour writes for OpenAI. A long-context tier applies when the request's whole prompt, uncached input plus cache reads and writes, exceeds the tier's size.

The calculator runs in your browser on the same data as the [model-prices Python package](https://pypi.org/project/model-prices/), and a test checks that it gives the same result as `model_prices.cost()` on thousands of requests.
