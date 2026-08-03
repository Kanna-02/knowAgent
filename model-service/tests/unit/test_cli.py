from __future__ import annotations

import pytest

from knowagent_model import cli


def test_cli_starts_uvicorn_with_configured_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, int, bool]] = []

    def fake_run(app: str, *, host: str, port: int, reload: bool) -> None:
        calls.append((app, host, port, reload))

    monkeypatch.setenv("KNOWAGENT_MODEL_HOST", "0.0.0.0")
    monkeypatch.setenv("KNOWAGENT_MODEL_PORT", "8200")
    monkeypatch.setattr("knowagent_model.cli.uvicorn.run", fake_run)

    cli.main()

    assert calls == [("knowagent_model.app:app", "0.0.0.0", 8200, False)]
