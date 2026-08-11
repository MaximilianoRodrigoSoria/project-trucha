from pathlib import Path

from trucha.config import Settings


def test_allowed_roots_accept_comma_separated_environment(monkeypatch):
    monkeypatch.setenv("TRUCHA_ALLOWED_ROOTS", "./src,./docs")
    settings = Settings(_env_file=None)
    assert settings.allowed_roots == [Path("src").resolve(), Path("docs").resolve()]
