"""Research when each models.dev price change really took effect.

models.dev dates a price by the commit that recorded it, which can lag the provider's
change by days or fix a price that was never right. This tool lists every recorded
change, writes one research task per change for an AOP batch of cheap web-research
agents, and verifies their findings. Cited pages form a shared Markdown library under
research/sources/, one file per URL, which each agent reads and adds to; every quote
must appear in the library copy of its page.

    uv run --no-config python research/price_dates.py changes MODELS_DEV_CHECKOUT
    uv run --no-config python research/price_dates.py manifest [--only ID ...]
    aop batch research/price-dates/batch.toml --jobs 4        (from research/price-dates)
    uv run --no-config python research/price_dates.py collect BATCH_JSON
    uv run --no-config python research/price_dates.py verify
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
EXTRACT = Path("/code/scripts/extract_web.py")
# The sealed runs have the system Python but neither uv nor the user's packages.
EXTRACT_DEPS = ROOT / "price-dates" / "extract-deps"
WORK = ROOT / "price-dates"
SOURCES = ROOT / "sources"
PRICES = ROOT.parent / "src" / "llm_prices" / "data" / "prices.json"
FIELDS = ("input", "output", "cache_read", "cache_write", "tiers")

PROMPT = """\
You are researching one recorded API price change for llm-prices, an open dataset of
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
    else:
        verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
