+++
title = "About the data"
description = "Where model-prices' prices come from, how they are checked, and how their dates are found."

[extra]
navigation_group = "prices"
+++

model-prices records the per-token price of every model sold by the labs that sell their own models, and when each price took effect, so usage is priced at the rate in effect when it happened. That prices pay-per-token usage, and shows what a subscription's usage would cost at the same rates; the [Plans](../plans/) page lists the subscriptions themselves. The same data is published as the [model-prices Python package](https://pypi.org/project/model-prices/) and as a JSON snapshot on the repository's [`data` branch](https://github.com/wakamex/model-prices/tree/data).

## Sources

Most prices come from the git history of [models.dev](https://github.com/sst/models.dev), an open catalog of model metadata: each commit that changed a price starts a new price from that commit's time. Models that models.dev does not list, such as Cursor's Composer models and Cognition's SWE models, are read from the provider's own pricing page, and dated by the first run that saw them. Fees and discounts that apply across a provider's models and that no page lists per model, such as a batch discount or a peak-hour multiplier, come from rules that cite the provider's documentation and the date each began.

## Checks

Every day, within minutes of a models.dev change, and whenever an hourly reading of the providers' pricing pages finds a changed price, model-prices reads each provider's official pricing page and compares every price it lists with the price model-prices uses. A provider whose prices disagree is held back from the published data until the difference is resolved, so the data keeps that provider's last checked prices rather than taking an unchecked change. Each model page says whether its current price matches the official page. Subscription prices are checked against each lab's pricing page the same way.

Every page a check reads is kept in a private archive, and the time, address, and hash of each fetch, with the prices read from it, are published on the `data` branch, so a price can be traced to the page that stated it.

## Corrections and dates

models.dev sometimes records a change days late, or a wrong price for a while. A correction overrides those periods with the official price, and cites its source, such as the provider's announcement, its changelog, or an archived copy of its pricing page. The [Corrections](../corrections/) page lists every one. Each price on a model page says how its start date was found:

- `models.dev commit`: the time models.dev recorded it, which usually lags the provider's change by days.
- `documented`: a date from a correction's cited source.
- `first observed`: the first run that read the price on the provider's page.
- `scheduled`: a change the provider announced ahead of its date.

## What is priced

Prices cover standard requests and the service tiers each model page lists, such as OpenAI's flex and priority tiers and Anthropic's fast mode, along with:

- Batch API prices for Anthropic, OpenAI, Google, and xAI, at each provider's batch discount from the date it began, checked against the batch tables on their pricing pages. Mistral's batch discount is left out, since its pricing page names the models it covers only in a browser.
- Long-context tiers, which apply when a request's whole prompt exceeds the tier's size.
- Time-of-day prices, such as DeepSeek's peak hours.
- Regional prices: Anthropic's US-only inference, xAI's US endpoint, and OpenAI's data residency endpoints, which each cost 1.1 times the listed price on the models they cover.
- Audio, image, and video tokens, at their own prices where a provider prices them apart from text.
- Web search fees, per 1,000 billable calls, which the [calculator](../calculator/) takes as call counts.

Not priced: storage for cached context, tool fees other than web search, and prices per image, per second, or per minute, such as those of image models priced per image and of speech endpoints that report no tokens.

## License

The price history derives from [models.dev](https://github.com/sst/models.dev), used under its [MIT license](https://github.com/wakamex/model-prices/blob/main/data/LICENSE.models.dev). model-prices is MIT licensed, and its source is on [GitHub](https://github.com/wakamex/model-prices).
