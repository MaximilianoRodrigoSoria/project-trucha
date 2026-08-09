import io
import json
import unittest

from trucha.interface.mcp import handle, serve


class McpTests(unittest.TestCase):
    def test_initialize_advertises_server_and_tools(self) -> None:
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )

        self.assertEqual(response["result"]["serverInfo"]["name"], "project-trucha")
        self.assertEqual(
            response["result"]["capabilities"]["tools"], {"listChanged": False}
        )

    def test_hello_tool_returns_structured_content(self) -> None:
        response = handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "trucha_hello",
                    "arguments": {"name": "Gerard", "agent": "OpenCode"},
                },
            }
        )

        self.assertEqual(response["result"]["structuredContent"]["agent"], "OpenCode")
        self.assertIn("Gerard", response["result"]["content"][0]["text"])

    def test_stdio_transport_uses_one_json_object_per_line(self) -> None:
        source = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}) + "\n"
        )
        target = io.StringIO()

        serve(source, target)

        response = json.loads(target.getvalue())
        self.assertEqual(
            {tool["name"] for tool in response["result"]["tools"]},
            {"trucha_hello", "trucha_project_info"},
        )


if __name__ == "__main__":
    unittest.main()
