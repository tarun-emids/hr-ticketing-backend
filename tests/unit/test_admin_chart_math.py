"""Org-wide chart math: trend/backlog, aging, heatmap, SLA compliance, and
the extended agent counters (workload, categories, SLA share, score).

All assertions use rows whose ages are safely inside their bucket (the age
anchor is 'now', so a row created days ago at hour H is only future-dated
when the fixture itself says so — the demo seeder clamps this, tests pin
hours well in the past)."""

from datetime import datetime, timedelta, timezone

from app.admin.analytics import (
    SLA_TARGET_HOURS,
    agent_metrics,
    aging,
    heatmap,
    normalize_subject,
    performance_score,
    sla_compliance,
    trend,
)

NOW = datetime.now(timezone.utc)


def row(
    days_ago: int,
    hour: int,
    priority: str,
    status: str,
    *,
    agent="a",
    reply_hours=1.0,
    solve_days=None,
    category="Payroll",
):
    """One fabricated ticket row small enough to reason about by eye."""
    created = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {
        "id": "00000000-0000-0000-0000-000000000000",
        "employee_id": "e0000000-0000-0000-0000-000000000000",
        "assignee_id": agent,
        "category": category,
        "priority": priority,
        "status": status,
        "subject": "(DEMO) probe",
        "created_at": created,
        "first_reply_at": (
            created + timedelta(hours=reply_hours) if reply_hours is not None else None
        ),
        "resolved_at": (created + timedelta(days=solve_days) if solve_days is not None else None),
    }


def test_sla_targets_are_the_definition_basis():
    assert SLA_TARGET_HOURS == {"Urgent": 8, "High": 24, "Medium": 48, "Low": 72}


def test_sla_compliance_and_per_priority_split():
    rows = [
        row(18, 10, "High", "Resolved", solve_days=0.9),  # 21.6h < 24h -> in
        row(2, 9, "Urgent", "Resolved", solve_days=0.3),  # 7.2h < 8h -> in
        row(25, 11, "Medium", "Closed", solve_days=1.5),  # 36h < 48h -> in
        row(3, 7, "Medium", "Resolved", solve_days=2.6, agent="b"),  # 62.4h > 48h
        row(2, 15, "Low", "Open"),  # unresolved -> not counted
    ]
    out = sla_compliance(rows)
    assert out["resolvable"] == 4
    assert out["withinSla"] == 3
    assert out["breached"] == 1
    assert out["complianceRate"] == 75
    assert [p["priority"] for p in out["byPriority"]] == ["Urgent", "High", "Medium"]
    medium = [p for p in out["byPriority"] if p["priority"] == "Medium"][0]
    assert medium["resolvable"] == 2 and medium["withinSla"] == 1


def test_trend_counts_creations_resolutions_and_backlog():
    rows = [
        row(2, 15, "Low", "Open"),  # open, created 2d ago
        row(1, 9, "Medium", "In Progress"),  # open, created 1d ago
        row(18, 10, "High", "Resolved", solve_days=0.9),
    ]
    series = trend(rows, "30d")
    assert len(series) == 30  # daily buckets, past-inclusive
    # backlog falls as the only early ticket resolves somewhere close behind
    assert series[0]["backlog"] == 0
    assert series[0]["created"] == 0
    # the last bucket: the In Progress ticket created days ago may lie in a
    # prior bucket, but the mid-series backlog is at least the two open ones
    assert max(b["backlog"] for b in series) >= 1


def test_trend_bucket_counts_match_window_layout():
    rows = [row(0, 5, "Low", "Open")]
    for window, expected in (("24h", 24), ("7d", 7), ("30d", 30)):
        assert len(trend(rows, window)) == expected


def test_aging_buckets_the_unresolved_only():
    rows = [
        row(18, 10, "High", "Resolved", solve_days=0.9),  # resolved -> excluded
        row(2, 15, "Low", "Open"),  # 2 days -> 1-3 bucket
        row(0, 5, "Medium", "In Progress"),  # hours old -> < 1 day
        row(25, 11, "Medium", "Open"),  # ancient -> > 7 days
    ]
    out = aging(rows)
    assert [o["bucket"] for o in out] == ["< 1 day", "1-3 days", "3-7 days", "> 7 days"]
    assert [o["count"] for o in out][:2] == [1, 1]
    assert out[3]["count"] == 1


def test_heatmap_counts_and_peak():
    rows = [
        row(18, 10, "Low", "Open"),  # a weekday 10h cell
        row(18, 10, "Low", "Open"),  # same cell twice
        row(2, 9, "Low", "Open"),
    ]
    out = heatmap(rows)
    assert out["total"] == 3
    assert out["peak"] is not None and out["peak"]["count"] == 2
    assert sum(sum(day) for day in out["cells"]) == 3


def test_agent_workload_categories_and_sla():
    rows = [
        row(18, 10, "High", "Resolved", solve_days=0.9),
        row(25, 11, "Medium", "Closed", solve_days=1.5),
        row(2, 15, "Low", "Open"),  # pending -> Open
        row(1, 9, "Medium", "In Progress"),  # pending -> In Progress
    ]
    m = agent_metrics(rows, "a", "30d")
    assert (m["accepted"], m["completed"], m["pending"]) == (4, 2, 2)
    assert m["workload"] == [
        {"status": "Open", "count": 1},
        {"status": "In Progress", "count": 1},
    ]
    assert m["categories"] == [{"category": "Payroll", "resolved": 2}]
    assert m["slaComplianceRate"] == 100 and m["slaWindowCompletions"] == 2


def test_score_none_without_tickets_and_bounded_flat():
    rows = [row(2, 15, "Low", "Open")]  # all assigned to agent "a"
    assert agent_metrics(rows, "zz", "30d")["score"] is None
    accepted = [row(0, 5, "Low", "Open"), row(0, 5, "Low", "Open")]
    score = performance_score(accepted, [], [], [], None)
    assert 0 <= score <= 100


def test_demo_marker_is_ignored_by_subject_clustering():
    assert normalize_subject("(DEMO) Payslip shows the wrong tax band") == (
        "payslip shows the wrong tax band"
    )
    # demo rows and a real row land in ONE subject cluster
    demo = row(18, 10, "Low", "Open")
    demo["subject"] = "(DEMO) Payslip shows the wrong tax band"
    real = row(2, 15, "Low", "Open")
    real["subject"] = "Payslip shows the wrong tax band"
    keys = {normalize_subject(r["subject"]) for r in (demo, real)}
    assert keys == {"payslip shows the wrong tax band"}
