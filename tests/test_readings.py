from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from model_prices import checks, readings

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

if __name__ == "__main__":
    unittest.main()
