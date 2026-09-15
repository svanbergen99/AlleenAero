import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import aero.permissions as permissions


class PermissionTests(unittest.TestCase):
    def test_repo_relative_path_is_authorized(self):
        path = permissions.authorize_path("README.md")
        self.assertTrue(str(path).endswith("README.md"))

    def test_external_path_is_denied_without_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            external = Path(tmp).resolve()
            if permissions._within(external, permissions.ROOT):
                self.skipTest("temporary directory is inside repo")
            with patch.object(permissions, "_load_grants", return_value=[]):
                with self.assertRaises(PermissionError):
                    permissions.authorize_path(external)


if __name__ == "__main__":
    unittest.main()
