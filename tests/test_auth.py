import unittest
from types import SimpleNamespace

from auth import is_operator


class AuthTests(unittest.TestCase):
    def test_loopback_is_operator(self):
        handler = SimpleNamespace(
            client_address=("127.0.0.1", 50000),
            headers={},
        )
        self.assertTrue(is_operator(handler))


if __name__ == "__main__":
    unittest.main()

