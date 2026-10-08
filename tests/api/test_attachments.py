import io

from tests.conftest import U


def upload(api, tid, filename="note.pdf", content=b"PDF-ish bytes", content_type="application/pdf"):
    return api.client.post(
        f"/api/tickets/{tid}/attachment",
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


def test_get_attachment_without_attachment_404(api):
    r = api.client.get("/api/tickets/TKT-101/attachment")
    assert r.status_code == 404


def test_upload_attachment_success(api):
    r = upload(api, "TKT-101", content=b"binary payload here")
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["attachment"]["name"] == "note.pdf"
    assert t["attachment"]["size"] == len(b"binary payload here")
    path = t["attachment"]["path"]
    assert path.startswith("TKT-101/")


def test_signed_url_for_stored_attachment(api):
    api.client.post(
        "/api/tickets", json={
            "employeeId": U["priya"], "category": "Other",
            "subject": "Office badge replacement needed",
            "description": "My badge stopped working at the lobby reader and HR needs a replacement.",
        },
    )
    tid = api.client.get("/api/tickets").json()[0]["id"]
    upload(api, tid, content=b"abc")
    r = api.client.get(f"/api/tickets/{tid}/attachment")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "note.pdf"
    assert body["size"] == 3
    assert body["url"].startswith("https://fake.supabase.co/storage/v1/object/sign/")
    assert body["expiresInSeconds"] == 3600


def test_signed_url_ttl_clamped(api):
    upload(api, "TKT-102")
    api.client.get("/api/tickets/TKT-102/attachment", params={"ttl": 5})
    assert api.fake.last_signed_ttl == 60
    api.client.get("/api/tickets/TKT-102/attachment", params={"ttl": 999999})
    assert api.fake.last_signed_ttl == 86400


def test_reupload_replaces_previous_attachment(api):
    upload(api, "TKT-101", content=b"first", filename="one.txt")
    r = api.client.post(
        "/api/tickets/TKT-101/attachment",
        files={"file": ("two.txt", io.BytesIO(b"second payload"), "text/plain")},
    )
    t = r.json()
    assert t["attachment"]["name"] == "two.txt"
    assert t["attachment"]["size"] == len(b"second payload")
    keys = list(api.fake.storage_files.keys())
    assert all(k[1].endswith(".txt") for k in keys)


def test_upload_too_large_413(api):
    big = b"z" * (5 * 1024 * 1024 + 1)
    r = upload(api, "TKT-101", content=big)
    assert r.status_code == 413
    assert "larger than 5 MB" in r.json()["detail"]


def test_upload_to_missing_ticket_404(api):
    r = upload(api, "TKT-777")
    assert r.status_code == 404


def test_upload_storage_failure_502(api):
    api.fake.fail_uploads = True
    r = upload(api, "TKT-101")
    assert r.status_code == 502
    assert "Storage upload failed" in r.json()["detail"]
