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

## Review

Verification shows that each quote is on its page, not that it is about the right model or event. A second agent therefore reviews every verified finding before it can become a correction: `review-manifest` writes one task per finding, and each reviewer receives the change, the finding, and the cited pages, with web access disabled. It checks that each quote concerns this model and this change, that the quotes support the classification, that the sources place the price in the right period, and that any official price matches a quote. `collect-reviews` appends each verdict to the finding's `reviews.jsonl`, tagged with a hash of the review prompt.

Single reviews are noisy: across three passes of the same prompt over 111 findings, two reviews of the same finding agreed 83% of the time. `corrections` therefore applies a finding only when most of at least three reviews made with the current prompt support it. The gate errs toward leaving models.dev's data in place; it rejects some correct findings, such as Sonnet 4.6's March 13 change, whose saved page lacks its publication date. Run several passes with `PASSES=3 run-reviews.sh`, or one `aop batch review-batch.toml` per pass followed by `collect-reviews`.

## From finding to correction

`price_dates.py corrections` turns verified, reviewed findings into `src/llm_prices/data/research_corrections.toml`, which is generated and not edited by hand. A `models_dev_fix` keeps models.dev's earlier entry over its whole period and replaces only the prices the finding quotes, together with those quoted for a fix that directly follows it; a correction never copies an unquoted value from models.dev's later entry, which was itself sometimes wrong. A dated `price_change` moves the start of the new price to the documented date, or keeps the old price until that date when models.dev recorded the change early. A date without a time applies from 00:00 UTC. When sources only bracket a change, the earlier documented price applies until the first observation of the new one.

The command lists every verified finding it leaves out: changes without a documented date, changes dated before the earlier price was even recorded (usually a quote about a different event), findings marked in its `REVIEWED` table after reading them, and periods that `corrections.toml` already covers. Hand corrections in `corrections.toml` take precedence over researched ones.

## Cross-check against genai-prices

`crosscheck_genai_prices.py GENAI_PRICES_CHECKOUT` prices every correction's period with [Pydantic's genai-prices](https://github.com/pydantic/genai-prices), both from its current data, which dates a few changes, and from the `data.json` it had committed at that time. Each corrected field is reported as agreeing with the correction, with models.dev, with neither, or as missing from genai-prices.

genai-prices lags providers much as models.dev does: on 2026-10-01 it agreed with models.dev against DeepSeek's own pricing page and OpenAI's GPT-5.6 Sol announcement. Agreement with models.dev is therefore weak evidence against a correction, and a disagreement is a lead to check against archived copies of the provider's page. The first run found two wrong corrections this way: Gemini 3.6 Flash's promotional price taken as its price since launch, which archived copies date to 2026-08-13, and a Claude Opus 4 cache-write price copied from models.dev's own wrong entry.

`score_dating.py GENAI_PRICES_CHECKOUT` measures how promptly each source recorded nine price changes whose times are known from provider announcements or archived pricing pages. On 2026-10-01 models.dev recorded seven of them, from 12 hours to 7.5 days late, and never recorded DeepSeek's peak pricing. genai-prices committed only the Claude 4.6 long-context change, 4.5 days late but with the correct 2026-03-13 start date, and still lists the old price for the other seven changes to models it carries.

## Calibration

The workflow was calibrated on four changes already researched by hand. GPT-6 Luna at medium effort classified all four correctly, taking 53 to 134 seconds and about $0.005 to $0.010 API-equivalent each. It also found two errors in the hand-made corrections: GPT-5.6 Sol's cut started on August 21, not August 22, and GLM-5.3 Flash's $0.075 was a real promotional price until early September, not a models.dev error.
