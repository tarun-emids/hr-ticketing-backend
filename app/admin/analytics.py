"""Pure analytics rules: period windows, KPIs, repetition and per-agent math.

Everything here is a module-level function on plain ticket-row dicts (the
shape AdminRepository.ticket_rows() returns), so it is unit-testable without
time, a DB or a user. The definition basis (agreed with the product owner)
— there is no assignment-history table in the schema:

- window      = "24h" | "7d" | "30d"
- accepted    tickets assigned to the agent AND created inside the window
- completed   tickets assigned to the agent AND resolved inside the window
- pending     tickets assigned to the agent, created inside the window,
              still open
- response    first_reply_at - created_at
- solve       resolved_at - created_at
- SLA         resolution within the priority target (SLA_TARGET_HOURS);
              there are no escalation/reopen events in the schema, so the
              breach share inside sla_compliance() is the closest honest
              proxy and reopen rate is not reported at all
- backlog     at a moment T: tickets created ≤ T not yet resolved (status
              may have changed later — backlog series is timestamp-based)

Percentiles are computed on sorted seconds lists in Python (the offline
SQLite double has no percentile aggregation).
"""

import re
from datetime import datetime, timedelta, timezone
from statistics import median

PERIODS: dict[str, float] = {
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
    "30d": 30 * 24 * 3600,
}
DEFAULT_PERIOD = "7d"

# Resolution SLA target per priority in hours (resolution deadline = the
# target, measured creation -> resolved_at). Pure reporting math — no schema.
SLA_TARGET_HOURS: dict[str, int] = {"Urgent": 8, "High": 24, "Medium": 48, "Low": 72}

# First-response expectation that feeds the performance score (same target
# for every priority; response HELD IN ONE constant so the definition basis
# lives in exactly one file).
RESPONSE_TARGET_HOURS = 4

# Composite agent performance score weights (0-100 rounded):
#   40% SLA compliance  - share of the agent's completions resolved in target
#   30% responsiveness  - share of accepted tickets answered in target
#   30% throughput      - share of accepted tickets completed in the window
SCORE_WEIGHTS = {"sla": 0.4, "response": 0.3, "throughput": 0.3}

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_PRIORITY_ORDER = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}


def period_seconds(period: str) -> float:
    """KeyError on unknown period — callers map it to HTTPException(422)."""
    return PERIODS[period]


def _as_dt(value) -> datetime | None:
    """SQL rows hand datetimes back (psycopg) or ISO strings (SQLite double)."""
    if value is None or isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _within(value, seconds: float, now: datetime | None = None) -> bool:
    dt = _as_dt(value)
    if not dt:
        return False
    anchor = now or datetime.now(timezone.utc)
    return 0 <= (anchor - _aware(dt)).total_seconds() <= seconds


def _age_of(value, now: datetime) -> float | None:
    """Seconds since `value` (past-only), or None when absent/unparseable."""
    dt = _as_dt(value)
    if not dt:
        return None
    return max(0.0, (now - _aware(dt)).total_seconds())


# -- time metrics on rows ------------------------------------------------------


def _rep_seconds(t: dict) -> float | None:
    created = _as_dt(t.get("created_at"))
    first = _as_dt(t.get("first_reply_at"))
    if not created or not first:
        return None
    return max(0.0, (first - created).total_seconds())


def _solve_seconds(t: dict) -> float | None:
    created = _as_dt(t.get("created_at"))
    resolved = _as_dt(t.get("resolved_at"))
    if not created or not resolved:
        return None
    return max(0.0, (resolved - created).total_seconds())


def _hours(seconds: float | None) -> float | None:
    return None if seconds is None else round(seconds / 3600, 2)


def distribution(seconds_list: list[float], buckets: int = 8) -> list[dict]:
    """Histogram of a time metric in whole hours: 'how many answers/solves
    land inside <N h' — read top-down to tune SLA expectations."""
    usable = [s for s in seconds_list if s is not None]
    if not usable:
        return []
    step_hours = max(1.0, max(usable) / 3600 / buckets)
    out: dict[int, int] = {}
    for s in usable:
        index = min(int(s / 3600 / step_hours), buckets - 1)
        out[index] = out.get(index, 0) + 1
    return [
        {"to": f"≤{(i + 1) * step_hours:.0f}h", "count": out.get(i, 0)}
        for i in range(buckets)
        if out.get(i)
    ]


# -- overall picture -----------------------------------------------------------


def status_counts(rows: list[dict]) -> dict[str, int]:
    out = {
        status: 0 for status in ("Open", "In Progress", "Waiting on Employee", "Resolved", "Closed")
    }
    for row in rows:
        status = row.get("status")
        if status in out:
            out[status] += 1
    return out


def overall_metrics(rows: list[dict]) -> dict:
    """Head KPI band: counts + whole-scan time metrics."""
    counts = status_counts(rows)
    responses = [s for t in rows if (s := _rep_seconds(t)) is not None]
    solves = [s for t in rows if (s := _solve_seconds(t)) is not None]
    return {
        "total": len(rows),
        "open": counts["Open"],
        "inProgress": counts["In Progress"],
        "waitingOnEmployee": counts["Waiting on Employee"],
        "resolved": counts["Resolved"],
        "closed": counts["Closed"],
        "active": counts["Open"] + counts["In Progress"] + counts["Waiting on Employee"],
        "avgFirstResponseHrs": _hours(sum(responses) / len(responses)) if responses else None,
        "medianFirstResponseHrs": _hours(median(responses)) if responses else None,
        "avgSolveHrs": _hours(sum(solves) / len(solves)) if solves else None,
        "medianSolveHrs": _hours(median(solves)) if solves else None,
        "answeredShare": round(100 * len(responses) / len(rows)) if rows else 0,
        "responseDistribution": distribution(responses),
        "solveDistribution": distribution(solves),
    }


def normalize_subject(subject: str) -> str:
    """Cluster key for repetitive tickets: lowercased, the demo seed marker
    "(DEMO) " ignored, ticket refs/punctuation stripped, whitespace
    collapsed."""
    cleaned = re.sub(r"^\s*\(demo\)\s*", "", (subject or "").lower())
    cleaned = re.sub(r"tkt-?\d+", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", cleaned)
    return " ".join(cleaned.split())


def repeated_subjects(rows: list[dict], limit: int = 5) -> list[dict]:
    """Subject clusters reported more than once — the 'write me a policy' hint.
    Each carries sample ticket refs so the admin can read the phrasings."""
    clusters: dict[str, list[dict]] = {}
    for row in rows:
        key = normalize_subject(row.get("subject") or "")
        if len(key.split()) < 2:  # one-word keys are noise, not clusters
            continue
        clusters.setdefault(key, []).append(row)
    ranked = sorted(clusters.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    return [
        {
            "normalized": key,
            "count": len(group),
            "title": group[0].get("subject") or key,
            "sampleRefs": [r.get("ref") for r in group[:4]],
        }
        for key, group in ranked[:limit]
        if len(group) > 1
    ]


def category_breakdown(rows: list[dict]) -> list[dict]:
    """Per-category load with its own repetitive-subject clusters inside."""
    by_category: dict[str, list[dict]] = {}
    for row in rows:
        by_category.setdefault(row.get("category") or "Other", []).append(row)
    return [
        {
            "category": category,
            "total": len(group),
            "open": sum(1 for t in group if t.get("status") not in ("Resolved", "Closed")),
            "repeatedSubjects": repeated_subjects(group, limit=3),
        }
        for category, group in sorted(
            by_category.items(), key=lambda pair: (-len(pair[1]), pair[0])
        )
    ]


# -- org-wide chart math (dashboard trend / aging / heatmap / SLA) --------------


def _trend_grid(window: str, now: datetime) -> tuple[float, list[tuple[str, int, int]]]:
    """Bucket geometry for trend(): (width_seconds, [(label, lo_age, hi_age)]),
    oldest bucket first. 24h runs hourly, every other window daily;
    the boundary is calendar-aligned (today at H:00 / midnight) so the chart's
    last bucket is a partial day that grows during the day."""
    seconds = PERIODS.get(window, PERIODS["30d"])
    if window == "24h":
        width = 3600.0
        count = 24
        anchor = now.replace(minute=0, second=0, microsecond=0)
    else:
        width = 86400.0
        count = int(seconds // 86400)
        anchor = now.replace(hour=0, minute=0, second=0, microsecond=0)
    buckets = []
    for i in range(count):
        hi = anchor - timedelta(seconds=i * width)  # bucket end (age 0 side)
        lo = hi - timedelta(seconds=width)
        if window == "24h":
            label = hi.strftime("%H:%M")
        else:
            label = hi.strftime("%d %b")
        buckets.append((label, lo, hi))
    return width, buckets[::-1]


def trend(rows: list[dict], window: str) -> list[dict]:
    """Org-wide volume series per bucket (oldest -> newest): creations,
    resolutions, average/median isn't repeated (avg only) and the BACKLOG at
    each bucket end — created ≤ end and not resolved by the end."""
    now = datetime.now(timezone.utc)
    _, grid = _trend_grid(window, now)
    created = [_as_dt(r.get("created_at")) for r in rows]
    resolved = [_as_dt(r.get("resolved_at")) for r in rows]
    hides = [r.get("status") in ("Resolved", "Closed") for r in rows]

    out = []
    for label, lo, hi in grid:
        created_in = sum(1 for c in created if c is not None and lo <= c < hi)
        resolved_in = sum(
            1 for i, s in enumerate(resolved) if s is not None and lo <= s < hi and hides[i]
        )
        backlog = sum(1 for i, c in enumerate(created) if c is not None and c <= hi) - sum(
            1 for i, s in enumerate(resolved) if s is not None and s <= hi and hides[i]
        )
        solves = [
            (resolved[i] - created[i]).total_seconds() / 3600
            for i in range(len(rows))
            if created[i] and resolved[i] and lo <= resolved[i] < hi and hides[i]
        ]
        out.append(
            {
                "label": label,
                "created": created_in,
                "resolved": resolved_in,
                "avgSolveHrs": round(sum(solves) / len(solves), 1) if solves else None,
                "backlog": max(0, backlog),
            }
        )
    return out


def aging(rows: list[dict], now: datetime | None = None) -> list[dict]:
    """Current age buckets of the still-unresolved tickets — 'how long the
    waiting work has been waiting' (fresh <1d … stall >7d)."""
    anchor = now or datetime.now(timezone.utc)
    bounds = [
        (-1, 86400, "< 1 day"),
        (86400, 3 * 86400, "1-3 days"),
        (3 * 86400, 7 * 86400, "3-7 days"),
        (7 * 86400, float("inf"), "> 7 days"),
    ]
    counts = [0] * len(bounds)
    oldest = None
    for row in rows:
        if row.get("status") in ("Resolved", "Closed"):
            continue
        dt = _as_dt(row.get("created_at"))
        if not dt:
            continue
        age = (anchor - _aware(dt)).total_seconds()
        oldest = age if oldest is None else max(oldest, age)
        for i, (lo, hi, _) in enumerate(bounds):
            if lo < age <= hi:
                counts[i] += 1
                break
    out = [{"bucket": b[2], "count": counts[i]} for i, b in enumerate(bounds)]
    return out


def heatmap(rows: list[dict]) -> dict:
    """Creation-count matrix weekday (Mon-first) x hour (0-23) — the peak
    activity grid the console draws; plus the single busiest cell."""
    grid = [[0] * 24 for _ in range(7)]
    total = 0
    for row in rows:
        dt = _as_dt(row.get("created_at"))
        if not dt:
            continue
        grid[dt.weekday()][dt.hour] += 1
        total += 1
    peak = None
    for d in range(7):
        for h in range(24):
            if peak is None or grid[d][h] > grid[peak[0]][peak[1]]:
                if grid[d][h]:
                    peak = (d, h)
    return {
        "days": list(_WEEKDAYS),
        "cells": grid,
        "total": total,
        "peak": (
            {"day": _WEEKDAYS[peak[0]], "hour": peak[1], "count": grid[peak[0]][peak[1]]}
            if peak
            else None
        ),
    }


def sla_compliance(rows: list[dict]) -> dict:
    """Resolution-SLA compliance over tickets with a resolvable timeline:
    a ticket counts INSIDE SLA when resolved_at - created_at fits the
    priority target (SLA_TARGET_HOURS). Breach share is what the console
    shows instead of escalation counts (nothing else in the schema can
    honestly measure escalation)."""
    met = 0
    total = 0
    per: dict[str, dict] = {}
    for row in rows:
        if row.get("status") not in ("Resolved", "Closed"):
            continue
        seconds = _solve_seconds(row)
        if seconds is None:
            continue
        priority = row.get("priority") or "Medium"
        in_sla = seconds <= SLA_TARGET_HOURS.get(priority, 48) * 3600
        total += 1
        met += int(in_sla)
        bucket = per.setdefault(priority, {"total": 0, "met": 0})
        bucket["total"] += 1
        bucket["met"] += int(in_sla)
    return {
        "resolvable": total,
        "withinSla": met,
        "breached": total - met,
        "complianceRate": round(100 * met / total) if total else None,
        "byPriority": [
            {
                "priority": priority,
                "resolvable": counts["total"],
                "withinSla": counts["met"],
                "complianceRate": round(100 * counts["met"] / counts["total"]),
            }
            for priority, counts in sorted(
                per.items(), key=lambda pair: (_PRIORITY_ORDER.get(pair[0], 9), pair[0])
            )
            if counts["total"]
        ],
    }


def agent_window_rows(rows: list[dict], agent_id: str, period: str) -> dict:
    """The groups behind the counters (created/resolved basis)."""
    seconds = period_seconds(period)
    accepted = [
        r
        for r in rows
        if r.get("assignee_id") == agent_id and _within(r.get("created_at"), seconds)
    ]
    completed = [
        r
        for r in rows
        if r.get("assignee_id") == agent_id
        and r.get("status") in ("Resolved", "Closed")
        and _within(r.get("resolved_at"), seconds)
    ]
    return {"accepted": accepted, "completed": completed}


def agent_metrics(rows: list[dict], agent_id: str, period: str) -> dict:
    """The drill-down the admin sees for any agent (the agent sees their own
    identical payload through /admin/metrics/agents/{self})."""
    groups = agent_window_rows(rows, agent_id, period)
    accepted, completed = groups["accepted"], groups["completed"]
    pending = [r for r in accepted if r.get("status") not in ("Resolved", "Closed")]
    responses = [s for t in accepted if (s := _rep_seconds(t)) is not None]
    solves = [s for t in completed if (s := _solve_seconds(t)) is not None]
    in_sla = [
        s <= SLA_TARGET_HOURS.get(t.get("priority") or "Medium", 48) * 3600
        for t, s in ((t, _solve_seconds(t)) for t in completed)
        if s is not None
    ]
    answered_in = [
        s <= RESPONSE_TARGET_HOURS * 3600
        for t, s in ((t, _rep_seconds(t)) for t in accepted)
        if s is not None
    ]
    return {
        "period": period,
        "accepted": len(accepted),
        "completed": len(completed),
        "pending": len(pending),
        "avgFirstResponseHrs": _hours(sum(responses) / len(responses)) if responses else None,
        "medianFirstResponseHrs": _hours(median(responses)) if responses else None,
        "fastestFirstResponseHrs": _hours(min(responses)) if responses else None,
        "avgSolveHrs": _hours(sum(solves) / len(solves)) if solves else None,
        "medianSolveHrs": _hours(median(solves)) if solves else None,
        "fastestSolveHrs": _hours(min(solves)) if solves else None,
        "responseDistribution": distribution(responses),
        "solveDistribution": distribution(solves),
        "series": _series(rows, agent_id, period),
        # workload: the pending side by current status (open / in progress /
        # waiting) — "where the agent's unfinished work sits"
        "workload": [
            {"status": status, "count": sum(1 for r in pending if r.get("status") == status)}
            for status in ("Open", "In Progress", "Waiting on Employee")
            if sum(1 for r in pending if r.get("status") == status)
        ],
        # resolution-by-category over the agent's completions
        "categories": [
            {
                "category": category,
                "resolved": sum(1 for r in completed if r.get("category") == category),
            }
            for category in sorted({r.get("category") or "Other" for r in completed})
        ],
        "slaWindowCompletions": len(in_sla),
        "slaWithinTarget": sum(in_sla),
        "slaComplianceRate": (round(100 * sum(in_sla) / len(in_sla)) if in_sla else None),
        "score": performance_score(
            accepted,
            completed,
            responses,
            answered_in,
            sum(in_sla) / len(in_sla) if in_sla else None,
        ),
    }


def performance_score(
    accepted: list[dict],
    completed: list[dict],
    responses: list[float],
    answered_in: list[bool],
    sla_share: float | None,
) -> int | None:
    """Single 0-100 composite over the window (weights in SCORE_WEIGHTS):
    SLA compliance share of completions + on-target first-response share +
    throughput share (completed / accepted). None when the window carries
    no accepted tickets (no basis, no fabricated number)."""
    if not accepted:
        return None
    sla_share = sla_share if sla_share is not None else 0.0
    response_share = sum(answered_in) / len(answered_in) if answered_in else 0.0
    throughput = min(1.0, len(completed) / max(1, len(accepted)))
    return round(
        100
        * (
            SCORE_WEIGHTS["sla"] * sla_share
            + SCORE_WEIGHTS["response"] * response_share
            + SCORE_WEIGHTS["throughput"] * throughput
        )
    )


def _buckets(period: str) -> tuple[float, list[str]]:
    """Chart buckets (age measured backwards from now): hourly for 24h,
    daily otherwise. Returns (bucket_width_seconds, labels oldest->newest)."""
    seconds = PERIODS[period]
    if period == "24h":
        width, count = 3600.0, 24
        labels = [f"-{h}h" for h in range(count, 0, -1)]
    else:
        count = seconds // 86400
        width = seconds / count
        labels = [f"-{d}d" for d in range(count, 0, -1)]
    return width, labels


def _series(rows: list[dict], agent_id: str, period: str) -> list[dict]:
    """Created/resolved counts per bucket + the bucket's average response
    and solve hours — the lines the drill-down draws (oldest bucket first)."""
    width, labels = _buckets(period)
    now = datetime.now(timezone.utc)
    out = []
    for i, label in enumerate(labels):
        lo_age = (len(labels) - 1 - i) * width
        hi_age = lo_age + width
        created_in = [
            r
            for r in rows
            if r.get("assignee_id") == agent_id
            and (a := _age_of(r.get("created_at"), now)) is not None
            and lo_age <= a < hi_age
        ]
        resolved_in = [
            r
            for r in rows
            if r.get("assignee_id") == agent_id
            and (a := _age_of(r.get("resolved_at"), now)) is not None
            and lo_age <= a < hi_age
        ]
        resp_in = [s for r in created_in if (s := _rep_seconds(r)) is not None]
        solve_in = [s for r in resolved_in if (s := _solve_seconds(r)) is not None]
        out.append(
            {
                "label": label,
                "created": len(created_in),
                "resolved": len(resolved_in),
                "avgResponseHrs": round(sum(resp_in) / len(resp_in) / 3600, 1) if resp_in else None,
                "avgSolveHrs": round(sum(solve_in) / len(solve_in) / 3600, 1) if solve_in else None,
            }
        )
    return out


def leaderboard(rows: list[dict], agents: list[dict], period: str, limit: int = 10) -> list[dict]:
    """Ranked by the composite performance score (0-100; SLA 40%, response
    30%, throughput 30% — SCORE_WEIGHTS), then completed count, then fastest
    average solve. Agents with zero accepted tickets in the window are
    omitted."""
    table = []
    for agent in agents:
        metrics = agent_metrics(rows, agent["id"], period)
        if metrics["accepted"] == 0 and metrics["completed"] == 0:
            continue
        table.append(
            {
                "agentId": agent["id"],
                "name": agent.get("name") or "",
                "email": agent.get("email") or "",
                "accepted": metrics["accepted"],
                "completed": metrics["completed"],
                "pending": metrics["pending"],
                "avgSolveHrs": metrics["avgSolveHrs"],
                "avgFirstResponseHrs": metrics["avgFirstResponseHrs"],
                "slaComplianceRate": metrics["slaComplianceRate"],
                "score": metrics["score"],
            }
        )
    table.sort(
        key=lambda m: (
            -(m["score"] if m["score"] is not None else -1),
            -m["completed"],
            m["avgSolveHrs"] if m["avgSolveHrs"] is not None else 10**9,
        )
    )
    return table[:limit]
