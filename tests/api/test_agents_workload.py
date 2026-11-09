import uuid as uuidlib

from tests.conftest import U, auth_headers

ALICIA = auth_headers("alicia")
RUTH = auth_headers("ruth")


def _bulk_ticket(fake, *, employee_id, assignee_id, status):
    fake.execute(
        "INSERT INTO tickets (id, employee_id, category, subject, description, priority,"
        " status, assignee_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            str(uuidlib.uuid4()),
            employee_id,
            "Payroll",
            "Workload counter bulk seed",
            "The bulk-seeded ticket body exists only to exercise workload counters.",
            "Medium",
            status,
            assignee_id,
        ),
    )


def workload_by_id(api):
    r = api.client.get("/api/agents/workload", params={"viewerId": U["alicia"]}, headers=ALICIA)
    assert r.status_code == 200
    return {row["id"]: row for row in r.json()}


def test_open_total_split_across_agents(api):
    """Seeded: TKT-102 In Progress -> alicia (active), TKT-103 Resolved ->
    ben (not active). A fresh unassigned Open ticket must land nowhere."""
    res = api.client.post(                       # priya default token mismatch → use tomas
        "/api/tickets",
        json={
            "employeeId": U["tomas"],
            "category": "Leave",
            "subject": "Unassigned ticket for the workload split test",
            "description": "This Open ticket must stay unassigned in the workload split test.",
        },
        headers=auth_headers("tomas"),
    )
    assert res.status_code == 201

    wl = workload_by_id(api)
    assert len(wl) == 3
    assert wl[U["alicia"]]["openCount"] == 1
    assert wl[U["alicia"]]["totalCount"] == 1
    assert wl[U["ben"]]["openCount"] == 0
    assert wl[U["ben"]]["totalCount"] == 1
    assert wl[U["ruth"]]["openCount"] == 0
    assert wl[U["ruth"]]["totalCount"] == 0


def test_workload_orders_agents_by_account_creation(api):
    """Contract: roster order (account creation date), not workload order."""
    r = api.client.get("/api/agents/workload", params={"viewerId": U["ruth"]}, headers=RUTH)
    assert [row["id"] for row in r.json()] == [U["alicia"], U["ben"], U["ruth"]]


def test_workload_counts_survive_past_old_2000_row_cap(api):
    """The replaced scan capped at LIMIT 2000; the GROUP BY aggregate has
    no ceiling. 2001 bulk active tickets for ben must count fully — with
    TKT-103 (Resolved): 2001 open, 2002 total."""
    for _ in range(2001):
        _bulk_ticket(api.fake, employee_id=U["priya"], assignee_id=U["ben"], status="In Progress")

    wl = workload_by_id(api)
    assert wl[U["ben"]]["openCount"] == 2001
    assert wl[U["ben"]]["totalCount"] == 2002
    assert wl[U["alicia"]]["openCount"] == 1
    assert wl[U["alicia"]]["totalCount"] == 1
