from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest import mock
import urllib.error

import model_prices
from model_prices import checks, main, plan_checks

FIXTURES = Path(__file__).parent / "fixtures" / "plans"
# Each source as served on 2026-11-06: the visible HTML of the web pages, and whole copies of
# the Markdown pages and of the JSON price feeds, which allow no provenance comment.
PAGES = {key: next(FIXTURES.glob(key + ".*")).read_text() for key in plan_checks.PLAN_PAGES}
TODAY = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
UNREADABLE = {"zai/lite", "zai/pro", "zai/max", "perplexity/max",
              "xai/plus", "xai/premium", "xai/super", "xai/ultra"}


def _results(pages=PAGES):
    return {result.model: result for result in plan_checks.check_plans(TODAY, pages)}


def _statuses(pages=PAGES):
    return {model: result.status for model, result in _results(pages).items()}


class PlanCheckTests(unittest.TestCase):
    def test_every_page_is_read_and_compared(self):
        statuses = _statuses()

        self.assertEqual({model for model, status in statuses.items() if status == "unchecked"}, UNREADABLE)
        self.assertEqual({status for model, status in statuses.items() if model not in UNREADABLE}, {"ok"})
        self.assertIn("unchecked zai/lite plan from https://z.ai/subscribe: no page can be read for it",
                      checks.report(plan_checks.check_plans(TODAY, PAGES)))

    def test_a_changed_price_is_a_mismatch_and_a_new_plan_one_plans_toml_lacks(self):
        feed = json.loads(PAGES["xiaomi"])
        feed["data"][0]["originalPrice"] = "7.00"
        feed["data"].append({**feed["data"][3], "planCode": "ultra", "originalPrice": "200.00"})
        results = _results({**PAGES, "xiaomi": json.dumps(feed)})

        self.assertEqual((results["xiaomi/lite"].status, results["xiaomi/lite"].official), ("mismatch", 7.0))
        self.assertEqual((results["xiaomi/ultra"].status, results["xiaomi/ultra"].effective), ("mismatch", None))
        self.assertIn("xiaomi/ultra plan: official $200, plans.toml not listed",
                      checks.report([results["xiaomi/ultra"]]))

    def test_an_unreadable_page_fails_alone_and_covers_its_plans(self):
        statuses = _statuses({**PAGES, "cursor": re.sub(r"\bSuper\b", "Turbo", PAGES["cursor"])})

        self.assertEqual(statuses["cursor"], "error")
        self.assertNotIn("cursor/plus", statuses)
        self.assertEqual(statuses["meta/power"], "ok")

    def test_ambiguous_or_changed_layouts_fail(self):
        feed = json.loads(PAGES["moonshotai"])
        for goods in feed["goods"]:
            goods["amounts"] = [amount for amount in goods["amounts"] if amount["currency"] != "USD"]
        steps = json.loads(PAGES["stepfun-ai"])
        steps["plans"][0]["type"] = 9
        changed = {
            # A plan listed at a second price.
            "cursor": PAGES["cursor"] + "<p>Plus</p><p>$9</p><p>/month</p>",
            # A struck-out original price before the plan's price.
            "google": PAGES["google"].replace("$4.99", "<s>$9.99</s> $4.99", 1),
            # A price shown beside the plan's other than the labelled new-user price.
            "alibaba-token": PAGES["alibaba-token"].replace("Limited-time new-user price", "Sale price", 1),
            # A feed without the expected field, which must not stop the other pages.
            "moonshotai": json.dumps(feed),
            "stepfun-ai": json.dumps(steps),
            "anthropic": PAGES["anthropic"].replace("if billed monthly", "if billed each month"),
        }
        for key, page in changed.items():
            with self.subTest(key=key):
                statuses = _statuses({**PAGES, key: page})
                self.assertEqual(statuses[key], "error")
                self.assertEqual(statuses["meta/power"], "ok")

    def test_feeds_give_monthly_list_prices(self):
        # Kimi's feed lists the Free tier and yearly billing beside the monthly prices.
        self.assertEqual(plan_checks.read_kimi(PAGES["moonshotai"]), {
            ("moonshotai", "plus"): 19, ("moonshotai", "pro"): 39, ("moonshotai", "max"): 99,
            ("moonshotai", "ultra"): 199})
        # StepFun's feed names each plan by a type number, in cents.
        self.assertEqual(plan_checks.read_stepfun(PAGES["stepfun-ai"])[("stepfun-ai", "mini")], 6.99)
        self.assertEqual(plan_checks.read_alibaba_token(PAGES["alibaba-token"])[("alibaba", "token_lite")], 6)

    def test_plan_changes_are_dated(self):
        # ChatGPT's pro names several tiers from OpenAI's announcement of the $100 tier.
        self.assertEqual(model_prices.plan("openai", "pro", at="2026-04-09T17:00:00Z").usd_per_month, 200)
        self.assertIsNone(model_prices.plan("openai", "pro", at="2026-04-09T18:00:00Z"))
        self.assertIsNone(model_prices.plan("openai", "pro_500", at="2026-10-15"))
        self.assertNotIn("openai/pro", _statuses())
        # Alibaba's limited-time Token Plan prices became its list prices between 2026-11-02 and
        # their first reading on 2026-11-06.
        self.assertEqual(model_prices.plan("alibaba", "token_lite", at="2026-11-05").usd_per_month, 8)
        self.assertEqual(model_prices.plan("alibaba", "token_lite", at="2026-11-06").usd_per_month, 6)

    def test_a_failed_fetch_is_retried_but_a_refusal_is_not(self):
        # The page archive records real fetches only, never a mocked response.
        self.enterContext(mock.patch.dict("os.environ", {}, clear=False))
        os.environ.pop("MODEL_PRICES_ARCHIVE", None)
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"{}"
        with (mock.patch("urllib.request.urlopen", side_effect=[TimeoutError("timed out"), response]),
              mock.patch("time.sleep") as sleep):
            self.assertEqual(plan_checks._fetch("https://example.com", b"{}"), "{}")
        sleep.assert_called_once()
        with (mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")) as urlopen,
              mock.patch("time.sleep"), self.assertRaises(TimeoutError)):
            plan_checks._fetch("https://example.com", None)
        self.assertEqual(urlopen.call_count, 3)
        refused = urllib.error.HTTPError("https://example.com", 403, "Forbidden", {}, None)
        with (mock.patch("urllib.request.urlopen", side_effect=refused) as urlopen,
              self.assertRaises(urllib.error.HTTPError)):
            plan_checks._fetch("https://example.com", None)
        self.assertEqual(urlopen.call_count, 1)

    def test_the_full_check_command_includes_plans(self):
        mismatch = checks.Result("xiaomi", "xiaomi/lite", "plan", None, None, 7.0, 6.0, None, "mismatch")
        with (mock.patch.object(checks, "run", return_value=[]),
              mock.patch.object(plan_checks, "check_plans", return_value=[mismatch]) as plans,
              mock.patch("sys.stdout", new_callable=io.StringIO) as stdout):
            self.assertEqual(main(["check"]), 1)
            self.assertIn("mismatch  xiaomi/lite plan: official $7, plans.toml $6", stdout.getvalue())
            # A check of named providers leaves plans out.
            main(["check", "zai"])
        plans.assert_called_once()


if __name__ == "__main__":
    unittest.main()
