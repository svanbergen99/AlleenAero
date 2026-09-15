import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aero.memory as memory


class MemoryTests(unittest.TestCase):
    def test_save_and_reload_recent_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "aero.db"
            with patch.object(memory, "DB_FILE", db):
                memory.initialize()
                sid = memory.current_session_id()
                memory.save_message(sid, "user", "KOBALT77")
                memory.save_message(sid, "assistant", "OK")
                self.assertEqual(
                    memory.recent_messages(sid, 2),
                    [
                        {"role": "user", "content": "KOBALT77"},
                        {"role": "assistant", "content": "OK"},
                    ],
                )


if __name__ == "__main__":
    unittest.main()
