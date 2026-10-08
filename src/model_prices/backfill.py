"""Build effective-dated API prices from the git history of a models.dev checkout."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tomllib
from typing import Any, Iterator

SOURCE_URL = "https://github.com/sst/models.dev"

# Labs whose first-party API prices define API-equivalent cost.
TRACKED_PROVIDERS = (
    "ai21",
    "alibaba",
    "amazon-bedrock",
    "anthropic",
    "arcee",
    "bailing",
    "cohere",
    "deepseek",
    "google",
    "inception",
    "longcat",
    "meta",
    "minimax",
    "mistral",
    "moonshotai",
    "nova",
    "openai",
    "perplexity",
    "poolside",
    "sakana",
    "sarvam",
    "sensenova",
    "stepfun-ai",
    "tencent-tokenhub",
    "thinkingmachines",
    "upstage",
    "volcengine",
    "xai",
    "xiaomi",
    "zai",
)

# Providers tracked only for some models: Amazon Bedrock hosts many labs' models, and is
# tracked for Amazon's own Nova models, which it sells.
TRACKED_MODELS = {"amazon-bedrock": re.compile(r"(^|\.)amazon\.nova-")}

def _tracked(path: str) -> bool:
    """Whether a model file belongs to a tracked model of its provider."""
    _, provider, _, *model_parts = path.removesuffix(".toml").split("/")
    pattern = TRACKED_MODELS.get(provider)
    return pattern is None or bool(pattern.search("/".join(model_parts)))


RATE_FIELDS = ("input", "output", "cache_read", "cache_write")

# models.dev lab ids that differ from the id of the lab's own API provider.
LAB_PROVIDERS = {"bytedance-seed": "volcengine", "stepfun": "stepfun-ai", "zhipuai": "zai"}

# Providers whose models.dev `reasoning` cost is the output price in thinking mode, which bills
# the chain of thought and the answer alike. Elsewhere the field means other things, such as
# Perplexity's separate charge for Sonar Deep Research's reasoning tokens.
THINKING_OUTPUT = {"alibaba"}


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value).astimezone(timezone.utc)
    return parsed.isoformat().replace("+00:00", "Z")


def _rate_values(cost: dict[str, Any]) -> dict[str, float]:
    return {
        field: float(cost[field])
        for field in RATE_FIELDS
        if isinstance(cost.get(field), (int, float))
    }


def parse_rates(document: dict[str, Any], provider: str = "") -> dict[str, Any] | None:
    """Return per-million rates, long-context tiers, and alternate modes from a model file."""
    cost = document.get("cost")
    if not isinstance(cost, dict):
        return None
    rates: dict[str, Any] = _rate_values(cost)
    if "input" not in rates or "output" not in rates:
        return None

    tiers = []
    for tier in cost.get("tiers") or []:
        size = (tier.get("tier") or {}).get("size")
        values = _rate_values(tier)
        if isinstance(size, int) and values:
            tiers.append({"above": size, **values})
    legacy = cost.get("context_over_200k")
    if not tiers and isinstance(legacy, dict) and _rate_values(legacy):
        tiers.append({"above": 200_000, **_rate_values(legacy)})
    if tiers:
        rates["tiers"] = sorted(tiers, key=lambda item: item["above"])

    experimental = document.get("experimental")
    configured = experimental.get("modes") if isinstance(experimental, dict) else None
    modes = {}
    for name, mode in (configured if isinstance(configured, dict) else {}).items():
        values = _rate_values(mode.get("cost") or {}) if isinstance(mode, dict) else {}
        if values:
            modes[name] = values
    reasoning = cost.get("reasoning")
    if provider in THINKING_OUTPUT and isinstance(reasoning, (int, float)):
        modes["thinking"] = {"output": float(reasoning)}
    if modes:
        rates["modes"] = dict(sorted(modes.items()))
    return rates


def _link_target(blob: bytes) -> str | None:
    """Return the target of a symlinked model file, whose blob is just the target path."""
    text = blob.decode(errors="replace").strip()
    if "\n" in text or "=" in text or not text.endswith(".toml"):
        return None
    return text


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _changes(repo: Path, providers: tuple[str, ...]) -> Iterator[tuple[str, str, str, str]]:
    """Yield (status, commit, committed_at, path) for model file changes on main's history."""
    paths = [f"providers/{provider}/models" for provider in providers]
    log = _git(
        repo, "log", "--reverse", "--first-parent", "--diff-merges=first-parent",
        "--no-renames", "--name-status", "--format=%x00%H %cI", "--", *paths,
    )
    commit = committed_at = ""
    for line in log.splitlines():
        if line.startswith("\0"):
            commit, committed_at = line[1:].split(" ", 1)
            continue
        status, _, path = line.partition("\t")
        if status in {"A", "M", "D"} and path.endswith(".toml"):
            yield status, commit, _utc(committed_at), path


def _read_blobs(repo: Path, specs: list[str]) -> list[bytes | None]:
    process = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input="".join(f"{spec}\n" for spec in specs).encode(),
        check=True, capture_output=True,
    )
    output = process.stdout
    blobs: list[bytes | None] = []
    offset = 0
    for _ in specs:
        end = output.index(b"\n", offset)
        header = output[offset:end].split()
        offset = end + 1
        if len(header) < 3 or header[1] != b"blob":
            blobs.append(None)
            continue
        size = int(header[2])
        blobs.append(output[offset:offset + size])
        offset += size + 1
    return blobs


def _replay(repo: Path, providers: tuple[str, ...]) -> tuple[dict, dict, dict]:
    """Each provider's price history, its aliases, and the lab model each file serves."""
    changes = [change for change in _changes(repo, providers) if _tracked(change[3])]
    blobs = iter(_read_blobs(repo, [
        f"{commit}:{path}" for status, commit, _, path in changes if status != "D"
    ]))
    history: dict[str, dict[str, list[dict[str, Any]]]] = {}
    links: dict[str, dict[str, str]] = {}
    # The lab model each first-party provider file currently serves, and whether the
    # file is deprecated, so lab model names resolve to the id that prices them.
    serves: dict[tuple[str, str], tuple[str, bool]] = {}
    for status, commit, committed_at, path in changes:
        _, provider, _, *model_parts = path.removesuffix(".toml").split("/")
        model = "/".join(model_parts)
        blob = None if status == "D" else next(blobs)
        if blob is None:
            serves.pop((provider, model), None)
            continue
        target = _link_target(blob)
        if target is not None:
            # An alias follows its target's history, including periods before the alias
            # later became a regular file.
            linked = (Path(model).parent / target.removesuffix(".toml")).as_posix()
            links.setdefault(provider, {})[model] = linked.removeprefix("./")
            continue
        try:
            document = tomllib.loads(blob.decode())
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            continue
        base = document.get("base_model")
        lab, _, lab_model = base.partition("/") if isinstance(base, str) else ("", "", "")
        if lab_model and LAB_PROVIDERS.get(lab, lab) == provider:
            serves[(provider, model)] = (lab_model, document.get("status") == "deprecated")
        else:
            serves.pop((provider, model), None)
        rates = parse_rates(document, provider)
        if rates is None:
            continue
        entries = history.setdefault(provider, {}).setdefault(model, [])
        if entries and entries[-1]["rates"] == rates:
            continue
        entries.append({"valid_from": committed_at, "commit": commit[:12], "rates": rates})
    return history, links, serves


def build(repo: Path, providers: tuple[str, ...] = TRACKED_PROVIDERS) -> dict[str, Any]:
    """Replay every price change of the tracked providers into effective-dated entries."""
    history, links, serves = _replay(repo, providers)
    # An alias of another provider's file, such as StepFun's global models linking to its
    # China ones, takes that file's history.
    foreign = {(provider, model): target.split("/", 3)
               for provider, models in links.items() for model, target in models.items()
               if target.startswith("../../")}
    if foreign:
        other, _, _ = _replay(repo, tuple(sorted({parts[2] for parts in foreign.values()})))
        for (provider, model), (_, _, source, path) in foreign.items():
            del links[provider][model]
            entries = other.get(source, {}).get(path.removeprefix("models/"))
            if entries:
                history.setdefault(provider, {})[model] = entries

    head = _git(repo, "log", "-1", "--format=%H %cI").split()
    return {
        "schema_version": 1,
        "source": SOURCE_URL,
        "source_commit": head[0],
        "source_committed_at": _utc(head[1]),
        "providers": {
            provider: dict(sorted(models.items()))
            for provider, models in sorted(history.items())
        },
        "links": {
            provider: dict(sorted(models.items()))
            for provider, models in sorted(links.items()) if models
        },
        "bases": _bases(serves),
    }


def _bases(serves: dict[tuple[str, str], tuple[str, bool]]) -> dict[str, dict[str, str]]:
    """Map each lab model to the first-party id serving it, preferring current ids."""
    bases: dict[str, dict[str, str]] = {}
    ranked = sorted(serves.items(), key=lambda item: (item[1][1], item[0][1]))
    for (provider, model), (lab_model, _) in ranked:
        if lab_model != model:
            bases.setdefault(provider, {}).setdefault(lab_model, model)
    return {provider: dict(sorted(models.items())) for provider, models in sorted(bases.items())}


_PER_PROVIDER = ("providers", "links", "bases")


def _current(output: Path) -> dict[str, Any]:
    return json.loads(output.read_text()) if output.exists() else {}


def changed_providers(output: Path, data: dict[str, Any]) -> list[str]:
    """The providers whose history, aliases, or served ids differ from those in `output`."""
    current = _current(output)
    return sorted({provider for key in _PER_PROVIDER
                   for provider in {*current.get(key, {}), *data[key]}
                   if current.get(key, {}).get(provider) != data[key].get(provider)})


def hold(data: dict[str, Any], output: Path, providers: set[str]) -> dict[str, Any]:
    """Keep the history of `providers` as `output` has it, such as while their changes
    await review."""
    current = _current(output)
    held = dict(data)
    for key in _PER_PROVIDER:
        merged = {provider: value for provider, value in data[key].items()
                  if provider not in providers}
        merged |= {provider: value for provider, value in current.get(key, {}).items()
                   if provider in providers}
        held[key] = dict(sorted(merged.items()))
    return held


def write(data: dict[str, Any], output: Path) -> bool:
    """Write the price history if any tracked price changed; return whether it did."""
    if output.exists():
        current = json.loads(output.read_text())
        if all(current.get(key) == data[key]
               for key in ("schema_version", "providers", "links", "bases")):
            return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return True
