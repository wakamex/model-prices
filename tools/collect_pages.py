#!/usr/bin/env python3
"""Collect the pages the daily workflow fetched into the local page archive.

Each run of update-prices.yml uploads the pages it fetched as an artifact named
pages-<run id>-<attempt>, encrypted to the archive's public key, and kept for 90 days. This
collects every such artifact not yet collected: it decrypts it with the private key, checks it
holds only blobs/<sha256> files and fetches.jsonl, adds each blob to the archive under its hash,
and appends the run's fetch log lines, tagged with the run, to the archive's fetches.jsonl.

    python3 tools/collect_pages.py [--archive DIR] [--key FILE]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile

REPOSITORY = "wakamex/model-prices"
GH = "/home/linuxbrew/.linuxbrew/bin/gh"
ARCHIVE = Path("/mnt/raid5/model-prices-pages")
KEY = Path.home() / ".config" / "model-prices" / "archive-key.txt"
BLOB = re.compile(r"\./blobs/[0-9a-f]{64}")


def artifacts() -> list[dict]:
    """The repository's unexpired page artifacts, oldest first."""
    pages = subprocess.run([GH, "api", "--paginate", f"repos/{REPOSITORY}/actions/artifacts?per_page=100",
                            "--jq", ".artifacts[]"], check=True, capture_output=True, text=True).stdout
    found = [json.loads(line) for line in pages.splitlines() if line.strip()]
    return sorted((item for item in found if item["name"].startswith("pages-") and not item["expired"]),
                  key=lambda item: item["created_at"])


def unpack(bundle: bytes, key: Path) -> dict[str, bytes]:
    """The members of one decrypted bundle, refusing anything but blobs and the fetch log."""
    plain = subprocess.run(["/usr/bin/age", "-d", "-i", str(key)], input=bundle, check=True,
                           capture_output=True).stdout
    members = {}
    with tarfile.open(fileobj=io.BytesIO(plain)) as tar:
        for member in tar.getmembers():
            if member.isdir() and member.name in {".", "./blobs"}:
                continue
            if not member.isfile() or not (member.name == "./fetches.jsonl" or BLOB.fullmatch(member.name)):
                raise ValueError(f"unexpected member {member.name!r} in the page bundle")
            data = tar.extractfile(member).read()
            if member.name != "./fetches.jsonl" and hashlib.sha256(data).hexdigest() != member.name[-64:]:
                raise ValueError(f"{member.name} does not match its hash")
            members[member.name] = data
    if "./fetches.jsonl" not in members:
        raise ValueError("the page bundle has no fetch log")
    return members


def collect(archive: Path, key: Path) -> int:
    (archive / "blobs").mkdir(parents=True, exist_ok=True)
    done_path = archive / "collected.txt"
    done = set(done_path.read_text().split()) if done_path.exists() else set()
    count = 0
    for item in artifacts():
        if item["name"] in done:
            continue
        zipped = subprocess.run([GH, "api", f"repos/{REPOSITORY}/actions/artifacts/{item['id']}/zip"],
                                check=True, capture_output=True).stdout
        with zipfile.ZipFile(io.BytesIO(zipped)) as package:
            members = unpack(package.read("pages.tar.age"), key)
        for name, data in members.items():
            if name != "./fetches.jsonl":
                blob = archive / "blobs" / name[-64:]
                if not blob.exists():
                    with tempfile.NamedTemporaryFile(dir=archive / "blobs", delete=False) as part:
                        part.write(data)
                    Path(part.name).rename(blob)
        run = item["workflow_run"]["id"] if item.get("workflow_run") else None
        lines = [json.dumps({**json.loads(line), "run": run}, sort_keys=True)
                 for line in members["./fetches.jsonl"].decode().splitlines() if line.strip()]
        with (archive / "fetches.jsonl").open("a") as log:
            log.write("".join(line + "\n" for line in lines))
        with done_path.open("a") as record:
            record.write(item["name"] + "\n")
        count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--key", type=Path, default=KEY)
    args = parser.parse_args(argv)
    print(f"collected {collect(args.archive, args.key)} page bundles into {args.archive}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
