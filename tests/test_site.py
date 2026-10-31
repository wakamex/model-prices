from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

import model_prices

ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("input", "output", "cache_read", "cache_write", "cache_write_1h")


def _cases(count: int, seed: int = 0) -> list[dict]:
    """Requests for every model the package resolves to itself, at times that cross price
    changes, peak and off-peak hours, weekends, holidays, and long-context tiers."""
    data = model_prices._data()
    rng = random.Random(seed)
    models = [(provider, model, [None, *sorted(timelines), "thinking"])
              for provider, listed in data["prices"].items()
              for model, timelines in listed.items()
              if (model_prices.resolve_details(model, provider) or ())[:3] == (provider, model, "")]
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    modal = {provider: {model for model, timelines in listed.items()
                        if any((interval["rates"] or {}).get("modalities")
                               for intervals in timelines.values() for interval in intervals)}
             for provider, listed in data["prices"].items()}
    regional = {provider: {model for model, timelines in listed.items()
                           if any((interval["rates"] or {}).get("regions")
                                  for intervals in timelines.values() for interval in intervals)}
                for provider, listed in data["prices"].items()}
    # Every model priced by modality or by region is drawn often enough to be tested.
    models += [entry for entry in models if entry[1] in modal.get(entry[0], ())
               or entry[1] in regional.get(entry[0], ())] * 20
    # A third of the cases fall inside a time-of-day schedule, for the models it covers.
    scheduled = []
    for schedule in data["schedules"]["schedule"]:
        begin = model_prices._parse_time(schedule["valid_from"])
        end = model_prices._parse_time(schedule.get("valid_until", "2027-01-01T00:00:00Z"))
        covered = [entry for entry in models if entry[0] == schedule["provider"] and (
            "peak_hours_utc" in schedule or entry[1] in schedule["off_peak_multiplier"])]
        scheduled += [(entry, begin, end) for entry in covered]
    cases = []
    for _ in range(count):
        provider, model, modes = rng.choice(models)
        at = start + timedelta(seconds=rng.randrange(0, 760 * 86400))
        if rng.random() < 0.33:
            (provider, model, modes), begin, end = rng.choice(scheduled)
            at = begin + timedelta(seconds=rng.randrange(int((end - begin).total_seconds())))
        if rng.random() < 0.3:
            # Close to an hour boundary, where time-of-day windows open and close.
            at = at.replace(minute=rng.choice((0, 29, 30, 59)), second=rng.choice((0, 59)))
        prompt = rng.choice((1_000, 33_000, 130_000, 210_000, 260_000, 300_000, 600_000))
        tokens = {"input": rng.randrange(prompt), "output": rng.randrange(200_000),
                  "cache_read": rng.randrange(prompt), "cache_write": rng.randrange(prompt // 4),
                  "cache_write_1h": rng.randrange(prompt // 8)}
        # Models priced by modality also get requests split by modality, some naming a
        # modality the model does not list.
        if model in modal.get(provider, ()) and rng.random() < 0.5:
            names = rng.sample(["text", "audio", "image", "video", "document"], rng.randint(1, 3))
            tokens |= {"input": 0, "output": 0, "cache_read": 0, "modalities": {
                name: {"input": rng.randrange(prompt), "cache_read": rng.randrange(prompt // 2),
                       "output": rng.randrange(50_000)} for name in names}}
        # Models priced by region also get requests served in one, or in one they do not list.
        region = rng.choice([None, "us", "eu"]) if model in regional.get(provider, ()) else None
        cases.append({"provider": provider, "model": model, "mode": rng.choice(modes),
                      "at": at.isoformat().replace("+00:00", "Z"), "region": region,
                      "tokens": tokens})
    return cases


@unittest.skipUnless(shutil.which("node") and (ROOT / "site").is_dir(),
                     "Node.js runs the site's calculator, which a source distribution leaves out")
class CalculatorTests(unittest.TestCase):
    def test_calculator_matches_the_package_exactly(self):
        cases = _cases(5000)
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "snapshot.json"
            snapshot.write_text(json.dumps(model_prices._data()))
            listed = Path(directory) / "cases.json"
            listed.write_text(json.dumps(cases))
            output = subprocess.run(
                ["node", str(ROOT / "tests" / "price_cases.mjs"), str(snapshot), str(listed),
                 str(ROOT / "site" / "static" / "model-prices.js")],
                check=True, capture_output=True, text=True).stdout
        priced = 0
        for case, result in zip(cases, json.loads(output), strict=True):
            found = model_prices.rates(case["model"], at=case["at"], provider=case["provider"],
                                       mode=case["mode"], region=case["region"])
            if found is None:
                self.assertIsNone(result, case)
                continue
            parts = found.breakdown(*(case["tokens"][field] for field in FIELDS),
                                    modality_tokens=case["tokens"].get("modalities"))
            expected = {"period": found.period, "region": found.region, "tier_above": parts.tier_above,
                        "total": parts.total, **{field: getattr(parts, field) for field in FIELDS}}
            self.assertEqual(result, expected, case)
            priced += 1
        self.assertGreater(priced, 4000)
        self.assertGreater(sum("modalities" in case["tokens"] for case in cases), 500)
        self.assertGreater(sum(case["region"] == "us" for case in cases), 100)
        self.assertGreater(sum(1 for case in cases if model_prices.rates(
            case["model"], at=case["at"], provider=case["provider"]).period), 1000)
