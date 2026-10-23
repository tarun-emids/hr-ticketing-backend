"""Knowledge base endpoints — thin HTTP face over KbService.

The controller validates only what is cheapest at the edge (query param
shape); everything content-sensitive — viewer existence, role pools,
403/404 gates, signing — lives in the service.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response

from app.config import SIGNED_URL_TTL
from app.deps import get_kb_service, get_kb_storage
from app.repositories.kb_storage import KbStorageRepository
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


@router.get("/{slug}/file")
def file_url(
    slug: str,
    viewerId: str,
    request: Request,
    ttl: int = SIGNED_URL_TTL,
    download: bool = False,
    svc: KbService = Depends(get_kb_service),
):
    """GET /kb/{slug}/file — signed PDF URL. download=true returns an
    attachment link that proposes the policy title as the save-as name."""
    result = svc.file_url(slug, viewerId, ttl, download=download)
    result["url"] = f"{str(request.base_url).rstrip('/')}{result['url']}"
    return result


@router.get("/pdf/{slug}", include_in_schema=False)
def download_pdf(
    slug: str,
    expires: int,
    download: bool,
    sig: str,
    storage: KbStorageRepository = Depends(get_kb_storage),
):
    """Serve a knowledge-base PDF only with a valid signed URL."""
    data, filename, as_attachment = storage.read_signed(slug, expires, download, sig)
    disposition = "attachment" if as_attachment else "inline"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}"},
    )
