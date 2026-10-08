import pytest

from app.models import attachment_out, ticket_out, turn_out, user_out


def test_user_out_shape():
    u = {"id": "u1", "name": "Priya Sharma", "email": "priya@acme.com", "role": "employee"}
    assert user_out(u) == {"id": "u1", "name": "Priya Sharma", "email": "priya@acme.com", "role": "employee"}


def test_turn_out_maps_snake_to_camel():
    r = {
        "author_id": "a1",
        "author_role": "agent",
        "body": "hello",
        "created_at": "2026-01-01T00:00:00Z",
    }
    assert turn_out(r) == {
        "authorId": "a1",
        "role": "agent",
        "text": "hello",
        "at": "2026-01-01T00:00:00Z",
    }


def test_attachment_out_none_when_no_path():
    assert attachment_out({}) is None
    assert attachment_out({"attachment_path": None}) is None


def test_attachment_out_shape():
    row = {
        "attachment_path": "TKT-101/abc.pdf",
        "attachment_name": "payslip.pdf",
        "attachment_size": 42,
    }
    a = attachment_out(row)
    assert a == {
        "name": "payslip.pdf",
        "size": 42,
        "path": "TKT-101/abc.pdf",
        "url": None,
    }


def test_ticket_out_full_shape():
    row = {
        "ref": "TKT-104",
        "id": "uuid-1",
        "employee_id": "e1",
        "category": "Payroll",
        "subject": "Missing shift allowance",
        "description": "The payslip did not include weekend shift allowance.",
        "priority": "High",
        "status": "Open",
        "assignee_id": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "first_reply_at": None,
        "resolved_at": None,
        "closed_by": None,
        "attachment_path": None,
    }
    t = ticket_out(row, [])
    assert t["id"] == "TKT-104"
    assert t["uuid"] == "uuid-1"
    assert t["turns"] == []
    assert t["attachment"] is None
    assert set(t.keys()) == {
        "id", "uuid", "employeeId", "category", "subject", "description",
        "priority", "status", "assigneeId", "createdAt", "updatedAt",
        "firstReplyAt", "resolvedAt", "closedBy", "turns", "attachment",
    }


def test_ticket_out_includes_turns_and_attachment():
    row = {
        "ref": "TKT-101", "id": "uuid-1", "employee_id": "e1",
        "category": "Payroll", "subject": "Missing shift allowance",
        "description": "The payslip did not include weekend shift allowance.",
        "priority": "High", "status": "Open", "assignee_id": "ag1",
        "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        "first_reply_at": "2026-01-01T01:00:00Z",
        "resolved_at": None, "closed_by": None,
        "attachment_path": "TKT-101/x.png", "attachment_name": "x.png",
        "attachment_size": 7,
    }
    replies = [{
        "author_id": "ag1", "author_role": "agent", "body": "got it",
        "created_at": "2026-01-01T01:00:00Z",
    }]
    t = ticket_out(row, replies)
    assert t["turns"] == [{
        "authorId": "ag1", "role": "agent", "text": "got it",
        "at": "2026-01-01T01:00:00Z",
    }]
    assert t["attachment"]["path"] == "TKT-101/x.png"
    assert t["firstReplyAt"] == "2026-01-01T01:00:00Z"
    assert t["closedBy"] is None
