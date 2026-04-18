"""Functional tests for configuration loading from real files."""

from __future__ import annotations

from pathlib import Path

import pytest

from komyt.core.config import load_config, save_config, KomytConfig


@pytest.mark.functional
class TestConfigRoundTrip:
    """Test saving and loading config produces consistent results."""

    def test_save_and_reload(self, tmp_path: Path) -> None:
        config = KomytConfig()
        config.trigger.keyword = "@testbot"
        config.opencode.default_model = "gpt-4o"
        config.gui.port = 9999

        config_path = tmp_path / "komyt.toml"
        save_config(config, config_path)

        loaded = load_config(config_path)
        assert loaded.trigger.keyword == "@testbot"
        assert loaded.opencode.default_model == "gpt-4o"
        assert loaded.gui.port == 9999

    def test_example_config_is_valid(self) -> None:
        """Verify that komyt.example.toml can be loaded without errors."""
        example_path = Path(__file__).parent.parent.parent / "komyt.example.toml"
        if example_path.exists():
            config = load_config(example_path)
            assert config.trigger.keyword == "@komyt"
