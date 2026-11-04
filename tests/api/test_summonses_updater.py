import asyncio
import datetime as dt
import inspect
import threading
import time
from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from simsim_tools_server.api.v1.endpoints import summonses_updater as endpoint
from simsim_tools_server.services import summonses_updater_service as svc

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
URL = "/api/v1/summonses-updater"
D = dt.datetime(2024, 7, 31)


def _xlsx(rows, headers=("Number", "Date of Offense", "Results of Hearing")):
    wb = Workbook()
    ws = wb.active
    ws.cell(1, 2, headers[0])
    ws.cell(1, 7, headers[1])
    ws.cell(1, 17, headers[2])
    for r, (n, d, q) in enumerate(rows, start=2):
        ws.cell(r, 2, n)
        ws.cell(r, 7, d)
        ws.cell(r, 17, q)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, data, name="avps.xlsx"):
    return client.post(URL, files=[("file", (name, data, XLSX))])


def _wait(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snap = client.get(f"{URL}/{job_id}").json()
        if snap["status"] != "running":
            return snap
        time.sleep(0.02)
    pytest.fail("job did not finish in time")


class FakeEcb:
    """Stands in for EcbClient; `answer` maps a number to a LookupResult."""

    answer = staticmethod(lambda number: svc.LookupResult(False, "", ""))
    gate: threading.Event | None = None

    def start_session(self):
        pass

    def lookup(self, number):
        if self.gate is not None:
            self.gate.wait(5)
        return type(self).answer(number)

    def close(self):
        pass


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(endpoint, "EcbClient", FakeEcb)
    monkeypatch.setattr(svc, "PAUSE_SECONDS", 0)
    FakeEcb.answer = staticmethod(lambda number: svc.LookupResult(False, "", ""))
    FakeEcb.gate = None
    yield FakeEcb
    if FakeEcb.gate is not None:
        FakeEcb.gate.set()


def test_start_poll_download(client: TestClient, fake):
    fake.answer = staticmethod(
        lambda n: (
            svc.LookupResult(True, "RESCHEDULED", "DEFAULTED")
            if n == "0213681142"
            else svc.LookupResult(False, "", "")
        )
    )
    rows = [("213681142", D, None), ("213681143", D, None), ("213681144", D, "Paid")]
    response = _upload(client, _xlsx(rows))
    assert response.status_code == 202
    body = response.json()
    assert body["total_rows"] == 3
    assert body["filename"] == "avps.xlsx"
    assert body["sheet"] == "Sheet"
    job_id = body["job_id"]

    snap = _wait(client, job_id)
    assert snap["status"] == "done"
    assert snap["counts"] == {
        "looked_up": 2,
        "changed": 1,
        "no_record": 1,
        "skipped": 1,
        "errors": 0,
    }
    assert snap["changes"] == [
        {"row": 2, "number": "0213681142", "before": None, "after": "Defaulted"}
    ]
    assert (
        client.get(f"{URL}/{job_id}", params={"after": snap["next"]}).json()["log"]
        == []
    )

    download = client.get(f"{URL}/{job_id}/file")
    assert download.status_code == 200
    assert download.headers["content-type"] == XLSX
    assert 'filename="avps.xlsx"' in download.headers["content-disposition"]
    ws = load_workbook(BytesIO(download.content)).active
    assert [ws.cell(r, 17).value for r in (2, 3, 4)] == [
        "Defaulted",
        "No Record Available",
        "Paid",
    ]


def test_rejects_wrong_extension(client: TestClient):
    response = _upload(client, b"x", name="avps.xls")
    assert response.status_code == 400
    assert response.json()["detail"] == "Only .xlsx files are accepted"


def test_rejects_too_large(client: TestClient, monkeypatch):
    monkeypatch.setattr(svc, "MAX_UPLOAD_BYTES", 10)
    response = _upload(client, _xlsx([]))
    assert response.status_code == 400
    assert response.json()["detail"] == "File is larger than 25 MB"


def test_rejects_wrong_headers(client: TestClient):
    response = _upload(client, _xlsx([], headers=("Name", "When", "Outcome")))
    assert response.status_code == 400
    assert "B1='Name'" in response.json()["detail"]


def test_rejects_unreadable_workbook(client: TestClient):
    response = _upload(client, b"nope")
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not read the workbook"


def test_download_while_running_is_409(client: TestClient, fake):
    fake.gate = threading.Event()
    job_id = _upload(client, _xlsx([("213681142", D, None)])).json()["job_id"]
    assert client.get(f"{URL}/{job_id}/file").status_code == 409
    fake.gate.set()
    assert _wait(client, job_id)["status"] == "done"


def test_cancel_mid_run(client: TestClient, fake):
    fake.gate = threading.Event()
    rows = [("213681142", D, None), ("213681143", D, None)]
    job_id = _upload(client, _xlsx(rows)).json()["job_id"]
    response = client.delete(f"{URL}/{job_id}")
    assert response.status_code == 200
    fake.gate.set()
    snap = _wait(client, job_id)
    assert snap["status"] == "cancelled"
    assert snap["counts"]["looked_up"] == 1
    assert client.get(f"{URL}/{job_id}/file").status_code == 200


def test_cancel_after_finish_is_noop(client: TestClient, fake):
    # Review Focus 5
    job_id = _upload(client, _xlsx([("213681142", D, None)])).json()["job_id"]
    assert _wait(client, job_id)["status"] == "done"
    response = client.delete(f"{URL}/{job_id}")
    assert response.status_code == 200
    assert response.json() == {"status": "done"}
    assert client.get(f"{URL}/{job_id}/file").status_code == 200


def test_five_errors_fail_job(client: TestClient, fake):
    def boom(_number):
        raise RuntimeError("down")

    fake.answer = staticmethod(boom)
    rows = [(f"21368114{i}", D, None) for i in range(6)]
    job_id = _upload(client, _xlsx(rows)).json()["job_id"]
    snap = _wait(client, job_id)
    assert snap["status"] == "failed"
    assert snap["error"] == svc.SITE_DOWN_MESSAGE
    assert client.get(f"{URL}/{job_id}/file").status_code == 404


def test_unknown_job_is_404(client: TestClient):
    assert client.get(f"{URL}/nope").status_code == 404
    assert client.get(f"{URL}/nope/file").status_code == 404
    assert client.delete(f"{URL}/nope").status_code == 404


def test_sweep_drops_old_finished_jobs(monkeypatch):
    wb = Workbook()
    now = dt.datetime.now(dt.UTC)
    old = svc.Job(id="old", filename="a", workbook=wb, sheet=wb.active, total_rows=0)
    old.status = "done"
    old.finished_at = now - dt.timedelta(minutes=61)
    fresh = svc.Job(
        id="fresh", filename="a", workbook=wb, sheet=wb.active, total_rows=0
    )
    fresh.status = "done"
    fresh.finished_at = now - dt.timedelta(minutes=59)
    running = svc.Job(
        id="run", filename="a", workbook=wb, sheet=wb.active, total_rows=0
    )
    monkeypatch.setattr(endpoint, "_jobs", {"old": old, "fresh": fresh, "run": running})
    endpoint._sweep(now)
    assert set(endpoint._jobs) == {"fresh", "run"}


def test_download_non_ascii_filename(client: TestClient, fake):
    job_id = _upload(client, _xlsx([]), name="AVPS – é 传票.xlsx").json()["job_id"]
    assert _wait(client, job_id)["status"] == "done"
    download = client.get(f"{URL}/{job_id}/file")
    assert download.status_code == 200
    disposition = download.headers["content-disposition"]
    assert "filename*=UTF-8''AVPS%20%E2%80%93%20%C3%A9%20%E4%BC%A0%E7%A5%A8.xlsx" in (
        disposition
    )


def test_poll_after_past_end_over_http(client: TestClient, fake):
    # Review Focus 4, over HTTP.
    job_id = _upload(client, _xlsx([("213681142", D, None)])).json()["job_id"]
    _wait(client, job_id)
    snap = client.get(f"{URL}/{job_id}", params={"after": 99}).json()
    assert snap["log"] == []
    assert snap["next"] == 1


def test_start_session_failure_is_site_down(client: TestClient, fake):
    def refuse(self):
        raise httpx.ConnectError("[Errno 111] Connection refused")

    fake.start_session = refuse
    job_id = _upload(client, _xlsx([("213681142", D, None)])).json()["job_id"]
    snap = _wait(client, job_id)
    assert snap["status"] == "failed"
    assert snap["error"] == svc.SITE_DOWN_MESSAGE


def test_upload_parses_workbook_off_the_event_loop(
    client: TestClient, fake, monkeypatch
):
    seen = {}
    real = endpoint.load_workbook_bytes

    def spy(data):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return real(data)

    monkeypatch.setattr(endpoint, "load_workbook_bytes", spy)
    assert _upload(client, _xlsx([])).status_code == 202
    assert seen["on_loop"] is False


def test_status_endpoint_runs_in_threadpool():
    # snapshot() takes a threading.Lock; a coroutine handler would block the loop.
    assert not inspect.iscoroutinefunction(endpoint.summonses_update_status)
