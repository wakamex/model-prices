<!-- Excerpt of https://docs.x.ai/developers/pricing.md as served on 2026-11-07: its Batch API Pricing section. -->

## Batch API Pricing

The [Batch API](/developers/advanced-api-usage/batch-api) lets you process large volumes of requests asynchronously at a discount to standard pricing. The size of the discount varies by model. Batch requests are queued and processed in the background, with most completing within 24 hours.

| | Real-time API | Batch API |
|---|---|---|
| Token pricing | Standard rates | Discounted rates (varies by model) |
| Response time | Immediate (seconds) | Typically within 24 hours |
| Rate limits | Per-minute limits apply | Requests don't count towards rate limits |

The batch discount applies to all token types — input tokens, output tokens, cached tokens, and reasoning tokens. Batch discounts by model:

**20% off standard rates**

- grok-4.7
- grok-4.6
- grok-4.5
- grok-4.3
- grok-4.20-0309-reasoning
- grok-4.20-0309-non-reasoning
- grok-4.20-multi-agent-0309

Models not listed above have no batch discount.
