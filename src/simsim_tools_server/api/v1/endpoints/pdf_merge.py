from fastapi import APIRouter, HTTPException, File, UploadFile, status
from fastapi.responses import StreamingResponse
import logging

from simsim_tools_server.services.pdf_merge_service import merge_pdfs


router = APIRouter()


@router.post("/pdf-merge")
async def pdf_merge(files: list[UploadFile] = File(...)):
    try:
        merged_pdf_bytes = await merge_pdfs(files)

        return StreamingResponse(
            merged_pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=merged.pdf"},
        )
    except Exception as e:
        logging.error(f"Failed to merge PDFs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
