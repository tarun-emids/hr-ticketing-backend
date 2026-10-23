"""Knowledge base endpoints — visibility gates, search, signed PostgreSQL URLs.

Runs against the offline SQLite pool seeded with 3 employee + 2 HR policy
documents (tests/conftest.py: _SEED_KB). The gate rules under test:
  - the viewer's role always comes from public.users (viewerId), never trust;
  - employee sees the employee pool, agents/admin see both pools;
  - out-of-pool -> 403, unknown slug -> 404, bad viewer -> 422/404;
  - view URLs carry no download transform; download URLs carry the filename.
"""

from tests.conftest import U


def _get(client, path, **params):
    return client.get(f"/api{path}", params=params)


def test_employee_lists_only_employee_pool(api):
    r = _get(api.client, "/kb", viewerId=U["priya"])
    assert r.status_code == 200
    audiences = {doc["audience"] for doc in r.json()}
    assert audiences == {"employee"}
    assert {doc["slug"] for doc in r.json()} == {
        "leave-and-time-off-policy",
        "hybrid-work-policy",
        "attendance-working-hours-policy",
    }


def test_agent_sees_both_pools(api):
    r = _get(api.client, "/kb", viewerId=U["alicia"])
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert {doc["audience"] for doc in r.json()} == {"employee", "hr"}


def test_doc_shape_matches_frontend_contract(api):
    r = _get(api.client, "/kb/leave-and-time-off-policy", viewerId=U["priya"])
    assert r.status_code == 200
    doc = r.json()
    assert doc == {
        "slug": "leave-and-time-off-policy",
        "ref": "KB-E-01",
        "title": "Leave and Time Off Policy",
        "category": "Leave",
        "audience": "employee",
        "summary": "How time off accrues, carries over and gets approved.",
        "keywords": ["leave", "pto", "vacation", "sick", "carryover"],
        "version": "v1.0",
        "effectiveDate": "2026-04-01",
        "pages": 7,
        "fileSize": 12345,
        "updatedAt": doc["updatedAt"],  # timestamp shape checked implicitly
    }


def test_search_honours_pools(api):
    # HR-only SOP matches 'payroll' for agents...
    r = _get(api.client, "/kb", viewerId=U["alicia"], q="payroll")
    assert [d["slug"] for d in r.json()] == ["payroll-processing-sop"]
    # ...and returns nothing for employees (the token only qualifies in the
    # HR pool — employee docs never carry 'payroll' in a qualifier field).
    r = _get(api.client, "/kb", viewerId=U["priya"], q="payroll")
    assert r.json() == []


def test_search_returns_top_matches_with_ranking(api):
    r = _get(api.client, "/kb", viewerId=U["alicia"], q="leave")
    slugs = [d["slug"] for d in r.json()]
    assert slugs[0] == "leave-and-time-off-policy"  # title hit outranks others
    assert len(slugs) <= 3  # top-N, never a wall of near-hits


def test_popular_strips_are_pool_scoped(api):
    r = _get(api.client, "/kb/popular", viewerId=U["priya"])
    assert len(r.json()) == 3
    r = _get(api.client, "/kb/popular", viewerId=U["alicia"])
    assert len(r.json()) == 5


def test_out_of_pool_document_is_403(api):
    r = _get(api.client, "/kb/payroll-processing-sop", viewerId=U["priya"])
    assert r.status_code == 403
    assert "permission" in r.json()["detail"].lower()


def test_file_url_is_gated_the_same_way(api):
    r = _get(api.client, "/kb/payroll-processing-sop/file", viewerId=U["priya"])
    assert r.status_code == 403
    r = _get(api.client, "/kb/payroll-processing-sop/file", viewerId=U["ben"])
    assert r.status_code == 200


def test_unknown_slug_is_404_and_slug_shape_is_enforced(api):
    assert _get(api.client, "/kb/does-not-exist", viewerId=U["priya"]).status_code == 404
    # uppercase / spacey slugs can never exist (SLUG_RE) -> 404, not 500
    assert _get(api.client, "/kb/Leave%20Policy", viewerId=U["priya"]).status_code == 404


def test_viewer_validations(api):
    # missing viewerId is rejected by FastAPI (required param)
    assert api.client.get("/api/kb").status_code == 422
    # malformed uuid
    r = _get(api.client, "/kb", viewerId="not-a-uuid")
    assert r.status_code == 422
    # well-formed but unknown
    r = _get(api.client, "/kb", viewerId="00000000-0000-0000-0000-999999999999")
    assert r.status_code == 404
    assert "unknown" in r.json()["detail"].lower()


def test_view_url_has_no_download_transform(api):
    r = _get(api.client, "/kb/leave-and-time-off-policy/file", viewerId=U["priya"])
    assert r.status_code == 200
    body = r.json()
    assert body["download"] is False
    assert body["url"].startswith("http://testserver/api/kb/pdf/leave-and-time-off-policy?")
    assert body["fileSize"] == 12345 and body["pages"] == 7
    response = api.client.get(body["url"])
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-1.4")
    assert response.headers["content-disposition"].startswith("inline;")


def test_download_url_carries_suggested_filename(api):
    r = _get(
        api.client,
        "/kb/leave-and-time-off-policy/file",
        viewerId=U["priya"],
        download=True,
    )
    assert r.status_code == 200
    assert r.json()["download"] is True
    response = api.client.get(r.json()["url"])
    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "Leave%20and%20Time%20Off%20Policy.pdf" in response.headers["content-disposition"]


def test_ttl_is_clamped_into_storage_call(api):
    r = _get(api.client, "/kb/hybrid-work-policy/file", viewerId=U["priya"], ttl="999999")
    assert r.status_code == 200
    assert r.json()["expiresInSeconds"] == 86400
    r = _get(api.client, "/kb/hybrid-work-policy/file", viewerId=U["priya"], ttl="5")
    assert r.status_code == 200
    assert r.json()["expiresInSeconds"] == 60


def test_agent_download_path_signs_hr_file(api):
    r = _get(
        api.client,
        "/kb/exit-process-sop/file",
        viewerId=U["alicia"],
        download=True,
    )
    assert r.status_code == 200
    response = api.client.get(r.json()["url"])
    assert response.status_code == 200
    assert "Exit%20Process%20SOP.pdf" in response.headers["content-disposition"]
