import unittest

from trucha.core import hello, project_info


class CoreTests(unittest.TestCase):
    def test_hello_uses_defaults_for_blank_values(self) -> None:
        result = hello("  ", "  ")

        self.assertEqual(
            result,
            {
                "message": "Hola, mundo. La memoria de project-trucha esta despierta.",
                "agent": "terminal",
                "project": "project-trucha",
            },
        )

    def test_project_info_exposes_cli_and_mcp(self) -> None:
        result = project_info()

        self.assertEqual(result["interfaces"], ["CLI", "MCP stdio"])
        self.assertIn("trucha_hello", result["tools"])


if __name__ == "__main__":
    unittest.main()
