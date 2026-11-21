from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from model_prices import checks, compiler, readings

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://platform.claude.com/docs/en/about-claude/pricing.md"


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.archive, self.store = self.root / "archive", self.root / "store"
        (self.archive / "blobs").mkdir(parents=True)
        self.page = (FIXTURES / "anthropic.md").read_text()
        # Opus 5.5's $4 input, as Anthropic's page stated it in November 2026, raised to $5.
        self.raised = self.page.replace("| Claude Opus 5.5 | $4 / MTok", "| Claude Opus 5.5 | $5 / MTok", 1)
        self.assertNotEqual(self.raised, self.page)
        # The fixture is an excerpt, shorter than the live page's minimum.
        self.enterContext(mock.patch.dict(checks.MINIMUM_MODELS, {"anthropic": 0}))

    def tearDown(self):
        self.directory.cleanup()

    def fetch(self, run: str, at: str, body: str | None):
        entry = {"run": run, "fetched_at": at, "url": URL, "status": 200 if body else 503,
                 "sha256": None, "error": None if body else "Service Unavailable"}
        if body:
            entry["sha256"] = hashlib.sha256(body.encode()).hexdigest()
            (self.archive / "blobs" / entry["sha256"]).write_text(body)
        with (self.archive / "fetches.jsonl").open("a") as log:
            log.write(json.dumps(entry) + "\n")

    def test_runs_are_read_once_into_dated_page_history(self):
        self.fetch("1", "2026-11-10T06:00:00Z", self.page)
        self.fetch("2", "2026-11-10T12:00:00Z", None)
        self.fetch("3", "2026-11-11T06:00:00Z", self.raised)
        self.fetch("4", "2026-11-12T06:00:00Z", self.page)
        # Anthropic's pricing page is read for its prices and for its web search fee.
        self.assertEqual(readings.record(self.archive, self.store), 8)
        # A second pass adds nothing: a reading, once recorded, is never read again.
        self.assertEqual(readings.record(self.archive, self.store), 0)

        log = [line for line in readings.load_log(self.store) if line["reader"] == "anthropic"]
        self.assertEqual([line["run"] for line in log], ["1", "2", "3", "4"])
        self.assertIn("was not stored in run 2: Service Unavailable", log[1]["error"])
        # The same page gives the same reading, stored once.
        self.assertEqual(log[0]["reading"], log[3]["reading"])
        self.assertEqual(log[0]["inputs"], {URL: hashlib.sha256(self.page.encode()).hexdigest()})
        # The fixture, an excerpt, leaves out the web search fee, which fails that reader alone.
        tools = [line for line in readings.load_log(self.store) if line["reader"] == "anthropic:tools"]
        self.assertEqual(len(tools), 4)
        self.assertTrue(all("no web_search price" in line["error"] for line in tools if line["run"] != "2"))

        # A run whose reading differs from the one before it is what starts a full update.
        self.assertEqual([readings.changed(self.store, run) for run in "1234"],
                         [[], [], ["anthropic"], ["anthropic"]])

        changes = [change for change in readings.history(readings.readings(self.store))
                   if change.key[0] == "anthropic" and dict(change.key[1:]) == {
                       "field": '"input"', "model": '"claude-opus-5-5"'}]
        self.assertEqual([(change.value, change.first_seen, change.last_before) for change in changes],
                         [(4, "2026-11-10T06:00:00Z", None),
                          (5, "2026-11-11T06:00:00Z", "2026-11-10T06:00:00Z"),
                          (4, "2026-11-12T06:00:00Z", "2026-11-11T06:00:00Z")])

        differences = readings.diff(readings.readings(self.store))
        self.assertEqual([(item.model, item.field, item.official, item.published, item.since, item.until)
                          for item in differences],
                         [("anthropic/claude-opus-5-5", "input", 5, 4,
                           "2026-11-11T06:00:00Z", "2026-11-11T06:00:00Z")])

    def test_a_failed_reading_is_read_again_after_a_parser_fix(self):
        self.fetch("1", "2026-11-10T06:00:00Z", self.page)
        self.fetch("2", "2026-11-10T12:00:00Z", None)
        # A parser that fails on the page, as before a fix.
        with mock.patch.dict(checks.MINIMUM_MODELS, {"anthropic": 1000}):
            readings.record(self.archive, self.store)
        retryable = {(line["run"], line["reader"]) for line in readings.retryable(self.store)}
        # A page the run did not store cannot be read again; the excerpt's missing web search
        # fee fails again on the same page.
        self.assertEqual(retryable, {("1", "anthropic"), ("1", "anthropic:tools")})
        self.assertEqual(readings.retry_pages(self.store, self.archive),
                         {hashlib.sha256(self.page.encode()).hexdigest()})
        self.assertEqual(readings.retry(self.archive, self.store), 1)
        fixed = next(line for line in readings.load_log(self.store) if line["reader"] == "anthropic")
        self.assertEqual((fixed["run"], "reading" in fixed), ("1", True))
        self.assertEqual(readings.retry(self.archive, self.store), 0)

    def test_a_reading_is_read_again_when_its_reader_gains_a_version(self):
        self.fetch("1", "2026-11-10T06:00:00Z", self.page)
        self.fetch("2", "2026-11-11T06:00:00Z", self.page)
        readings.record(self.archive, self.store)
        self.assertEqual(readings.retryable(self.store)[0]["reader"], "anthropic:tools")
        # A parser change that alters successful readings raises its reader's version.
        with mock.patch.dict(readings.VERSIONS, {"anthropic": 2}):
            outdated = {(line["run"], line["reader"]) for line in readings.retryable(self.store)
                        if line["reader"] == "anthropic"}
            self.assertEqual(outdated, {("1", "anthropic"), ("2", "anthropic")})
            # Only the pages those readings read are needed, and for the failed tool readings
            # every page their runs stored.
            self.assertEqual(readings.retry_pages(self.store, self.archive),
                             {hashlib.sha256(self.page.encode()).hexdigest()})
            self.assertEqual(readings.retry(self.archive, self.store), 2)
            lines = [line for line in readings.load_log(self.store) if line["reader"] == "anthropic"]
            self.assertEqual([line.get("version") for line in lines], [2, 2])
            self.assertFalse(any(line["reader"] == "anthropic" for line in readings.retryable(self.store)))

    def test_a_run_that_stored_only_a_bare_shell_is_not_read_again(self):
        body = "<html>shell</html>"
        digest = hashlib.sha256(body.encode()).hexdigest()
        (self.archive / "blobs" / digest).write_text(body)
        entry = {"run": "1", "fetched_at": "2026-11-18T21:25:38Z", "url": checks.BYTEPLUS_PRICING,
                 "status": 200, "sha256": digest}
        (self.archive / "fetches.jsonl").write_text(json.dumps(entry) + "\n")
        readings.record(self.archive, self.store)
        line = next(line for line in readings.load_log(self.store) if line["reader"] == "byteplus")
        self.assertIn("bare shell", line["error"])
        self.assertEqual(readings.retryable(self.store), [])

    def test_every_reader_names_a_page_a_run_fetches(self):
        # Each kind of source is read: pricing pages, pages for models models.dev lacks, tool
        # fees, peak-hour terms, batch discounts, regional factors, and subscription plans.
        names = set(readings.READERS)
        for name in ("anthropic", "cognition", "openai:tools", "deepseek:terms:zh", "xai:batch",
                     "openai:regions", "plan:moonshotai"):
            self.assertIn(name, names)
        self.assertFalse(readings.READERS["openai:regions"].hourly)
        self.assertEqual(readings.READERS["plan:moonshotai"].payload, b"{}")

    def test_a_reading_does_not_depend_on_the_hour_it_was_made(self):
        # DeepSeek's peak and off-peak prices are compared at the next such hour after a reading.
        page = (FIXTURES / "deepseek.html").read_text()
        morning, evening = (checks.parse("deepseek", page, datetime(2026, 11, 12, hour, tzinfo=timezone.utc),
                                         None) for hour in (5, 21))
        self.assertNotEqual({item.at for item in morning}, {item.at for item in evening})
        self.assertEqual(sorted(map(readings._sort_key, map(readings._price, morning))),
                         sorted(map(readings._sort_key, map(readings._price, evening))))

class PageBuildTests(unittest.TestCase):
    URL = "https://example.com/pricing"

    def page(self, at, rates):
        return {"valid_from": at, "source": self.URL, "rates": rates}

    def test_a_page_states_its_prices_over_models_dev_from_its_first_reading(self):
        entries = [{"valid_from": "2026-10-01T00:00:00Z", "commit": "a",
                    "rates": {"input": 1.25, "output": 7.5, "cache_read": 0.125,
                              "tiers": [{"above": 272000, "input": 2.5}]}},
                   {"valid_from": "2026-11-20T00:00:00Z", "commit": "b",
                    "rates": {"input": 1.25, "output": 7.5, "cache_read": 0.125, "cache_write": 1.5}},
                   # A change models.dev records ahead of its date, after the last reading.
                   {"valid_from": "2027-01-01T00:00:00Z", "commit": "c", "scheduled": True,
                    "rates": {"input": 2.5, "output": 15.0}}]
        pages = [self.page("2026-11-12T06:00:00Z", {"input": 1.25, "output": 7.5, "cache_read": 0.13}),
                 self.page("2026-11-13T06:00:00Z", {"input": 1.0, "output": 7.5, "cache_read": 0.13})]
        merged = compiler._with_pages(entries, pages)
        self.assertEqual([entry["valid_from"] for entry in merged],
                         ["2026-10-01T00:00:00Z", "2026-11-12T06:00:00Z", "2026-11-13T06:00:00Z",
                          "2026-11-20T00:00:00Z", "2027-01-01T00:00:00Z"])
        # The page's $0.13 is models.dev's $0.125 shown rounded, so the exact price is kept;
        # fields the page does not state, such as tiers, stay models.dev's.
        self.assertEqual(merged[1]["rates"]["cache_read"], 0.125)
        self.assertEqual(merged[1]["rates"]["tiers"], [{"above": 272000, "input": 2.5}])
        self.assertEqual((merged[1]["source"], merged[2]["rates"]["input"]), (self.URL, 1.0))
        # A later models.dev change to a field the page does not state keeps the page's prices.
        self.assertEqual((merged[3]["commit"], merged[3]["rates"]["input"], merged[3]["rates"]["cache_write"]),
                         ("b", 1.0, 1.5))
        # A scheduled change after the last reading applies as models.dev records it.
        self.assertEqual(merged[4], entries[2])

    def test_the_build_prices_a_model_from_its_page(self):
        pages = {("anthropic", "claude-opus-5-5"): [
            self.page("2026-11-12T06:00:00Z", {"input": 4.0, "output": 20.0}),
            self.page("2026-11-13T06:00:00Z", {"input": 5.0, "output": 20.0})]}
        built = compiler.build(Path(__file__).parent.parent / "data", pages)
        timeline = built["prices"]["anthropic"]["claude-opus-5-5"]["standard"]
        rates = readings._at(timeline, "2026-11-13T07:00:00Z")
        self.assertEqual((rates["input"], rates["valid_from"], rates["valid_from_basis"]),
                         (5.0, "2026-11-13T06:00:00Z", "first observed"))
        # The cache prices the page excerpt does not state stay models.dev's.
        self.assertEqual(rates["cache_read"], readings._at(timeline, "2026-11-01T00:00:00Z")["cache_read"])


    def test_a_page_listing_a_model_before_models_dev_keeps_its_unstated_fields(self):
        # OpenAI's page listed GPT-6.2 Sol eight minutes before models.dev, whose entry gives
        # the web search fee the page's prices table does not.
        entries = [{"valid_from": "2026-11-17T18:07:07Z", "commit": "a",
                    "rates": {"input": 2.0, "output": 10.0, "tools": {"web_search": 10.0}}}]
        merged = compiler._with_pages(entries, [self.page("2026-11-17T17:59:44Z", {"input": 2.0, "output": 10.0})])
        self.assertEqual(merged[0]["rates"]["tools"], {"web_search": 10.0})

    def test_differences_are_listed_once_as_additions_or_changes(self):
        def timeline(*intervals):
            return [{"start": start, "rates": rates} for start, rates in intervals]
        published = {"prices": {"p": {"m": {"standard": timeline((None, {"input": 1.0}))}}}}
        built = {"prices": {"p": {"m": {
            "standard": timeline((None, {"input": 1.0}), ("2026-11-13T00:00:00Z", {"input": 1.0}),
                                 ("2026-11-14T00:00:00Z", {"input": 2.0})),
            "thinking": timeline((None, {"output": 3.0}), ("2026-11-14T00:00:00Z", {"output": 3.0}))}}}}
        self.assertEqual(readings._differences(built, published, "2026-11-12T00:00:00Z"), [
            "changes  p/m standard from 2026-11-14T00:00:00Z: input 1.0 -> 2.0",
            "adds     p/m thinking from 2026-11-12T00:00:00Z: output none -> 3.0"])

    def test_an_impossible_price_fails_the_build_and_an_unlikely_one_is_reported(self):
        pages = {("anthropic", "claude-opus-5-5"): [
            self.page("2026-11-12T06:00:00Z", {"input": 4.0, "output": 20.0}),
            # A per-thousand row read as per million, and cached input above input.
            self.page("2026-11-13T06:00:00Z", {"input": 0.004, "output": 20.0, "cache_read": 0.2}),
            self.page("2026-11-14T06:00:00Z", {"input": 4.0, "output": 0.0})]}
        built = compiler.build(Path(__file__).parent.parent / "data", pages)
        self.assertEqual(readings.impossible(built, "2026-11-12T06:00:00Z"),
                         ["anthropic/claude-opus-5-5 from 2026-11-13T06:00:00Z: "
                          "cached input $0.2 above input $0.004; "
                          "cached input $0.1 above input $0.002 in batch"])
        self.assertEqual(readings.unlikely(pages), [
            "anthropic/claude-opus-5-5 input $0.004 from 2026-11-13T06:00:00Z: "
            "outside $0.01 to $1000, 0.001 times $4",
            "anthropic/claude-opus-5-5 input $4 from 2026-11-14T06:00:00Z: 1e+03 times $0.004",
            "anthropic/claude-opus-5-5 output $0 from 2026-11-14T06:00:00Z: from $20"])


if __name__ == "__main__":
    unittest.main()
