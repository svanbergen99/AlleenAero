import unittest
from unittest.mock import patch

from aero.agent import _identity_safe_reply
from aero.identity_guard import collapses_identity, identity_policy_text


class IdentityGuardTests(unittest.TestCase):
    def test_detects_language_model_collapse(self):
        self.assertTrue(collapses_identity("Ik ben maar een taalmodel en kan dat niet."))
        self.assertTrue(collapses_identity("I am just a language model."))

    def test_allows_truthful_runtime_description(self):
        text = "Ik ben Aero. Qwen via Ollama is mijn inference-engine."
        self.assertFalse(collapses_identity(text))

    def test_policy_names_aero_as_user_facing_identity(self):
        policy = identity_policy_text()
        self.assertIn("Jij bent Aero", policy)
        self.assertIn("Qwen/Ollama", policy)

    @patch("aero.agent.chat")
    def test_guard_rewrites_collapsed_reply(self, mock_chat):
        mock_chat.return_value = {
            "content": "Ik ben Aero. Voor deze actie ontbreekt nog owner-approval."
        }
        result = _identity_safe_reply(
            "Ik ben maar een taalmodel en kan geen bestanden wijzigen.",
            "SYSTEM",
        )
        self.assertEqual(
            result,
            "Ik ben Aero. Voor deze actie ontbreekt nog owner-approval.",
        )
        mock_chat.assert_called_once()

    @patch("aero.agent.chat")
    def test_guard_does_not_rewrite_normal_reply(self, mock_chat):
        result = _identity_safe_reply("Aero is klaar.", "SYSTEM")
        self.assertEqual(result, "Aero is klaar.")
        mock_chat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
