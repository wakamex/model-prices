"""Start the price update workflow when models.dev changes a tracked provider, and report
its failures to the model-prices agent session.

Meant to run every minute from a timer. Each run asks for the head of models.dev's default
branch with `git ls-remote`, which costs one small request. Only when the head has moved
does it list the provider folders through the GitHub API, one request, and compare the
tree hashes of the tracked providers with the last run's. models.dev merges reseller
catalog syncs many times an hour, so most new heads change no tracked provider and start
nothing. A change starts `update-prices.yml`, which imports, checks, and publishes.

Each run also looks at the workflow's latest completed run. A failure is sent once,
through Panetone, to the session named model-prices, with the run's link and its failed
check lines; it is marked as reported only once Panetone accepts it, and its Panetone
message id is derived from the run, so a repeated send delivers nothing. A failure whose only
errors are fetch timeouts or HTTP 5xx server errors is sent only when the run before it also
failed, since such a failure usually clears on the next run.

State is kept in $XDG_STATE_HOME/model-prices/models-dev.json. The workflow's own daily
schedule still runs, so a missed change is picked up within a day.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from model_prices.backfill import LAB_PROVIDERS, TRACKED_PROVIDERS  # noqa: E402

MODELS_DEV = "anomalyco/models.dev"
REPOSITORY = "wakamex/model-prices"
WORKFLOW = "update-prices.yml"
SESSION = "model-prices"
GH = os.environ.get("GH", "gh")
PANETONE = os.environ.get("PANETONE", "panetone")
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / (
    "model-prices/models-dev.json")
# A tracked provider's files can link to another provider's, such as StepFun's global
# models to its China ones, so those folders are watched too.
WATCHED = {*TRACKED_PROVIDERS, *LAB_PROVIDERS}


def _run(*command: str) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=60).stdout


def head() -> str:
    """The commit at the head of models.dev's default branch."""
    return _run("git", "ls-remote", f"https://github.com/{MODELS_DEV}.git", "HEAD").split()[0]


def tracked_trees(commit: str) -> dict[str, str]:
    """The tree hash of each watched provider folder at `commit`."""
    listing = json.loads(_run(GH, "api", f"repos/{MODELS_DEV}/contents/providers?ref={commit}"))
    return {entry["name"]: entry["sha"] for entry in listing if entry["name"] in WATCHED}


def failed_lines(run: int) -> list[str]:
    """The check report lines and raised errors of a failed run, or its failed step's last
    lines when it has none. The whole log is read, since a step that records a failure
    for a later step to report, such as reading an official page, does not fail itself."""
    def messages(*flags: str) -> list[str]:
        log = _run(GH, "run", "view", str(run), "--repo", REPOSITORY, *flags).splitlines()
        return [re.sub(r"\x1b\[[0-9;]*m", "", line.split("Z ", 1)[-1]) for line in log]
    found = [line for line in messages("--log")
             if line.startswith(("mismatch  ", "error     ", "FAIL: "))
             or re.match(r"[A-Za-z]+Error: ", line)]
    return found or messages("--log-failed")[-15:]


def transient(lines: list[str]) -> bool:
    """Whether a failure's only reported errors are fetch timeouts or server errors, such
    as Cloudflare's 522 when a provider's server does not answer."""
    return bool(lines) and all("timed out" in line or re.search(r"HTTP Error 5\d\d", line)
                               for line in lines)


def report_failure(state: dict) -> None:
    """Send the latest completed workflow run's failure, once."""
    runs = json.loads(_run(GH, "run", "list", "--repo", REPOSITORY, "--workflow", WORKFLOW,
                           "--status", "completed", "--limit", "2",
                           "--json", "databaseId,conclusion,url,event"))
    if not runs or runs[0]["databaseId"] == state.get("reported"):
        return
    latest = runs[0]
    if latest["conclusion"] == "failure":
        lines = failed_lines(latest["databaseId"])
        if transient(lines) and not (len(runs) > 1 and runs[1]["conclusion"] == "failure"):
            return
        message = (f"The {latest['event']} run of {WORKFLOW} failed: {latest['url']}\n\n"
                   + "\n".join(lines[:30]) + "\n\nFix it, publish, and reply with the commit.")
        # A message id derived from the run makes a repeated send deliver nothing, such as
        # when the state could not be saved after the send.
        message_id = uuid.uuid5(uuid.NAMESPACE_URL, latest["url"])
        _run(PANETONE, "send", "--as", "model-prices-watch", "--to", SESSION,
             "--id", str(message_id), message)
        print(f"reported run {latest['databaseId']}")
    state["reported"] = latest["databaseId"]


def main() -> int:
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    # A report that cannot be sent, such as while no model-prices session runs, is retried
    # next minute and does not stop the models.dev check.
    try:
        report_failure(state)
    except subprocess.CalledProcessError as error:
        print(f"failure report not sent: {error.stderr.strip() or error}", file=sys.stderr)
    commit = head()
    if commit == state.get("head"):
        STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
        return 0
    trees = tracked_trees(commit)
    changed = sorted(name for name in trees.keys() | state.get("trees", {}).keys()
                     if trees.get(name) != state.get("trees", {}).get(name))
    # The first run records the current state without starting anything.
    if changed and "trees" in state:
        _run(GH, "workflow", "run", WORKFLOW, "--repo", REPOSITORY)
        print(f"{commit[:9]}: started {WORKFLOW} for {', '.join(changed)}")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    state.update(head=commit, trees=trees)
    STATE.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
