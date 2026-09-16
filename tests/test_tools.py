import unittest

from aero.owner_tools import TOOL_SCHEMAS, select_tool_names


class ToolSelectionTests(unittest.TestCase):
    def test_normal_chat_has_no_tools(self):
        self.assertEqual(select_tool_names("hoi hoe gaat het"), [])

    def test_gpu_request_adds_gpu_tool(self):
        self.assertIn("gpu_info", select_tool_names("hoeveel VRAM gebruikt mijn GPU?"))

    def test_file_request_has_file_tools(self):
        names = select_tool_names("lees dit project en zoek naar config")
        self.assertIn("list_dir", names)
        self.assertIn("find_files", names)
        self.assertIn("search_text", names)

    def test_operator_categories_are_registered(self):
        expected = {
            "env_get", "env_set", "env_delete",
            "pip_check", "pip_install", "npm_check", "npm_install",
            "syntax_check", "sqlite_query", "json_query",
            "resource_monitor", "gpu_info",
            "list_dir", "find_files", "search_text", "file_info", "tail_log",
            "list_processes", "process_status", "start_process", "kill_process",
            "zip_create", "zip_extract", "port_check", "ping_host", "http_request",
            "clipboard_read", "clipboard_write", "run_command",
            "service_status", "service_start", "service_stop", "service_restart",
            "git_status", "git_diff", "git_commit", "git_pull", "git_push",
            "analyze_document", "analyze_image", "analyze_audio",
        }
        self.assertTrue(expected.issubset(TOOL_SCHEMAS.keys()), expected - TOOL_SCHEMAS.keys())


if __name__ == "__main__":
    unittest.main()
