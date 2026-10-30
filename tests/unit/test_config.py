"""Configuration tests use subprocesses to isolate import-time environment parsing."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_ENV = (
    "DATABASE_URL",
    "ATTACHMENT_SIGNED_URL_TTL",
    "CORS_ORIGINS",
    "RETRY_MAX_ATTEMPTS",
    "RETRY_BACKOFF_INITIAL_S",
    "RETRY_BACKOFF_MAX_S",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_RECOVERY_SECONDS",
    "OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS",
)
CODE = (
    "import json, app.config as c; "
    "print(json.dumps({'url': c.DATABASE_URL, 'ttl': c.SIGNED_URL_TTL, "
    "'cors': c.CORS_ORIGINS, 'retries': c.RETRY_MAX_ATTEMPTS, "
    "'backoff': c.RETRY_BACKOFF_INITIAL_S, 'backoff_cap': c.RETRY_BACKOFF_MAX_S, "
    "'breaker_threshold': c.BREAKER_FAILURE_THRESHOLD, "
    "'breaker_recovery': c.BREAKER_RECOVERY_SECONDS, "
    "'export_log_window': c.OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS, "
    "'max': c.MAX_ATTACHMENT_BYTES}))"
)


def run_config(extra_env):
    env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}
    env["PYTHON_DOTENV_DISABLED"] = "true"
    for key in CONFIG_ENV:
        env.pop(key, None)
    env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, "-c", CODE],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def test_env_overrides_are_honored():
    cfg = run_config(
        {
            "DATABASE_URL": "******localhost:5432/unit",
            "ATTACHMENT_SIGNED_URL_TTL": "120",
            "CORS_ORIGINS": "http://a.test,http://b.test",
        }
    )
    assert cfg["url"] == "******localhost:5432/unit"
    assert cfg["ttl"] == 120
    assert cfg["cors"] == ["http://a.test", "http://b.test"]


def test_constants_match_schema_contract():
    cfg = run_config({})
    assert cfg["max"] == 5 * 1024 * 1024
    assert isinstance(cfg["ttl"], int) and cfg["ttl"] > 0


def test_postgresql_retry_and_breaker_settings_have_defaults_and_overrides():
    defaults = run_config({})
    assert defaults["retries"] == 3
    assert defaults["backoff"] == 0.5
    assert defaults["backoff_cap"] == 2.0
    assert defaults["breaker_threshold"] == 5
    assert defaults["breaker_recovery"] == 30.0

    tuned = run_config(
        {
            "RETRY_MAX_ATTEMPTS": "5",
            "RETRY_BACKOFF_INITIAL_S": "0.2",
            "RETRY_BACKOFF_MAX_S": "4",
            "CIRCUIT_BREAKER_FAILURE_THRESHOLD": "7",
            "CIRCUIT_BREAKER_RECOVERY_SECONDS": "45",
        }
    )
    assert tuned["retries"] == 5
    assert tuned["backoff"] == 0.2
    assert tuned["backoff_cap"] == 4.0
    assert tuned["breaker_threshold"] == 7
    assert tuned["breaker_recovery"] == 45.0


def test_exporter_error_log_window_has_default_and_override():
    assert run_config({})["export_log_window"] == 300
    assert run_config({"OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS": "0"})["export_log_window"] == 0


def test_empty_cors_env_gives_safe_fallback_input():
    cfg = run_config({"CORS_ORIGINS": ""})
    assert cfg["cors"] == []


def test_missing_database_url_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    import importlib

    import app.config as cfg

    module = importlib.reload(cfg)
    module._database = None
    with pytest.raises(RuntimeError, match="Missing DATABASE_URL"):
        module.get_database()
    importlib.reload(cfg)  # restore real config state for other tests
