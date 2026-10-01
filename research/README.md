# Price date research

models.dev dates each price by the commit that recorded it. That commit can follow the provider's change by days, or fix a price that was never correct. `price_dates.py` checks every recorded change against primary sources, using one inexpensive web-research agent per change through [AOP](https://github.com/wakamex/agent-orchestration-process), and verifies each finding by machine before it becomes a correction.

## Workflow

```sh
uv run --no-config python research/price_dates.py changes /path/to/models.dev   # list every change
uv run --no-config python research/price_dates.py manifest [--only ID ...]       # one task per change
(cd research/price-dates && aop batch batch.toml --jobs 4)                       # GPT-6 Luna, medium effort
uv run --no-config python research/price_dates.py collect .aop/batches/BATCH.json
uv run --no-config python research/price_dates.py verify
```

Each agent classifies a change as a real `price_change` or a `models_dev_fix` of a price that was never official, and finds the effective date from provider pages, changelogs, announcements, and Internet Archive copies. It must quote every claim verbatim from the Markdown copy of a page.

Agents read pages from a shared library in `sources/`, one Markdown file per URL named by the first 16 hex digits of the URL's SHA-256, with the URL and retrieval time in its header and `sources/index.tsv` listing them all. Each run receives the library, `/code/scripts/extract_web.py`, and `price-dates/extract-deps/` as read-only inputs; sealed runs have the system Python but neither uv nor user packages, so `manifest` installs the extractor's dependencies into that directory once and agents run it with `PYTHONPATH=/inputs/extract-deps python3`. An agent uses the library copy of a page when there is one and extracts any other page with `extract_web.py`, which returns the site's own Markdown copy when it publishes one. It quotes only from those files and returns copies of every file it cites. `collect` adds the pages a run extracted and cited to the library, so later runs reuse them, and keeps the run's own copies with its finding; run large batches in waves so that early runs fill the library for later ones.

`verify` checks each quote against the library copy of its page, extracting any cited page the library lacks, and otherwise against the agent's own copy, which can differ when a page changed after the library copy was made. For findings from the first batch, made before the library existed, the agent's copy is the raw page it saved. Findings record which copy verified each quote.

## What is kept where

- `price-dates/changes.json`: every recorded change, with its models.dev commit and message. Committed.
- `price-dates/findings/<change>/finding.json`: each agent's classification, date, sources, quotes, and verification result, plus `run.json` with the AOP run, model, and cost. Committed.
- `sources/`: the Markdown library of cited third-party pages, for reuse by later research. Kept out of git, since the pages belong to their publishers. Raw pages saved by the first batch remain under `price-dates/findings/<change>/sources/`, also out of git.

## From finding to correction

Only a verified finding becomes a correction in `src/llm_prices/data/corrections.toml`. A `models_dev_fix` corrects the whole earlier period. A dated `price_change` moves the start of the new price to the documented date. When sources only bracket a change, the earlier documented price applies until the first observation of the new one.

## Calibration

The workflow was calibrated on four changes already researched by hand. GPT-6 Luna at medium effort classified all four correctly, taking 53 to 134 seconds and about $0.005 to $0.010 API-equivalent each. It also found two errors in the hand-made corrections: GPT-5.6 Sol's cut started on August 21, not August 22, and GLM-5.3 Flash's $0.075 was a real promotional price until early September, not a models.dev error.
