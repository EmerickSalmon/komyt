"""Configuration management for Komyt."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import tomli
import tomli_w

DEFAULT_CONFIG_FILENAME = "komyt.toml"
DEFAULT_DATA_DIR = "~/.komyt"


@dataclass
class TriggerConfig:
    keyword: str = "@komyt"
    case_sensitive: bool = False


@dataclass
class OpenCodeConfig:
    server_url: str = "http://localhost:54321"
    default_model: str = "claude-sonnet-4-6"
    max_tokens_per_task: int = 500_000
    max_retries_per_step: int = 5
    stop_on_step_failure: bool = False
    use_cli: bool = True
    python_image: str = "komyt-python:latest"
    skip_validation: bool = False


@dataclass
class GitHubConfig:
    token: str = ""
    default_org: str = ""
    poll_interval_seconds: int = 300
    labels_filter: list[str] = field(default_factory=list)


@dataclass
class DockerConfig:
    enabled: bool = True
    default_image: str = "ubuntu:24.04"
    memory_limit: str = "4g"
    cpu_limit: int = 2
    cleanup_after: bool = True


@dataclass
class GUIConfig:
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8420


@dataclass
class AnalysisConfig:
    clarity_threshold: int = 70
    require_agent_instructions: bool = False


@dataclass
class NotificationsConfig:
    webhook_url: str = ""
    notify_on: list[str] = field(default_factory=lambda: ["success", "failure", "needs_review"])


@dataclass
class KomytConfig:
    """Root configuration object."""

    max_parallel_tasks: int = 3
    log_level: str = "info"
    data_dir: str = DEFAULT_DATA_DIR

    trigger: TriggerConfig = field(default_factory=TriggerConfig)
    opencode: OpenCodeConfig = field(default_factory=OpenCodeConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    gui: GUIConfig = field(default_factory=GUIConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)


def _resolve_env_vars(value: str) -> str:
    """Resolve ${ENV_VAR} patterns in string values."""
    if value.startswith("${") and value.endswith("}"):
        env_key = value[2:-1]
        return os.environ.get(env_key, "")
    return value


def load_config(config_path: Path | None = None) -> KomytConfig:
    """Load configuration from a TOML file.

    Looks for komyt.toml in:
    1. Explicit path (if provided)
    2. Current working directory
    3. ~/.komyt/komyt.toml
    """
    if config_path and config_path.exists():
        path = config_path
    elif Path(DEFAULT_CONFIG_FILENAME).exists():
        path = Path(DEFAULT_CONFIG_FILENAME)
    elif Path.home().joinpath(".komyt", DEFAULT_CONFIG_FILENAME).exists():
        path = Path.home() / ".komyt" / DEFAULT_CONFIG_FILENAME
    else:
        return KomytConfig()

    with open(path, "rb") as f:
        raw = tomli.load(f)

    config = KomytConfig()

    # General
    general = raw.get("general", {})
    config.max_parallel_tasks = general.get("max_parallel_tasks", config.max_parallel_tasks)
    config.log_level = general.get("log_level", config.log_level)
    config.data_dir = general.get("data_dir", config.data_dir)

    # Trigger
    trigger = raw.get("trigger", {})
    config.trigger.keyword = trigger.get("keyword", config.trigger.keyword)
    config.trigger.case_sensitive = trigger.get("case_sensitive", config.trigger.case_sensitive)

    # OpenCode
    oc = raw.get("opencode", {})
    config.opencode.server_url = oc.get("server_url", config.opencode.server_url)
    config.opencode.default_model = oc.get("default_model", config.opencode.default_model)
    config.opencode.max_tokens_per_task = oc.get(
        "max_tokens_per_task", config.opencode.max_tokens_per_task
    )
    config.opencode.max_retries_per_step = oc.get(
        "max_retries_per_step", config.opencode.max_retries_per_step
    )
    config.opencode.stop_on_step_failure = oc.get(
        "stop_on_step_failure", config.opencode.stop_on_step_failure
    )
    config.opencode.use_cli = oc.get("use_cli", config.opencode.use_cli)
    config.opencode.python_image = oc.get("python_image", config.opencode.python_image)
    config.opencode.skip_validation = oc.get(
        "skip_validation", config.opencode.skip_validation
    )

    # GitHub
    gh = raw.get("github", {})
    config.github.token = _resolve_env_vars(gh.get("token", config.github.token))
    config.github.default_org = gh.get("default_org", config.github.default_org)
    config.github.poll_interval_seconds = gh.get(
        "poll_interval_seconds", config.github.poll_interval_seconds
    )
    config.github.labels_filter = gh.get("labels_filter", config.github.labels_filter)

    # Docker
    dk = raw.get("docker", {})
    config.docker.enabled = dk.get("enabled", config.docker.enabled)
    config.docker.default_image = dk.get("default_image", config.docker.default_image)
    config.docker.memory_limit = dk.get("memory_limit", config.docker.memory_limit)
    config.docker.cpu_limit = dk.get("cpu_limit", config.docker.cpu_limit)
    config.docker.cleanup_after = dk.get("cleanup_after", config.docker.cleanup_after)

    # GUI
    gui = raw.get("gui", {})
    config.gui.enabled = gui.get("enabled", config.gui.enabled)
    config.gui.host = gui.get("host", config.gui.host)
    config.gui.port = gui.get("port", config.gui.port)

    # Analysis
    analysis = raw.get("analysis", {})
    config.analysis.clarity_threshold = analysis.get(
        "clarity_threshold", config.analysis.clarity_threshold
    )
    config.analysis.require_agent_instructions = analysis.get(
        "require_agent_instructions", config.analysis.require_agent_instructions
    )

    # Notifications
    notif = raw.get("notifications", {})
    config.notifications.webhook_url = notif.get("webhook_url", config.notifications.webhook_url)
    config.notifications.notify_on = notif.get("notify_on", config.notifications.notify_on)

    return config


def save_config(config: KomytConfig, path: Path) -> None:
    """Save configuration to a TOML file."""
    data = {
        "general": {
            "max_parallel_tasks": config.max_parallel_tasks,
            "log_level": config.log_level,
            "data_dir": config.data_dir,
        },
        "trigger": {
            "keyword": config.trigger.keyword,
            "case_sensitive": config.trigger.case_sensitive,
        },
        "opencode": {
            "server_url": config.opencode.server_url,
            "default_model": config.opencode.default_model,
            "max_tokens_per_task": config.opencode.max_tokens_per_task,
            "max_retries_per_step": config.opencode.max_retries_per_step,
            "stop_on_step_failure": config.opencode.stop_on_step_failure,
            "use_cli": config.opencode.use_cli,
            "python_image": config.opencode.python_image,
            "skip_validation": config.opencode.skip_validation,
        },
        "github": {
            "token": config.github.token,
            "default_org": config.github.default_org,
            "poll_interval_seconds": config.github.poll_interval_seconds,
            "labels_filter": config.github.labels_filter,
        },
        "docker": {
            "enabled": config.docker.enabled,
            "default_image": config.docker.default_image,
            "memory_limit": config.docker.memory_limit,
            "cpu_limit": config.docker.cpu_limit,
            "cleanup_after": config.docker.cleanup_after,
        },
        "gui": {
            "enabled": config.gui.enabled,
            "host": config.gui.host,
            "port": config.gui.port,
        },
        "analysis": {
            "clarity_threshold": config.analysis.clarity_threshold,
            "require_agent_instructions": config.analysis.require_agent_instructions,
        },
        "notifications": {
            "webhook_url": config.notifications.webhook_url,
            "notify_on": config.notifications.notify_on,
        },
    }
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
