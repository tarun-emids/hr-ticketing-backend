"""Live integration harness — runs against DATABASE_URL from .env.

These tests create real tickets/replies/attachments, so every test declares
what it created (refs + attachment paths) and the fixture deletes them again in
teardown. Runs only when opted in: pytest -m integration
"""

import pytest
from fastapi.testclient import TestClient

from app import config as cfg
from app.main import app as real_app


@pytest.fixture()
def live():
    """Real TestClient with automatic database cleanup."""
    client = TestClient(real_app)

    health = client.get("/health")
    assert health.status_code == 200

    users = client.get("/api/users").json()
    if len(users) < 7:
        pytest.skip("PostgreSQL users not seeded — run schema.sql first")

    employees = [u for u in users if u["role"] == "employee"]
    agents = [u for u in users if u["role"] == "agent"]
    if not employees or not agents:
        pytest.skip("PostgreSQL seed lacks employee/agent users")

    return {
        "client": client,
        "employees": employees,
        "agents": agents,
        "refs": [],  # ticket refs to delete in teardown
        "paths": [],  # attachment paths to delete in teardown
    }


@pytest.fixture()
def cleanup(live):
    yield live
    database = cfg.get_database()
    with database.connection() as connection:
        for path in live["paths"]:
            connection.execute("DELETE FROM attachments WHERE path = %s", (path,))
        for ref in live["refs"]:
            connection.execute("DELETE FROM tickets WHERE ref = %s", (ref,))


def create_ticket(
    live,
    employee=None,
    category="Payroll",
    priority="High",
    subject="Automated integration test ticket",
    description="Created by the automated integration suite and deleted again in teardown.",
):
    employee = employee or live["employees"][0]["id"]
    r = live["client"].post(
        "/api/tickets",
        json={
            "employeeId": employee,
            "category": category,
            "subject": subject,
            "description": description,
            "priority": priority,
        },
    )
    assert r.status_code == 201, r.text
    ref = r.json()["id"]
    live["refs"].append(ref)
    return ref
