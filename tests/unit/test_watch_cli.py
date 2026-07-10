"""Regression: cngx watch must not crash on Typer OptionInfo defaults."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cngx.cli.main import app
from cngx.cli.watch import run_watch

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


def test_run_watch_accepts_plain_python_defaults() -> None:
    """Calling run_watch without kwargs must not see Typer OptionInfo objects."""
    with (
        patch("cngx.core.config.get_config") as mock_cfg,
        patch("cngx.proxy.analysis.set_semantic_analysis_enabled"),
        patch("cngx.proxy.server.run_proxy"),
        patch("cngx.tui.dashboard.run_dashboard") as mock_dash,
        patch("cngx.cli.watch.threading.Thread") as mock_thread,
    ):
        mock_cfg.return_value.ensure_cngx_dir = MagicMock()
        mock_thread.return_value = MagicMock()
        mock_dash.side_effect = KeyboardInterrupt()

        try:
            run_watch()
        except KeyboardInterrupt:
            pass

        mock_thread.assert_called_once()
        kwargs = mock_thread.call_args.kwargs["kwargs"]
        assert kwargs["host"] == "127.0.0.1"
        assert kwargs["port"] == 8642
        assert isinstance(kwargs["host"], str)
        assert isinstance(kwargs["port"], int)


def test_watch_cli_help_lists_new_flags() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["watch", "--help"])
    assert result.exit_code == 0
    help_text = _plain(result.output)
    assert "--session-id" in help_text
    assert "--otel" in help_text
