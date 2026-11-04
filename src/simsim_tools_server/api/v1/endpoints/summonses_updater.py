import datetime as dt
import logging
import secrets
import threading
from io import BytesIO

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from simsim_tools_server.services import summonses_updater_service as svc
from simsim_tools_server.services.summonses_updater_service import (
    EcbClient,
    Job,
    load_workbook_bytes,
    run_job,
)

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
RETENTION = dt.timedelta(minutes=60)

# In-memory job registry: one uvicorn process, jobs do not survive a restart.
_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _sweep(now: dt.datetime) -> None:
    """Drop jobs that finished more than RETENTION ago."""
    with _jobs_lock:
        for job_id, job in list(_jobs.items()):
            if job.finished_at is not None and now - job.finished_at > RETENTION:
                del _jobs[job_id]


def _launch(job: Job) -> None:
    def work() -> None:
        ecb = EcbClient()
        try:
            ecb.start_session()
            run_job(job, ecb.lookup)
        except Exception as e:
            logging.error(f"Summonses job {job.id} could not start: {e}")
            job._finish("failed", str(e))
        finally:
            ecb.close()
        logging.info(f"Summonses job {job.id} {job.status}: {job.counts}")

    threading.Thread(target=work, name=f"summonses-{job.id}", daemon=True).start()


def _get_job(job_id: str) -> Job:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown job")
    return job


@router.post("/summonses-updater", status_code=status.HTTP_202_ACCEPTED)
async def start_summonses_update(file: UploadFile = File(...)):
    filename = file.filename or "workbook.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx files are accepted",
        )
    data = await file.read()
    if len(data) > svc.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is larger than 25 MB",
        )
    try:
        workbook, sheet = load_workbook_bytes(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    now = dt.datetime.now(dt.UTC)
    _sweep(now)
    job = Job(
        id=secrets.token_urlsafe(8),
        filename=filename,
        workbook=workbook,
        sheet=sheet,
        total_rows=sheet.max_row - 1,
    )
    with _jobs_lock:
        _jobs[job.id] = job
    logging.info(f"Summonses job {job.id} started: {filename}, {job.total_rows} rows")
    _launch(job)
    return {
        "job_id": job.id,
        "total_rows": job.total_rows,
        "filename": filename,
        "sheet": sheet.title,
    }


@router.get("/summonses-updater/{job_id}")
async def summonses_update_status(job_id: str, after: int = 0):
    return _get_job(job_id).snapshot(after)


@router.get("/summonses-updater/{job_id}/file")
async def summonses_update_file(job_id: str):
    job = _get_job(job_id)
    if job.status == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Job is still running"
        )
    if job.file_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No file for this job"
        )
    return StreamingResponse(
        BytesIO(job.file_bytes),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{job.filename}"'},
    )


@router.delete("/summonses-updater/{job_id}")
async def cancel_summonses_update(job_id: str):
    job = _get_job(job_id)
    job.request_cancel()
    return {"status": job.status}
