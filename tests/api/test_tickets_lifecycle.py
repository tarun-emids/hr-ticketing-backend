from tests.conftest import U


def reply(api, tid, author, text="Replying right here."):
    return api.client.post(f"/api/tickets/{tid}/replies", json={"authorId": author, "text": text})


def test_agent_first_reply_stamps_and_moves_to_in_progress(api):
    before = api.client.get("/api/tickets/TKT-101").json()
    assert before["firstReplyAt"] is None
    assert before["status"] == "Open"

    r = reply(api, "TKT-101", U["alicia"])
    assert r.status_code == 200
    t = r.json()
    assert t["status"] == "In Progress"
    assert t["firstReplyAt"] is not None
    assert t["turns"][-1]["role"] == "agent"
    assert t["turns"][-1]["authorId"] == U["alicia"]


def test_second_agent_reply_keeps_first_reply_at(api):
    after_first = api.client.get("/api/tickets/TKT-102").json()
    stamp = after_first["firstReplyAt"]
    r = reply(api, "TKT-102", U["ben"])
    t = r.json()
    assert t["firstReplyAt"] == stamp


def test_employee_reply_moves_active_ticket_to_waiting_on_employee(api):
    api.client.post(
        "/api/tickets", json={
            "employeeId": U["priya"], "category": "Benefits",
            "subject": "Dental plan covers orthodontics?",
            "description": "Does the new dental plan cover partial orthodontic treatment, and where do I check coverage?",
        },
    )
    created = api.client.get("/api/tickets").json()[0]["id"]
    r = reply(api, created, U["priya"])
    t = r.json()
    assert t["status"] == "Waiting on Employee"
    assert t["firstReplyAt"] is None


def test_employee_reply_leaves_final_statuses_alone(api):
    r = reply(api, "TKT-103", U["dana"])
    assert r.json()["status"] == "Resolved"


def test_reply_unknown_author(api):
    r = reply(api, "TKT-101", "00000000-0000-0000-0000-999999999999")
    assert r.status_code == 422
    assert "does not match a known user" in r.json()["detail"]


def test_reply_empty_text_rejected(api):
    r = reply(api, "TKT-101", U["priya"], text="")
    assert r.status_code == 422


def test_reply_to_missing_ticket(api):
    r = reply(api, "TKT-999", U["priya"])
    assert r.status_code == 404


def test_resolve_stamps_resolved_at(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/status", json={"status": "Resolved", "actorId": U["ben"]}
    )
    t = r.json()
    assert t["status"] == "Resolved"
    assert t["resolvedAt"] is not None
    assert t["closedBy"] is None


def test_close_records_actor_keeps_resolved_at(api):
    resolved = api.client.patch(
        "/api/tickets/TKT-103/status", json={"status": "Closed", "actorId": U["ruth"]}
    ).json()
    assert resolved["closedBy"] == U["ruth"]
    assert resolved["resolvedAt"] is not None


def test_close_from_open_stamps_both(api):
    t = api.client.patch(
        "/api/tickets/TKT-101/status", json={"status": "Closed", "actorId": U["ben"]}
    ).json()
    assert t["closedBy"] == U["ben"]
    assert t["resolvedAt"] is not None


def test_reopening_clears_resolved_at_and_closed_by(api):
    api.client.patch("/api/tickets/TKT-101/status", json={"status": "Resolved", "actorId": U["ben"]})
    api.client.patch("/api/tickets/TKT-101/status", json={"status": "In Progress", "actorId": U["ben"]})
    t = api.client.get("/api/tickets/TKT-101").json()
    assert t["resolvedAt"] is None
    assert t["closedBy"] is None


def test_waiting_on_employee_keeps_timestamps(api):
    api.client.patch("/api/tickets/TKT-101/status", json={"status": "Resolved", "actorId": U["ben"]})
    stamp = api.client.get("/api/tickets/TKT-101").json()["resolvedAt"]
    t = api.client.patch(
        "/api/tickets/TKT-101/status", json={"status": "Waiting on Employee", "actorId": U["ben"]}
    ).json()
    assert t["status"] == "Waiting on Employee"
    assert t["resolvedAt"] == stamp
    assert t["closedBy"] is None


def test_status_invalid_value(api):
    r = api.client.patch("/api/tickets/TKT-101/status", json={"status": "Done", "actorId": U["ben"]})
    assert r.status_code == 422


def test_status_employee_can_act_as_actor(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/status", json={"status": "Resolved", "actorId": U["priya"]}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "Resolved"


def test_status_unknown_actor_rejected(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Resolved", "actorId": "00000000-0000-0000-0000-999999999999"},
    )
    assert r.status_code == 422
    assert "does not match a known user" in r.json()["detail"]


def test_assign_to_unanswered_ticket_posts_pickup_reply(api):
    r = api.client.patch("/api/tickets/TKT-101/assignee", json={"assigneeId": U["alicia"]})
    t = r.json()
    assert t["assigneeId"] == U["alicia"]
    assert t["firstReplyAt"] is not None
    assert t["status"] == "In Progress"
    pickup = t["turns"][-1]
    assert pickup["authorId"] == U["alicia"]
    assert pickup["role"] == "agent"
    assert pickup["text"] == (
        "Thanks for raising this — I've picked it up and will get back to you shortly."
    )


def test_assign_to_already_replied_ticket_no_duplicate_pickup(api):
    before = api.client.get("/api/tickets/TKT-102").json()
    stamp = before["firstReplyAt"]
    r = api.client.patch("/api/tickets/TKT-102/assignee", json={"assigneeId": U["ben"]})
    t = r.json()
    assert t["assigneeId"] == U["ben"]
    assert t["firstReplyAt"] == stamp
    assert len(t["turns"]) == 1
    assert t["status"] == "In Progress"


def test_unassign(api):
    r = api.client.patch("/api/tickets/TKT-102/assignee", json={"assigneeId": None})
    assert r.json()["assigneeId"] is None


def test_assign_unknown_user(api):
    r = api.client.patch("/api/tickets/TKT-101/assignee", json={"assigneeId": U["priya"]})
    assert r.status_code == 422
    assert "must be an HR agent" in r.json()["detail"]


def test_set_priority_and_category(api):
    t = api.client.patch("/api/tickets/TKT-101/priority", json={"priority": "Urgent"}).json()
    assert t["priority"] == "Urgent"
    t = api.client.patch("/api/tickets/TKT-101/category", json={"category": "Leave"}).json()
    assert t["category"] == "Leave"


def test_set_priority_invalid(api):
    r = api.client.patch("/api/tickets/TKT-101/priority", json={"priority": "Someday"})
    assert r.status_code == 422


def test_set_category_invalid(api):
    r = api.client.patch("/api/tickets/TKT-101/category", json={"category": "Wages"})
    assert r.status_code == 422


def test_updates_bump_updated_at(api):
    before = api.client.get("/api/tickets/TKT-101").json()["updatedAt"]
    api.client.patch("/api/tickets/TKT-101/priority", json={"priority": "Low"})
    after = api.client.get("/api/tickets/TKT-101").json()["updatedAt"]
    assert after > before
