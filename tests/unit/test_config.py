"""Config-level unit tests defined in-process plus subprocess tests so that
module import-time env parsing can be exercised with controlled env vars
without disturbing the running test process."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

CODE = (
    "import json, app.config as c; "
    "print(json.dumps({'url': c.SUPABASE_URL, 'ttl': c.SIGNED_URL_TTL, "
    "'cors': c.CORS_ORIGINS, 'bucket': c.ATTACHMENT_BUCKET, "
    "'max': c.MAX_ATTACHMENT_BYTES}))"
)


def run_config(extra_env):
    env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR), **extra_env}
    proc = subprocess.run(
        [sys.executable, "-c", CODE],
        cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def test_env_overrides_are_honored():
    cfg = run_config({
        "SUPABASE_URL": "https://unit.example.com/",
        "SUPABASE_SERVICE_ROLE_KEY": "k",
        "ATTACHMENT_SIGNED_URL_TTL": "120",
        "CORS_ORIGINS": "http://a.test,http://b.test",
    })
    assert cfg["url"] == "https://unit.example.com"  # trailing slash stripped
    assert cfg["ttl"] == 120
    assert cfg["cors"] == ["http://a.test", "http://b.test"]


def test_constants_match_schema_contract():
    cfg = run_config({})
    assert cfg["bucket"] == "ticket-attachments"
    assert cfg["max"] == 5 * 1024 * 1024
    assert isinstance(cfg["ttl"], int) and cfg["ttl"] > 0


def test_empty_env_gives_safe_fallbacks():
    cfg = run_config({"CORS_ORIGINS": ""})
    # blank string means env-var-set-to-empty: os.getenv default does NOT apply,
    # config yields [] and main.py's `CORS_ORIGINS or [...]` substitutes localhost.
    assert cfg["cors"] == []


def test_missing_client_raises_runtime_error(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    import importlib
    import app.config as cfg

    m = importlib.reload(cfg)
    m._client = None
    with pytest.raises(RuntimeError, match="Missing SUPABASE_URL"):
        m.get_client()
    importlib.reload(cfg)  # restore real config state for other tests
