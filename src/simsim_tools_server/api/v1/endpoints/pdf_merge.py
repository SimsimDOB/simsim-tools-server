from fastapi import APIRouter, HTTPException, File, UploadFile, status
from tempfile import NamedTemporaryFile
import logging
from pathlib import Path

from simsim_tools_server.services.pdf_merge_service import merge_pdfs

router = APIRouter()


@router.post("/pdf-merge")
async def pdf_merge(files: list[UploadFile] = File(...)):
    try:
        merged_pdf_bytes = await merge_pdfs(files)

        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(merged_pdf_bytes.getvalue())
            temp_file.flush()
            temp_file.seek(0)
            temp_path = temp_file.name
            temp_name = Path(temp_path).stem
            logging.info(f"Merged PDF saved temporarily at: {temp_path}")

        return {"filename": temp_name}
    except Exception as e:
        logging.error(f"Failed to merge PDFs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
