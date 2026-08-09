import contextlib
import io
import json
import unittest

from trucha.interface.cli import main


class CliTests(unittest.TestCase):
    def test_cli_hello_json(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = main(["--json", "hello", "Joel", "--agent", "Codex"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["message"].startswith("Hola, Joel."))
        self.assertEqual(payload["agent"], "Codex")


if __name__ == "__main__":
    unittest.main()
