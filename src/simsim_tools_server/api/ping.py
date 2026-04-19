from fastapi import APIRouter, Response, status

router = APIRouter()


@router.get("/ping")
async def ping(response: Response):
    response.status_code = status.HTTP_200_OK
    return
