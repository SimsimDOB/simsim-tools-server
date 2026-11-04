# Summonses Updater — Design

Date: 2026-11-04
Branch: `feat/summonses-updater` (both repos)
Status: approved, not yet implemented

## Problem

The office keeps a workbook of plumbing summonses (the "AVPS" sheet, ~2,900
rows). Column Q, *Results of Hearing*, goes stale: summonses that were blank,
adjourned, rescheduled or newly issued at the last check have since been
decided. Today someone refreshes it by running a Python script by hand
(`summonses_2026-11-04/main.py`, kept outside this repo) that walks every row,
looks each candidate summons up on the NYC OATH/ECB ticket finder, and writes
the result back into Q. That requires a machine with Python, a Windows venv,
and a headless Chromium — so only one person can run it.

## Goal

A simsim-tools page, **Summonses Updater**, where anyone can drop the workbook,
watch the lookup run with live progress, and download the updated workbook
when it finishes. The row logic stays exactly what the script does today.

## Non-goals

- Changing which rows are looked up or how results are mapped. Behavior is
  the script's, warts included (see "Row logic").
- Persisting jobs across server restarts, or any database.
- Touching sheets other than the active one, or columns other than Q.
- Detecting columns by header position. B / G / Q are fixed.
- Speeding up the lookup. The 3-second pause between site hits stays.
- Auth, multi-user coordination, or a history of past runs.

## Anti-goals (what would make this a failure even if it "works")

- A run that silently writes a different value than the script would have.
- A run that freezes the other tools (`/api/ping`, PDF Merger) while it is
  going. The backend is one uvicorn process; the loop must not block it.
- Losing formatting the script preserves today. openpyxl load/save is what
  the script already does, so parity means: same preservation, same losses.

## Constraints and facts

- Backend: FastAPI, Python ≥3.13, single uvicorn process, deployed from the
  `release` branch as a Docker web service (Render-style; ephemeral
  filesystem; may spin down when idle). Nothing in the codebase writes to
  disk; all tools work in memory. There is no job, streaming or background
  infrastructure yet — this is the first.
- Frontend: Vue 3 + TS (strict), Tailwind v4, Nord palette, PrimeIcons, one
  page component + one composable per tool, routes drive the navbar and home
  cards. No test runner. GitHub Pages at `/simsim-tools/`.
- A full run on the real workbook takes about 4 minutes: of 2,891 rows only
  ~54 reach the site; the rest are skipped instantly.
- CORS is `*`.
- **Unknown: whether the deployed backend can reach the ECB site.** The
  lookup is verified from a workstation only. NYC `.gov` hosts sometimes
  refuse cloud datacenter IPs. The delivery order below exists to answer this
  before the page is built.

### The ECB site (verified 2026-11-04)

- Search page: `GET http://a820-ecbticketfinder.nyc.gov/searchHome.action`.
  It sets a `JSESSIONID` cookie. The "Search by Summons Number" tab's
  `onclick` only sets a hidden field and the form action — no browser needed.
- Lookup: `POST http://a820-ecbticketfinder.nyc.gov/getViolationbyID.action`
  with form fields
  `searchViolationObject.violationNo=<10 digits>`,
  `searchViolationObject.searchType=violationNumber`,
  `submit=  Search  `, sending the session cookie.
- Result page: `table#vioContent` cells — cell[1] is the summons number, or
  the text `No Record Available`. `div#moreDetails` cells — cell[1] is
  *Status of Summons/Notice* (e.g. `RESCHEDULED`, `PAID IN FULL`,
  `SETTL/IN-VIOLATION`, `NEW ISSUANCE`), cell[3] is *Hearing Result*
  (e.g. `DEFAULTED`, `DISMISSED`, empty).

## Workbook contract

- `.xlsx`, one active sheet (currently `AEU - AVPS - EFF 7-1-16`), header in
  row 1, data from row 2 to the sheet's last row.
- Column B — summons number. Column G — date of offense. Column Q — result.
- Row 1 sanity check before starting: B1 contains "number", G1 contains
  "date", Q1 contains "result" (case-insensitive substring). Otherwise the
  upload is rejected with a message that names the three headers actually
  found. (My call: catches the wrong file without inventing column detection.)
- Upload limit 25 MB, `.xlsx` only. (My call.)

## Row logic (parity with the script)

For each row r from 2 to the last row, with `number = B[r]`, `date = G[r]`,
`result = Q[r]`:

1. **Empty number** (B is `None`/blank) → skipped, reason `empty`. (My call;
   the script would have stringified `None` and reported it INCORRECT.)
2. **Unreadable date**: `date` is not a `datetime`/`date` (e.g. a `time`,
   `None`, text) → skipped, reason `bad date`. Logged as a warning and listed
   in the finish summary. Nothing written.
3. **Out of date**: `date.year < 2021` → skipped, reason `before 2021`.
4. **Occupied**: `result` is not one of: blank, `adjourned`, `new issuance`,
   `rescheduled`, `no record available` (compared after `.strip().lower()`;
   the script compares `.lower()` without strip — my call, strip too, since
   `"Adjourned "` with a trailing space clearly means adjourned) → skipped,
   reason `has result`.
5. **Normalize number**: `str(number)` with spaces removed; if 9 chars and no
   `E` → prefix `0`; if 10 chars containing `E` → replace `E` with `0`.
6. **Invalid number**: not (10 chars and starts with `0`) → skipped, reason
   `invalid number`, logged as a warning.
7. **Look up** on the site. Then:
   - cell[1] of `vioContent` is `No Record Available` → write
     `No Record Available` to Q.
   - else read `status` (moreDetails cell[1]) and `hearing_result`
     (cell[3]), both stripped, and:
     - `status == "PAID IN FULL"` → `Paid before Hearing`
     - elif `hearing_result` non-empty:
       `SETTL/IN-VIOLATION` → `In Violation`, else `hearing_result.capitalize()`
     - else (no hearing result):
       `SETTL/IN-VIOLATION` → `In Violation`;
       `NEW ISSUANCE` → `New Issuance`;
       `RESCHEDULED` → `Adjourned`;
       anything else → cell left unchanged.
   - A row counts as **changed** when a *found-record* write differs from the
     previous cell value (exact string compare, `None` ≠ `""`), same as the
     script's Same/Changed log line. A `No Record Available` write is counted
     under *no record* only, never under *changed*, and does not appear in
     the changed-cells table — matching the approved mockup's tiles. (My call.)
   - Sleep 3 seconds after every lookup, success or failure.
8. **Lookup error** (network error, unexpected page, parse failure) → counted
   as an error, logged with the exception, nothing written, continue with the
   next row. After **5 consecutive** lookup errors the job fails with
   "the ECB site is not responding" rather than grinding through hundreds of
   doomed rows. (My call.)

Note on `capitalize()`: it lowercases everything after the first letter, so
`ADMIN. DISMISSAL` becomes `Admin. dismissal`. That is what the script writes
today and is kept deliberately.

Session handling: fetch the search page once at job start to get the cookie;
if a lookup response has no `vioContent` table, refetch the search page and
retry that row once before treating it as an error. (Builder's call on the
exact retry mechanics; the intent is "one cheap retry on a lost session".)

## Backend — `simsim-tools-server`

### Job model

In-memory jobs, one dict keyed by a random `job_id`, guarded by a lock. Each
job holds: the original filename, the loaded `openpyxl.Workbook`, status
(`running` / `done` / `cancelled` / `failed`), counters, the ordered list of
log lines, the list of changed cells, the list of rows with problems,
`started_at` / `finished_at`, a cancel flag, and — once finished — the saved
workbook bytes.

The row loop runs in a worker thread (`asyncio.to_thread` or a
`threading.Thread`), using a synchronous `httpx.Client`, so the event loop
stays free. Concurrent jobs are allowed and independent (each has its own
`httpx.Client` and its own 3-second pacing).

Finished jobs (any terminal status) are dropped 60 minutes after they finish;
a sweep runs whenever a new job starts. (My call.) Jobs do not survive a
restart; the page tells the user to re-upload if a poll gets a 404.

### Endpoints (`api/v1/endpoints/summonses_updater.py`)

- `POST /api/v1/summonses-updater` — multipart `file: UploadFile`. Validates
  (extension, size, loads with openpyxl, header check), creates the job,
  starts the thread. Returns `202 {"job_id": "...", "total_rows": 2890,
  "filename": "AVPS- WORKING VERSION - 07.10.2026.xlsx", "sheet": "AEU - AVPS - EFF 7-1-16"}`.
  Validation failures are `400` with a human `detail`; the house style is
  `500` for everything, but a wrong file is the user's mistake and the page
  must be able to say so.
- `GET /api/v1/summonses-updater/{job_id}?after=<n>` — status snapshot:

  ```json
  {
    "status": "running",
    "current_row": 1204, "total_rows": 2890,
    "counts": {"looked_up": 21, "changed": 6, "no_record": 11,
               "skipped": 1172, "errors": 0},
    "started_at": "...", "finished_at": null,
    "error": null,
    "log": [{"i": 1201, "row": 1201, "number": "0351812406", "kind": "changed",
             "text": "Adjourned → Defaulted"}, ...],
    "next": 1206,
    "changes": [{"row": 214, "number": "0213681142", "before": "Adjourned",
                 "after": "Defaulted"}, ...],
    "problems": [{"row": 1337, "reason": "bad date"}]
  }
  ```

  `log` holds only entries with index ≥ `after`; `next` is the cursor for the
  next poll. `kind` is one of `skipped`, `changed`, `same`, `no_record`,
  `error`, `invalid`, `bad_date`. `changes` and `problems` are always complete
  (they are small). `404` if the job is unknown.
- `GET /api/v1/summonses-updater/{job_id}/file` — the workbook, as
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` with
  `Content-Disposition: attachment; filename="<original name>"`. Available
  once status is `done` or `cancelled` (rows completed so far are in it);
  `409` while running, `404` if failed or unknown.
- `DELETE /api/v1/summonses-updater/{job_id}` — request cancel. The loop
  stops after the current row, saves, and the status becomes `cancelled`.

The workbook is saved to bytes once, when the job reaches a terminal state —
not after every row as the script does; nothing can read a half-written
in-memory file, so per-row saves buy nothing here.

### Files

- New: `services/summonses_updater_service.py` — row logic, ECB client,
  result-page parser, job runner. Keep the pure pieces (number normalization,
  row decision, result mapping, HTML parsing) as plain functions.
- New: `api/v1/endpoints/summonses_updater.py` — the four routes above and
  the job registry.
- Modified: `api/router.py` — one `include_router` line.
- Modified: `pyproject.toml` — runtime deps `openpyxl`, `httpx`,
  `beautifulsoup4` (PEP 621 form, pinned like the others); `httpx` leaves the
  dev group. `poetry lock`. Dockerfile unchanged.

Logging follows the house style (root logger, f-strings, INFO per job
start/finish, WARNING per invalid row, ERROR with traceback per lookup error).

## Frontend — `simsim-tools`

### Files

- New: `src/composables/useSummonsesUpdater.ts` — `start(file)`,
  `poll(jobId, after)`, `cancel(jobId)`, `download(jobId)` over the shared
  axios `api` instance. Polling interval 1 s while running. Axios surfaces
  server messages as `error.response?.data?.detail`; the composable should
  pass that through so the page can show it instead of
  "Request failed with status code 400".
- New: `src/components/SummonsesUpdater.vue` — the page.
- New: `public/summonses_updater.png` — icon. If no suitable asset is at
  hand, point `meta.icon` at `/summonses_counter.png` as the last tool did.
- Modified: `src/router/routes.ts` — one entry, path `/summonses-updater`,
  name `SummonsesUpdater`, title `Summonses Updater`. Navbar and Home pick it
  up.

### The page (approved mockup, three states)

Same frame as PDF Merger: dark Nord card, `font-['MakoP']`, heading in
`#88c0d0`.

1. **Before.** Drop zone (also clickable to open a file picker — my call,
   PDF Merger is drop-only) accepting one `.xlsx`. Once a file is chosen it
   shows as a file row (name, size). A one-line note: "Looks up every summons
   on the NYC ECB ticket finder and fills in *Results of Hearing* (column Q).
   Takes a few minutes." A green **Start** button, disabled until a file is
   present.
2. **During.** "Row N of T · elapsed", a progress bar of N/T, five tiles
   (Looked up / Changed / No record / Skipped / Errors), a monospace log
   panel appending the polled lines with skipped rows dimmed, changed rows
   green, no-record amber, errors red, auto-scrolled to the bottom. A red
   **Cancel** button. The log panel keeps everything received; the view is
   capped in height and scrolls.
3. **After** (`done` or `cancelled`). "Done · T rows in M min S s" (or
   "Cancelled at row N"), the five tiles, an amber callout listing rows with
   problems (bad date / invalid number) if any, the download block in the
   PDF Merger style (icon link, click or drag-out, original filename), and a
   **Changed cells (k)** table: Row / Number / Before / After, with blank
   shown as *(blank)*, plus a "Show full log" toggle that expands the log
   panel. A red **Clear** resets the page. On `failed`, the same frame with
   the error message in red where the download would be.

Errors from `start` (wrong file, too large, bad headers) show inline under
the drop zone in red; the house `alert()` is not used here. If a poll returns
`404` (server restarted), show "The server restarted mid-run — please upload
again" and return to state 1.

Leaving the page while a job runs: the job keeps running on the server; the
page simply stops polling. Resuming an in-flight job after navigation is out
of scope.

## Testing

### Backend

Pure functions first (TDD), `tests/services/test_summonses_updater_service.py`:

- number normalization: `"213681142"` → `"0213681142"`; `"E213681142"` →
  `"0213681142"`; `" 0213 681142 "` → `"0213681142"`; `"1234567890"` →
  invalid; `"E12345678"` (9 chars with E) → invalid.
- row decision: each skip reason, with the trailing-space `"Adjourned "`
  case counting as a candidate.
- result mapping: the full table above, including `capitalize()` and the
  "anything else → unchanged" branch.
- HTML parsing against two fixture files captured from the live site (found
  with status/hearing result; `No Record Available`), plus a page with no
  `vioContent` → session-lost signal. Both repos are public and result pages
  carry respondent names and addresses, so **fixtures are scrubbed before
  commit**: names, addresses, locations and the summons number replaced with
  placeholders, markup untouched, and a comment at the top saying so.
  (My call.)

API, `tests/api/test_summonses_updater.py`, lookup function patched:

- start → poll until done → download; the downloaded bytes open with
  openpyxl and Q holds the expected values; `changes` lists the changed rows.
- header check rejects a workbook with the wrong headers (400, message
  names the headers found).
- cancel mid-run yields `cancelled` and a downloadable file.
- 5 consecutive lookup errors → `failed`.
- the 3-second sleep is patched out in tests.

### Frontend

`deno task build` (vue-tsc + vite) must pass. Manual pass against a local
backend with the real workbook: start, watch counts move, cancel once, run to
completion, download, open the file and spot-check two changed rows against
the site.

### Live check

The old script cannot be run here (Windows-only venv, Chromium), so the
baseline is the run already made on 2026-11-04 with the same workbook:
`summonses_2026-11-04/log.txt` — 24 found, 30 no record, 14 changed, 12
INCORRECT, 1 DATE_INCORRECT. One end-to-end run of the tool against the real
site with that workbook, done soon so site data has not drifted, must match
it row for row except these known, intended deltas:

- the 8 rows with an empty column B read `empty` instead of INCORRECT;
- row 2 (a `time` in column G) reads `bad date` instead of DATE_INCORRECT.

Any other difference is a bug in the port.

## Delivery

Two worktrees on `feat/summonses-updater`, one per repo, two PRs. Order is
fixed by the open egress question:

1. **Backend PR** — service, endpoints, tests. Merge and `just deploy`
   (main → release).
2. **Production probe** — from a workstation, `curl` the deployed backend:
   upload the real workbook, poll until terminal, download. If it reaches
   `done` and the live check above passes, continue. If it `fail`s with the
   site-not-responding error, stop: the site blocks the host, and the fix
   (an outbound proxy, a static egress IP, or a different host) is a
   decision to bring back to the owner before any page work.
3. **Frontend PR** — composable, page, route, icon; links to the backend PR.
   `npm run build && npm run deploy`.

## Left to the builder

- Thread vs `asyncio.to_thread`, lock granularity, exact job-id format.
- Exact retry mechanics for a lost ECB session.
- Whether the log line list is trimmed server-side for very long runs (it is
  ~3k lines for this workbook; fine as-is).
- Icon artwork.
- Tailwind details of the progress bar and tiles; the mockup is the guide,
  not a pixel spec.
