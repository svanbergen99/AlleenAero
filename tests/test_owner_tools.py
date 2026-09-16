import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import owner_tools as owner_tools
import permissions as permissions


class OwnerToolApprovalTests(unittest.TestCase):
    def setUp(self):
        permissions._PENDING.clear()

    def test_write_inside_project_executes_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "new.txt"
            with patch.object(permissions, "ROOT", root), patch.object(owner_tools, "PROJECT_ROOT", root):
                result = owner_tools.execute("write_text", {"path": str(target), "content": "hello"})
                self.assertEqual(result["path"], str(target))
                self.assertEqual(target.read_text(encoding="utf-8"), "hello")
                self.assertFalse(permissions._PENDING)

    def test_read_inside_project_executes_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "readme.txt"
            target.write_text("project data", encoding="utf-8")
            with patch.object(permissions, "ROOT", root), patch.object(owner_tools, "PROJECT_ROOT", root):
                result = owner_tools.execute("read_text", {"path": str(target)})
                self.assertEqual(result["content"], "project data")
                self.assertFalse(permissions._PENDING)

    def test_outside_project_is_approval_gated(self):
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as external_tmp:
            project = Path(project_tmp).resolve()
            outside = Path(external_tmp).resolve() / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            with patch.object(permissions, "ROOT", project), patch.object(owner_tools, "PROJECT_ROOT", project):
                result = owner_tools.execute("read_text", {"path": str(outside)})
                self.assertTrue(result["approval_required"])
                self.assertIn("BUITEN PROJECT", result["summary"])

    def test_outside_approval_is_one_time(self):
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as external_tmp:
            project = Path(project_tmp).resolve()
            outside = Path(external_tmp).resolve() / "outside.txt"
            with patch.object(permissions, "ROOT", project), patch.object(owner_tools, "PROJECT_ROOT", project):
                request = owner_tools.execute("write_text", {"path": str(outside), "content": "ok"})
                item = permissions.consume_approval(request["approval_id"])
                owner_tools.execute_approved(item["kind"], item["args"])
                self.assertEqual(outside.read_text(encoding="utf-8"), "ok")
                with self.assertRaises(ValueError):
                    permissions.consume_approval(request["approval_id"])

    def test_execute_file_inside_project_still_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            target = root / "task.py"
            target.write_text("print('ok')", encoding="utf-8")
            with patch.object(permissions, "ROOT", root), patch.object(owner_tools, "PROJECT_ROOT", root):
                result = owner_tools.execute("execute_file", {"path": str(target)})
                self.assertTrue(result["approval_required"])


if __name__ == "__main__":
    unittest.main()

