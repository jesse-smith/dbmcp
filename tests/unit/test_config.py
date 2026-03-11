"""Tests for TOML configuration loading, validation, and singleton pattern."""

import textwrap

import pytest

from src.config import (
    AppConfig,
    ConnectionConfig,
    DefaultsConfig,
    _parse_config,
    _validate_defaults,
    get_config,
    init_config,
    load_config,
    resolve_env_vars,
)

# =============================================================================
# DefaultsConfig validation
# =============================================================================


class TestDefaultsConfig:
    """Test DefaultsConfig frozen dataclass defaults and bounds."""

    def test_defaults(self):
        d = DefaultsConfig()
        assert d.query_timeout == 30
        assert d.text_truncation_limit == 1000
        assert d.sample_size == 5
        assert d.row_limit == 1000

    def test_frozen(self):
        d = DefaultsConfig()
        with pytest.raises(AttributeError):
            d.query_timeout = 99  # type: ignore[misc]


class TestValidateDefaults:
    """Test _validate_defaults bounds checking."""

    def test_valid_values(self):
        d = _validate_defaults({
            "query_timeout": 60,
            "text_truncation_limit": 2000,
            "sample_size": 50,
            "row_limit": 5000,
        })
        assert d.query_timeout == 60
        assert d.text_truncation_limit == 2000
        assert d.sample_size == 50
        assert d.row_limit == 5000

    def test_below_min_uses_default(self):
        d = _validate_defaults({"query_timeout": 1})
        assert d.query_timeout == 30  # default, since 1 < 5

    def test_above_max_uses_default(self):
        d = _validate_defaults({"query_timeout": 999})
        assert d.query_timeout == 30  # default, since 999 > 300

    def test_text_truncation_below_min(self):
        d = _validate_defaults({"text_truncation_limit": 10})
        assert d.text_truncation_limit == 1000

    def test_text_truncation_above_max(self):
        d = _validate_defaults({"text_truncation_limit": 99999})
        assert d.text_truncation_limit == 1000

    def test_sample_size_below_min(self):
        d = _validate_defaults({"sample_size": 0})
        assert d.sample_size == 5

    def test_sample_size_above_max(self):
        d = _validate_defaults({"sample_size": 9999})
        assert d.sample_size == 5

    def test_row_limit_below_min(self):
        d = _validate_defaults({"row_limit": 0})
        assert d.row_limit == 1000

    def test_row_limit_above_max(self):
        d = _validate_defaults({"row_limit": 99999})
        assert d.row_limit == 1000

    def test_boundary_min_accepted(self):
        d = _validate_defaults({
            "query_timeout": 5,
            "text_truncation_limit": 100,
            "sample_size": 1,
            "row_limit": 1,
        })
        assert d.query_timeout == 5
        assert d.text_truncation_limit == 100
        assert d.sample_size == 1
        assert d.row_limit == 1

    def test_boundary_max_accepted(self):
        d = _validate_defaults({
            "query_timeout": 300,
            "text_truncation_limit": 10000,
            "sample_size": 1000,
            "row_limit": 10000,
        })
        assert d.query_timeout == 300
        assert d.text_truncation_limit == 10000
        assert d.sample_size == 1000
        assert d.row_limit == 10000


# =============================================================================
# ConnectionConfig
# =============================================================================


class TestConnectionConfig:
    """Test ConnectionConfig frozen dataclass."""

    def test_defaults(self):
        c = ConnectionConfig(server="localhost", database="mydb")
        assert c.server == "localhost"
        assert c.database == "mydb"
        assert c.port == 1433
        assert c.authentication_method == "sql"
        assert c.username is None
        assert c.password is None
        assert c.trust_server_cert is False
        assert c.connection_timeout == 30
        assert c.tenant_id is None

    def test_frozen(self):
        c = ConnectionConfig(server="localhost", database="mydb")
        with pytest.raises(AttributeError):
            c.server = "other"  # type: ignore[misc]


# =============================================================================
# Environment variable resolution
# =============================================================================


class TestResolveEnvVars:
    """Test resolve_env_vars() with ${VAR} syntax."""

    def test_plain_string_unchanged(self):
        assert resolve_env_vars("hello world") == "hello world"

    def test_single_var_resolved(self, monkeypatch):
        monkeypatch.setenv("DB_PASSWORD", "s3cret")
        assert resolve_env_vars("${DB_PASSWORD}") == "s3cret"

    def test_multiple_vars_resolved(self, monkeypatch):
        monkeypatch.setenv("HOST", "server1")
        monkeypatch.setenv("PORT", "1434")
        assert resolve_env_vars("${HOST}:${PORT}") == "server1:1434"

    def test_missing_var_raises(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        with pytest.raises(ValueError, match="NONEXISTENT_VAR"):
            resolve_env_vars("${NONEXISTENT_VAR}")

    def test_partial_missing_raises(self, monkeypatch):
        monkeypatch.setenv("GOOD", "ok")
        monkeypatch.delenv("BAD_VAR", raising=False)
        with pytest.raises(ValueError, match="BAD_VAR"):
            resolve_env_vars("${GOOD}/${BAD_VAR}")


# =============================================================================
# SP allowlist name validation (via _parse_config)
# =============================================================================


class TestSPAllowlistValidation:
    """Test stored procedure name validation in config parsing."""

    def test_valid_sp_names(self):
        raw = {"allowed_stored_procedures": ["my_proc", "dbo.my_proc", "mySchema.sp_custom"]}
        config = _parse_config(raw)
        assert "my_proc" in config.allowed_stored_procedures
        assert "dbo.my_proc" in config.allowed_stored_procedures
        assert "mySchema.sp_custom" in config.allowed_stored_procedures

    def test_invalid_sp_names_rejected(self):
        raw = {"allowed_stored_procedures": ["valid_proc", "'; DROP TABLE--", "good_one"]}
        config = _parse_config(raw)
        assert "valid_proc" in config.allowed_stored_procedures
        assert "good_one" in config.allowed_stored_procedures
        assert "'; DROP TABLE--" not in config.allowed_stored_procedures

    def test_empty_allowlist(self):
        raw = {"allowed_stored_procedures": []}
        config = _parse_config(raw)
        assert config.allowed_stored_procedures == frozenset()


# =============================================================================
# TOML file discovery and loading
# =============================================================================


class TestLoadConfig:
    """Test load_config() with file discovery."""

    def test_no_config_file_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))
        config = load_config()
        assert config == AppConfig()

    def test_valid_toml_parsed(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        toml_content = textwrap.dedent("""\
            allowed_stored_procedures = ["sp_custom_report"]

            [defaults]
            query_timeout = 60
            sample_size = 10

            [connections.prod]
            server = "prod-server"
            database = "proddb"
            port = 1434
            authentication_method = "windows"
        """)
        (tmp_path / "dbmcp.toml").write_text(toml_content)
        config = load_config()
        assert config.defaults.query_timeout == 60
        assert config.defaults.sample_size == 10
        assert "prod" in config.connections
        assert config.connections["prod"].server == "prod-server"
        assert config.connections["prod"].port == 1434
        assert "sp_custom_report" in config.allowed_stored_procedures

    def test_malformed_toml_returns_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "dbmcp.toml").write_text("this is not valid TOML {{{{")
        config = load_config()
        assert config == AppConfig()

    def test_local_takes_precedence_over_home(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        home_dir = tmp_path / "fakehome" / ".dbmcp"
        home_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))

        (home_dir / "config.toml").write_text(textwrap.dedent("""\
            [defaults]
            query_timeout = 100
        """))
        (tmp_path / "dbmcp.toml").write_text(textwrap.dedent("""\
            [defaults]
            query_timeout = 200
        """))
        config = load_config()
        assert config.defaults.query_timeout == 200

    def test_home_config_used_when_no_local(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        home_dir = tmp_path / "fakehome" / ".dbmcp"
        home_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))

        (home_dir / "config.toml").write_text(textwrap.dedent("""\
            [defaults]
            query_timeout = 100
        """))
        config = load_config()
        assert config.defaults.query_timeout == 100

    def test_connection_with_env_var_password_not_resolved(self, tmp_path, monkeypatch):
        """Env vars stay as ${VAR} strings in ConnectionConfig; resolved at connection time."""
        monkeypatch.chdir(tmp_path)
        toml_content = textwrap.dedent("""\
            [connections.dev]
            server = "dev-server"
            database = "devdb"
            password = "${DB_PASSWORD}"
        """)
        (tmp_path / "dbmcp.toml").write_text(toml_content)
        config = load_config()
        assert config.connections["dev"].password == "${DB_PASSWORD}"


# =============================================================================
# Singleton pattern
# =============================================================================


class TestSingleton:
    """Test init_config() / get_config() singleton pattern."""

    def test_get_config_before_init_returns_defaults(self, monkeypatch):
        import src.config as config_mod
        monkeypatch.setattr(config_mod, "_config", None)
        result = get_config()
        assert result == AppConfig()

    def test_init_stores_and_get_retrieves(self, tmp_path, monkeypatch):
        import src.config as config_mod
        monkeypatch.setattr(config_mod, "_config", None)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))

        toml_content = textwrap.dedent("""\
            [defaults]
            row_limit = 500
        """)
        (tmp_path / "dbmcp.toml").write_text(toml_content)

        result = init_config()
        assert result.defaults.row_limit == 500
        assert get_config().defaults.row_limit == 500

    def test_init_config_idempotent(self, tmp_path, monkeypatch):
        """Second call to init_config reloads (not cached)."""
        import src.config as config_mod
        monkeypatch.setattr(config_mod, "_config", None)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path / "fakehome"))
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "fakehome"))

        first = init_config()
        second = init_config()
        assert first == second
