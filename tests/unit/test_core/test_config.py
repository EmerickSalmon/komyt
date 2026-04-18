"""Unit tests for configuration management."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from komyt.core.config import KomytConfig, _resolve_env_vars, load_config


@pytest.mark.unit
class TestResolveEnvVars:
    def test_resolves_existing_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_TOKEN", "my-secret")
        assert _resolve_env_vars("${TEST_TOKEN}") == "my-secret"

    def test_returns_empty_for_missing_env_var(self) -> None:
        result = _resolve_env_vars("${NONEXISTENT_VAR_12345}")
        assert result == ""

    def test_returns_plain_string_unchanged(self) -> None:
        assert _resolve_env_vars("hello") == "hello"

    def test_partial_env_syntax_unchanged(self) -> None:
        assert _resolve_env_vars("${INCOMPLETE") == "${INCOMPLETE"


@pytest.mark.unit
class TestKomytConfig:
    def test_default_values(self) -> None:
        config = KomytConfig()
        assert config.max_parallel_tasks == 3
        assert config.log_level == "info"
        assert config.trigger.keyword == "@komyt"
        assert config.trigger.case_sensitive is False
        assert config.opencode.default_model == "claude-sonnet-4-6"
        assert config.opencode.max_retries_per_step == 5
        assert config.analysis.clarity_threshold == 70
        assert config.gui.port == 8420

    def test_load_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        os.chdir(tmp_path)
        config = load_config()
        assert config.trigger.keyword == "@komyt"

    def test_load_from_explicit_path(self, tmp_path: Path) -> None:
        config_file = tmp_path / "komyt.toml"
        config_file.write_text(
            '[trigger]\nkeyword = "@mybot"\n\n'
            "[opencode]\n"
            'default_model = "gpt-4o"\n'
            "max_retries_per_step = 3\n"
        )
        config = load_config(config_file)
        assert config.trigger.keyword == "@mybot"
        assert config.opencode.default_model == "gpt-4o"
        assert config.opencode.max_retries_per_step == 3

    def test_load_partial_config_keeps_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "komyt.toml"
        config_file.write_text('[trigger]\nkeyword = "@custom"\n')
        config = load_config(config_file)
        assert config.trigger.keyword == "@custom"
        # All other values should remain default
        assert config.opencode.default_model == "claude-sonnet-4-6"
        assert config.gui.port == 8420
