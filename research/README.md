# Price date research

models.dev dates each price by the commit that recorded it. That commit can follow the provider's change by days, or fix a price that was never correct. `price_dates.py` checks every recorded change against primary sources, using one inexpensive web-research agent per change through [AOP](https://github.com/wakamex/agent-orchestration-process), and verifies each finding by machine before it becomes a correction.

## Workflow

```sh
uv run --no-config python research/price_dates.py changes /path/to/models.dev   # list every change
uv run --no-config python research/price_dates.py manifest [--only ID ...]       # one task per change
(cd research/price-dates && aop batch batch.toml --jobs 8)                       # GPT-6 Luna, medium effort
uv run --no-config python research/price_dates.py collect .aop/batches/BATCH.json
uv run --no-config python research/price_dates.py verify
```

Each agent classifies a change as a real `price_change` or a `models_dev_fix` of a price that was never official, and finds the effective date from provider pages, changelogs, announcements, and Internet Archive copies. It must quote every claim verbatim from a page it saved.

`verify` extracts every cited URL to Markdown with `/code/scripts/extract_web.py` (raw files are fetched directly), records the URL and retrieval time in the file header, and checks each quote against that independent copy, falling back to the agent's own saved copy for pages that need JavaScript. Findings record which copy verified each quote.

## What is kept where

- `price-dates/changes.json`: every recorded change, with its models.dev commit and message. Committed.
- `price-dates/findings/<change>/finding.json`: each agent's classification, date, sources, quotes, and verification result, plus `run.json` with the AOP run, model, and cost. Committed.
- `sources/` and `price-dates/findings/<change>/sources/`: local copies of the cited third-party pages, for reuse by later research. Kept out of git, since the pages belong to their publishers.

## From finding to correction

Only a verified finding becomes a correction in `src/llm_prices/data/corrections.toml`. A `models_dev_fix` corrects the whole earlier period. A dated `price_change` moves the start of the new price to the documented date. When sources only bracket a change, the earlier documented price applies until the first observation of the new one.

## Calibration

The workflow was calibrated on four changes already researched by hand. GPT-6 Luna at medium effort classified all four correctly, taking 53 to 134 seconds and about $0.005 to $0.010 API-equivalent each. It also found two errors in the hand-made corrections: GPT-5.6 Sol's cut started on August 21, not August 22, and GLM-5.3 Flash's $0.075 was a real promotional price until early September, not a models.dev error.
