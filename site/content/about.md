+++
title = "About the data"
description = "Where model-prices' prices come from, how they are checked, and how their dates are found."

[extra]
navigation_group = "prices"
+++

model-prices records the API price of every model sold by the labs that sell their own models, and when each price took effect, so usage is priced at the rate in effect when it happened. The same data is published as the [model-prices Python package](https://pypi.org/project/model-prices/) and as a JSON snapshot on the repository's [`data` branch](https://github.com/wakamex/model-prices/tree/data).

## Sources

Most prices come from the git history of [models.dev](https://github.com/sst/models.dev), an open catalog of model metadata: each commit that changed a price starts a new price from that commit's time. Models that models.dev does not list are read from the provider's own pricing page, and dated by the first daily run that saw them.

## Checks

Every day, and within minutes of a models.dev change, model-prices reads each provider's official pricing page and compares every price it lists with the price model-prices uses. A provider whose prices disagree is held back until the difference is resolved. Each model page says whether its current price matches the official page.

## Corrections and dates

models.dev sometimes records a change days late, or a wrong price for a while. A correction overrides those periods with the official price, and cites its source, such as the provider's announcement, its changelog, or an archived copy of its pricing page. The [Corrections](../corrections/) page lists every one. Each price on a model page says how its start date was found:

- `models.dev commit`: the time models.dev recorded it, which usually lags the provider's change by days.
- `documented`: a date from a correction's cited source.
- `first observed`: the first daily run that read the price on the provider's page.

## What is not priced

Prices are for standard synchronous requests, plus the modes models.dev records for some models, such as OpenAI's flex and fast modes and Anthropic's fast mode, which each model page lists. Batch pricing, regional surcharges, storage for cached context, tool fees such as web search, and per-image or per-second prices are not priced. Each model has one input and one output price: for image and video generation models the output price is that of the media they generate.

## License

The price history derives from [models.dev](https://github.com/sst/models.dev), used under its [MIT license](https://github.com/wakamex/model-prices/blob/main/data/LICENSE.models.dev). model-prices is MIT licensed, and its source is on [GitHub](https://github.com/wakamex/model-prices).
