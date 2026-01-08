from fastapi import APIRouter
from . import ping
from .v1.endpoints import summonses_count, pdf_merge, download


api_router = APIRouter(prefix="/api")
api_router.include_router(ping.router)


api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(summonses_count.router)
api_v1_router.include_router(pdf_merge.router)
api_v1_router.include_router(download.router)
