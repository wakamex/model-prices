+++
title = "Calculator"
description = "Price one LLM API request at the rates in effect at any time."
template = "calculator.html"

[extra]
navigation_group = "prices"
+++

Price one request at the rates in effect when it ran. The calculator runs in your browser on the same price data as the [model-prices Python package](https://pypi.org/project/model-prices/), and gives the same result as `model_prices.cost()` to the last digit: a test compares the two on thousands of requests, including long-context tiers, peak and off-peak hours, and thinking mode.

Input tokens exclude cache reads and writes. Longer-lived cache writes are one-hour writes for Anthropic and Moonshot AI and 12-hour writes for OpenAI; other providers charge them as cache writes. A long-context tier applies when the request's whole prompt, uncached input plus cache reads and writes, exceeds the tier's size.
