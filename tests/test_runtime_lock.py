import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_lock as locks


class RuntimeLockTests(unittest.TestCase):
    def test_dead_owner_lock_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            lock = root / "gpu.lock"
            lock.mkdir()
            (lock / "owner.json").write_text(json.dumps({"pid": 99999999, "time": time.time()}))
            with patch.object(locks, "RUNTIME_DIR", root), patch.object(locks, "_pid_running", return_value=False):
                with locks.runtime_lock("gpu", timeout=1):
                    self.assertTrue(lock.exists())
                self.assertFalse(lock.exists())


if __name__ == "__main__":
    unittest.main()

