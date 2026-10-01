"""Compare llm-prices corrections with Pydantic's genai-prices, an independent price list.

For each correction, takes the middle of its period and prices the model there three ways:
the correction, models.dev's own entry, and genai-prices. genai-prices is read twice: its
current data, which dates a few price changes with start_date, and the data.json committed
on or before that moment, which shows what it listed then. Each corrected field is then
reported as agreeing with the correction, with models.dev, or with neither, or as
missing when genai-prices lists no price for it.

    uv run --locked python research/crosscheck_genai_prices.py GENAI_PRICES_CHECKOUT
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import cache
import json
from pathlib import Path
import subprocess
import tomllib

import llm_prices
from llm_prices import genai_prices
from llm_prices.genai_prices import FIELDS, _time

DATA = Path(__file__).resolve().parent.parent / "src" / "llm_prices" / "data"


def genai_rates(data: list, provider: str, model: str, at: datetime) -> dict | None:
    """The model's prices at a moment, with the prompt size its higher tier starts at."""
    if genai_prices.model_prices(data, provider, model, at) is None:
        return None
    return {**{field: genai_prices.price(data, provider, model, field, at) for field in FIELDS},
            "tier": genai_prices.tier_start(data, provider, model, at)}


@cache
def _snapshot(checkout: Path, commit: str) -> list:
    return json.loads(subprocess.run(["git", "-C", str(checkout), "show", f"{commit}:prices/data.json"],
                                     check=True, capture_output=True, text=True).stdout)


def _commits(checkout: Path) -> list[tuple[datetime, str]]:
    log = subprocess.run(["git", "-C", str(checkout), "log", "--format=%H %cI", "--", "prices/data.json"],
                         check=True, capture_output=True, text=True).stdout
    return sorted((_time(when), commit) for commit, when in (line.split() for line in log.splitlines()))


def _compare(value: object, corrected: object, recorded: object) -> str:
    def same(left: object, right: object) -> bool:
        if left is None or right is None:
            return left is None and right is None
        return abs(float(left) - float(right)) < 1e-9
    if value is None:
        return "missing"  # genai-prices lists no price, which is no evidence either way
    if same(value, corrected):
        return "correction"
    if same(value, recorded):
        return "models.dev"
    return "neither"


def crosscheck(checkout: Path) -> None:
    current = json.loads((checkout / "prices" / "data.json").read_text())
    commits = _commits(checkout)
    totals: Counter[tuple[str, str]] = Counter()
    for name in ("corrections.toml", "research_corrections.toml"):
        for item in tomllib.loads((DATA / name).read_text())["correction"]:
            start = _time(item["valid_from"])
            end = _time(item["valid_until"]) if "valid_until" in item else datetime.now(timezone.utc)
            at = start + (end - start) / 2
            recorded = llm_prices.rates(item["model"], provider=item["provider"], at=at,
                                        corrected=False)
            earlier = [commit for when, commit in commits if when <= at]
            views = {"now": genai_rates(current, item["provider"], item["model"], at),
                     "then": genai_rates(_snapshot(checkout, earlier[-1]), item["provider"],
                                         item["model"], at) if earlier else None}
            changed = [field for field in FIELDS if item.get(field) != getattr(recorded, field)]
            corrected_tier = min((tier["above"] for tier in item.get("tiers", [])), default=None)
            recorded_tier = min((tier.above for tier in recorded.tiers), default=None)
            line = []
            for view, rates in views.items():
                if rates is None:
                    line.append(f"{view}: no data")
                    totals[(view, "no data")] += 1
                    continue
                verdicts = {field: _compare(rates[field], item.get(field), getattr(recorded, field))
                            for field in changed}
                if corrected_tier != recorded_tier:
                    verdicts["tier"] = _compare(rates["tier"], corrected_tier, recorded_tier)
                for verdict in verdicts.values():
                    totals[(view, verdict)] += 1
                line.append(f"{view}: " + (", ".join(f"{field} {verdict}" for field, verdict in
                                                    verdicts.items()) or "no field changed"))
            print(f"{name.split('.')[0]:22} {item['provider']}/{item['model']} "
                  f"{start.date()}..{end.date()} | " + " | ".join(line))
    print()
    for (view, verdict), count in sorted(totals.items()):
        print(f"{view:5} {verdict:11} {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checkout", type=Path, help="a git checkout of pydantic/genai-prices")
    crosscheck(parser.parse_args().checkout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
