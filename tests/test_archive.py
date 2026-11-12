import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

from model_prices import archive

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("collect_pages", ROOT / "tools" / "collect_pages.py")
collect_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(collect_pages)


class ArchiveTests(unittest.TestCase):
    def test_every_fetch_is_logged_and_each_body_stored_once(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(os.environ, {"MODEL_PRICES_ARCHIVE": directory}):
            archive.record("https://example.com/pricing", b"<p>$1</p>", 200, content_type="text/html")
            archive.record("https://example.com/pricing", b"<p>$1</p>", 200)
            archive.record("https://example.com/feed", None, 403, payload=b"{}", error="Forbidden")
            log = [json.loads(line) for line in (Path(directory) / "fetches.jsonl").read_text().splitlines()]
            blobs = list((Path(directory) / "blobs").iterdir())
        digest = hashlib.sha256(b"<p>$1</p>").hexdigest()
        self.assertEqual([entry["sha256"] for entry in log], [digest, digest, None])
        self.assertEqual([blob.name for blob in blobs], [digest])
        self.assertEqual((log[2]["status"], log[2]["payload"], log[2]["error"]), (403, "{}", "Forbidden"))

    def test_nothing_is_recorded_without_an_archive_directory(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(Path, "mkdir") as mkdir:
            archive.record("https://example.com", b"x", 200)
        mkdir.assert_not_called()


@unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "needs age")
class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.key = Path(self.directory.name) / "key.txt"
        subprocess.run(["age-keygen", "-o", str(self.key)], check=True, capture_output=True)
        self.recipient = subprocess.run(["age-keygen", "-y", str(self.key)], check=True,
                                        capture_output=True, text=True).stdout.strip()

    def tearDown(self):
        self.directory.cleanup()

    def bundle(self, members: dict[str, bytes]) -> bytes:
        plain = io.BytesIO()
        with tarfile.open(fileobj=plain, mode="w") as tar:
            for name, data in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return subprocess.run(["age", "-r", self.recipient], input=plain.getvalue(), check=True,
                              capture_output=True).stdout

    def test_a_bundle_unpacks_to_its_blobs_and_log(self):
        body = b"<p>$1</p>"
        name = f"./blobs/{hashlib.sha256(body).hexdigest()}"
        members = collect_pages.unpack(self.bundle({name: body, "./fetches.jsonl": b"{}\n"}), self.key)
        self.assertEqual(members[name], body)

    def test_a_bundle_with_anything_else_is_refused(self):
        for members in ({"../escape": b"x", "./fetches.jsonl": b""},
                        {"./blobs/" + "0" * 64: b"not that hash", "./fetches.jsonl": b""},
                        {"./blobs/" + hashlib.sha256(b"x").hexdigest(): b"x"}):
            with self.subTest(members=sorted(members)), self.assertRaises(ValueError):
                collect_pages.unpack(self.bundle(members), self.key)


if __name__ == "__main__":
    unittest.main()
