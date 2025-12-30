from fastapi import APIRouter, HTTPException, File, UploadFile
import logging
import traceback

from simsim_tools_server.services.summonses_count_service import count_summonses

router = APIRouter()


@router.post("/summonses-count")
async def summonses_count(pdfs: list[UploadFile] = File(...)):
    try:
        total_count = 0
        details = []

        for pdf in pdfs:
            try:
                count, removed, pages_str = count_summonses(pdf)
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
