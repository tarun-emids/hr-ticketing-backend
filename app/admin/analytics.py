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

Percentiles are computed on sorted seconds lists in Python (the offline
SQLite double has no percentile aggregation).
"""

import re
from datetime import datetime, timezone
from statistics import median

PERIODS: dict[str, float] = {
    "24h": 24 * 3600,
    "7d": 7 * 24 * 3600,
    "30d": 30 * 24 * 3600,
}
DEFAULT_PERIOD = "7d"


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
        status: 0
        for status in ("Open", "In Progress", "Waiting on Employee", "Resolved", "Closed")
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
    """Cluster key for repetitive tickets: lowercased, ticket refs/punctuation
    stripped, whitespace collapsed."""
    cleaned = re.sub(r"tkt-?\d+", "", (subject or "").lower())
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


# -- per-agent picture ----------------------------------------------------------


def agent_window_rows(rows: list[dict], agent_id: str, period: str) -> dict:
    """The groups behind the counters (created/resolved basis)."""
    seconds = period_seconds(period)
    accepted = [
        r for r in rows if r.get("assignee_id") == agent_id and _within(r.get("created_at"), seconds)
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
    }


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
    hours — the lines the drill-down draws (oldest bucket first)."""
    width, labels = _buckets(period)
    now = datetime.now(timezone.utc)
    out = []
    for i, label in enumerate(labels):
        lo_age = (len(labels) - 1 - i) * width
        hi_age = lo_age + width
        created_in = [
            r for r in rows
            if r.get("assignee_id") == agent_id
            and (a := _age_of(r.get("created_at"), now)) is not None
            and lo_age <= a < hi_age
        ]
        resolved_in = [
            r for r in rows
            if r.get("assignee_id") == agent_id
            and (a := _age_of(r.get("resolved_at"), now)) is not None
            and lo_age <= a < hi_age
        ]
        resp_in = [s for r in created_in if (s := _rep_seconds(r)) is not None]
        out.append({
            "label": label,
            "created": len(created_in),
            "resolved": len(resolved_in),
            "avgResponseHrs": round(sum(resp_in) / len(resp_in) / 3600, 1) if resp_in else None,
        })
    return out


def leaderboard(
    rows: list[dict], agents: list[dict], period: str, limit: int = 10
) -> list[dict]:
    """Top performers first (completed desc, then fastest solve). Agents with
    zero accepted tickets in the window are omitted."""
    table = []
    for agent in agents:
        metrics = agent_metrics(rows, agent["id"], period)
        if metrics["accepted"] == 0 and metrics["completed"] == 0:
            continue
        table.append({
            "agentId": agent["id"],
            "name": agent.get("name") or "",
            "email": agent.get("email") or "",
            "accepted": metrics["accepted"],
            "completed": metrics["completed"],
            "pending": metrics["pending"],
            "avgSolveHrs": metrics["avgSolveHrs"],
            "avgFirstResponseHrs": metrics["avgFirstResponseHrs"],
        })
    table.sort(key=lambda m: (-m["completed"], m["avgSolveHrs"] or 10**9))
    return table[:limit]
