"""Tests for the faberon console entry point."""

import uvicorn

from faberon import cli
from faberon.api.app import GRACEFUL_SHUTDOWN_TIMEOUT


def test_main_graceful_shutdown(monkeypatch):
    """Production uvicorn gets a finite graceful-shutdown timeout."""
    captured = {}
    monkeypatch.setattr(
        uvicorn, "run", lambda *a, **kw: captured.update({"args": a, "kwargs": kw})
    )

    cli.main()

    assert captured["kwargs"]["timeout_graceful_shutdown"] == GRACEFUL_SHUTDOWN_TIMEOUT
