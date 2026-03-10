"""TOML configuration file support for dbmcp.

Loads optional configuration from dbmcp.toml (local) or ~/.dbmcp/config.toml (home).
Provides named connections, configurable defaults, and SP allowlist extensions.

Environment variable references (${VAR}) in credentials are NOT resolved at load time;
they stay as literal strings until resolve_env_vars() is called at connection time.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from src.logging_config import get_logger

logger = get_logger(__name__)

# Pattern for ${VAR_NAME} environment variable references
_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# SP name validation: identifier chars and dots for schema-qualified names
_SP_NAME_PATTERN = re.compile(r"^[a-zA-Z_][\w.]*$")

# Bounds for configurable defaults: (min, max, hardcoded_default)
_DEFAULTS_BOUNDS: dict[str, tuple[int, int, int]] = {
    "query_timeout": (5, 300, 30),
    "text_truncation_limit": (100, 10000, 1000),
    "sample_size": (1, 1000, 5),
    "row_limit": (1, 10000, 1000),
}


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(frozen=True)
class DefaultsConfig:
    """Configurable default parameter values."""

    query_timeout: int = 30
    text_truncation_limit: int = 1000
    sample_size: int = 5
    row_limit: int = 1000


@dataclass(frozen=True)
class ConnectionConfig:
    """A named database connection configuration."""

    server: str = ""
    database: str = ""
    port: int = 1433
    authentication_method: str = "sql"
    username: str | None = None
    password: str | None = None
    trust_server_cert: bool = False
    connection_timeout: int = 30
    tenant_id: str | None = None


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    connections: dict[str, ConnectionConfig] = field(default_factory=dict)
    allowed_stored_procedures: frozenset[str] = field(default_factory=frozenset)


# =============================================================================
# Environment variable resolution
# =============================================================================


def resolve_env_vars(value: str) -> str:
    """Replace all ${VAR_NAME} occurrences with environment variable values.

    Args:
        value: String potentially containing ${VAR} references.

    Returns:
        String with all variables resolved.

    Raises:
        ValueError: If any referenced variable is not set.
    """
    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            raise ValueError(
                f"Environment variable '{var_name}' is not set "
                f"(referenced as '${{{var_name}}}' in config)"
            )
        return env_val

    return _ENV_VAR_PATTERN.sub(_replace, value)


# =============================================================================
# File discovery
# =============================================================================


def _find_config_file() -> Path | None:
    """Find the config file, preferring local over home directory.

    Search order:
        1. ./dbmcp.toml (current working directory)
        2. ~/.dbmcp/config.toml (home directory)

    Returns:
        Path to config file, or None if not found.
    """
    local_path = Path("dbmcp.toml")
    if local_path.is_file():
        return local_path

    home_path = Path.home() / ".dbmcp" / "config.toml"
    if home_path.is_file():
        return home_path

    return None


# =============================================================================
# Parsing and validation
# =============================================================================


def _validate_defaults(raw_defaults: dict) -> DefaultsConfig:
    """Validate default values against bounds, using hardcoded defaults on violation.

    Args:
        raw_defaults: Dict of default parameter overrides from TOML.

    Returns:
        Validated DefaultsConfig.
    """
    validated: dict[str, int] = {}
    for field_name, (min_val, max_val, default_val) in _DEFAULTS_BOUNDS.items():
        if field_name in raw_defaults:
            val = raw_defaults[field_name]
            if not isinstance(val, int) or val < min_val or val > max_val:
                logger.warning(
                    "Config: %s=%r out of range [%d, %d]; using default %d",
                    field_name, val, min_val, max_val, default_val,
                )
                validated[field_name] = default_val
            else:
                validated[field_name] = val
    return DefaultsConfig(**validated)


def _parse_connections(raw_connections: dict) -> dict[str, ConnectionConfig]:
    """Parse connection definitions from TOML config.

    Args:
        raw_connections: Dict of connection name -> connection params.

    Returns:
        Dict of connection name -> ConnectionConfig.
    """
    connections: dict[str, ConnectionConfig] = {}
    for name, params in raw_connections.items():
        if not isinstance(params, dict):
            logger.warning("Config: connection '%s' is not a table, skipping", name)
            continue
        connections[name] = ConnectionConfig(
            server=params.get("server", ""),
            database=params.get("database", ""),
            port=params.get("port", 1433),
            authentication_method=params.get("authentication_method", "sql"),
            username=params.get("username"),
            password=params.get("password"),
            trust_server_cert=params.get("trust_server_cert", False),
            connection_timeout=params.get("connection_timeout", 30),
            tenant_id=params.get("tenant_id"),
        )
    return connections


def _validate_sp_names(names: list) -> frozenset[str]:
    """Validate stored procedure names, rejecting invalid identifiers.

    Args:
        names: List of SP name strings from config.

    Returns:
        Frozenset of validated SP names.
    """
    valid: set[str] = set()
    for name in names:
        if not isinstance(name, str):
            logger.warning("Config: SP allowlist entry %r is not a string, skipping", name)
            continue
        if _SP_NAME_PATTERN.match(name):
            valid.add(name)
        else:
            logger.warning("Config: SP name '%s' contains invalid characters, skipping", name)
    return frozenset(valid)


def _parse_config(raw: dict) -> AppConfig:
    """Parse a raw TOML dict into an AppConfig.

    Args:
        raw: Parsed TOML dictionary.

    Returns:
        Validated AppConfig.
    """
    defaults = _validate_defaults(raw.get("defaults", {}))
    connections = _parse_connections(raw.get("connections", {}))
    sp_names = raw.get("allowed_stored_procedures", [])
    allowed_sps = _validate_sp_names(sp_names)

    return AppConfig(
        defaults=defaults,
        connections=connections,
        allowed_stored_procedures=allowed_sps,
    )


# =============================================================================
# Loading
# =============================================================================


def load_config() -> AppConfig:
    """Load configuration from TOML file, returning defaults if none found.

    Searches for config files in order: ./dbmcp.toml, ~/.dbmcp/config.toml.
    On parse errors, logs a warning and returns default config.

    Returns:
        AppConfig with loaded or default values.
    """
    config_path = _find_config_file()
    if config_path is None:
        return AppConfig()

    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
        logger.info("Config loaded from %s", config_path)
        return _parse_config(raw)
    except tomllib.TOMLDecodeError as e:
        logger.warning("Config: malformed TOML in %s: %s; using defaults", config_path, e)
        return AppConfig()
    except Exception as e:
        logger.warning("Config: error reading %s: %s; using defaults", config_path, e)
        return AppConfig()


# =============================================================================
# Singleton
# =============================================================================

_config: AppConfig | None = None


def init_config() -> AppConfig:
    """Load config from disk and store as module singleton.

    Returns:
        The loaded AppConfig.
    """
    global _config  # noqa: PLW0603
    _config = load_config()
    return _config


def get_config() -> AppConfig:
    """Get the current config singleton, returning defaults if not initialized.

    Returns:
        The current AppConfig (or defaults if init_config() not yet called).
    """
    if _config is None:
        return AppConfig()
    return _config
