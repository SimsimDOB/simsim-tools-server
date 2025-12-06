from fastapi import APIRouter
from .v1.endpoints import summonses_count


api_router = APIRouter()
api_router.include_router(summonses_count.router)
