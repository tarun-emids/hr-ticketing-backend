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
    "'max': c.MAX_ATTACHMENT_BYTES, 'kb_bucket': c.KB_BUCKET, "
    "'supa_timeout': c.SUPABASE_TIMEOUT, 'connect_timeout': c.CONNECT_TIMEOUT, "
    "'retries': c.RETRY_MAX_ATTEMPTS, 'backoff': c.RETRY_BACKOFF_INITIAL_S, "
    "'backoff_cap': c.RETRY_BACKOFF_MAX_S}))"
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
    assert cfg["kb_bucket"] == "knowledge-base"  # schema.sql section 10
    assert cfg["max"] == 5 * 1024 * 1024
    assert isinstance(cfg["ttl"], int) and cfg["ttl"] > 0


def test_timeout_and_retry_env_overrides_and_defaults():
    defaults = run_config({})
    assert defaults["supa_timeout"] == 60.0
    assert defaults["connect_timeout"] == 10.0
    assert defaults["retries"] == 3
    assert defaults["backoff"] == 0.5
    assert defaults["backoff_cap"] == 2.0

    tuned = run_config({
        "SUPABASE_TIMEOUT": "30",
        "SUPABASE_CONNECT_TIMEOUT": "5",
        "RETRY_MAX_ATTEMPTS": "5",
        "RETRY_BACKOFF_INITIAL_S": "0.2",
        "RETRY_BACKOFF_MAX_S": "4",
    })
    assert tuned["supa_timeout"] == 30.0
    assert tuned["connect_timeout"] == 5.0
    assert tuned["retries"] == 5
    assert tuned["backoff"] == 0.2
    assert tuned["backoff_cap"] == 4.0


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


def test_build_options_resolves_canonical_sync_options(monkeypatch):
    """_build_options must hand create_client the SAME options class shape it
    uses internally. On supabase 2.x that is SyncClientOptions — the bare
    base ClientOptions (no .storage) crashes auth initialisation at boot
    with `AttributeError: 'ClientOptions' object has no attribute 'storage'`.
    These fakes mirror 2.32: _sync/client.py aliases the sync-era class as
    ClientOptions; lib.client_options exports both, base without .storage."""
    import sys
    import types

    from app import config as c

    class BaseOptions:  # what bit us: no .storage field at all
        postgrest_client_timeout = None

    class SyncOptions(BaseOptions):  # full 2.3x sync shape
        def __init__(self):
            self.storage = "sync-memory-storage"  # create_client reads this
            self.postgrest_client_timeout = 120
            self.storage_client_timeout = 20

    monkeypatch.setitem(
        sys.modules, "supabase._sync.client",
        types.SimpleNamespace(ClientOptions=SyncOptions))
    monkeypatch.setitem(
        sys.modules, "supabase.lib.client_options",
        types.SimpleNamespace(ClientOptions=BaseOptions, SyncClientOptions=SyncOptions))

    options = c._build_options()
    assert isinstance(options, SyncOptions)
    assert options.storage == "sync-memory-storage"   # the crash point, now safe
    assert options.postgrest_client_timeout is not None
    assert options.storage_client_timeout == max(int(c.SUPABASE_TIMEOUT), 40)


def test_build_options_degrades_when_no_candidate_matches(monkeypatch):
    """No matching class anywhere -> None -> plain client with library-default
    timeouts. Startup must never fail because of a supabase-py reshuffle."""
    import types

    from app import config as c

    # a module that exists but exposes nothing usable + one that cannot be imported
    monkeypatch.setitem(sys.modules, "supabase.hollow",
                        types.SimpleNamespace())
    candidates = (("supabase.nt_importable", "ClientOptions"),
                  ("supabase.hollow", "ClientOptions"))
    assert c._build_options(candidates=candidates) is None
