# Summonses Updater Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A simsim-tools page that takes the AVPS workbook, looks every candidate summons up on the NYC ECB ticket finder with live progress, and hands back the updated workbook.

**Architecture:** Backend: one service module (pure row/number/result functions, an `httpx` ECB client, a `Job` dataclass and the row loop) plus one endpoint module holding an in-memory job registry and four routes; the loop runs in a daemon thread. Frontend: one composable over the shared axios instance and one page component that polls once a second. Backend ships and is probed from production before the frontend is built.

**Tech Stack:** FastAPI, openpyxl, httpx, beautifulsoup4, pytest (backend). Vue 3 + TypeScript strict, Tailwind v4, axios, PrimeIcons (frontend).

**Spec:** `docs/superpowers/specs/2026-11-04-summonses-updater-design.md` (this repo). Read it first; this plan argues from it.

## Global Constraints

- Backend worktree: `/home/fernando-yu/Documents/sim/simsim-tools/worktrees/simsim-tools-server/feat/summonses-updater` (exists, branch `feat/summonses-updater`). Frontend worktree is created in Task 10 at `/home/fernando-yu/Documents/sim/simsim-tools/worktrees/simsim-tools/feat/summonses-updater`. Never edit the root repos `simsim-tools/` or `simsim-tools-server/`.
- Python ≥3.13; ruff `E`,`F`,`I`, line length 88, double quotes; CI runs `ruff format --check` and `ruff check` only. Pre-commit runs ruff on commit.
- Dependencies go in `[project] dependencies` as `"pkg (>=x,<y)"` (use `poetry add`, which writes that form).
- Routes: kebab-case paths under `/api/v1`; endpoint module exposes `router = APIRouter()`; one `include_router` line in `api/router.py`.
- Logging: root `logging.info/warning/error(f"...")`, traceback on errors.
- Frontend: TypeScript strict with `noUnusedLocals`, `noUnusedParameters`, `erasableSyntaxOnly` (no `enum`). `@/` → `src/`. Build gate is `deno task build` (`vue-tsc -b && vite build`). No PrimeVue components; Tailwind + Nord hex values, `font-['MakoP']`, PrimeIcons `pi pi-*`.
- Exact strings from the spec: skip reasons `empty`, `bad date`, `before 2021`, `has result`, `invalid number`; statuses `running`/`done`/`cancelled`/`failed`; log kinds `skipped`/`changed`/`same`/`no_record`/`error`/`invalid`/`bad_date`; failure message `The ECB site is not responding`; pause 3 s; 5 consecutive errors; retention 60 min; upload limit 25 MB; `MIN_YEAR = 2021`.
- Commit messages: conventional, scope `summonses-updater`, e.g. `feat(summonses-updater): ...`, ending with the attribution trailer the session provides.

## Review Focus

Inputs the spec implies but does not spell out, each pinned by a test in the owning task:

1. Column B holds an Excel number, not text (`213681142` as `int`) → normalizes to `0213681142` and is looked up, as `str()` in the script did. (Task 2)
2. Column G holds a text date like `"2024-07-31"` → `bad date`, skipped and listed under problems, not crashed. (Task 2)
3. Column Q holds a non-string (a number) → counts as `has result`; no `.strip()` crash. (Task 2)
4. `GET …/{job_id}?after=N` with `N` past the end of the log → empty `log`, `next` equals the log length, 200. (Task 6 at the model, Task 7 over HTTP)
5. `DELETE …/{job_id}` on a job that already finished → 200, status unchanged, file still downloadable. (Task 7)

---

## Part A — Backend

### Task 1: Dependencies and module skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/simsim_tools_server/services/summonses_updater_service.py` (empty module docstring)
- Create: `tests/services/test_summonses_updater_service.py` (empty)
- Create: `tests/fixtures/__init__.py` (empty), `tests/api/test_summonses_updater.py` (empty)

**Interfaces:**
- Produces: a worktree where `poetry run pytest` and `poetry run ruff check` pass with `openpyxl`, `httpx`, `beautifulsoup4` importable at runtime.

- [ ] **Step 1: Install the worktree's venv**

Run (in the backend worktree): `poetry install`
Expected: ends with "Installing the current project: simsim-tools-server".

- [ ] **Step 2: Add runtime deps, move httpx out of dev**

Run: `poetry remove --group dev httpx && poetry add "openpyxl>=3.1,<4" "httpx>=0.28,<0.29" "beautifulsoup4>=4.13,<5"`
Expected: `pyproject.toml` `[project] dependencies` gains three `"pkg (>=x,<y)"` lines; `[tool.poetry.group.dev.dependencies]` no longer lists httpx; `poetry.lock` updated.

- [ ] **Step 3: Create the empty modules and run the suite**

Run: `poetry run pytest -q && poetry run ruff check . && poetry run ruff format --check .`
Expected: existing tests pass, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml poetry.lock src/simsim_tools_server/services/summonses_updater_service.py tests/
git commit -m "build(summonses-updater): add openpyxl, httpx, beautifulsoup4"
```

### Task 2: Row decision — number normalization and skip reasons

**Files:**
- Modify: `src/simsim_tools_server/services/summonses_updater_service.py`
- Test: `tests/services/test_summonses_updater_service.py`

**Interfaces:**
- Produces:
  - `MIN_YEAR: int = 2021`
  - `CANDIDATE_RESULTS: frozenset[str] = frozenset({"", "adjourned", "new issuance", "rescheduled", "no record available"})`
  - `normalize_number(value: object) -> str` — `str(value)` with spaces removed; 9 chars without `E` → prefixed `0`; 10 chars containing `E` → `E` replaced by `0`. No other change.
  - `is_valid_number(number: str) -> bool` — `len == 10 and startswith("0")`.
  - `@dataclass(frozen=True) class RowDecision: skip: str | None; number: str` — `skip` is one of the five spec reasons or `None` (look it up); `number` is the normalized number (`""` when B is empty).
  - `decide_row(number: object, date: object, result: object) -> RowDecision` — applies spec "Row logic" steps 1–6 in that order. A `datetime.datetime` or `datetime.date` is a readable date; anything else (incl. `None`, `datetime.time`, `str`) is `bad date`. `result` is compared as `str(result).strip().lower()` with `None` → `""`.

- [ ] **Step 1: Write the failing tests**

```python
import datetime as dt
import pytest
from simsim_tools_server.services.summonses_updater_service import (
    RowDecision, decide_row, is_valid_number, normalize_number,
)

@pytest.mark.parametrize(("value", "expected"), [
    ("213681142", "0213681142"),
    ("E213681142", "0213681142"),
    (" 0213 681142 ", "0213681142"),
    (213681142, "0213681142"),          # Review Focus 1: int cell
    ("0213681142", "0213681142"),
    ("1234567890", "1234567890"),       # untouched, invalid later
    ("E12345678", "E12345678"),         # 9 chars with E: untouched
])
def test_normalize_number(value, expected):
    assert normalize_number(value) == expected

@pytest.mark.parametrize(("number", "expected"), [
    ("0213681142", True), ("1234567890", False), ("021368114", False), ("E12345678", False),
])
def test_is_valid_number(number, expected):
    assert is_valid_number(number) is expected

D = dt.datetime(2024, 7, 31)

@pytest.mark.parametrize(("number", "date", "result", "expected"), [
    (None, D, None, RowDecision("empty", "")),
    ("", D, None, RowDecision("empty", "")),
    ("213681142", dt.time(4, 48), None, RowDecision("bad date", "0213681142")),
    ("213681142", "2024-07-31", None, RowDecision("bad date", "0213681142")),  # Review Focus 2
    ("213681142", None, None, RowDecision("bad date", "0213681142")),
    ("213681142", dt.datetime(2020, 12, 31), None, RowDecision("before 2021", "0213681142")),
    ("213681142", D, "Defaulted", RowDecision("has result", "0213681142")),
    ("213681142", D, 5, RowDecision("has result", "0213681142")),            # Review Focus 3
    ("213681142", D, "Adjourned ", RowDecision(None, "0213681142")),
    ("213681142", D, "NEW ISSUANCE", RowDecision(None, "0213681142")),
    ("213681142", D, "rescheduled", RowDecision(None, "0213681142")),
    ("213681142", D, "No Record Available", RowDecision(None, "0213681142")),
    ("213681142", D, None, RowDecision(None, "0213681142")),
    ("213681142", dt.date(2021, 1, 1), "", RowDecision(None, "0213681142")),
    ("1234567890", D, None, RowDecision("invalid number", "1234567890")),
    ("E12345678", D, None, RowDecision("invalid number", "E12345678")),
])
def test_decide_row(number, date, result, expected):
    assert decide_row(number, date, result) == expected
```

- [ ] **Step 2: Run to verify they fail**

Run: `poetry run pytest tests/services/test_summonses_updater_service.py -q`
Expected: FAIL, `ImportError` on the names.

- [ ] **Step 3: Implement the constants, `normalize_number`, `is_valid_number`, `RowDecision`, `decide_row`**

Order inside `decide_row`: empty → bad date → before 2021 → has result → normalize → invalid number → `RowDecision(None, number)`. Note `bool` is a subclass of `int`, irrelevant here; `datetime.datetime` is a subclass of `datetime.date`, so one `isinstance(date, dt.date)` check covers both and excludes `dt.time`.

- [ ] **Step 4: Run to verify they pass**

Run: `poetry run pytest tests/services/test_summonses_updater_service.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/simsim_tools_server/services/summonses_updater_service.py tests/services/test_summonses_updater_service.py
git commit -m "feat(summonses-updater): row decision and number normalization"
```

### Task 3: Result mapping

**Files:**
- Modify: `src/simsim_tools_server/services/summonses_updater_service.py`
- Test: `tests/services/test_summonses_updater_service.py`

**Interfaces:**
- Produces: `map_result(status: str, hearing_result: str) -> str | None` — the value to write to Q, or `None` to leave the cell unchanged. Inputs are already stripped.

- [ ] **Step 1: Write the failing tests**

```python
from simsim_tools_server.services.summonses_updater_service import map_result

@pytest.mark.parametrize(("status", "hearing", "expected"), [
    ("PAID IN FULL", "", "Paid before Hearing"),
    ("PAID IN FULL", "DEFAULTED", "Paid before Hearing"),
    ("RESCHEDULED", "DEFAULTED", "Defaulted"),
    ("HEARING HELD", "SETTL/IN-VIOLATION", "In Violation"),
    ("HEARING HELD", "ADMIN. DISMISSAL", "Admin. dismissal"),   # capitalize(), kept on purpose
    ("SETTL/IN-VIOLATION", "", "In Violation"),
    ("NEW ISSUANCE", "", "New Issuance"),
    ("RESCHEDULED", "", "Adjourned"),
    ("HEARING SCHEDULED", "", None),
])
def test_map_result(status, hearing, expected):
    assert map_result(status, hearing) == expected
```

- [ ] **Step 2: Run to verify it fails** — `poetry run pytest tests/services/test_summonses_updater_service.py -q -k map_result`; expected `ImportError`.

- [ ] **Step 3: Implement `map_result`** following spec step 7 literally (the `elif hearing_result:` branch uses `str.capitalize()`).

- [ ] **Step 4: Run to verify it passes** — same command, all PASS.

- [ ] **Step 5: Commit** — `git commit -m "feat(summonses-updater): map ECB status to hearing result"`

### Task 4: ECB result-page parser with scrubbed fixtures

**Files:**
- Create: `tests/fixtures/ecb_found.html`, `tests/fixtures/ecb_no_record.html`, `tests/fixtures/ecb_no_table.html`
- Modify: `src/simsim_tools_server/services/summonses_updater_service.py`
- Test: `tests/services/test_summonses_updater_service.py`

**Interfaces:**
- Produces:
  - `class SessionLostError(Exception)` — raised when the page has no `table#vioContent`.
  - `@dataclass(frozen=True) class LookupResult: found: bool; status: str; hearing_result: str` — `found=False` means `No Record Available` (status/hearing empty).
  - `parse_result_page(html: str) -> LookupResult`.

- [ ] **Step 1: Create the fixtures**

Raw captures from 2026-11-04 are at
`/tmp/claude-1000/-home-fernando-yu-Documents-sim/d2b2e70a-dc73-4b96-a0aa-c01243ad2cfa/scratchpad/ecb.RUpM/result.html` (found: status `RESCHEDULED`, hearing result `DEFAULTED`) and `.../no_record.html`. If that directory is gone, recapture:

```bash
curl -sL -c c.txt -A "Mozilla/5.0" "http://a820-ecbticketfinder.nyc.gov/searchHome.action" -o /dev/null
curl -sL -b c.txt -A "Mozilla/5.0" -X POST "http://a820-ecbticketfinder.nyc.gov/getViolationbyID.action" \
  --data-urlencode "searchViolationObject.violationNo=0213681142" \
  --data-urlencode "searchViolationObject.searchType=violationNumber" \
  --data-urlencode "submit=  Search  " -o result.html   # use 0000000001 for no_record.html
```

Copy each into `tests/fixtures/` and **scrub**: replace the summons number with `0000000000`, the respondent name with `RESPONDENT NAME`, the inspection location and any address with `1 MAIN STREET NEW YORK NY 10001`, the balance with `$0.00`. Keep every tag, id and class unchanged. Add as the first line: `<!-- Captured from the ECB ticket finder on 2026-11-04 and scrubbed: names, addresses and the summons number are placeholders. -->`. `ecb_no_table.html` is a minimal `<html><body><p>Session expired</p></body></html>`.

- [ ] **Step 2: Write the failing tests**

```python
from pathlib import Path
from simsim_tools_server.services.summonses_updater_service import (
    LookupResult, SessionLostError, parse_result_page,
)
FIXTURES = Path(__file__).parent.parent / "fixtures"

def test_parse_found_page():
    html = (FIXTURES / "ecb_found.html").read_text()
    assert parse_result_page(html) == LookupResult(True, "RESCHEDULED", "DEFAULTED")

def test_parse_no_record_page():
    html = (FIXTURES / "ecb_no_record.html").read_text()
    assert parse_result_page(html) == LookupResult(False, "", "")

def test_parse_page_without_table_raises():
    with pytest.raises(SessionLostError):
        parse_result_page((FIXTURES / "ecb_no_table.html").read_text())
```

- [ ] **Step 3: Run to verify they fail** — expected `ImportError`.

- [ ] **Step 4: Implement `parse_result_page`** with BeautifulSoup (`html.parser`): `vioContent` `td`s, cell[1] text stripped; if it equals `No Record Available` → not found; else `moreDetails` `td`s, cell[1] and cell[3] `.get_text().strip()`. Missing `vioContent` → `SessionLostError`.

- [ ] **Step 5: Run to verify they pass.**

- [ ] **Step 6: Commit** — `git add tests/fixtures src/... tests/services/...; git commit -m "test(summonses-updater): parse ECB result pages from scrubbed fixtures"`

### Task 5: ECB client

**Files:**
- Modify: `src/simsim_tools_server/services/summonses_updater_service.py`
- Test: `tests/services/test_summonses_updater_service.py`

**Interfaces:**
- Produces:
  - `ECB_SEARCH_URL = "http://a820-ecbticketfinder.nyc.gov/searchHome.action"`, `ECB_LOOKUP_URL = "http://a820-ecbticketfinder.nyc.gov/getViolationbyID.action"`.
  - `class EcbClient:` `__init__(self, client: httpx.Client | None = None)` (default: `httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})`); `start_session(self) -> None` GETs `ECB_SEARCH_URL`; `lookup(self, number: str) -> LookupResult` POSTs the three form fields from the spec, parses; on `SessionLostError` calls `start_session()` and retries once, then lets the second `SessionLostError` propagate; `close(self) -> None`.

- [ ] **Step 1: Write the failing tests** using `httpx.MockTransport`:

```python
import httpx
from simsim_tools_server.services.summonses_updater_service import (
    ECB_LOOKUP_URL, ECB_SEARCH_URL, EcbClient,
)

def _client(handler):
    return EcbClient(httpx.Client(transport=httpx.MockTransport(handler)))

def test_lookup_posts_form_and_parses():
    seen = []
    def handler(request):
        seen.append(request)
        if str(request.url) == ECB_SEARCH_URL:
            return httpx.Response(200, text="<html></html>")
        return httpx.Response(200, text=(FIXTURES / "ecb_found.html").read_text())
    ecb = _client(handler); ecb.start_session()
    assert ecb.lookup("0213681142") == LookupResult(True, "RESCHEDULED", "DEFAULTED")
    post = seen[-1]
    assert post.method == "POST" and str(post.url) == ECB_LOOKUP_URL
    body = post.content.decode()
    assert "searchViolationObject.violationNo=0213681142" in body
    assert "searchViolationObject.searchType=violationNumber" in body

def test_lookup_refreshes_session_once_on_lost_session():
    calls = {"search": 0, "lookup": 0}
    def handler(request):
        if str(request.url) == ECB_SEARCH_URL:
            calls["search"] += 1; return httpx.Response(200, text="")
        calls["lookup"] += 1
        text = "ecb_no_table.html" if calls["lookup"] == 1 else "ecb_no_record.html"
        return httpx.Response(200, text=(FIXTURES / text).read_text())
    ecb = _client(handler); ecb.start_session()
    assert ecb.lookup("0213681142") == LookupResult(False, "", "")
    assert calls == {"search": 2, "lookup": 2}

def test_lookup_gives_up_after_one_retry():
    def handler(request):
        return httpx.Response(200, text=(FIXTURES / "ecb_no_table.html").read_text())
    ecb = _client(handler)
    with pytest.raises(SessionLostError):
        ecb.lookup("0213681142")
```

- [ ] **Step 2: Run to verify they fail.** — `ImportError`.
- [ ] **Step 3: Implement `EcbClient`.** `raise_for_status()` on both responses so HTTP errors surface as `httpx.HTTPStatusError`.
- [ ] **Step 4: Run to verify they pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(summonses-updater): httpx client for the ECB ticket finder"`

### Task 6: Job, workbook validation and the row loop

**Files:**
- Modify: `src/simsim_tools_server/services/summonses_updater_service.py`
- Test: `tests/services/test_summonses_updater_service.py`

**Interfaces:**
- Consumes: Tasks 2–4 (`decide_row`, `map_result`, `LookupResult`).
- Produces:
  - `PAUSE_SECONDS: float = 3.0`, `MAX_CONSECUTIVE_ERRORS: int = 5`, `MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024`, `SITE_DOWN_MESSAGE = "The ECB site is not responding"`.
  - `NUMBER_COL = 2`, `DATE_COL = 7`, `RESULT_COL = 17` (B, G, Q).
  - `check_headers(sheet: Worksheet) -> None` — raises `ValueError(f"Unexpected headers: B1={b!r}, G1={g!r}, Q1={q!r}. Expected the summons Number, Date of Offense and Results of Hearing columns.")` unless `"number" in str(b).lower()`, `"date" in str(g).lower()`, `"result" in str(q).lower()`.
  - `load_workbook_bytes(data: bytes) -> tuple[Workbook, Worksheet]` — `openpyxl.load_workbook(BytesIO(data))`, active sheet, `check_headers`; openpyxl errors propagate as `ValueError("Could not read the workbook")`.
  - Dataclasses (plain, converted with `dataclasses.asdict` in snapshots): `LogEntry(i: int, row: int, number: str, kind: str, text: str)`, `Change(row: int, number: str, before: str | None, after: str)`, `Problem(row: int, reason: str)`.
  - `@dataclass class Job:` fields `id: str`, `filename: str`, `workbook: Workbook`, `sheet: Worksheet`, `total_rows: int` (= `sheet.max_row - 1`), `status: str = "running"`, `current_row: int = 1`, `counts: dict[str, int]` (keys `looked_up`, `changed`, `no_record`, `skipped`, `errors`, all 0), `log: list[LogEntry]`, `changes: list[Change]`, `problems: list[Problem]`, `error: str | None = None`, `started_at: datetime` (UTC now), `finished_at: datetime | None = None`, `cancel_requested: bool = False`, `file_bytes: bytes | None = None`, `lock: threading.Lock`. Methods: `snapshot(self, after: int = 0) -> dict` (the spec's JSON; `started_at`/`finished_at` as ISO strings; `log` = entries with `i >= after`; `next` = `len(self.log)`), `request_cancel(self) -> None`.
  - `run_job(job: Job, lookup: Callable[[str], LookupResult], *, pause: float | None = None, sleep: Callable[[float], None] = time.sleep) -> None` — the loop; `pause=None` reads `PAUSE_SECONDS` at call time. Always ends by setting a terminal status, `finished_at`, and `file_bytes` (for `done`/`cancelled`) under `job.lock`; any unexpected exception → `failed` with `error=str(exc)` and `logging.error` with traceback.

Loop semantics (spec "Row logic"): per row set `current_row`; `decide_row` → skip: `counts["skipped"] += 1`, log kind `skipped` text `f"skipped ({reason})"`, except `bad date` → kind `bad_date` + `Problem(row, "bad date")`, and `invalid number` → kind `invalid` + `Problem(row, "invalid number")` + `logging.warning`. Lookup: `try: result = lookup(number)` → `counts["looked_up"] += 1`; not found → write `"No Record Available"`, `counts["no_record"] += 1`, kind `no_record`, text `"No Record Available"`; found → `map_result`; `None` → kind `same`, text `f"left unchanged ({status})"`; else write, compare with previous value (`None` ≠ `""`): differs → `counts["changed"] += 1`, `Change(row, number, before, after)`, kind `changed`, text `f"{before or '(blank)'} → {after} (changed)"`; same → kind `same`, text `f"{after} (same)"`. Exception → `counts["errors"] += 1`, kind `error`, text `f"error: {exc}"`, `logging.error`, consecutive counter; at `MAX_CONSECUTIVE_ERRORS` → status `failed`, `error = SITE_DOWN_MESSAGE`, stop. After every lookup (success or error) `sleep(pause)`. After each row, if `cancel_requested` → status `cancelled`, stop. Log appends and counter updates happen under `job.lock`; `LogEntry.i` is the index in `job.log`.

- [ ] **Step 1: Write the failing tests**

Helper and tests (abridged to what each asserts; write the full bodies):

```python
from io import BytesIO
from openpyxl import Workbook, load_workbook
from simsim_tools_server.services import summonses_updater_service as svc

def _xlsx(rows):  # rows: list of (number, date, result)
    wb = Workbook(); ws = wb.active
    ws.cell(1, 2, "Number"); ws.cell(1, 7, "Date of Offense"); ws.cell(1, 17, "Results of Hearing")
    for r, (n, d, q) in enumerate(rows, start=2):
        ws.cell(r, 2, n); ws.cell(r, 7, d); ws.cell(r, 17, q)
    buf = BytesIO(); wb.save(buf); return buf.getvalue()

def _job(rows, **kw):
    wb, ws = svc.load_workbook_bytes(_xlsx(rows))
    return svc.Job(id="j", filename="a.xlsx", workbook=wb, sheet=ws, total_rows=ws.max_row - 1, **kw)

def _q(job):  # column Q values of the saved file, rows 2..
    ws = load_workbook(BytesIO(job.file_bytes)).active
    return [ws.cell(r, 17).value for r in range(2, ws.max_row + 1)]

def test_check_headers_rejects_wrong_file():
    wb = Workbook(); wb.active.cell(1, 2, "Name")
    with pytest.raises(ValueError, match="B1='Name'"):
        svc.check_headers(wb.active)

def test_run_job_writes_results_and_counts():
    rows = [("213681142", D, None), ("213681143", D, "Adjourned"), ("213681144", D, "Defaulted"),
            ("213681145", dt.datetime(2019, 1, 1), None), ("213681146", D, None), (None, D, None)]
    answers = {"0213681142": svc.LookupResult(True, "RESCHEDULED", "DEFAULTED"),
               "0213681143": svc.LookupResult(True, "RESCHEDULED", ""),       # Adjourned -> Adjourned (same)
               "0213681146": svc.LookupResult(False, "", "")}
    slept = []
    job = _job(rows)
    svc.run_job(job, answers.__getitem__, pause=0, sleep=slept.append)
    assert job.status == "done" and job.finished_at is not None
    assert job.counts == {"looked_up": 3, "changed": 1, "no_record": 1, "skipped": 3, "errors": 0}
    assert _q(job) == ["Defaulted", "Adjourned", "Defaulted", None, "No Record Available", None]
    assert job.changes == [svc.Change(2, "0213681142", None, "Defaulted")]
    assert [e.kind for e in job.log] == ["changed", "same", "skipped", "skipped", "no_record", "skipped"]
    assert job.log[0].text == "(blank) → Defaulted (changed)"
    assert slept == [0, 0, 0]

def test_run_job_records_problems():
    job = _job([("213681142", dt.time(4, 48), None), ("1234567890", D, None)])
    svc.run_job(job, lambda n: pytest.fail("no lookup expected"), pause=0, sleep=lambda s: None)
    assert job.problems == [svc.Problem(2, "bad date"), svc.Problem(3, "invalid number")]
    assert [e.kind for e in job.log] == ["bad_date", "invalid"]
    assert job.counts["skipped"] == 2

def test_run_job_fails_after_five_consecutive_errors():
    rows = [(f"21368114{i}", D, None) for i in range(7)]
    def boom(n): raise httpx.ConnectError("down")
    job = _job(rows)
    svc.run_job(job, boom, pause=0, sleep=lambda s: None)
    assert job.status == "failed" and job.error == svc.SITE_DOWN_MESSAGE
    assert job.counts["errors"] == 5 and job.file_bytes is None

def test_run_job_error_streak_resets_on_success():
    rows = [(f"21368114{i}", D, None) for i in range(9)]
    def lookup(n):  # 4 errors, 1 success, 4 errors
        if n == "0213681144":
            return svc.LookupResult(False, "", "")
        raise httpx.ConnectError("down")
    job = _job(rows)
    svc.run_job(job, lookup, pause=0, sleep=lambda s: None)
    assert job.status == "done" and job.counts["errors"] == 8 and job.counts["no_record"] == 1

def test_run_job_cancel_stops_after_current_row_and_saves():
    rows = [("213681142", D, None), ("213681143", D, None)]
    job = _job(rows)
    def lookup(n):
        job.request_cancel(); return svc.LookupResult(True, "PAID IN FULL", "")
    svc.run_job(job, lookup, pause=0, sleep=lambda s: None)
    assert job.status == "cancelled" and job.counts["looked_up"] == 1
    assert _q(job) == ["Paid before Hearing", None]

def test_snapshot_after_cursor():
    job = _job([("213681142", D, None), ("213681143", D, "Defaulted")])
    svc.run_job(job, lambda n: svc.LookupResult(False, "", ""), pause=0, sleep=lambda s: None)
    snap = job.snapshot(after=1)
    assert [e["i"] for e in snap["log"]] == [1] and snap["next"] == 2
    assert snap["status"] == "done" and snap["counts"]["no_record"] == 1
    assert job.snapshot(after=99)["log"] == [] and job.snapshot(after=99)["next"] == 2   # Review Focus 4
```

- [ ] **Step 2: Run to verify they fail.**
- [ ] **Step 3: Implement `check_headers`, `load_workbook_bytes`, the dataclasses, `Job`, `run_job`.** Save with `workbook.save(BytesIO)` once at the end.
- [ ] **Step 4: Run to verify they pass** — `poetry run pytest tests/services -q`.
- [ ] **Step 5: Ruff** — `poetry run ruff format . && poetry run ruff check .`
- [ ] **Step 6: Commit** — `git commit -m "feat(summonses-updater): job model, workbook validation and row loop"`

### Task 7: Endpoints and job registry

**Files:**
- Create: `src/simsim_tools_server/api/v1/endpoints/summonses_updater.py`
- Modify: `src/simsim_tools_server/api/router.py` (import + `api_v1_router.include_router(summonses_updater.router)`)
- Test: `tests/api/test_summonses_updater.py`

**Interfaces:**
- Consumes: Task 6 (`load_workbook_bytes`, `Job`, `run_job`, `MAX_UPLOAD_BYTES`), Task 5 (`EcbClient`).
- Produces (module `summonses_updater`): `router`, `RETENTION = timedelta(minutes=60)`, `_jobs: dict[str, Job]`, `_jobs_lock: threading.Lock`, `_sweep(now: datetime) -> None` (drops jobs with `finished_at` older than `RETENTION`), `_launch(job: Job) -> None` (creates `EcbClient()`, `start_session()`, runs `run_job(job, ecb.lookup)` in a `threading.Thread(daemon=True)`, closes the client when done), and the four routes:
  - `POST /summonses-updater` (`file: UploadFile = File(...)`) → 202 `{"job_id", "total_rows", "filename", "sheet"}`; 400 `detail="Only .xlsx files are accepted"` / `"File is larger than 25 MB"` / the `ValueError` message from `load_workbook_bytes`.
  - `GET /summonses-updater/{job_id}` (`after: int = 0`) → `job.snapshot(after)`; 404 `"Unknown job"`.
  - `GET /summonses-updater/{job_id}/file` → `StreamingResponse(BytesIO(job.file_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{job.filename}"'})`; 409 `"Job is still running"` while `running`; 404 if unknown or `failed`.
  - `DELETE /summonses-updater/{job_id}` → `request_cancel()`, 200 `{"status": job.status}`; 404 unknown.
  - `job_id` = `secrets.token_urlsafe(8)`.

- [ ] **Step 1: Write the failing tests**

Tests monkeypatch `summonses_updater.EcbClient` with a fake exposing `start_session()`, `lookup(number)`, `close()`, and `summonses_updater_service.PAUSE_SECONDS` to `0`. Helper `_wait(client, job_id, timeout=5)` polls until status is not `running`.

```python
TARGET = "simsim_tools_server.api.v1.endpoints.summonses_updater"

def test_start_poll_download(client, monkeypatch):
    # fake lookup: 0213681142 -> found RESCHEDULED/DEFAULTED; others -> no record
    # POST with _xlsx([...]) as files=[("file", ("avps.xlsx", data, "application/vnd...sheet"))]
    # assert 202, body has job_id, total_rows == number of rows, filename == "avps.xlsx"
    # poll until done; assert counts and changes; GET /file -> 200, content-type xlsx,
    # Content-Disposition contains 'filename="avps.xlsx"', column Q of returned bytes as expected
    # GET ?after=<next> -> log == []

def test_rejects_wrong_extension(client): ...  # 400, detail == "Only .xlsx files are accepted"
def test_rejects_wrong_headers(client): ...    # 400, "B1='Name'" in detail
def test_rejects_unreadable_workbook(client): ...  # bytes b"nope" named a.xlsx -> 400 "Could not read the workbook"
def test_download_while_running_is_409(client, monkeypatch): ...  # fake lookup blocks on a threading.Event; GET /file -> 409; set event; wait
def test_cancel_mid_run(client, monkeypatch): ...  # DELETE while blocked -> 200 ; wait -> "cancelled"; GET /file -> 200
def test_cancel_after_finish_is_noop(client, monkeypatch): ...  # Review Focus 5: wait done; DELETE -> 200 {"status": "done"}; GET /file -> 200
def test_five_errors_fail_job(client, monkeypatch): ...  # lookup raises; status "failed", error == SITE_DOWN_MESSAGE; GET /file -> 404
def test_unknown_job_is_404(client): ...  # GET, GET /file, DELETE on "nope"
def test_sweep_drops_old_finished_jobs(monkeypatch): ...  # put a done Job with finished_at = now - 61 min in _jobs; _sweep(now); gone; a running one stays
```

- [ ] **Step 2: Run to verify they fail** — 404s / `ImportError`.
- [ ] **Step 3: Implement the endpoint module and register the router.** Validation order in `POST`: extension → size (`len(await file.read())`) → `load_workbook_bytes` → `_sweep(now)` → create `Job`, store, `_launch`. Hold `_jobs_lock` only around dict mutation.
- [ ] **Step 4: Run to verify they pass** — `poetry run pytest -q` (whole suite).
- [ ] **Step 5: Ruff** — `poetry run ruff format . && poetry run ruff check .`
- [ ] **Step 6: Commit** — `git commit -m "feat(summonses-updater): job endpoints"`

### Task 8: Local end-to-end against the live site

**Files:** none.

- [ ] **Step 1: Run the server** — `poetry run main` (port 10827).
- [ ] **Step 2: Upload the real workbook**

```bash
curl -s -F 'file=@/home/fernando-yu/Documents/sim/summonses_2026-11-04/AVPS- WORKING VERSION - 07.10.2026.xlsx' http://localhost:10827/api/v1/summonses-updater
```
Expected: 202 with `total_rows: 2890`, sheet `AEU - AVPS - EFF 7-1-16`.

- [ ] **Step 3: Poll** — `curl -s "http://localhost:10827/api/v1/summonses-updater/<id>?after=0" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["current_row"], d["counts"])'` every ~30 s until terminal (~4 min).
- [ ] **Step 4: Compare with the baseline** — spec "Live check": expect `looked_up` 54, `no_record` 30, `changed` 14, `skipped` 2836 (12 invalid + 8 empty + 1 bad date + the rest), `errors` 0; `problems` lists row 2 `bad date` plus 4 `invalid number` rows (the baseline's 12 INCORRECT minus the 8 rows whose column B is empty, which this tool reports as `empty`). Cross-check the `changes` list against the `Changed` lines in `/home/fernando-yu/Documents/sim/summonses_2026-11-04/log.txt` (`grep Changed`). Any other delta is a bug; fix and re-run.
- [ ] **Step 5: Download** — `curl -s -o out.xlsx -D - http://localhost:10827/api/v1/summonses-updater/<id>/file`; headers show the xlsx content type and the original filename; the file opens.
- [ ] **Step 6: Record the result** in the PR description (counts, and that it matched the baseline).

### Task 9: Backend PR, deploy, production probe

**Files:** none.

- [ ] **Step 1: Push and open the PR** — `git push -u origin feat/summonses-updater && gh pr create --title "feat(summonses-updater): ECB lookup job endpoints" --base main --body-file -` (body: what it adds, the local live-check numbers, link to the spec; end with the attribution line).
- [ ] **Step 2: Merge** — ask the owner, then `just merge` (in this repo's justfile).
- [ ] **Step 3: Deploy** — `just deploy` (PR main → release); wait for the host to build.
- [ ] **Step 4: Probe from production** — repeat Task 8 steps 2–5 against the production URL (the frontend's `VITE_API_URL` host; `/api/v1/summonses-updater`). Outcome A: `done` with counts matching → continue to Part B. Outcome B: `failed` with `The ECB site is not responding` → **stop and report**: the host cannot reach the site; the fix (outbound proxy / static egress IP / other host) is the owner's decision.

## Part B — Frontend

### Task 10: Frontend worktree and composable

**Files:**
- Create: `src/composables/useSummonsesUpdater.ts`

**Interfaces:**
- Produces (all exported):
  - `type JobStatus = "running" | "done" | "cancelled" | "failed"`
  - `type LogKind = "skipped" | "changed" | "same" | "no_record" | "error" | "invalid" | "bad_date"`
  - `interface Counts { looked_up: number; changed: number; no_record: number; skipped: number; errors: number }`
  - `interface LogEntry { i: number; row: number; number: string; kind: LogKind; text: string }`
  - `interface Change { row: number; number: string; before: string | null; after: string }`
  - `interface Problem { row: number; reason: string }`
  - `interface StartResponse { job_id: string; total_rows: number; filename: string; sheet: string }`
  - `interface JobSnapshot { status: JobStatus; current_row: number; total_rows: number; counts: Counts; started_at: string; finished_at: string | null; error: string | null; log: LogEntry[]; next: number; changes: Change[]; problems: Problem[] }`
  - `errorMessage(error: unknown): string` — `axios.isAxiosError(error) && typeof error.response?.data?.detail === "string"` → that detail; else `error instanceof Error ? error.message : String(error)`.
  - `isNotFound(error: unknown): boolean` — axios error with `response.status === 404`.
  - `useSummonsesUpdater()` → `{ start(file: File): Promise<StartResponse>; poll(jobId: string, after: number): Promise<JobSnapshot>; cancel(jobId: string): Promise<void>; download(jobId: string): Promise<Blob> }` over `api` (`/v1/summonses-updater...`; `start` posts `FormData` with key `file` and the multipart header like the other composables; `download` uses `responseType: "blob"`).

- [ ] **Step 1: Create the worktree** — from the workspace root: `just new front feat/summonses-updater` (creates `worktrees/simsim-tools/feat/summonses-updater`, copies env, runs `deno install`). Work there from now on.
- [ ] **Step 2: Write the composable** as specified.
- [ ] **Step 3: Typecheck** — `deno task build`; expected: passes (the composable is unused yet; `noUnusedLocals` applies to locals, not exports).
- [ ] **Step 4: Commit** — `git add src/composables/useSummonsesUpdater.ts && git commit -m "feat(summonses-updater): api composable"`

### Task 11: Page, route, icon

**Files:**
- Create: `src/components/SummonsesUpdater.vue`, `public/summonses_updater.png`
- Modify: `src/router/routes.ts`

**Interfaces:**
- Consumes: Task 10's composable and types.
- Produces: route `{ path: "/summonses-updater", name: "SummonsesUpdater", component: SummonsesUpdater, meta: { icon: "/summonses_updater.png", title: "Summonses Updater" } }`.

Component state (all `ref`s): `phase: "idle" | "running" | "finished"`, `file: File | null`, `isDragging`, `startError: string | null`, `jobId`, `totalRows`, `filename`, `snapshot: JobSnapshot | null`, `logEntries: LogEntry[]` (accumulated), `nextCursor: number`, `showFullLog: boolean`, `downloadUrl: string | null`, `elapsedSeconds` (ticked by the same interval). One `setInterval` of 1000 ms started by `start()`, cleared on terminal status, on `onUnmounted`, and on `clear()`.

Behavior, per spec "The page":
- **Idle:** drop zone (`@drop`, plus a hidden `<input type="file" accept=".xlsx">` opened on click); non-`.xlsx` drops are ignored. File row with name and size. The note text verbatim: "Looks up every summons on the NYC ECB ticket finder and fills in *Results of Hearing* (column Q). Takes a few minutes." Green **Start** (disabled without a file). `startError` renders in `text-[#bf616a]` under the drop zone; no `alert()`.
- **Running:** header `Row {current_row} of {total_rows} · {m} min {s} s elapsed`; progress bar width `current_row / total_rows`; five tiles in this order: Looked up / Changed / No record / Skipped / Errors; log panel (`font-mono text-xs`, `max-h-64 overflow-y-auto custom-scrollbar`, auto-scroll to bottom on append) with classes by kind: `skipped`/`bad_date`/`invalid` → `opacity-45`, `changed` → `text-[#a3be8c]`, `no_record` → `text-[#ebcb8b]`, `error` → `text-[#bf616a]`, `same` → default; each line `B{row} · {number} · {text}`. Red **Cancel** → `cancel(jobId)`.
- Each poll: `poll(jobId, nextCursor)` → append `log`, set `nextCursor = next`, replace `snapshot`. If status is terminal: clear interval; if `done`/`cancelled` → `download(jobId)` → `URL.createObjectURL(new Blob([blob], { type: XLSX_MIME }))` (revoke the previous), `phase = "finished"`. If `failed` → `phase = "finished"` with `snapshot.error` shown in red where the download block sits. On a poll error with `isNotFound(error)` → `startError = "The server restarted mid-run — please upload again"`, `clear()` back to idle.
- **Finished:** `Done · {total_rows} rows in {m} min {s} s` or `Cancelled at row {current_row}`; tiles; amber callout (`border-l-4 border-[#ebcb8b] bg-[#4c566a]`) listing `problems` as `B{row}: {reason}` if any; download block in PDF Merger's markup (`<a :href :download="filename">` with `pi pi-file-excel`, `draggable`, `DownloadURL` dragstart using the xlsx MIME); **Changed cells ({n})** table with the `MultiSummonsesCounter` table/scrollbar classes: Row / Number / Before / After, blank shown as `(blank)` in `opacity-60`; "Show full log" / "Hide log" toggle revealing the same log panel; red **Clear** → `clear()`.
- `XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"`.

- [ ] **Step 1: Add the icon** — a 256×256 PNG with the same look as `public/summonses_counter.png` (a spreadsheet/refresh glyph in `#88c0d0` on transparent). If no artwork is at hand, copy `summonses_counter.png` to `summonses_updater.png` and say so in the PR.
- [ ] **Step 2: Write `SummonsesUpdater.vue`** per the behavior above, copying the frame, drop-zone, button and download markup from `PdfMerger.vue` and the table + `custom-scrollbar` style from `MultiSummonsesCounter.vue`.
- [ ] **Step 3: Add the route** to `src/router/routes.ts` (after `PdfMerger`).
- [ ] **Step 4: Typecheck and build** — `deno task build`; expected: passes with no type errors.
- [ ] **Step 5: Manual pass** against a local backend (`just dev server feat/summonses-updater` in one terminal, `just dev front feat/summonses-updater` in another, open `http://localhost:5173/simsim-tools/summonses-updater`): drop a `.txt` (ignored), drop the real workbook, Start, watch tiles and log move, Cancel once (file downloads, status says cancelled), run again to completion, download, open the file and spot-check two rows from the Changed table against the site. Try a workbook with wrong headers → inline red message. Note results in the PR.
- [ ] **Step 6: Commit** — `git add public/summonses_updater.png src/components/SummonsesUpdater.vue src/router/routes.ts && git commit -m "feat(summonses-updater): page and route"`

### Task 12: Frontend PR and deploy

- [ ] **Step 1: Push and open the PR** — `git push -u origin feat/summonses-updater && gh pr create --title "feat(summonses-updater): add Summonses Updater page" --base main` with a body linking the backend PR and the spec, and the manual-pass notes.
- [ ] **Step 2: Merge** — ask the owner, then `just merge`.
- [ ] **Step 3: Deploy** — the deploy builds from the checkout, so after the merge, in the frontend worktree: `git fetch origin && git reset --hard origin/main` (the branch is merged; nothing is lost), then `deno task build && deno task deploy`. Confirm the page loads at `https://simsimdob.github.io/simsim-tools/summonses-updater` and a run completes against the deployed backend.
- [ ] **Step 4: Clean up** — `just rm server feat/summonses-updater && just rm front feat/summonses-updater && just pull`.
