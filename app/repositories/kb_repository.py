"""Knowledge base document metadata (public.kb_documents).

Metadata only — the PDF bytes live in the private `knowledge-base` storage
bucket (see KbStorageRepository). Repositories stay role-agnostic: callers
pass the audience pool(s) the viewer may read, which the KbService derives
from the viewer's role resolved from public.users.
"""
from typing import Optional, Sequence

from app.repositories.base import SupabaseRepository, first_of, rows_of


class KbRepository(SupabaseRepository):
    TABLE_NAME = "kb_documents"

    def list_by_audiences(
        self, audiences: Sequence[str], limit: int = 200
    ) -> list[dict]:
        """All documents in the viewer's pools, newest-refresh first."""
        if not audiences:
            return []
        return rows_of(
            self.table()
            .select("*")
            .in_("audience", list(audiences))
            .order("updated_at", desc=True)
            .limit(limit)
        )

    def get_by_slug(self, slug: str) -> Optional[dict]:
        return first_of(self.table().select("*").eq("slug", slug).limit(1))
