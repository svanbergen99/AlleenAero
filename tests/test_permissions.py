import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aero.permissions as permissions


class PermissionTests(unittest.TestCase):
    def test_project_relative_path_is_authorized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch.object(permissions, "ROOT", root):
                path = permissions.authorize_path("README.md")
                self.assertEqual(path, root / "README.md")

    def test_external_direct_access_is_denied(self):
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as external_tmp:
            project = Path(project_tmp).resolve()
            external = Path(external_tmp).resolve() / "outside.txt"
            with patch.object(permissions, "ROOT", project):
                with self.assertRaises(PermissionError):
                    permissions.authorize_path(external)

    def test_external_path_can_be_prepared_for_exact_approval(self):
        with tempfile.TemporaryDirectory() as project_tmp, tempfile.TemporaryDirectory() as external_tmp:
            project = Path(project_tmp).resolve()
            external = Path(external_tmp).resolve() / "outside.txt"
            with patch.object(permissions, "ROOT", project):
                self.assertEqual(permissions.prepare_path_for_approval(external), external)
                self.assertFalse(permissions.is_inside_project(external))


if __name__ == "__main__":
    unittest.main()
