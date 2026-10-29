"""Admin console — accounts, KB document admin, analytics, guards.

Runs on the offline SQLite double (conftest). Insert helpers create the
admin/supervisor mix the guards distinguish; provider touchpoints (Gemini
embeddings, pypdf paragraphs) are faked at their seams so the tests pin the
SERVICE contract, not the network.
"""

import json
import uuid as uuidlib

import pytest

from tests.conftest import U


def _actor(fake, name, email, role):
    actor_id = str(uuidlib.uuid4())
    fake.execute(
        "INSERT INTO users (id, name, email, role) VALUES (%s, %s, %s, %s)",
        (actor_id, name, email, role),
    )
    return actor_id


@pytest.fixture()
def admin_id(api):
    """One admin account per test, straight into the fake."""
    admin = U.get("admin") or str(uuidlib.uuid4())
    api.fake.execute(
        "INSERT INTO users (id, name, email, role) VALUES (%s, %s, %s, %s)",
        (admin, "Ada Admin", "ada@acme.com", "admin"),
    )
    return admin


@pytest.fixture()
def agent_id(api):
    return U["alicia"]  # harness-seeded agent


# -- guards -------------------------------------------------------------------


def test_admin_endpoints_reject_unknown_and_non_admin_actors(api, admin_id):
    # unknown actor (nonexistent uuid)
    r = api.client.get("/api/admin/accounts", params={"actorId": str(uuidlib.uuid4())})
    assert r.status_code == 404
    # valid account, wrong role (the harness employee)
    r = api.client.get("/api/admin/accounts", params={"actorId": U["priya"]})
    assert r.status_code == 403
    r = api.client.post(
        "/api/admin/accounts",
        params={"actorId": U["priya"]},
        json={"name": "X", "email": "x@y.com", "role": "agent", "password": "12345678"},
    )
    assert r.status_code == 403


# -- accounts -------------------------------------------------------------------


def test_create_account_promote_delete_lifecycle(api, admin_id):
    r = api.client.post(
        "/api/admin/accounts",
        params={"actorId": admin_id},
        json={
            "name": "Nina Nunes",
            "email": "nina@acme.com",
            "role": "agent",
            "password": "Password!2026",
        },
    )
    assert r.status_code == 201
    created = r.json()
    assert created["role"] == "agent"

    # duplicate (case-insensitive) creation is refused
    r = api.client.post(
        "/api/admin/accounts",
        params={"actorId": admin_id},
        json={
            "name": "Nina Again",
            "email": "NINA@ACME.com",
            "role": "employee",
            "password": "Password!2026",
        },
    )
    assert r.status_code == 409

    # role change employee <-> agent <-> admin
    r = api.client.patch(
        f"/api/admin/accounts/{created['id']}/role",
        params={"actorId": admin_id},
        json={"role": "admin"},
    )
    assert r.status_code == 200 and r.json()["role"] == "admin"

    # deletion of a clean account works
    r = api.client.delete(f"/api/admin/accounts/{created['id']}", params={"actorId": admin_id})
    assert r.status_code == 200


def test_delete_never_destroys_history(api, admin_id):
    # the harness employee Marcus owns a ticket — deleting him is refused
    r = api.client.delete(f"/api/admin/accounts/{U['marcus']}", params={"actorId": admin_id})
    assert r.status_code == 409
    assert "ticket" in r.json()["detail"].lower()


def test_demoting_an_agent_with_open_tickets_is_refused(api, admin_id):
    # TKT-102 belongs to Alicia and is open ("In Progress") in the harness
    r = api.client.patch(
        f"/api/admin/accounts/{U['alicia']}/role",
        params={"actorId": admin_id},
        json={"role": "employee"},
    )
    assert r.status_code == 409
    assert "open ticket" in r.json()["detail"].lower()


def test_last_admin_is_protected(api, admin_id):
    r = api.client.delete(f"/api/admin/accounts/{admin_id}", params={"actorId": admin_id})
    assert r.status_code == 409
    assert "only admin" in r.json()["detail"].lower()
    r = api.client.patch(
        f"/api/admin/accounts/{admin_id}/role",
        params={"actorId": admin_id},
        json={"role": "agent"},
    )
    assert r.status_code == 409


# -- KB document administration ---------------------------------------------------


def _upload(api, admin_id, filename="new-leave-policy.pdf", **over):
    form = {
        "title": "New Leave Policy",
        "category": "Leave",
        "audience": "employee",
        "summary": "Freshly uploaded",
        "keywords": "leave, upload",
        "version": "v1.2",
        "effectiveDate": "2026-11-01",
    }
    form.update(over)
    return api.client.post(
        "/api/admin/kb/documents",
        params={"actorId": admin_id},
        files={"file": (filename, b"%PDF-1.4 uploaded-bytes", "application/pdf")},
        data=form,
    )


def test_kb_document_upload_lists_edits_and_deletes(api, admin_id):
    r = _upload(api, admin_id)
    assert r.status_code == 201
    doc = r.json()
    assert doc["slug"] == "new-leave-policy"
    assert doc["ref"].startswith("KB-E-")  # employee audience pool
    assert doc["fileSize"] == len(b"%PDF-1.4 uploaded-bytes")

    r = api.client.get("/api/admin/kb/documents", params={"actorId": admin_id})
    assert r.status_code == 200
    titles = [d["title"] for d in r.json()]
    assert "New Leave Policy" in titles

    # metadata edit without touching the PDF
    r = api.client.patch(
        f"/api/admin/kb/documents/{doc['slug']}",
        params={"actorId": admin_id},
        data={"title": "New Leave Policy (2026 update)"},
    )
    assert r.status_code == 200
    assert r.json()["title"].endswith("(2026 update)")

    # delete removes both the document (chunks cascade)
    r = api.client.delete(f"/api/admin/kb/documents/{doc['slug']}", params={"actorId": admin_id})
    assert r.status_code == 200
    rows = api.fake.execute("SELECT count(*) AS n FROM kb_documents", ())
    assert rows[0]["n"] == 5  # back to the 5 harness documents

    # duplicate upload is refused
    assert _upload(api, admin_id).status_code == 201  # the first one is gone
    assert _upload(api, admin_id).status_code == 409


def test_kb_upload_without_pdf_bytes_is_422(api, admin_id):
    r = api.client.post(
        "/api/admin/kb/documents",
        params={"actorId": admin_id},
        files={"file": ("notes.txt", b"plain text", "text/plain")},
        data={"title": "Not a PDF", "audience": "employee"},
    )
    assert r.status_code == 422


# -- analytics ------------------------------------------------------------------


def test_overview_counts_categories_and_repetition(api, admin_id):
    r = api.client.get(
        "/api/admin/analytics/overview",
        params={"actorId": admin_id, "window": "all"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3  # the harness seeds three tickets
    assert body["open"] == 1 and body["closed"] == 0 and body["resolved"] == 1
    assert body["categories"] and body["categories"][0]["total"] >= 1
    assert isinstance(body["responseDistribution"], list)


def test_bad_window_and_period_answer_422(api, admin_id):
    r = api.client.get(
        "/api/admin/analytics/overview", params={"actorId": admin_id, "window": "fortnight"}
    )
    assert r.status_code == 422
    r = api.client.get("/api/admin/analytics/agents", params={"actorId": admin_id, "period": "8d"})
    assert r.status_code == 422


def test_leaderboard_ranks_by_resolved(api, admin_id):
    r = api.client.get("/api/admin/analytics/agents", params={"actorId": admin_id, "period": "30d"})
    assert r.status_code == 200
    table = r.json()
    by_id = {m["agentId"]: m for m in table}
    # Ben closed TKT-103 in the harness; Alicia only picked TKT-102 up
    assert by_id[U["ben"]]["completed"] >= 1
    assert by_id[U["alicia"]]["pending"] >= 1
    # ranked by the composite score (0-100); completed count as tie-break
    if len(table) > 1:
        assert (table[0]["score"] or 0) >= (table[-1]["score"] or 0)
        assert all(0 <= m["score"] <= 100 for m in table if m["score"] is not None)


def test_agent_drilldown_self_ok_other_forbidden(api, agent_id, admin_id):
    # the agent may read their own numbers (powering the HR personal view)
    r = api.client.get(
        f"/api/admin/metrics/agents/{agent_id}",
        params={"actorId": agent_id, "period": "30d"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] >= 1  # TKT-102 in the harness
    assert "series" in body and len(body["series"]) == 30

    # ...but may NOT read anyone else's
    r = api.client.get(
        f"/api/admin/metrics/agents/{agent_id}",
        params={"actorId": U["ben"], "period": "30d"},
    )
    assert r.status_code == 403

    # metrics apply to agents only
    r = api.client.get(
        f"/api/admin/metrics/agents/{U['priya']}",
        params={"actorId": admin_id, "period": "30d"},
    )
    assert r.status_code == 422


def test_agent_chunk_rows_feed_the_assistant_gate(api, admin_id):
    """KB admin + RAG stay in one ledger: deleting a document deletes its
    citation paragraphs (FK cascade); the assistant cannot cite a ghost."""
    doc_id = api.fake.execute("SELECT id FROM kb_documents WHERE slug = %s", ("leave-policy",))[0][
        "id"
    ]
    api.fake.execute(
        "INSERT INTO kb_document_chunks (id, document_id, document_slug, ref, title,"
        " audience, section, block_no, body, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            str(uuidlib.uuid4()),
            doc_id,
            "leave-policy",
            "KB-E-01",
            "Leave Policy",
            "employee",
            "1. Scope",
            1,
            "text",
            json.dumps([0.1, 0.2]),
        ),
    )
    r = api.client.delete("/api/admin/kb/documents/leave-policy", params={"actorId": admin_id})
    assert r.status_code == 200
    rows = api.fake.execute(
        "SELECT count(*) AS n FROM kb_document_chunks WHERE document_slug=%s", ("leave-policy",)
    )
    assert rows[0]["n"] == 0
