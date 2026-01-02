from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pathlib import Path
from tempfile import gettempdir
import logging


router = APIRouter()


@router.get("/download/{filename}")
async def download(filename: str):
    file_path = Path(gettempdir()) / f"{filename}.pdf"
    logging.info(f"Attempting to download file at: {file_path}")

    if not file_path.exists():
        logging.error(f"File not found: {file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    return FileResponse(
        path=file_path, filename=file_path.name, media_type="application/pdf"
    )
