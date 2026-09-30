# llm-prices

LLM API prices as they were at any point in time. Pricing past usage at today's rates misstates it whenever a price changed: GPT-5.6 Sol cost $5/$30 per million input/output tokens until August 22, 2026, and $4/$20 after. This package answers "what did this request cost at API prices when it ran?"

```python
import llm_prices

llm_prices.cost(
    "gpt-5.6-sol",
    input_tokens=12_000,        # uncached input only
    cache_read_tokens=180_000,
    output_tokens=900,
    at="2026-08-20T14:00:00Z",
)

llm_prices.rates("claude-opus-5-5")  # current rates, per million tokens
```

```sh
llm-prices rate gpt-5.6-sol --at 2026-08-20
llm-prices rate "Gemini 3.5 Flash (High)" --json
```

## Install

Requires Python 3.12 or newer.

```sh
uv add llm-prices
```

## Where the prices come from

Prices come from the git history of [models.dev](https://github.com/sst/models.dev), an open catalog of model metadata that records each model's price in one TOML file per provider. Every commit on its main branch that changed a tracked model's price becomes an entry effective from that commit's time. The tracked providers are the labs that sell their own models: Alibaba, Anthropic, DeepSeek, Google, Moonshot AI, OpenAI, xAI, and Z.ai.

models.dev sometimes records a change days after the provider made it, or lists a wrong price for a while. `corrections.toml` overrides those periods, and every correction cites its source. Usage from before a model's first recorded price is priced at that first price.

Each entry keeps input, output, cache read, and cache write rates, long-context tiers, and alternate modes such as fast mode. A tier applies when one request's whole prompt, meaning uncached input plus cache reads and writes, exceeds the tier size. A missing cache price falls back to the input price.

## Model names

`resolve()` maps the names that logs and agent harnesses use to models.dev ids. It lowercases the name and normalizes display names such as `Gemini 3.5 Flash (High)`. It reads a `provider/` prefix or the `provider` argument as a hint, and removes effort suffixes such as `-high` and date suffixes such as `-20251001` when the full name is unknown. A model is looked up at its own lab before other labs that also serve it. A lab model name resolves to the first-party API id that serves it, using models.dev's `base_model` links and preferring ids that are not deprecated: DeepSeek serves `deepseek-v4.1-flash` as `deepseek-flash`, so that name gets `deepseek-flash`'s price. `aliases.toml` holds the few names that need an explicit mapping. Unknown models return `None` rather than a guessed price.

## Recording what was used

`pricing_basis()` returns an identifier such as `llm-prices-0.1.0+models.dev@e2bf2e470a1b`, naming the package version and the models.dev commit its data came from. Store it next to computed costs.

## Updating prices

A daily workflow clones models.dev, rebuilds `src/llm_prices/data/prices.json` with `llm-prices update`, and opens a pull request when a tracked price changed. Before merging, check each changed model's effective date against the provider's announcement and add a correction when models.dev recorded the change late.

To rebuild locally:

```sh
git clone https://github.com/sst/models.dev.git /tmp/models.dev
uv run --locked llm-prices update /tmp/models.dev
```

## Development

```sh
uv run --locked pytest
```

## License

MIT. Price data is derived from [models.dev](https://github.com/sst/models.dev), which is MIT licensed.
