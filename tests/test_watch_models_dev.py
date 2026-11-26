import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("watch_models_dev", ROOT / "tools" / "watch_models_dev.py")
watch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watch)


class StateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name) / "models-dev.json"
        self.enterContext(mock.patch.object(watch, "STATE", self.state))

    def test_the_state_is_replaced_whole(self):
        watch.save({"head": "a"})
        watch.save({"head": "b"})
        self.assertEqual(json.loads(self.state.read_text()), {"head": "b"})
        self.assertEqual([path.name for path in self.state.parent.iterdir()], ["models-dev.json"])

    def test_an_unreadable_state_starts_over(self):
        # A run killed while the state was written in place left it empty, which stopped
        # every later run.
        self.assertEqual(watch.load(), {})
        self.state.write_text("")
        with mock.patch("sys.stderr"):
            self.assertEqual(watch.load(), {})


    def test_the_page_watch_starts_once_an_hour(self):
        state = {}
        with mock.patch.object(watch, "_run") as run, mock.patch("sys.stdout"):
            for now in (10_000, 11_000, 10_000 + watch.PAGE_WATCH_INTERVAL):
                watch.start_page_watch(state, now)
        self.assertEqual(run.call_count, 2)
        self.assertIn("watch-pages.yml", run.call_args.args)
        self.assertEqual(state["page_watch_started"], 10_000 + watch.PAGE_WATCH_INTERVAL)

    def test_nothing_starts_while_the_state_cannot_be_saved(self):
        # On a full disk the watch started the page watch every minute, since the time it
        # started could not be saved.
        state = {}
        with mock.patch.object(watch, "_run") as run, \
                mock.patch.object(watch, "save", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(OSError):
                watch.start_page_watch(state, 10_000)
        run.assert_not_called()
        # A start that fails is undone, so the next run tries again.
        with mock.patch.object(watch, "_run", side_effect=watch.subprocess.CalledProcessError(1, "gh")), \
                mock.patch("sys.stdout"):
            with self.assertRaises(watch.subprocess.CalledProcessError):
                watch.start_page_watch(state, 20_000)
        self.assertNotIn("page_watch_started", state)


if __name__ == "__main__":
    unittest.main()
