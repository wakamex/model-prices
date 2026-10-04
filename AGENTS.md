# Price sources

- Prefer prices read automatically from an official page over hand-entered ones. When models.dev lacks a provider or model whose official page publishes prices, make that page the source: have the daily job parse it and record a new entry whenever the price changes, dated by the first run that saw it, and backfill earlier periods through `research/price_dates.py gaps`. Hand-entered prices go stale silently, while a parsed page fails loudly when its layout changes. Check every format a page offers before calling it unparseable: Cursor's Markdown copies omit the rate tables that its HTML pages contain.

# Release policy exceptions

- `tests/fixtures/genai-prices.json` is a real excerpt of Pydantic's genai-prices data rather than a synthetic fixture, so the comparison is tested against its actual format. It is MIT licensed, and its license ships beside it as `tests/fixtures/LICENSE.genai-prices`.
