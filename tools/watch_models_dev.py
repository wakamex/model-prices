"""Start the price update workflow when models.dev changes a tracked provider.

Meant to run every minute from a timer. Each run asks for the head of models.dev's default
branch with `git ls-remote`, which costs one small request. Only when the head has moved
does it list the provider folders through the GitHub API, one request, and compare the
tree hashes of the tracked providers with the last run's. models.dev merges reseller
catalog syncs many times an hour, so most new heads change no tracked provider and start
nothing. A change starts `update-prices.yml`, which imports, checks, and publishes.

State is kept in $XDG_STATE_HOME/model-prices/models-dev.json. The workflow's own daily
schedule still runs, so a missed change is picked up within a day.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from model_prices.backfill import LAB_PROVIDERS, TRACKED_PROVIDERS  # noqa: E402

MODELS_DEV = "anomalyco/models.dev"
REPOSITORY = "wakamex/model-prices"
WORKFLOW = "update-prices.yml"
GH = os.environ.get("GH", "gh")
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


def main() -> int:
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    commit = head()
    if commit == state.get("head"):
        return 0
    trees = tracked_trees(commit)
    changed = sorted(name for name in trees.keys() | state.get("trees", {}).keys()
                     if trees.get(name) != state.get("trees", {}).get(name))
    # The first run records the current state without starting anything.
    if changed and "trees" in state:
        _run(GH, "workflow", "run", WORKFLOW, "--repo", REPOSITORY)
        print(f"{commit[:9]}: started {WORKFLOW} for {', '.join(changed)}")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"head": commit, "trees": trees}, indent=1, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
