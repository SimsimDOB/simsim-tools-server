from fastapi import APIRouter, HTTPException, File, UploadFile
from typing import List

from simsim_tools_server.services.summonses_count_service import count_summonses

router = APIRouter()


@router.post("/v1/summonses-count")
async def summonses_count(pdfs: List[UploadFile] = File(...)):
    try:
        # count = len(pdfs)
        # return {"summonses_count": count}

        total_count = 0
        details = []

        for pdf in pdfs:
            pdf_bytes = await pdf.read()
            count, removed, pages_str = count_summonses(pdf_bytes)
            total_count += count
            details.append(
                {
                    "filename": pdf.filename,
                    "count": count,
                    "removed": removed,
                    "pages": pages_str,
                }
            )
        return {"total_count": total_count, "details": details}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
