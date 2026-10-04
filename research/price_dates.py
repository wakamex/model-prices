"""Research when each models.dev price change really took effect.

models.dev dates a price by the commit that recorded it, which can lag the provider's
change by days or fix a price that was never right. This tool lists every recorded
change, writes one research task per change for an AOP batch of cheap web-research
agents, and verifies their findings. Cited pages form a shared Markdown library under
research/sources/, one file per URL, which each agent reads and adds to; every quote
must appear in the library copy of its page.

    uv run --locked python research/price_dates.py changes MODELS_DEV_CHECKOUT
    uv run --locked python research/price_dates.py manifest [--only ID ...]
    aop batch research/price-dates/batch.toml --jobs 4        (from research/price-dates)
    uv run --locked python research/price_dates.py collect BATCH_JSON
    uv run --locked python research/price_dates.py verify
    uv run --locked python research/price_dates.py review-manifest
    aop batch research/price-dates/review-batch.toml --jobs 4
    uv run --locked python research/price_dates.py collect-reviews BATCH_JSON
    uv run --locked python research/price_dates.py corrections
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
# extract_web.py from https://github.com/wakamex/scripts, located by the EXTRACT_WEB variable.
EXTRACT = Path(os.environ.get("EXTRACT_WEB", "extract_web.py")).resolve()
# The sealed runs have the system Python but neither uv nor the user's packages.
EXTRACT_DEPS = ROOT / "price-dates" / "extract-deps"
WORK = ROOT / "price-dates"
SOURCES = ROOT / "sources"
DATA = ROOT.parent / "data"
PRICES = DATA / "prices.json"
RESEARCHED = DATA / "research_corrections.toml"
FIELDS = ("input", "output", "cache_read", "cache_write", "tiers")

PROMPT = """\
You are researching one recorded API price change for model-prices, an open dataset of
LLM API prices over time.

models.dev, an open model catalog, recorded this change:

- Model: {provider}/{model}
- Price before (USD per million tokens): {before}
- Price after: {after}
- Recorded in models.dev at {recorded_at} by commit {commit_url}
- Commit message: {message}
- The earlier price was recorded starting {previous_at}.

models.dev's commit time is not necessarily when the provider changed its price. Find out:

1. Classification. Was the earlier price really the provider's price before this change
   ("price_change"), or was it never the provider's official price, so models.dev was
   fixing its own error ("models_dev_fix")? Use "unclear" if the evidence does not decide.
2. For a price_change: when the new price took effect, as precisely as the sources state,
   with the timezone if given. For a models_dev_fix: the official price during the
   earlier period, if a source states it.

Use primary sources: the provider's pricing pages, documentation, changelogs, release
notes, and announcements, including Internet Archive copies of pricing pages
(https://web.archive.org/cdx/search/cdx?url=URL&output=json lists snapshots; open one as
https://web.archive.org/web/TIMESTAMP/URL). A snapshot pair bracketing the change, one
before and one after, is good evidence when no announcement gives the date. models.dev
pull requests and third-party articles are leads, not evidence.

Pages are read and quoted as Markdown. /inputs/sources/ holds pages earlier research
already extracted, one file per URL; /inputs/sources/index.tsv lists each URL and file.
Use a library copy when the page you need is there. To read any other page, extract it:

    PYTHONPATH=/inputs/extract-deps python3 /inputs/extract_web.py URL -o $AOP_OUTPUT_DIR/sources/NAME.md

where NAME is the first 16 hex digits of the SHA-256 of the exact URL
(printf %s URL | sha256sum | cut -c1-16). It returns the site's own Markdown copy when
there is one and otherwise converts the HTML. For an Internet Archive snapshot extract
https://web.archive.org/web/TIMESTAMPid_/URL, which serves the archived page itself. If
the archive answers 429, wait a minute before the next request. A page that cannot be
extracted, for example because it needs JavaScript, cannot be cited; find another
source for the claim. Copy each library file you quote into $AOP_OUTPUT_DIR/sources/
as well, so that directory holds every page your finding cites.

Then write $AOP_OUTPUT_DIR/finding.json:

{{
  "classification": "price_change" | "models_dev_fix" | "unclear",
  "effective_at": "ISO 8601 time or date, or null",
  "effective_precision": "exact" | "day" | "bracketed" | "unknown",
  "bracket": {{"last_before": "ISO time or null", "first_after": "ISO time or null"}},
  "official_previous_price": {{"input": null, "output": null, "cache_read": null}},
  "sources": [
    {{"url": "the exact URL you extracted", "file": "the Markdown file you quoted",
      "quote": "a verbatim passage copied from that file, under 300 characters",
      "supports": "what this source shows"}}
  ],
  "notes": "one or two sentences"
}}

Every claim must rest on a quote copied verbatim from the Markdown file of its page;
the quotes are checked by machine against that file. Copy one contiguous passage exactly
as it appears in the file, never text joined from different parts of it; for a table,
quote a single row. Do not guess a date: when the sources do not state or bracket it, set effective_at
to null and say so in notes. If a source you need, such as web.archive.org, is
unavailable, say so in notes rather than concluding there is no evidence.
"""


REVIEW_PROMPT = """\
You are checking one finding written by another researcher for model-prices, an open dataset
of LLM API prices over time. The finding explains a price change recorded by models.dev,
an open model catalog:

- Model: {provider}/{model}
- Price before (USD per million tokens): {before}, recorded from {previous_at}
- Price after: {after}, recorded from {recorded_at}

The finding is /inputs/{id}/finding.json. Every quote in it has been checked by machine to
appear in the page it cites, so do not check that again. Copies of the cited pages are in
/inputs/sources/ (one Markdown file per URL; /inputs/sources/index.tsv lists them) and in
/inputs/{id}/sources/. Judge only from these files; do not look for other sources.

Check whether the quotes, read in their surrounding text, support the finding:

1. Each quote offered as evidence for a claim is about this model, not another model,
   version, or alias, and about this price or this change, not a different event. A quote
   that only gives context, such as a model's capabilities, is not a failure.
2. The classification holds. "price_change": the provider's price changed from the before
   price to the after price. "models_dev_fix": during the period it was recorded, the
   before entry differed from the provider's official price in at least one field, either
   a wrong value or a missing price the provider charged, such as cached input; the after
   entry is models.dev's correction.
3. The sources place the claimed price in the right period. For a price_change, the
   effective_at date or bracket is stated in the cited pages, in a quote or the page's own
   date, and should not fall before the before price was recorded unless the sources show
   models.dev recorded both prices late. For a models_dev_fix, a current price page may
   stand for the earlier period when nothing in the cited pages shows a different price in
   between; say in notes when you rely on that. Fail the check when the sources show a
   different price applied then.
4. Each non-null value in official_previous_price matches a quoted price for this model.
   Null values claim nothing and pass.

Write $AOP_OUTPUT_DIR/review.json:

{{
  "verdict": "supported" | "unsupported",
  "problems": ["one entry per failed check, naming the check and the quote"],
  "notes": "one or two sentences"
}}

Use "supported" only when every check passes.
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


def _rates(entry: dict) -> dict:
    return {key: entry["rates"][key] for key in FIELDS if key in entry["rates"]}


def slug(change: dict) -> str:
    stamp = change["recorded_at"].replace("-", "").replace(":", "")[:13]
    return re.sub(r"[^a-z0-9.]+", "_", f"{change['provider']}__{change['model']}__{stamp}".lower())


def list_changes(models_dev: Path) -> list[dict]:
    data = json.loads(PRICES.read_text())
    changes = []
    for provider, models in sorted(data["providers"].items()):
        for model, entries in sorted(models.items()):
            for previous, current in zip(entries, entries[1:]):
                if _rates(previous) == _rates(current):
                    continue  # only alternate modes changed
                commit = _git(models_dev, "rev-parse", current["commit"]).strip()
                message = _git(models_dev, "log", "-1", "--format=%B", commit).strip()
                change = {
                    "provider": provider, "model": model,
                    "before": _rates(previous), "after": _rates(current),
                    "previous_at": previous["valid_from"], "recorded_at": current["valid_from"],
                    "commit": commit, "commit_url": f"{data['source']}/commit/{commit}",
                    "message": re.sub(r"\s+", " ", message)[:800],
                }
                change["id"] = slug(change)
                changes.append(change)
    return changes


def source_path(url: str) -> Path:
    return SOURCES / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}.md"


def library_entry(path: Path, url: str, retrieved: str, body: str) -> None:
    path.write_text(f"---\nurl: {url}\nretrieved: {retrieved}\n---\n\n{body}")


def write_index() -> None:
    """List each library file's URL and retrieval time for agents."""
    rows = []
    for path in sorted(SOURCES.glob("*.md")):
        header = dict(line.split(": ", 1) for line in
                      path.read_text().split("\n---\n", 1)[0].splitlines()[1:])
        rows.append(f"{header['url']}\t{path.name}\t{header['retrieved']}")
    (SOURCES / "index.tsv").write_text("url\tfile\tretrieved\n" + "\n".join(sorted(rows)) + "\n")


def write_manifest(changes: list[dict], only: set[str], model: str, effort: str) -> Path:
    tasks = WORK / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    write_index()
    if not EXTRACT_DEPS.exists():
        subprocess.run(["uv", "--no-config", "pip", "install", "--quiet", "--python",
                        "/usr/bin/python3", "--target", str(EXTRACT_DEPS),
                        "html2text", "readability-lxml", "requests"], check=True)
    blocks = []
    for change in changes:
        if only and change["id"] not in only:
            continue
        prompt = PROMPT.format(**{key: json.dumps(value) if isinstance(value, dict) else value
                                  for key, value in change.items()})
        (tasks / f"{change['id']}.md").write_text(prompt)
        blocks.append(
            f'[[tasks]]\nid = "{change["id"]}"\nagent = "codex"\nmodel = "{model}"\n'
            f'effort = "{effort}"\nprofile = "sealed"\ntimeout = 1200\n'
            f'prompt_file = "tasks/{change["id"]}.md"\n'
            f'inputs = ["../sources", "{EXTRACT}", "extract-deps"]\n'
            f'artifacts = ["finding.json", "sources"]\n'
        )
    manifest = WORK / "batch.toml"
    manifest.write_text("\n".join(blocks))
    return manifest


def write_review_manifest(changes: list[dict], only: set[str], model: str, effort: str) -> Path:
    """One review task per verified finding that could become a correction."""
    tasks = WORK / "review-tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    write_index()
    blocks = []
    for change in changes:
        if only and change["id"] not in only:
            continue
        try:
            finding = json.loads((WORK / "findings" / change["id"] / "finding.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            continue
        if not finding.get("verified") or finding.get("classification") == "unclear":
            continue
        prompt = REVIEW_PROMPT.format(**{key: json.dumps(value) if isinstance(value, dict) else value
                                         for key, value in change.items()})
        (tasks / f"{change['id']}.md").write_text(prompt)
        blocks.append(
            f'[[tasks]]\nid = "{change["id"]}"\nagent = "codex"\nmodel = "{model}"\n'
            f'effort = "{effort}"\nprofile = "sealed"\nno_web = true\ntimeout = 900\n'
            f'prompt_file = "review-tasks/{change["id"]}.md"\n'
            f'inputs = ["../sources", "findings/{change["id"]}"]\n'
            f'artifacts = ["review.json"]\n'
        )
    manifest = WORK / "review-batch.toml"
    manifest.write_text("\n".join(blocks))
    return manifest


def review_prompt_id() -> str:
    return hashlib.sha256(REVIEW_PROMPT.encode()).hexdigest()[:12]


def collect_reviews(batch: Path) -> None:
    """Append each review to its finding's reviews.jsonl, tagged with the review prompt."""
    summary = json.loads(batch.read_text())
    runs = batch.resolve().parent.parent / "runs"
    for result in summary["tasks"]:
        artifact = runs / str(result.get("run_id")) / "artifacts" / "review.json"
        try:
            review = json.loads(artifact.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as error:
            print(f"skip {result['task']}: {result['status']}, {error}", file=sys.stderr)
            continue
        record = {"run_id": result["run_id"], "prompt": review_prompt_id(), **review}
        with (WORK / "findings" / result["task"] / "reviews.jsonl").open("a") as log:
            log.write(json.dumps(record) + "\n")


def review_verdict(change_id: str) -> tuple[str | None, list[str]]:
    """The majority verdict of the reviews made with the current prompt, and their problems.

    A single review is noisy, so a finding counts as supported only when most of at least
    three reviews say so.
    """
    path = WORK / "findings" / change_id / "reviews.jsonl"
    reviews = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    reviews = [review for review in reviews if review["prompt"] == review_prompt_id()]
    if len(reviews) < 3:
        return None, []
    supported = sum(review.get("verdict") == "supported" for review in reviews)
    problems = [problem for review in reviews if review.get("verdict") != "supported"
                for problem in review.get("problems", [])]
    return ("supported" if supported * 2 > len(reviews) else "unsupported"), problems


def collect(batch: Path) -> None:
    """Copy each run's finding into price-dates/findings/<id>/ and add the pages it
    extracted to the source library.

    AOP writes the batch summary to .aop/batches/<batch>.json and archives each run's
    artifacts under .aop/runs/<run_id>/artifacts/.
    """
    summary = json.loads(batch.read_text())
    runs = batch.resolve().parent.parent / "runs"
    for result in summary["tasks"]:
        artifacts = runs / str(result.get("run_id")) / "artifacts"
        if not (artifacts / "finding.json").is_file():
            print(f"skip {result['task']}: {result['status']}, no finding.json", file=sys.stderr)
            continue
        destination = WORK / "findings" / result["task"]
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(artifacts, destination)
        add_extracts(destination, runs / str(result["run_id"]) / "result.json")
        (destination / "run.json").write_text(json.dumps({
            key: result.get(key) for key in (
                "run_id", "status", "model", "effort", "duration_seconds", "input_tokens",
                "cached_input_tokens", "output_tokens", "calculated_cost_usd")
        }, indent=1) + "\n")


def add_extracts(finding_dir: Path, result: Path) -> None:
    """Add the pages a run extracted to the library, keyed by URL. The run keeps its own
    copies, which can differ from an earlier library copy of a page that has changed."""
    try:
        finding = json.loads((finding_dir / "finding.json").read_text())
    except json.JSONDecodeError:
        return
    retrieved = json.loads(result.read_text())["finished_at"]
    SOURCES.mkdir(parents=True, exist_ok=True)
    for source in finding.get("sources", []):
        # Agents are asked to name extracts by URL hash but sometimes name them freely.
        named = finding_dir / "sources" / Path(source.get("file", "")).name
        extract = named if named.is_file() else finding_dir / "sources" / source_path(source["url"]).name
        if (extract.is_file() and not source_path(source["url"]).exists()
                and not extract.read_text().startswith("---\nurl: ")):  # a library copy
            library_entry(source_path(source["url"]), source["url"], retrieved,
                          extract.read_text())
    write_index()


def _normalize(text: str) -> str:
    """Reduce Markdown to its visible text, so a quote of what a reader sees matches."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links keep only their text
    return re.sub(r"\s+", " ", re.sub(r"[*_`#>|\\]", " ", text)).strip().lower()


def save_source(url: str) -> Path | None:
    """Extract a cited page to research/sources/ as Markdown with its provenance."""
    SOURCES.mkdir(parents=True, exist_ok=True)
    path = source_path(url)
    if path.exists():
        return path
    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
    fetched = subprocess.run([str(EXTRACT), url], capture_output=True, text=True)
    if fetched.returncode != 0 or not fetched.stdout:
        return None
    library_entry(path, url, retrieved, fetched.stdout)
    return path


def verify() -> None:
    """Check each finding's quotes against independently saved copies of its sources."""
    for finding_path in sorted((WORK / "findings").glob("*/finding.json")):
        try:
            finding = json.loads(finding_path.read_text())
        except json.JSONDecodeError as error:
            print(f"BAD {finding_path.parent.name}: invalid finding.json ({error})")
            continue
        own_sources = finding_path.parent
        for source in finding.get("sources", []):
            saved = save_source(source["url"])
            texts = [saved.read_text()] if saved else []
            agent_copy = (own_sources / "sources" / Path(source["file"]).name if source.get("file")
                          else own_sources / source.get("saved_as", ""))
            if agent_copy.is_file():
                texts.append(agent_copy.read_text(errors="replace"))
            quote = _normalize(source.get("quote", ""))
            source["extracted_as"] = str(saved.relative_to(ROOT.parent)) if saved else None
            source["quote_verified"] = bool(quote) and any(quote in _normalize(text)
                                                           for text in texts)
            source["verified_in"] = ("independent extract" if saved and quote
                                     and quote in _normalize(texts[0]) else
                                     "agent copy" if source["quote_verified"] else None)
        finding["verified"] = bool(finding.get("sources")) and all(
            source["quote_verified"] for source in finding["sources"])
        finding_path.write_text(json.dumps(finding, indent=1) + "\n")
        print(f"{'ok ' if finding['verified'] else 'NO '} {finding_path.parent.name}: "
              f"{finding.get('classification')} {finding.get('effective_at')}")


# Findings read by hand, which settles them whatever the agent review says: "after" applies
# the models.dev fix's own rates, ignoring the finding's official price; "quoted" applies only
# the quoted prices to models.dev's earlier entry; and "skip" leaves the finding out.
REVIEWED = {
    # The official cache_read of 0 is xAI's price for a model without caching; the fix was
    # dropping models.dev's cache_write, which its fixed entry already does.
    "xai_grok_2_1212_20250909t2003": "after",
    # The official 0.6 is the cache_read above 200K tokens, which the fixed tier carries.
    "xai_grok_4.5_20260731t1900": "after",
    # The cited prices are Gemini Flash-Lite's, while both models.dev entries carry Flash
    # prices; the finding does not settle what the alias pointed to.
    "google_gemini_flash_lite_latest_20260821t0642": "skip",
    # These date a model's release, not the latest alias switching to it, which is inferred.
    # gemini-flash-latest also pointed to Gemini 3 Flash Preview from 2026-01-21.
    "google_gemini_flash_latest_20260715t1513": "skip",
    "google_gemini_flash_lite_latest_20260715t1513": "skip",
    # Classified as a fix of the earlier entry, but its notes say the later entry added a
    # wrong cache_write, and its price quote is about Claude 3.5 Sonnet.
    "anthropic_claude_3_sonnet_20240229_20250617t2226": "skip",
    # xAI charges no cache writes; models.dev's fix added one and removed it in a later change
    # whose finding is unclear, so only the quoted cache read applies.
    "xai_grok_3_mini_20250617t2226": "quoted",
    # Applies new base prices for 3.5 months on an inferred classification with no date.
    "alibaba_qwen3.7_plus_20260928t0401": "skip",
}


def _day_start(value: str) -> datetime:
    """A documented date without a time applies from the start of that day in UTC."""
    if len(value) == 10:
        value += "T00:00:00Z"
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _toml_value(value: object) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key} = {_toml_value(item)}" for key, item in value.items()) + " }"
    return json.dumps(value)


def derive_corrections() -> tuple[list[dict], list[str]]:
    """Turn verified findings into corrections, and list the findings left out and why.

    A models_dev_fix replaces models.dev's earlier entry over its whole period with the
    prices the finding quotes, and takes every other field from the rates models.dev
    settled on after its last consecutive fix. A dated price_change moves the start of the
    new rates to the documented time, or keeps the old rates until it when models.dev
    recorded the change early; a bracketed one applies the new rates from the first
    observation of them.
    """
    changes = json.loads((WORK / "changes.json").read_text())
    entries, skipped = [], []
    # Official prices quoted by each models_dev_fix, keyed by the start of the entry it
    # corrects. When models.dev fixed a model twice in a row, a corrected period also takes
    # the prices quoted for the fix that directly follows it.
    fixed: dict[tuple[str, str, str], dict] = {}
    following = {(item["provider"], item["model"], item["previous_at"]): item for item in changes}

    def classification(item: dict) -> str | None:
        try:
            path = WORK / "findings" / item["id"] / "finding.json"
            return json.loads(path.read_text()).get("classification")
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def settled(item: dict) -> dict:
        """models.dev's rates once it stopped fixing the model: after the last of a run of
        consecutive fixes. Its first fix was sometimes still wrong in other fields."""
        while (later := following.get((item["provider"], item["model"], item["recorded_at"]))) \
                and classification(later) == "models_dev_fix" and REVIEWED.get(later["id"]) != "skip":
            item = later
        return item["after"]

    for change in sorted(changes, key=lambda item: item["recorded_at"], reverse=True):
        try:
            finding = json.loads((WORK / "findings" / change["id"] / "finding.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            skipped.append(f"{change['id']}: no valid finding")
            continue
        kind = finding.get("classification")
        if not finding.get("verified") or kind not in ("models_dev_fix", "price_change"):
            continue
        verdict, problems = review_verdict(change["id"])
        if verdict is None:
            skipped.append(f"{change['id']}: fewer than three reviews")
            continue
        if verdict != "supported" and change["id"] not in REVIEWED:
            skipped.append(f"{change['id']}: reviews found {' | '.join(problems)[:300]}")
            continue
        previous = _day_start(change["previous_at"])
        recorded = _day_start(change["recorded_at"])
        review = REVIEWED.get(change["id"])
        if review == "skip":
            skipped.append(f"{change['id']}: reviewed, not applied")
            continue
        if kind == "models_dev_fix":
            quoted = {key: value for key, value in
                      (finding.get("official_previous_price") or {}).items() if value is not None}
            later = fixed.get((change["provider"], change["model"], change["recorded_at"]), {})
            quoted = {**later, **quoted}
            fixed[(change["provider"], change["model"], change["previous_at"])] = quoted
            # Quoted prices are the evidence; other fields take the value models.dev settled
            # on, since the earlier entry was the wrong one.
            rates = (dict(change["after"]) if review == "after"
                     else {**change["before"], **quoted} if review == "quoted"
                     else {**settled(change), **quoted})
            if rates == change["before"]:
                skipped.append(f"{change['id']}: no quoted price differs from models.dev")
                continue
            start, end = previous, recorded
        else:
            bracket = finding.get("bracket") or {}
            moment = finding.get("effective_at") or bracket.get("first_after")
            if not moment:
                skipped.append(f"{change['id']}: price change without a documented date")
                continue
            effective = _day_start(moment)
            if effective < previous:
                # Dated before the earlier price was recorded: likely a different event,
                # as when a 2026 cut was matched to a 2025 announcement.
                skipped.append(f"{change['id']}: dated {moment}, before the earlier price "
                               f"was recorded at {change['previous_at']}; needs review")
                continue
            if effective < recorded:
                rates, start, end = dict(change["after"]), effective, recorded
            elif effective > recorded:
                rates, start, end = dict(change["before"]), recorded, effective
            else:
                continue
        if start >= end:
            continue
        sources = [source["url"] for source in finding["sources"]]
        entries.append({
            "provider": change["provider"], "model": change["model"],
            "valid_from": _iso(start), "valid_until": _iso(end), **rates,
            "source": sources[0],
            "note": f"{kind}: {finding.get('notes', '').strip()} "
                    f"Finding research/price-dates/findings/{change['id']}.",
        })
    return entries, skipped


def write_corrections() -> None:
    import tomllib  # noqa: PLC0415
    manual = tomllib.loads((DATA / "corrections.toml").read_text()).get("correction", [])
    entries, skipped = derive_corrections()
    kept = []
    for entry in entries:
        # Hand corrections in corrections.toml take precedence over overlapping research.
        overlap = [item for item in manual
                   if (item["provider"], item["model"]) == (entry["provider"], entry["model"])
                   and _day_start(item["valid_from"]) < _day_start(entry["valid_until"])
                   and _day_start(entry["valid_from"]) < _day_start(item.get("valid_until", "9999-12-31"))]
        if overlap:
            skipped.append(f"{entry['note'].rsplit('findings/', 1)[1].rstrip('.')}: "
                           "covered by corrections.toml")
        else:
            kept.append(entry)
    blocks = ["# Generated by research/price_dates.py corrections from verified price-date findings.\n"
              "# Do not edit: change the findings or corrections.toml, which takes precedence.\n"]
    for entry in sorted(kept, key=lambda item: (item["provider"], item["model"], item["valid_from"])):
        blocks.append("[[correction]]\n" + "".join(f"{key} = {_toml_value(value)}\n"
                                                    for key, value in entry.items()))
    RESEARCHED.write_text("\n".join(blocks))
    print(f"{len(kept)} corrections written to {RESEARCHED}")
    for line in skipped:
        print(f"skipped {line}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("changes")
    listing.add_argument("models_dev", type=Path)
    manifest = commands.add_parser("manifest")
    manifest.add_argument("--only", nargs="*", default=[])
    manifest.add_argument("--model", default="gpt-6-luna")
    manifest.add_argument("--effort", default="medium")
    gather = commands.add_parser("collect")
    gather.add_argument("batch", type=Path)
    commands.add_parser("verify")
    reviews = commands.add_parser("review-manifest")
    reviews.add_argument("--only", nargs="*", default=[])
    reviews.add_argument("--model", default="gpt-6-luna")
    reviews.add_argument("--effort", default="medium")
    gather_reviews = commands.add_parser("collect-reviews")
    gather_reviews.add_argument("batch", type=Path)
    commands.add_parser("corrections")
    args = parser.parse_args()

    changes_file = WORK / "changes.json"
    if args.command == "changes":
        WORK.mkdir(parents=True, exist_ok=True)
        changes = list_changes(args.models_dev)
        changes_file.write_text(json.dumps(changes, indent=1) + "\n")
        print(f"{len(changes)} changes written to {changes_file}")
    elif args.command == "manifest":
        changes = json.loads(changes_file.read_text())
        path = write_manifest(changes, set(args.only), args.model, args.effort)
        print(f"wrote {path}")
    elif args.command == "collect":
        collect(args.batch)
    elif args.command == "review-manifest":
        changes = json.loads(changes_file.read_text())
        path = write_review_manifest(changes, set(args.only), args.model, args.effort)
        print(f"wrote {path}")
    elif args.command == "collect-reviews":
        collect_reviews(args.batch)
    elif args.command == "corrections":
        write_corrections()
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
