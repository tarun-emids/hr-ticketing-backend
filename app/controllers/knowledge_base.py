"""Knowledge base endpoints — thin HTTP face over KbService.

The controller validates only what is cheapest at the edge (query param
shape); everything content-sensitive — viewer existence, role pools,
403/404 gates — lives in the service. The file endpoint streams the PDF
straight from PostgreSQL behind the same gate, so the browser gets an
always-fresh permission check instead of a long-signed URL.
"""

from fastapi import APIRouter, Depends, Response

from app.deps import get_kb_service
from app.services.kb_service import KbService

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("")
def list_or_search(
    viewerId: str,
    q: str = "",
    svc: KbService = Depends(get_kb_service),
):
    """GET /kb — documents the viewer may read; with q, top scored matches."""
    return svc.list_or_search(viewerId, q)


@router.get("/popular")
def popular(viewerId: str, svc: KbService = Depends(get_kb_service)):
    """GET /kb/popular — latest 8 docs in the viewer's pools (dashboard strip)."""
    return svc.popular(viewerId)


@router.get("/{slug}")
def get_document(
    slug: str,
    viewerId: str,
    svc: KbService = Depends(get_kb_service),
):
    """GET /kb/{slug} — metadata for one document (403 out of pool, 404 unknown)."""
    return svc.get_document(slug, viewerId)


@router.get("/{slug}/file", name="kb_document_file")
def document_file(
    slug: str,
    viewerId: str,
    download: bool = False,
    svc: KbService = Depends(get_kb_service),
):
    """GET /kb/{slug}/file — stream the PDF behind the visibility gate.
    download=true marks the response as an attachment whose save dialog
    proposes the policy title; the default renders inline (iframe / new tab).
    """
    result = svc.file_get(slug, viewerId, download=download)
    disposition = "attachment" if download else "inline"
    return Response(
        content=result["data"],
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{result["filename"]}"',
            "Cache-Control": "no-store",
        },
    )
