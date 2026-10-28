"""Console orchestration: composing scan + pure analytics.

Guards live in guards.py, math in analytics.py, SQL in repository.py; this
file is only the composition controller endpoints call into. Authorization
happens at the HTTP edge (controller) — EXCEPT the agent drill-down, where
the self-or-admin rule needs both ids right next to the query and is
enforced by analytics_service itself via require_self_or_admin.
"""

from fastapi import HTTPException

from app.admin import analytics
from app.admin.guards import require_self_or_admin
from app.admin.repository import AdminRepository
from app.repositories.user_repository import UserRepository


class AdminAnalyticsService:
    def __init__(self, repo: AdminRepository, users: UserRepository):
        self._repo = repo
        self._users = users

    def scan(self) -> list[dict]:
        """One ticket scan per console page (small org: the whole history
        fits; the pure rules aggregate in Python — portable + unit-tested)."""
        return self._repo.ticket_rows()

    def _period(self, period: str) -> None:
        if period not in analytics.PERIODS:
            raise HTTPException(
                status_code=422, detail=f"period must be one of: {', '.join(analytics.PERIODS)}"
            )

    def _windowed(self, window: str) -> list[dict]:
        """Rows created inside the analytics window ('all' = every row)."""
        if window not in ("all", *analytics.PERIODS):
            raise HTTPException(status_code=422, detail="Unknown window.")
        if window == "all":
            return self.scan()
        seconds = analytics.PERIODS[window]
        return [r for r in self.scan() if analytics._within(r.get("created_at"), seconds)]

    def overview(self, window: str) -> dict:
        """Org-wide KPI band + category/repetition breakdown for the window."""
        rows = self._windowed(window)
        return {
            "window": window,
            **analytics.overall_metrics(rows),
            "categories": analytics.category_breakdown(rows),
        }

    def leaderboard(self, period: str) -> list[dict]:
        self._period(period)
        rows = self.scan()
        return analytics.leaderboard(rows, self._users.agents(), period)

    def agent_drilldown(self, actor_id: str, target_id: str, period: str) -> dict:
        """Self-service for agents (their own numbers only), admin for any
        agent — one endpoint powers the console drill-down AND the HR
        dashboard's personal view."""
        require_self_or_admin(self._users, actor_id, target_id)
        self._period(period)
        target = self._users.get_by_id(target_id)
        if target.get("role") != "agent":
            raise HTTPException(
                status_code=422, detail="Performance metrics apply to agent accounts only."
            )
        return analytics.agent_metrics(self.scan(), target["id"], period)
