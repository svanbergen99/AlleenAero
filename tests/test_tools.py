import unittest

from aero.tools import select_tool_names


class ToolSelectionTests(unittest.TestCase):
    def test_normal_chat_has_no_tools(self):
        self.assertEqual(select_tool_names("hoi hoe gaat het"), [])

    def test_gpu_request_only_adds_relevant_tools(self):
        self.assertIn("gpu_info", select_tool_names("hoeveel VRAM gebruikt mijn GPU?"))

    def test_file_request_has_file_tools(self):
        names = select_tool_names("lees dit project en zoek naar config")
        self.assertIn("read_tree", names)
        self.assertIn("search_text", names)


if __name__ == "__main__":
    unittest.main()
