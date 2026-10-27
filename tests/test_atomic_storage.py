import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from bridge.storage import Config


class AtomicStorageTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / "data/atomic-test-temp"
        base.mkdir(parents=True, exist_ok=True)
        directory = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.path = self.root / "state.json"
        self.path.write_text('{"previous": true}', encoding="utf-8")

    def test_concurrent_writers_use_distinct_complete_staging_files(self):
        barrier = threading.Barrier(2)
        stages = []
        original = Path.replace

        def replace(source, target):
            stages.append(source)
            self.assertIn(json.loads(source.read_text(encoding="utf-8"))["value"], (1, 2))
            barrier.wait(timeout=3)
            return original(source, target)

        with patch.object(Path, "replace", replace), ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda value: Config._atomic(self.path, {"value": value}), (1, 2)))
        self.assertEqual(len(set(stages)), 2)
        self.assertIn(json.loads(self.path.read_text(encoding="utf-8"))["value"], (1, 2))
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_transient_windows_sharing_error_retries_without_truncating_old_file(self):
        original = Path.replace
        calls = []

        def replace(source, target):
            calls.append(source)
            if len(calls) == 1:
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"previous": True})
                error = PermissionError("sharing violation")
                error.winerror = 32
                raise error
            return original(source, target)

        with patch.object(Path, "replace", replace), patch("bridge.storage.time.sleep") as sleep:
            Config._atomic(self.path, {"value": "完整的新内容"})
        self.assertEqual(len(calls), 2)
        sleep.assert_called_once()
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["value"], "完整的新内容")

    def test_persistent_windows_denial_preserves_previous_file_and_is_bounded(self):
        error = PermissionError("access denied")
        error.winerror = 5
        with patch.object(Path, "replace", side_effect=error) as replace, patch("bridge.storage.time.sleep"):
            with self.assertRaises(PermissionError):
                Config._atomic(self.path, {"value": "not committed"})
        self.assertEqual(replace.call_count, 7)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"previous": True})
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_other_errors_are_not_retried(self):
        with patch.object(Path, "replace", side_effect=PermissionError("permission")) as replace, patch("bridge.storage.time.sleep") as sleep:
            with self.assertRaises(PermissionError):
                Config._atomic(self.path, {"value": "not committed"})
        self.assertEqual(replace.call_count, 1)
        sleep.assert_not_called()
