from fastapi import APIRouter
from .v1.endpoints import summonses_count, pdf_merge, download


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(summonses_count.router)
api_router.include_router(pdf_merge.router)
api_router.include_router(download.router)