"""Knowledge base endpoints — visibility gates, search, PDF streaming.

Runs against the offline SQLite-backed harness seeded with 3 employee + 2 HR
policy documents (tests/conftest.py). The gate rules under test:
  - the viewer is the bearer-token identity; every request posts AS the
    viewer whose pools it expects, and a foreign viewerId claim yields 403
    before the service resolves a role;
  - employee sees the employee pool, agents see both pools;
  - out-of-pool -> 403, unknown slug -> 404;
  - the file endpoint streams the PDF straight from the store: inline by
    default, attachment-disposition with the suggested filename when
    download=true — and the gate runs on EVERY fetch.
"""

from tests.conftest import U, auth_headers


def _get(api, path, viewer="priya", **params):
    """GET /kb as the named seeded viewer (token + matching viewerId claim)."""
    return api.client.get(
        f"/api{path}", params={"viewerId": U[viewer], **params}, headers=auth_headers(viewer)
    )


# -- catalogue + pools --------------------------------------------------------


def test_employee_lists_only_employee_pool(api):
    r = _get(api, "/kb", viewer="priya")
    assert r.status_code == 200
    audiences = {doc["audience"] for doc in r.json()}
    assert audiences == {"employee"}
    assert {doc["slug"] for doc in r.json()} == {
        "leave-policy",
        "payslip-guide",
        "work-time-policy",
    }


def test_agent_sees_both_pools(api):
    r = _get(api, "/kb", viewer="alicia")
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert {doc["audience"] for doc in r.json()} == {"employee", "hr"}


def test_borrowed_viewer_identity_rejected(api):
    """The old escalation path (employee passing an agent id as viewerId) is
    dead: the claim disagrees with the token, which is a 403 — not a wider
    knowledge pool."""
    r = api.client.get("/api/kb", params={"viewerId": U["alicia"]}, headers=auth_headers("priya"))
    assert r.status_code == 403


def test_viewer_claim_is_optional_now(api):
    """viewerId stays accepted (frontend contract) but is no longer needed:
    the token identity fills it in."""
    r = api.client.get("/api/kb", headers=auth_headers("priya"))
    assert r.status_code == 200
    assert {doc["audience"] for doc in r.json()} == {"employee"}


# -- search (weighted scorer lives behind GET /kb?q=) --------------------------


def test_search_returns_top_matches_only(api):
    r = _get(api, "/kb", viewer="alicia", q="leave")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) <= 3  # hard result cap
    assert rows[0]["slug"] == "leave-policy"  # title hit outranks keyword hits


def test_search_cap_actually_limits(api):
    # 'policy' hits several titles; the endpoint still never returns more than 3.
    r = _get(api, "/kb", viewer="alicia", q="policy")
    assert r.status_code == 200
    assert len(r.json()) <= 3


# -- doc shape contract --------------------------------------------------------


def test_doc_shape_matches_frontend_contract(api):
    r = _get(api, "/kb/leave-policy", viewer="priya")
    assert r.status_code == 200
    doc = r.json()
    assert set(doc.keys()) == {
        "slug",
        "ref",
        "title",
        "category",
        "audience",
        "summary",
        "keywords",
        "version",
        "effectiveDate",
        "pages",
        "fileSize",
        "updatedAt",
    }
    assert doc["title"] == "Leave Policy"
    assert doc["audience"] == "employee"


def test_unknown_slug_is_404_not_403(api):
    r = _get(api, "/kb/not-a-real-policy", viewer="priya")
    assert r.status_code == 404


def test_out_of_pool_slug_is_403(api):
    r = _get(api, "/kb/payroll-run-sop", viewer="priya")
    assert r.status_code == 403
    assert "permission" in r.json()["detail"].lower()


# -- file streaming ------------------------------------------------------------


def test_file_streams_pdf_inline_by_default(api):
    r = _get(api, "/kb/leave-policy/file", viewer="priya")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-1.4")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert "Leave Policy.pdf" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


def test_file_download_flavour_carries_filename(api):
    r = _get(api, "/kb/leave-policy/file", viewer="priya", download=True)
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert 'filename="Leave Policy.pdf"' in r.headers["content-disposition"]


def test_file_search_gate_blocks_out_of_pool(api):
    r = _get(api, "/kb/exit-offboard-policy/file", viewer="priya")
    assert r.status_code == 403


def test_file_allows_agent_across_pools(api):
    r = _get(api, "/kb/exit-offboard-policy/file", viewer="alicia")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-1.4")


def test_file_unknown_slug_404(api):
    r = _get(api, "/kb/no-such-doc/file", viewer="priya")
    assert r.status_code == 404
