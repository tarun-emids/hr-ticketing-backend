"""Live integration harness — runs the real backend against the real
Supabase project configured in backend/.env.

These tests create real tickets/replies/attachments, so every test declares
what it created (refs + storage paths) and the fixture deletes them again in
teardown. Runs only when opted in: pytest -m integration
"""
from types import SimpleNamespace
import uuid as uuidlib

import pytest
from fastapi.testclient import TestClient

from app import config as cfg
from app.main import app as real_app

BUCKET = cfg.ATTACHMENT_BUCKET


@pytest.fixture()
def live():
    """Real TestClient + Supabase handle with automatic cleanup."""
    client = TestClient(real_app)

    health = client.get("/health")
    assert health.status_code == 200

    users = client.get("/api/users").json()
    if len(users) < 7:
        pytest.skip("Supabase users not seeded — run backend/schema.sql first")

    employees = [u for u in users if u["role"] == "employee"]
    agents = [u for u in users if u["role"] == "agent"]
    if not employees or not agents:
        pytest.skip("Supabase seed lacks employee/agent users")

    return {
        "client": client,
        "employees": employees,
        "agents": agents,
        "refs": [],       # ticket refs to delete in teardown
        "paths": [],      # storage paths to delete in teardown
    }


@pytest.fixture()
def cleanup(live):
    yield live
    sb = cfg.get_client()
    for path in live["paths"]:
        try:
            sb.storage.from_(BUCKET).remove([path])
        except Exception:
            pass
    for ref in live["refs"]:
        try:
            sb.table("tickets").delete().eq("ref", ref).execute()
        except Exception:
            pass


def create_ticket(live, employee=None, category="Payroll", priority="High",
                  subject="Automated integration test ticket",
                  description="Created by the automated integration suite and deleted again in teardown."):
    employee = employee or live["employees"][0]["id"]
    r = live["client"].post("/api/tickets", json={
        "employeeId": employee,
        "category": category,
        "subject": subject,
        "description": description,
        "priority": priority,
    })
    assert r.status_code == 201, r.text
    ref = r.json()["id"]
    live["refs"].append(ref)
    return ref
