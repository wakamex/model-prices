"""Record every page a run fetches, for the page archive.

When the MODEL_PRICES_ARCHIVE environment variable names a directory, each fetch stores the
bytes it received under blobs/<sha256> there, once per distinct body, and appends one line to
fetches.jsonl: the time, URL, HTTP status, body hash and size, any request payload, and any
error. The daily workflow encrypts that directory and uploads it as a run artifact, which a
timer on the maintainer's machine collects into the archive; the log has a line for every
fetch, unchanged pages included, so a price change is bounded by the last fetch that showed
the old one.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


def record(url: str, body: bytes | None, status: int | None = None, payload: bytes | None = None,
           content_type: str | None = None, error: str | None = None) -> None:
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
             "bytes": len(body) if body is not None else None, "content_type": content_type}
    if payload is not None:
        entry["payload"] = payload.decode()
    if error is not None:
        entry["error"] = error
    with (root_path / "fetches.jsonl").open("a") as log:
        log.write(json.dumps(entry, sort_keys=True) + "\n")
