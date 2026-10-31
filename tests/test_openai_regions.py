from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from model_prices import openai_regions as regions
from model_prices.observe import observe_regions

# Excerpts in the formats of OpenAI's pages on 2026-10-31.
PRICING = ("Regional processing (data residency) endpoints are charged a 10% uplift for models "
           "released on or after March 5, 2026. FedRAMP endpoints are also charged a 10% uplift.")
YOUR_DATA = """### Support by region

| Region                     | Domain prefix       | Regional storage | Regional processing | MAM or ZDR required |
| -------------------------- | ------------------- | :--------------: | :-----------------: | :-----------------: |
| United States              | `us.api.openai.com` |       Yes        |         Yes         |         No          |
| Europe (EEA + Switzerland) | `eu.api.openai.com` |       Yes        |         Yes         |       Yes\\*\\*       |
| Japan\\*                    | `jp.api.openai.com` |       Yes        |         No          |         Yes         |
| United Arab Emirates\\*     | `ae.api.openai.com` |       Yes        |         Yes         |         Yes         |

#### API Endpoint, tool and model support

| Endpoint or feature | Service | Storage regions | Processing regions | Supported models and snapshots | Regional processing snapshot exceptions | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `/v1/chat/completions` | Chat Completions | All listed regions | United States, Europe (EEA + Switzerland), United Arab Emirates | `gpt-6.1-sol`, `gpt-5.6-luna`, `gpt-5.5-2026-04-23`, `gpt-4.1-2025-04-14`, `gpt-realtime-1.5` | United Arab Emirates: `gpt-5.6-luna`, `gpt-5.5-2026-04-23` | |
| `/v1/files` | Files | All listed regions | None | Service-level support | | |
"""
CHANGELOG = """# Changelog

## July, 2026

### Jul 9

Feature · Model: gpt-5.6-luna · API: v1/responses

Released GPT-5.6 Luna.

## February, 2026

### Feb 23

Feature · Model: gpt-realtime-1.5

Released GPT-Realtime-1.5.

### Feb 20

Update · Model: gpt-6.1-sol

An update that is not a release.
"""
PAGES = {
    "gpt-6.1-sol": "- Apr 30, 2026 knowledge cutoff\n- Regional processing adds a 10% premium where available.\n",
    "gpt-5.6-luna": "- Feb 16, 2026 knowledge cutoff\n\n## Snapshots\n\n- `gpt-5.6-luna`\n",
    "gpt-5.5": "- Regional processing (data residency) endpoints are charged a 10% uplift for GPT-5.5.\n",
    "gpt-4.1": "- Jun 01, 2024 knowledge cutoff\n",
    "gpt-realtime-1.5": "- Sep 30, 2024 knowledge cutoff\n",
}


def _get(overrides=None):
    pages = {regions.PRICING: PRICING, regions.YOUR_DATA: YOUR_DATA, regions.CHANGELOG: CHANGELOG,
             **{regions.model_page(name): page for name, page in PAGES.items()}, **(overrides or {})}
    return pages.__getitem__


class OpenAIRegionTests(unittest.TestCase):
    def test_regional_factors_follow_openai_pages(self):
        found = regions.read(_get())

        # Regional processing regions only, narrowed by a region's listed snapshots; a model
        # released before the cutoff, by its snapshot date or its changelog release, has none.
        self.assertEqual(found.factors, {
            "gpt-6.1-sol": {"eu": 1.1, "us": 1.1},
            "gpt-5.6-luna": {"ae": 1.1, "eu": 1.1, "us": 1.1},
            "gpt-5.5-2026-04-23": {"ae": 1.1, "eu": 1.1, "us": 1.1},
            "gpt-5.5": {"ae": 1.1, "eu": 1.1, "us": 1.1}})
        self.assertEqual(found.conflicts, {})

    def test_evidence_that_disagrees_is_a_conflict(self):
        # A page stating the uplift for a model released before the cutoff.
        found = regions.read(_get({regions.model_page("gpt-realtime-1.5"):
                                   "- Regional processing adds a 10% premium where available.\n"}))
        self.assertIn("gpt-realtime-1.5", found.conflicts)
        self.assertNotIn("gpt-realtime-1.5", found.factors)

    def test_changed_pages_fail_loudly(self):
        for url, page in ((regions.PRICING, "Prices"), (regions.YOUR_DATA, "# Your data"),
                          (regions.CHANGELOG, "# Changelog")):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "openai"):
                regions.read(_get({url: page}))

    def test_side_of_the_cutoff(self):
        cutoff = date(2026, 3, 5)
        page = regions.parse_model_page("- Jun 01, 2024 knowledge cutoff\n")
        self.assertFalse(regions.side("gpt-4.1-2025-04-14", cutoff, page, {}).after)
        self.assertTrue(regions.side("gpt-5.4-2026-03-05", cutoff, page, {}).after)
        # Without a dated snapshot or a statement, a model with no evidence gets no uplift.
        self.assertFalse(regions.side("tts-1", cutoff, page, {}).after)

    def test_observed_factors_are_dated_by_the_first_run_that_read_them(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "observed_regions.json"
            first = datetime(2026, 10, 31, 17, tzinfo=timezone.utc)
            self.assertTrue(observe_regions(output, _get(), first))
            self.assertFalse(observe_regions(output, _get(), datetime(2026, 11, 1, tzinfo=timezone.utc)))
            entries = json.loads(output.read_text())["providers"]["openai"]["gpt-6.1-sol"]
        self.assertEqual(entries, [{"valid_from": "2026-10-31T17:00:00Z", "source": regions.YOUR_DATA,
                                    "regions": {"eu": 1.1, "us": 1.1}}])


if __name__ == "__main__":
    unittest.main()
