"""Knowledge base endpoints — visibility gates, search, PDF streaming.

Runs against the offline SQLite-backed harness seeded with 3 employee + 2 HR
policy documents (tests/conftest.py). The gate rules under test:
  - the viewer's role always comes from `users` (viewerId), never trusted;
  - employee sees the employee pool, agents see both pools;
  - out-of-pool -> 403, unknown slug -> 404, bad viewer -> 422/404;
  - the file endpoint streams the PDF straight from the store: inline by
    default, attachment-disposition with the suggested filename when
    download=true — and the gate runs on EVERY fetch.
"""

from tests.conftest import U


def _get(client, path, **params):
    return client.get(f"/api{path}", params=params)


# -- catalogue + pools --------------------------------------------------------


def test_employee_lists_only_employee_pool(api):
    r = _get(api.client, "/kb", viewerId=U["priya"])
    assert r.status_code == 200
    audiences = {doc["audience"] for doc in r.json()}
    assert audiences == {"employee"}
    assert {doc["slug"] for doc in r.json()} == {
        "leave-policy",
        "payslip-guide",
        "work-time-policy",
    }


def test_agent_sees_both_pools(api):
    r = _get(api.client, "/kb", viewerId=U["alicia"])
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert {doc["audience"] for doc in r.json()} == {"employee", "hr"}


# -- search (weighted scorer lives behind GET /kb?q=) --------------------------


def test_search_returns_top_matches_only(api):
    r = _get(api.client, "/kb", viewerId=U["alicia"], q="leave")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) <= 3  # hard result cap
    assert rows[0]["slug"] == "leave-policy"  # title hit outranks keyword hits


def test_search_cap_actually_limits(api):
    # 'policy' hits several titles; the endpoint still never returns more than 3.
    r = _get(api.client, "/kb", viewerId=U["alicia"], q="policy")
    assert r.status_code == 200
    assert len(r.json()) <= 3


# -- doc shape contract --------------------------------------------------------


def test_doc_shape_matches_frontend_contract(api):
    r = _get(api.client, "/kb/leave-policy", viewerId=U["priya"])
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
    r = _get(api.client, "/kb/not-a-real-policy", viewerId=U["priya"])
    assert r.status_code == 404


def test_out_of_pool_slug_is_403(api):
    r = _get(api.client, "/kb/payroll-run-sop", viewerId=U["priya"])
    assert r.status_code == 403
    assert "permission" in r.json()["detail"].lower()


# -- viewer resolution ---------------------------------------------------------


def test_unknown_viewer_404(api):
    r = _get(api.client, "/kb", viewerId="00000000-0000-0000-0000-000000000abc")
    assert r.status_code == 404


def test_malformed_viewer_422(api):
    r = _get(api.client, "/kb", viewerId="not-a-uuid")
    assert r.status_code == 422


# -- file streaming ------------------------------------------------------------


def test_file_streams_pdf_inline_by_default(api):
    r = _get(api.client, "/kb/leave-policy/file", viewerId=U["priya"])
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-1.4")
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert "Leave Policy.pdf" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"


def test_file_download_flavour_carries_filename(api):
    r = _get(api.client, "/kb/leave-policy/file", viewerId=U["priya"], download=True)
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert 'filename="Leave Policy.pdf"' in r.headers["content-disposition"]


def test_file_search_gate_blocks_out_of_pool(api):
    r = _get(api.client, "/kb/exit-offboard-policy/file", viewerId=U["priya"])
    assert r.status_code == 403


def test_file_allows_agent_across_pools(api):
    r = _get(api.client, "/kb/exit-offboard-policy/file", viewerId=U["alicia"])
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-1.4")


def test_file_unknown_slug_404(api):
    r = _get(api.client, "/kb/no-such-doc/file", viewerId=U["priya"])
    assert r.status_code == 404
