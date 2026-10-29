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
# Models billed other than per token, which models.dev records at $0 per token: Google's
# Lyria music models cost a fixed price per generated song.
UNPRICED_MODELS = {"google": re.compile(r"^lyria-")}

def _tracked(path: str) -> bool:
    """Whether a model file belongs to a tracked model of its provider."""
    _, provider, _, *model_parts = path.removesuffix(".toml").split("/")
    model = "/".join(model_parts)
    pattern = TRACKED_MODELS.get(provider)
    unpriced = UNPRICED_MODELS.get(provider)
    return ((pattern is None or bool(pattern.search(model)))
            and not (unpriced and unpriced.search(model)))


# cache_read_explicit is a cache hit on a prefix the request marked for caching, where a
# provider prices it apart from an implicit hit, as Alibaba does; absent, it is cache_read.
RATE_FIELDS = ("input", "output", "cache_read", "cache_read_explicit", "cache_write")

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


# models.dev's schema 2 model files, which every tracked provider uses since 2026-10-21,
# are read through the translation models.dev itself applies to publish them in schema 1
# (costV2ToV1 and toV1Experimental in packages/core/src/translate.ts), so their prices
# continue the schema 1 history unchanged.
SCHEMAS = (1, 2)


def _first_price(write: Any) -> Any:
    """The first cache write price, the provider's default time to live, of `write`, which
    may be keyed by time to live, such as {"5m": 5, "1h": 8}."""
    return next(iter(write.values()), None) if isinstance(write, dict) else write


def _cache_write(cache: dict[str, Any] | None) -> Any:
    """Schema 1 has one cache write price; implicit caching usually has no write fee, so a
    file with only an explicit write price gives that one."""
    if cache is None:
        return None
    explicit = _first_price((cache.get("explicit") or {}).get("write"))
    return _first_price(cache.get("write")) if cache.get("write") is not None else explicit


def _explicit_read(cache: dict[str, Any] | None) -> Any:
    """An explicit cache hit's price, which schema 1 has no field for, where it differs
    from the cache read price."""
    read = (cache or {}).get("read")
    explicit = ((cache or {}).get("explicit") or {}).get("read")
    return explicit if explicit != read else None


def _present(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _schema1_cost(cost: dict[str, Any], where: str) -> dict[str, Any] | None:
    """A schema 2 cost in schema 1's per-token fields, or None when it has no per-token text
    input and output price, such as a model priced per image or per second."""
    text = cost.get("text") or {}
    given, made = text.get("input"), text.get("output")
    per_token = lambda price: price.get("unit") in (None, "token")
    if given is None or made is None or not per_token(given) or not per_token(made):
        return None
    tiers: dict[float, dict[str, Any]] = {}

    def tier(when: dict[str, Any]) -> dict[str, Any]:
        context = when.get("context") if len(when) == 1 else None
        size = (context or {}).get("gt", (context or {}).get("gte"))
        if not isinstance(size, (int, float)):
            raise ValueError(f"{where}: unsupported long-context override {when}")
        return tiers.setdefault(size, {"tier": {"type": "context", "size": size},
                                       "input": given["price"], "output": made["price"]})

    # Overrides on other conditions, such as service tier or region, have no schema 1 field.
    context_only = lambda override: set(override["when"]) <= {"context"}
    for override in filter(context_only, given.get("overrides") or []):
        cache = override.get("cache")
        tier(override["when"]).update(_present({
            "input": override.get("price"), "cache_read": (cache or {}).get("read"),
            "cache_read_explicit": _explicit_read(cache), "cache_write": _cache_write(cache)}))
    for override in filter(context_only, made.get("overrides") or []):
        tier(override["when"]).update(_present({
            "output": override.get("price"), "reasoning": override.get("reasoning")}))
    cache = given.get("cache")
    return _present({
        "input": given["price"], "output": made["price"], "reasoning": made.get("reasoning"),
        "cache_read": (cache or {}).get("read"), "cache_read_explicit": _explicit_read(cache),
        "cache_write": _cache_write(cache), "tiers": list(tiers.values()) or None,
    })


# Where each schema 1 price sits in a schema 2 cost, for reading a multiplier's factor.
_FACTOR_PATHS = {"input": ("text", "input", "price"), "output": ("text", "output", "price"),
                 "reasoning": ("text", "output", "reasoning"),
                 "cache_read": ("text", "input", "cache", "read"),
                 "cache_read_explicit": ("text", "input", "cache", "explicit", "read"),
                 "cache_write": ("text", "input", "cache", "write")}


def _factor(factor: Any, path: tuple[str, ...]) -> float:
    """A multiplier's factor for one price: a number scales every price below it, and a price
    an object factor does not name keeps factor 1."""
    for key in path:
        if not isinstance(factor, dict):
            break
        factor = factor.get(key)
    if isinstance(factor, dict):
        factor = _first_price(factor)
    return factor if isinstance(factor, (int, float)) else 1


def _schema1_modes(document: dict[str, Any], cost: dict[str, Any] | None,
                   where: str) -> dict[str, Any]:
    """Schema 1 modes, each with its own prices: a mode's stated cost, or the base prices
    scaled by the multiplier for its service tier, which defaults to the mode's name."""
    modes = {}
    multipliers = (document.get("cost") or {}).get("multipliers") or []
    for name, mode in ((document.get("experimental") or {}).get("modes") or {}).items():
        tier = mode.get("service_tier", name)
        factor = next((item["factor"] for item in multipliers
                       if item.get("when") == {"service_tier": {"equals": tier}}), None)
        if "cost" in mode:
            priced = _schema1_cost(mode["cost"], where)
        elif factor is not None and cost is not None:
            priced = {key: round(value * _factor(factor, _FACTOR_PATHS[key]), 10)
                      for key, value in cost.items() if key in _FACTOR_PATHS}
        else:
            priced = None
        if priced:
            modes[name] = {"cost": {key: value for key, value in priced.items() if key != "tiers"}}
    return modes


def schema1(document: dict[str, Any], where: str = "") -> dict[str, Any]:
    """A models.dev model file in schema 1's shape, translating a schema 2 file's prices;
    an unknown schema raises, so a format change stops the history build."""
    schema = document.get("schema", 1)
    if schema not in SCHEMAS:
        raise ValueError(f"{where}: models.dev schema {schema!r} is not supported")
    if schema == 1:
        return document
    cost = _schema1_cost(document["cost"], where) if document.get("cost") else None
    reasoning = (document.get("capabilities") or {}).get("reasoning")
    # Schema 1 drops the reasoning price of a model that does not reason.
    if cost and isinstance(reasoning, dict) and reasoning.get("supported") is False:
        cost.pop("reasoning", None)
        for tier in cost.get("tiers", []):
            tier.pop("reasoning", None)
    modes = _schema1_modes(document, cost, where)
    return _present({"base_model": document.get("base_model"), "status": document.get("status"),
                     "cost": cost, "experimental": {"modes": modes} if modes else None})


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
        # T is a type change, such as a link becoming a file with its own prices.
        if status in {"A", "M", "D", "T"} and path.endswith(".toml"):
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


def _replay(repo: Path, providers: tuple[str, ...]) -> tuple[dict, dict, dict, dict, dict]:
    """Each provider's price history, its aliases, the lab model each file serves, the
    models models.dev retired, and each file's current document."""
    changes = [change for change in _changes(repo, providers) if _tracked(change[3])]
    blobs = iter(_read_blobs(repo, [
        f"{commit}:{path}" for status, commit, _, path in changes if status != "D"
    ]))
    history: dict[str, dict[str, list[dict[str, Any]]]] = {}
    links: dict[str, dict[str, str]] = {}
    # The lab model each first-party provider file currently serves, and whether the
    # file is deprecated, so lab model names resolve to the id that prices them.
    serves: dict[tuple[str, str], tuple[str, bool]] = {}
    # Models models.dev marks deprecated, or whose file it deleted.
    retired: dict[tuple[str, str], str] = {}
    current: dict[tuple[str, str], dict[str, Any]] = {}
    for status, commit, committed_at, path in changes:
        _, provider, _, *model_parts = path.removesuffix(".toml").split("/")
        # No API accepts an id with surrounding spaces, such as a file models.dev later
        # renamed to drop a trailing space, so its history belongs to the trimmed id.
        model = "/".join(model_parts).strip()
        blob = None if status == "D" else next(blobs)
        if blob is None:
            serves.pop((provider, model), None)
            current.pop((provider, model), None)
            retired[(provider, model)] = "removed"
            continue
        target = _link_target(blob)
        if target is not None:
            # An alias follows its target's history, including periods before the alias
            # later became a regular file.
            linked = (Path(model).parent / target.removesuffix(".toml")).as_posix()
            links.setdefault(provider, {})[model] = linked.removeprefix("./")
            current.pop((provider, model), None)
            continue
        try:
            document = tomllib.loads(blob.decode())
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            continue
        current[(provider, model)] = document
        document = schema1(document, f"{commit[:12]}:{path}")
        if document.get("status") == "deprecated":
            retired[(provider, model)] = "deprecated"
        else:
            retired.pop((provider, model), None)
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
    statuses: dict[str, dict[str, str]] = {}
    for (provider, model), state in sorted(retired.items()):
        if model in history.get(provider, {}):
            statuses.setdefault(provider, {})[model] = state
    return history, links, serves, statuses, current


# Conditions on the time of a request, which schedules.toml records for model-prices.
_CLOCK = re.compile(r"'(utc_hours|utc_days|holiday)'")


def _rules(current: dict[tuple[str, str], dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The rules models.dev now gives that model-prices keeps in its own files, for the
    check to compare: time-of-day multipliers, which schedules.toml records, and cache
    write prices by lifetime, whose longer lifetimes cache_writes.toml records."""
    rules: dict[str, dict[str, Any]] = {}
    for (provider, model), document in sorted(current.items()):
        cost = document.get("cost") or {}
        given = (cost.get("text") or {}).get("input") or {}
        write = (given.get("cache") or {}).get("write")
        rule: dict[str, Any] = {}
        clock = [item for item in cost.get("multipliers") or []
                 if _CLOCK.search(repr(item.get("when")))]
        if clock:
            rule["multipliers"] = clock
        if isinstance(write, dict) and len(write) > 1:
            rule |= {"input": given.get("price"), "cache_write": write}
        if rule:
            rules.setdefault(provider, {})[model] = rule
    return rules


def build(repo: Path, providers: tuple[str, ...] = TRACKED_PROVIDERS) -> dict[str, Any]:
    """Replay every price change of the tracked providers into effective-dated entries."""
    history, links, serves, statuses, current = _replay(repo, providers)
    # An alias of another provider's file, such as StepFun's global models linking to its
    # China ones, takes that file's history.
    foreign = {(provider, model): target.split("/", 3)
               for provider, models in links.items() for model, target in models.items()
               if target.startswith("../../")}
    if foreign:
        other, *_ = _replay(repo, tuple(sorted({parts[2] for parts in foreign.values()})))
        for (provider, model), (_, _, source, path) in foreign.items():
            del links[provider][model]
            entries = other.get(source, {}).get(path.removeprefix("models/"), [])
            # The linked history applies until the file's own prices begin, as when StepFun's
            # global files, links before schema 2, became files with their own prices.
            own = history.get(provider, {}).get(model, [])
            start = own[0]["valid_from"] if own else None
            entries = [entry for entry in entries if start is None or entry["valid_from"] < start]
            joined = [entry for index, entry in enumerate(entries + own)
                      if index == 0 or entry["rates"] != (entries + own)[index - 1]["rates"]]
            if joined:
                history.setdefault(provider, {})[model] = joined

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
        "status": statuses,
        "rules": _rules(current),
    }


def _bases(serves: dict[tuple[str, str], tuple[str, bool]]) -> dict[str, dict[str, str]]:
    """Map each lab model to the first-party id serving it, preferring current ids."""
    bases: dict[str, dict[str, str]] = {}
    ranked = sorted(serves.items(), key=lambda item: (item[1][1], item[0][1]))
    for (provider, model), (lab_model, _) in ranked:
        if lab_model != model:
            bases.setdefault(provider, {}).setdefault(lab_model, model)
    return {provider: dict(sorted(models.items())) for provider, models in sorted(bases.items())}


_PER_PROVIDER = ("providers", "links", "bases", "status", "rules")


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
               for key in ("schema_version", *_PER_PROVIDER)):
            return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n")
    return True
