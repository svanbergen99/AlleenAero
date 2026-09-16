import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aero.owner_tools as owner_tools
import aero.permissions as permissions


class OwnerToolApprovalTests(unittest.TestCase):
    def setUp(self):
        permissions._PENDING.clear()

    def test_write_is_not_executed_before_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "new.txt"
            with patch.object(permissions, "ROOT", root), patch.object(owner_tools, "PROJECT_ROOT", root):
                result = owner_tools.execute("write_text", {"path": str(target), "content": "hello"})
                self.assertTrue(result["approval_required"])
                self.assertFalse(target.exists())

    def test_read_is_also_approval_gated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "readme.txt"
            target.write_text("secret-ish test", encoding="utf-8")
            with patch.object(permissions, "ROOT", root), patch.object(owner_tools, "PROJECT_ROOT", root):
                result = owner_tools.execute("read_text", {"path": str(target)})
                self.assertTrue(result["approval_required"])
                self.assertNotIn("secret-ish test", str(result))

    def test_outside_project_is_clearly_marked(self):
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as external_tmp:
            project = Path(project_tmp).resolve()
            outside = Path(external_tmp).resolve() / "outside.txt"
            with patch.object(permissions, "ROOT", project), patch.object(owner_tools, "PROJECT_ROOT", project):
                result = owner_tools.execute("read_text", {"path": str(outside)})
                self.assertTrue(result["approval_required"])
                self.assertIn("BUITEN PROJECT", result["summary"])

    def test_approval_is_one_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "once.txt"
            with patch.object(permissions, "ROOT", root), patch.object(owner_tools, "PROJECT_ROOT", root):
                request = owner_tools.execute("write_text", {"path": str(target), "content": "ok"})
                item = permissions.consume_approval(request["approval_id"])
                owner_tools.execute_approved(item["kind"], item["args"])
                self.assertEqual(target.read_text(encoding="utf-8"), "ok")
                with self.assertRaises(ValueError):
                    permissions.consume_approval(request["approval_id"])


if __name__ == "__main__":
    unittest.main()
