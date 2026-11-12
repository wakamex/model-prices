"""Record every page a run fetches, for the page archive.

When the MODEL_PRICES_ARCHIVE environment variable names a directory, each fetch stores the
bytes it received under blobs/<sha256> there, once per distinct body, and appends one line to
fetches.jsonl: the time, URL, any URL a redirect ended at, HTTP status, body hash and size, any
request payload, the workflow run, and any error. A page already fetched in the run is read
back from there instead of fetched again. The daily workflow stores each new page, encrypted,
in the archive's R2 bucket, and uploads the directory, encrypted, as a run artifact, which a
timer on the maintainer's machine collects into the local archive. The log has a line for
every fetch, unchanged pages included, so a price change is bounded by the last fetch that
showed the old one.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def fetched(url: str, payload: bytes | None = None) -> bytes | None:
    """The body this run already received for the URL and request payload, if it has one, so
    every check in a run reads the same bytes and each page is fetched once per run."""
    root = os.environ.get("MODEL_PRICES_ARCHIVE")
    log = Path(root) / "fetches.jsonl" if root else None
    if log is None or not log.exists():
        return None
    wanted = payload.decode() if payload is not None else None
    for line in reversed(log.read_text().splitlines()):
        entry = json.loads(line)
        if entry["url"] == url and entry.get("payload") == wanted and entry["status"] == 200 and entry["sha256"]:
            return (Path(root) / "blobs" / entry["sha256"]).read_bytes()
    return None


def record(url: str, body: bytes | None, status: int | None = None, payload: bytes | None = None,
           content_type: str | None = None, error: str | None = None, final_url: str | None = None) -> None:
    root = os.environ.get("MODEL_PRICES_ARCHIVE")
    if not root:
        return
    root_path = Path(root)
    (root_path / "blobs").mkdir(parents=True, exist_ok=True)
    digest = None
    if body is not None:
        digest = hashlib.sha256(body).hexdigest()
        blob = root_path / "blobs" / digest
        if not blob.exists():
            blob.write_bytes(body)
    entry = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
             "url": url, "status": status, "sha256": digest,
             "bytes": len(body) if body is not None else None, "content_type": content_type,
             "run": os.environ.get("GITHUB_RUN_ID")}
    if final_url is not None and final_url != url:
        entry["final_url"] = final_url
    if payload is not None:
        entry["payload"] = payload.decode()
    if error is not None:
        entry["error"] = error
    with (root_path / "fetches.jsonl").open("a") as log:
        log.write(json.dumps(entry, sort_keys=True) + "\n")
