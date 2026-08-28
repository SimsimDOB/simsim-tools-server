import logging
import traceback

from fastapi import APIRouter, File, HTTPException, UploadFile

from simsim_tools_server.services.multi_summonses_count_service import (
    count_multi_summonses,
)

# Twin file: endpoints/summonses_count.py. This handler is a deliberate
# duplicate of it; apply any shared-logic fix to both files.

router = APIRouter()


@router.post("/multi-summonses-count")
async def multi_summonses_count(pdfs: list[UploadFile] = File(...)):
    try:
        total_count = 0
        details = []

        for pdf in pdfs:
            try:
                count, removed, pages_str = count_multi_summonses(pdf)
                total_count += count
                details.append(
                    {
                        "filename": pdf.filename,
                        "count": count,
                        "removed_count": removed,
                        "removed_pages": pages_str,
                    }
                )
            except Exception as error:
                logging.error(f"Error processing file {pdf.filename}: {error}")
                logging.error(traceback.format_exc())

                details.append(
                    {
                        "filename": pdf.filename,
                        "error": str(error),
                    }
                )

        return {"total_count": total_count, "details": details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
