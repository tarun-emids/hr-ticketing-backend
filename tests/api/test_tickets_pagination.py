"""Phase 2 pagination tests: deterministic ordering, shared filter builder,
exact counts, and the single envelope contract (page/pageSize/total/hasNext).
Repository-level tests use the same offline fake the api fixtures use;
ordering fixtures insert rows with IDENTICAL stamps."""

import uuid as uuidlib
from datetime import timedelta

import pytest

from app.repositories.ticket_repository import TicketRepository
from tests.conftest import _ORIGIN, U, auth_headers

ALICIA = auth_headers("alicia")


def items(r):
    """The only legal reading of GET /tickets after legacy removal:
    paginated envelope -> its items list."""
    return r.json()["items"]


@pytest.fixture()
def repo(api):
    return TicketRepository(api.fake)


def test_count_matches_list_and_scope(api, repo):
    repo_count = repo.count_filtered()
    listed = api.client.get("/api/tickets", params={"viewerId": U["alicia"]}, headers=ALICIA)
    assert repo_count == len(items(listed))

    priya = repo.count_filtered(employee_scope_id=uuidlib.UUID(U["priya"]))
    priya_list = api.client.get("/api/tickets", params={"viewerId": U["priya"]})
    assert priya == len(items(priya_list))

    assert repo.count_filtered(status="Resolved") == 1


def test_count_includes_scope_not_filters_when_none(api, repo):
    # zero filters -> the count and the agent's page are the same shape
    assert repo.count_filtered() == repo.count_filtered(unassigned=False)


def test_list_is_deterministic_on_updated_at_ties(api):
    a_id, b_id = str(uuidlib.uuid4()), str(uuidlib.uuid4())
    stamp = (_ORIGIN + timedelta(hours=1)).isoformat()
    for tid in (a_id, b_id):  # b inserted last -> HIGHER number, same stamp
        api.fake._connection.execute(
            "INSERT INTO tickets (id, employee_id, category, subject, description,"
            " priority, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tid,
                U["priya"],
                "Payroll",
                f"Tiebreak ticket {tid[-4:]}",
                "Tiebreak placeholder long description here.",
                "Medium",
                "Open",
                stamp,
                stamp,
            ),
        )
    api.fake._connection.commit()
    listed = api.client.get("/api/tickets", params={"viewerId": U["alicia"]}, headers=ALICIA)
    top_two = [t["uuid"] for t in items(listed)[:2]]
    assert top_two == [b_id, a_id]  # identical stamps -> number decides, newest first


def test_default_request_is_an_envelope(api):
    """The legacy bare array is gone: a BARE request already pages. The
    defaults are the documented contract itself (page 1, 25 per page)."""
    body = api.client.get("/api/tickets", params={"viewerId": U["alicia"]}, headers=ALICIA).json()
    assert set(body.keys()) == {"items", "page", "pageSize", "total", "hasNext"}
    assert body["page"] == 1
    assert body["pageSize"] == 25
    assert body["total"] == 3
    assert body["hasNext"] is False


def test_envelope_shape_and_totals(api):
    body = api.client.get("/api/tickets", params={"viewerId": U["alicia"]}, headers=ALICIA).json()
    assert set(body.keys()) == {"items", "page", "pageSize", "total", "hasNext"}
    assert body["page"] == 1 and body["pageSize"] == 25 and body["total"] == 3
    assert body["hasNext"] is False
    assert [t["id"] for t in body["items"]] == ["TKT-103", "TKT-102", "TKT-101"]


def test_page_windows_and_has_next(api):
    r = api.client.get(
        "/api/tickets",
        params={"viewerId": U["alicia"], "page": 1, "pageSize": 2}, headers=ALICIA,
    )
    body = r.json()
    assert [t["id"] for t in body["items"]] == ["TKT-103", "TKT-102"]
    assert body["hasNext"] is True

    r = api.client.get(
        "/api/tickets",
        params={"viewerId": U["alicia"], "page": 2, "pageSize": 2}, headers=ALICIA,
    )
    body = r.json()
    assert [t["id"] for t in body["items"]] == ["TKT-101"]
    assert body["hasNext"] is False


def test_beyond_last_page_is_empty_not_error(api):
    r = api.client.get("/api/tickets", params={"viewerId": U["alicia"], "page": 9, "pageSize": 25}, headers=ALICIA)
    body = r.json()
    assert body["items"] == [] and body["total"] == 3 and body["hasNext"] is False


def test_validation_rejects_bad_pages_and_sizes(api):
    for params, field in (
        ({"page": 0}, "page"),
        ({"pageSize": 0}, "pageSize"),
        ({"pageSize": 101}, "pageSize"),
    ):
        r = api.client.get("/api/tickets", params={"viewerId": U["alicia"], **params}, headers=ALICIA)
        assert r.status_code == 422, params
        assert field in r.json()["detail"]


def test_envelope_respects_scope(api):
    body = api.client.get("/api/tickets", params={"viewerId": U["priya"]}).json()
    assert body["total"] == 1
    assert body["items"][0]["employeeId"] == U["priya"]


def test_sort_by_priority_matches_frontend_prio_order(api):
    # a fresh, newest-updated Medium ticket must NOT outrank the seeded
    # Urgent/High — recency must not leak into whitelisted sorts.
    api.client.post(
        "/api/tickets",
        json={
            "employeeId": U["dana"],
            "category": "Payroll",
            "subject": "Zebra payslip check for sorting",
            "description": "Sort-check ticket that is the newest row in the table.",
        },
        headers=auth_headers("dana"),
    ).json()
    body = api.client.get(
        "/api/tickets",
        params={"viewerId": U["alicia"], "sort": "priority", "order": "desc"}, headers=ALICIA,
    ).json()
    priorities = [t["priority"] for t in body["items"]]
    assert priorities[0] == "Urgent"  # TKT-103, not the newest Medium
    assert priorities[-2:].count("Medium") == 2  # both Mediums below High


def test_sort_by_subject_lowercase(api):
    body = api.client.get(
        "/api/tickets",
        params={"viewerId": U["alicia"], "sort": "subject", "order": "asc"}, headers=ALICIA,
    ).json()
    subjects = [t["subject"].lower() for t in body["items"]]
    assert subjects == sorted(subjects)


def test_sort_whitelist_rejects_unknown(api):
    for params in ({"sort": "assigneee"}, {"order": "sideways"}):
        r = api.client.get("/api/tickets", params={"viewerId": U["alicia"], **params}, headers=ALICIA)
        assert r.status_code == 422, params


def test_default_sort_preserves_legacy_order(api):
    body = api.client.get("/api/tickets", params={"viewerId": U["alicia"]}, headers=ALICIA).json()
    assert [t["id"] for t in body["items"]] == ["TKT-103", "TKT-102", "TKT-101"]


def test_sort_by_status_matches_lifecycle_not_alphabetical(api):
    # Seeded: TKT-101 Open, TKT-102 In Progress, TKT-103 Resolved.
    # Alphabetical would order: 'Closed' < 'In Progress' < 'Open' < 'Resolved'.
    # Lifecycle order (the frontend's STATUS_OPTIONS) is what must win.
    body = api.client.get(
        "/api/tickets", params={"viewerId": U["alicia"], "sort": "status", "order": "asc"}, headers=ALICIA
    ).json()
    assert [t["id"] for t in body["items"]] == ["TKT-101", "TKT-102", "TKT-103"]


def test_sort_by_employee_uses_owner_display_names(api):
    # Dana Cole < Marcus Webb < Priya Sharma — and the join must NOT leak
    # user columns into ticket rows (TKT-101 still identifies as TKT-101).
    body = api.client.get(
        "/api/tickets", params={"viewerId": U["alicia"], "sort": "employee", "order": "asc"}, headers=ALICIA
    ).json()
    assert [t["employeeId"] for t in body["items"]] == [U["dana"], U["marcus"], U["priya"]]
    assert body["items"][0]["id"] == "TKT-103"  # dana's ticket, correct shape
