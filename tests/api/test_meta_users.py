from tests.conftest import U


def test_health(api):
    r = api.client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_list_users_employees_then_agents(api):
    r = api.client.get("/api/users")
    assert r.status_code == 200
    users = r.json()
    assert len(users) == 7
    roles = [u["role"] for u in users]
    assert roles == ["employee"] * 4 + ["agent"] * 3
    by_id = {u["id"]: u for u in users}
    assert by_id[U["priya"]]["name"] == "Priya Sharma"
    assert by_id[U["priya"]]["email"] == "priya@acme.com"
    assert by_id[U["ruth"]]["role"] == "agent"
    for u in users:
        assert set(u.keys()) == {"id", "name", "email", "role"}


def test_list_agents_only(api):
    r = api.client.get("/api/users/agents")
    assert r.status_code == 200
    agents = r.json()
    assert [a["id"] for a in agents] == [U["alicia"], U["ben"], U["ruth"]]
    assert all(a["role"] == "agent" for a in agents)


def test_meta_lists(api):
    r = api.client.get("/api/meta")
    assert r.status_code == 200
    m = r.json()
    assert m["categories"] == ["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"]
    assert m["priorities"] == ["Low", "Medium", "High", "Urgent"]
    assert m["statuses"] == ["Open", "In Progress", "Waiting on Employee", "Resolved", "Closed"]
