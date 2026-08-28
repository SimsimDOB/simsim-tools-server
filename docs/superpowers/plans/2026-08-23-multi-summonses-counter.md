# Multi Summonses Counter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a second counting tool, "Multi Summonses Counter", that reads the
quantity printed on each matching PDF page (`"3 summonses"` → 3) instead of
adding a fixed 1, leaving the existing Summonses Counter untouched.

**Architecture:** Full copy, no shared code. The backend gets its own service
and endpoint alongside the existing pair; the frontend gets its own composable,
component, and route. The one genuinely new piece of logic is a pure function,
`parse_summons_quantity`, which is built test-first. Everything else is a
verbatim copy of a working file with a named, minimal edit.

**Tech Stack:** FastAPI / Python 3.13 / Poetry / pytest / PyMuPDF / pytesseract
(backend); Vue 3 / TypeScript / Vite / Deno / Tailwind / axios (frontend).

**Spec:** `docs/superpowers/specs/2026-08-23-multi-summonses-counter-design.md`
(in the backend repo; read it alongside this plan)

## Global Constraints

- **Two repos, two worktrees, one branch name, two PRs.** Backend worktree:
  `worktrees/simsim-tools-server/feat/multi-summonses-counter`. Frontend
  worktree: `worktrees/simsim-tools/feat/multi-summonses-counter`. Both already
  exist. Never edit the read-only root repos `simsim-tools/` or
  `simsim-tools-server/`.
- **Tasks 1–3 are backend; Task 4 is frontend.** Every `cd` and every command
  is written relative to the correct worktree — check which one before running.
- **Do not modify any existing summonses file.** `summonses_count_service.py`,
  `endpoints/summonses_count.py`, `SummonsesCounter.vue`, and
  `useSummonsesCount.ts` must show zero diff at the end. `api/router.py` and
  `router/routes.ts` are the only existing files that change.
- **Quantity ceiling is 99.** Above it, `parse_summons_quantity` returns `None`.
- **Response shape is unchanged** from the existing endpoint:
  `{"total_count": int, "details": [{"filename", "count", "removed_count",
  "removed_pages"}]}`, with an `{"filename", "error"}` entry for a failed file.
- **Ruff:** `line-length = 88`, `target-version = "py313"`,
  `select = ["E", "F", "I"]` (isort included — keep imports alphabetical).
  A pre-commit hook runs ruff format and ruff on commit.
- **Conventional commits** for every commit message.
- **`requiresGuest` is not copied** to the new route. It is vestigial — no
  navigation guard reads it.

---

## File Structure

**Backend** — `worktrees/simsim-tools-server/feat/multi-summonses-counter`

| File | Responsibility |
| --- | --- |
| `src/simsim_tools_server/services/multi_summonses_count_service.py` (new) | The quantity parser plus a copy of the page-walk loop and its four OCR helpers. |
| `src/simsim_tools_server/api/v1/endpoints/multi_summonses_count.py` (new) | HTTP boundary: accepts many PDFs, aggregates per-file results, isolates per-file failures. |
| `src/simsim_tools_server/api/router.py` (modify) | One import, one `include_router`. |
| `tests/services/test_multi_summonses_count_service.py` (new) | Unit tests for the parser. |
| `tests/api/test_multi_summonses_count.py` (new) | Endpoint tests with the service mocked. |

**Frontend** — `worktrees/simsim-tools/feat/multi-summonses-counter`

| File | Responsibility |
| --- | --- |
| `src/composables/useMultiSummonsesCount.ts` (new) | Posts the file batch to the new endpoint. |
| `src/components/MultiSummonsesCounter.vue` (new) | The page: drop zone, results table, totals. |
| `src/router/routes.ts` (modify) | One route entry; the navbar and home cards derive from it. |

---

## Task 1: The quantity parser (backend)

The only piece of real logic in this feature. Pure `str -> int | None`, so it
is built test-first and tested hard. The rest of the service file is added in
Task 2.

**Files:**
- Create: `src/simsim_tools_server/services/multi_summonses_count_service.py`
- Test: `tests/services/test_multi_summonses_count_service.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `parse_summons_quantity(text: str) -> int | None` and the module
  constant `_MAX_QUANTITY: int = 99`, both in
  `simsim_tools_server.services.multi_summonses_count_service`. Task 2 calls
  the parser from the counting loop in this same module.

**Background you need:** the OCR text reaching this function has already been
lowercased by the caller (`__get_summonses_str` calls `.lower()`), and it
normally ends in a newline. Real-world strings look like `"1 summons\n"` and
`"3 summonses\n"`. The existing tool's own source comment records the observed
variants as `1 summons`, `1. summons`, `1. summonses`, `1 summonses` — note the
optional period, which is why the pattern allows one.

- [ ] **Step 1: Write the failing tests**

Create `tests/services/test_multi_summonses_count_service.py`. Do **not** add an
`__init__.py` to `tests/services/` — `tests/api/` does not have one either.

```python
import pytest

from simsim_tools_server.services.multi_summonses_count_service import (
    parse_summons_quantity,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Singular and plural, with and without the OCR'd period.
        ("1 summons\n", 1),
        ("1. summonses\n", 1),
        ("3 summonses\n", 3),
        ("12 summonses", 12),
        # OCR sometimes eats the space between the digit and the word.
        ("3summonses", 3),
        # The case today's regex misses: text ending exactly after "summons".
        ("2 summons", 2),
        # No legible digit -> not a summons page.
        ("summonses\n", None),
        ("", None),
        # OCR noise in the word itself is not silently accepted.
        ("3 sumnonses", None),
        # Implausible value, most likely two numbers joined by OCR.
        ("400 summonses", None),
    ],
)
def test_parse_summons_quantity(text: str, expected: int | None):
    assert parse_summons_quantity(text) == expected


def test_parse_summons_quantity_accepts_the_ceiling_itself():
    assert parse_summons_quantity("99 summonses\n") == 99


def test_parse_summons_quantity_rejects_one_above_the_ceiling():
    assert parse_summons_quantity("100 summonses\n") is None
```

**Do not run ruff on the test file until Step 5.** Ruff resolves
`simsim_tools_server.*` as first-party only when the module exists on disk, so
between Steps 1 and 3 it misreads the import as third-party and reports a
spurious `I001`. Running `ruff check --fix` at that moment would delete the
blank line and leave the import block wrong once the module lands. The error
disappears on its own after Step 3 — verified.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/fernando-yu/Documents/sim/simsim-tools/worktrees/simsim-tools-server/feat/multi-summonses-counter
poetry run pytest tests/services/test_multi_summonses_count_service.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named
'simsim_tools_server.services.multi_summonses_count_service'`. That is the
correct failure; the module does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `src/simsim_tools_server/services/multi_summonses_count_service.py` with
exactly this content — nothing else goes in the file yet:

```python
import logging
import re

_MAX_QUANTITY = 99
_QUANTITY = re.compile(r"(\d+)\D*summons(?:es)?\b", re.IGNORECASE)


def parse_summons_quantity(text: str) -> int | None:
    """Read the summons quantity from a page's OCR'd text.

    Returns None when no quantity is legible, or when the value exceeds
    _MAX_QUANTITY. OCR joining two numbers is the realistic failure mode
    here, and it would otherwise be invisible in a bare total.
    """
    match = _QUANTITY.search(text)
    if match is None:
        return None
    quantity = int(match.group(1))
    if quantity > _MAX_QUANTITY:
        logging.warning(f"Implausible summons quantity {quantity} in {text!r}")
        return None
    return quantity
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
poetry run pytest tests/services/test_multi_summonses_count_service.py -v
```

Expected: 12 passed (10 parametrized cases + 2 ceiling tests).

- [ ] **Step 5: Check lint and confirm the existing suite still passes**

```bash
poetry run ruff format --check .
poetry run ruff check .
poetry run pytest
```

Expected: ruff clean, all tests pass including `test_ping`.

- [ ] **Step 6: Commit**

```bash
git add src/simsim_tools_server/services/multi_summonses_count_service.py \
        tests/services/test_multi_summonses_count_service.py
git commit -m "feat(summonses): add summons quantity parser"
```

---

## Task 2: The counting service (backend)

Appends the page-walk loop and its OCR helpers to the module Task 1 created.
This is a copy of `summonses_count_service.py` with exactly one behavioral
change: the per-page branch calls the parser and adds the quantity.

**Files:**
- Modify: `src/simsim_tools_server/services/multi_summonses_count_service.py`
  (append below the parser from Task 1)

**Interfaces:**
- Consumes: `parse_summons_quantity(text: str) -> int | None` from Task 1.
- Produces: `count_multi_summonses(pdf: UploadFile) -> tuple[int, int, str]`,
  returning `(count, removed_count, removed_pages_str)` where `count` is the
  sum of quantities, `removed_count` is a count of pages, and
  `removed_pages_str` is a comma-joined 1-based page list such as `"3, 9"`.
  Task 3 imports this function.

**Why this is a copy and not an import:** the spec's accepted trade — the
existing tool must not change, so its four OCR helpers are duplicated rather
than extracted. This is recorded as known debt; do not "helpfully" refactor
the original file.

**One subtlety — do not change the inner `while` loop's regex.** After counting
a page, the loop scans forward to the next document's first page using
`re.search(r"[0-9].*summons", summonses_str)`. That pattern already matches
both `"1 summons"` and `"3 summonses"`, and the spec says the page walk carries
over unchanged. Leave it exactly as written; do not swap in the parser there.

- [ ] **Step 1: Extend the imports**

Replace the two import lines at the top of
`src/simsim_tools_server/services/multi_summonses_count_service.py`:

```python
import logging
import re
```

with (isort order — stdlib, blank line, third-party):

```python
import logging
import re
import traceback
from io import BytesIO

import fitz
import pytesseract
from fastapi import UploadFile
from PIL import Image
```

- [ ] **Step 2: Append the counting function and helpers**

Append the following to the same file, below `parse_summons_quantity`:

```python
def count_multi_summonses(pdf: UploadFile) -> tuple[int, int, str]:
    try:
        total_count = 0
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

        with fitz.open(stream=pdf.file.read(), filetype="pdf") as pdf_document:
            logging.info(f"Processing file: {pdf.filename}")
            logging.info(f"Pdf length: {len(pdf_document)}")
            count = 0
            removed = 0
            pages = []

            images_index = 0
            while images_index < len(pdf_document):
                img = __page_to_image(pdf_document.load_page(images_index))
                summonses_str = __get_summonses_str(img)

                quantity = parse_summons_quantity(summonses_str)
                if quantity is not None:
                    logging.info(f"Found {quantity} on page {images_index + 1}")
                    count += quantity
                else:
                    logging.warning(
                        f"Removing page {images_index + 1}; no legible "
                        f"quantity in {summonses_str!r}"
                    )
                    pages.append(images_index + 1)
                    removed += 1
                images_index += 1

                if images_index >= len(pdf_document):
                    break

                img = __page_to_image(pdf_document.load_page(images_index))
                skip_pages = __get_skip_pages(img)

                if skip_pages is not None:
                    images_index += skip_pages + 1
                else:
                    summonses_str = __get_summonses_str(img)
                    while not re.search(r"[0-9].*summons", summonses_str):
                        images_index += 1
                        if images_index >= len(pdf_document):
                            break
                        img = __page_to_image(pdf_document.load_page(images_index))
                        summonses_str = __get_summonses_str(img)

            logging.info(
                f"File {pdf.filename} - Count: {count}, Removed: {removed}, "
                f"Pages: {pages}"
            )
            total_count += count
            pages_str = ", ".join(map(str, pages))

        return total_count, removed, pages_str
    except Exception as error:
        logging.error(f"Error counting summonses: {error}")
        logging.error(traceback.format_exc())
        raise error


def __page_to_image(page: fitz.Page) -> Image.Image:
    pix = page.get_pixmap(dpi=150)
    png_bytes = pix.tobytes("png")
    return Image.open(BytesIO(png_bytes))


def __get_summonses_str(img: Image.Image) -> str:
    cropped_img = __crop_summonses(img)
    summonses_str = pytesseract.image_to_string(cropped_img, lang="eng").lower()
    return summonses_str


def __crop_summonses(img: Image.Image) -> Image.Image:
    width, height = img.size
    left = width * 0.75
    top = height * 0.15
    right = width
    bottom = height * 0.27
    return img.crop((left, top, right, bottom))


def __crop_pages(img: Image.Image) -> Image.Image:
    width, height = img.size
    left = width * 0.7
    top = height * 0.85
    right = width
    bottom = height
    return img.crop((left, top, right, bottom))


def __get_skip_pages(img: Image.Image) -> int | None:
    pages_img = __crop_pages(img)
    pages_str = pytesseract.image_to_string(pages_img, lang="eng").lower()
    pages = re.search(r"[0-9].*of.*[0-9]", pages_str)
    if pages:
        cur_page, total_page = pages.group().split(" of ")
        cur_page = re.sub(r"[^0-9]", "", cur_page)
        total_page = re.sub(r"[^0-9]", "", total_page)
        return int(total_page) - int(cur_page)
    return None
```

- [ ] **Step 3: Verify the module's shape**

```bash
grep -n "^def \|^_" src/simsim_tools_server/services/multi_summonses_count_service.py
```

Expected, in this order: `_MAX_QUANTITY`, `_QUANTITY`,
`def parse_summons_quantity`, `def count_multi_summonses`,
`def __page_to_image`, `def __get_summonses_str`, `def __crop_summonses`,
`def __crop_pages`, `def __get_skip_pages`.

- [ ] **Step 4: Verify it imports and the existing suite still passes**

```bash
poetry run python -c "from simsim_tools_server.services.multi_summonses_count_service import count_multi_summonses; print(count_multi_summonses)"
poetry run pytest
```

Expected: prints the function object; all tests pass. There is no unit test for
the loop itself — it needs real PDFs and a tesseract binary, which the spec
scopes out. That gap is deliberate and documented.

- [ ] **Step 5: Confirm the original service is untouched**

```bash
git diff --stat src/simsim_tools_server/services/summonses_count_service.py
```

Expected: no output.

- [ ] **Step 6: Lint and commit**

```bash
poetry run ruff format --check .
poetry run ruff check .
git add src/simsim_tools_server/services/multi_summonses_count_service.py
git commit -m "feat(summonses): add multi summonses counting service"
```

---

## Task 3: The endpoint (backend)

**Files:**
- Create: `src/simsim_tools_server/api/v1/endpoints/multi_summonses_count.py`
- Modify: `src/simsim_tools_server/api/router.py`
- Test: `tests/api/test_multi_summonses_count.py`

**Interfaces:**
- Consumes: `count_multi_summonses(pdf: UploadFile) -> tuple[int, int, str]`
  from Task 2.
- Produces: `POST /api/v1/multi-summonses-count`, accepting a multipart form
  with repeated field name `pdfs`. Task 4's composable posts to it.

**How the mocking works:** the endpoint module does
`from ...services.multi_summonses_count_service import count_multi_summonses`,
which binds the name into the endpoint module. So the patch target is
`simsim_tools_server.api.v1.endpoints.multi_summonses_count.count_multi_summonses`
— patching it on the service module would have no effect.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_multi_summonses_count.py`:

```python
from unittest.mock import patch

from fastapi.testclient import TestClient

TARGET = (
    "simsim_tools_server.api.v1.endpoints.multi_summonses_count.count_multi_summonses"
)


def test_sums_counts_across_files(client: TestClient):
    """Two files: total_count is the sum, details carry each file."""
    with patch(TARGET, side_effect=[(3, 1, "2"), (4, 0, "")]):
        response = client.post(
            "/api/v1/multi-summonses-count",
            files=[
                ("pdfs", ("a.pdf", b"%PDF-1.4", "application/pdf")),
                ("pdfs", ("b.pdf", b"%PDF-1.4", "application/pdf")),
            ],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 7
    assert body["details"] == [
        {
            "filename": "a.pdf",
            "count": 3,
            "removed_count": 1,
            "removed_pages": "2",
        },
        {
            "filename": "b.pdf",
            "count": 4,
            "removed_count": 0,
            "removed_pages": "",
        },
    ]


def test_one_bad_file_does_not_sink_the_batch(client: TestClient):
    """A failing file yields an error entry; the other still counts."""
    with patch(TARGET, side_effect=[RuntimeError("boom"), (5, 0, "")]):
        response = client.post(
            "/api/v1/multi-summonses-count",
            files=[
                ("pdfs", ("bad.pdf", b"not a pdf", "application/pdf")),
                ("pdfs", ("good.pdf", b"%PDF-1.4", "application/pdf")),
            ],
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 5
    assert body["details"][0] == {"filename": "bad.pdf", "error": "boom"}
    assert body["details"][1]["count"] == 5
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd /home/fernando-yu/Documents/sim/simsim-tools/worktrees/simsim-tools-server/feat/multi-summonses-counter
poetry run pytest tests/api/test_multi_summonses_count.py -v
```

Expected: both fail — the patch target does not exist yet, raising
`ModuleNotFoundError` / `AttributeError` from `unittest.mock`.

- [ ] **Step 3: Write the endpoint**

Create `src/simsim_tools_server/api/v1/endpoints/multi_summonses_count.py`:

```python
import logging
import traceback

from fastapi import APIRouter, File, HTTPException, UploadFile

from simsim_tools_server.services.multi_summonses_count_service import (
    count_multi_summonses,
)

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
```

- [ ] **Step 4: Wire it into the router**

In `src/simsim_tools_server/api/router.py`, change the import line:

```python
from .v1.endpoints import pdf_merge, summonses_count
```

to (alphabetical, as ruff's isort rule requires):

```python
from .v1.endpoints import multi_summonses_count, pdf_merge, summonses_count
```

and add one line below the existing v1 includes, so the block reads:

```python
api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(summonses_count.router)
api_v1_router.include_router(pdf_merge.router)
api_v1_router.include_router(multi_summonses_count.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
poetry run pytest tests/api/test_multi_summonses_count.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run the whole suite and lint**

```bash
poetry run pytest
poetry run ruff format --check .
poetry run ruff check .
git diff --stat src/simsim_tools_server/services/summonses_count_service.py \
                src/simsim_tools_server/api/v1/endpoints/summonses_count.py
```

Expected: all tests pass, ruff clean, and the final `git diff --stat` prints
nothing — the existing tool is untouched.

- [ ] **Step 7: Commit**

```bash
git add src/simsim_tools_server/api/v1/endpoints/multi_summonses_count.py \
        src/simsim_tools_server/api/router.py \
        tests/api/test_multi_summonses_count.py
git commit -m "feat(api): add multi summonses count endpoint"
```

---

## Task 4: The frontend page

All of Task 4 runs in the **frontend** worktree. The repo has no test runner —
`deno task build` (vue-tsc typecheck + vite build) is the gate, plus a manual
pass against the running backend.

**Files:**
- Create: `src/composables/useMultiSummonsesCount.ts`
- Create: `src/components/MultiSummonsesCounter.vue`
- Modify: `src/router/routes.ts`

**Interfaces:**
- Consumes: `POST /api/v1/multi-summonses-count` from Task 3.
- Produces: the route `/multi-summonses-counter`, named
  `MultiSummonsesCounter`. `Navbar.vue` and `Home.vue` both iterate the routes
  array, so the nav link and the home card appear with no further change.

- [ ] **Step 1: Create the composable**

```bash
cd /home/fernando-yu/Documents/sim/simsim-tools/worktrees/simsim-tools/feat/multi-summonses-counter
```

Create `src/composables/useMultiSummonsesCount.ts`:

```ts
import api from "@/services/api";

export function useMultiSummonsesCount() {
  const countSummonses = async (files: File[]) => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append("pdfs", file);
    });

    const response = await api.post("/v1/multi-summonses-count", formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    });

    return response.data;
  };

  return {
    countSummonses,
  };
}
```

- [ ] **Step 2: Copy the component**

Use `cp` rather than retyping — it guarantees the ~230 lines of Tailwind markup
are identical, which is the whole point of the full-copy approach.

```bash
cp src/components/SummonsesCounter.vue src/components/MultiSummonsesCounter.vue
```

- [ ] **Step 3: Make the three edits to the copy**

In `src/components/MultiSummonsesCounter.vue` only — three changes, nothing
else:

1. The composable import:

```ts
import { useSummonsesCount } from "@/composables/useSummonsesCount";
```

becomes

```ts
import { useMultiSummonsesCount } from "@/composables/useMultiSummonsesCount";
```

2. The call:

```ts
const { countSummonses } = useSummonsesCount();
```

becomes

```ts
const { countSummonses } = useMultiSummonsesCount();
```

3. The heading text in the template:

```html
        <h1 class="text-3xl font-bold text-[#88c0d0] tracking-wide">
          Summonses Counter
        </h1>
```

becomes

```html
        <h1 class="text-3xl font-bold text-[#88c0d0] tracking-wide">
          Multi Summonses Counter
        </h1>
```

- [ ] **Step 4: Verify only those three lines differ**

```bash
diff src/components/SummonsesCounter.vue src/components/MultiSummonsesCounter.vue
```

Expected: exactly three changed hunks, matching the three edits above. Anything
else means the copy was altered — fix it before continuing.

- [ ] **Step 5: Register the route**

In `src/router/routes.ts`, add the import alongside the others:

```ts
import MultiSummonsesCounter from "@/components/MultiSummonsesCounter.vue";
```

and add this entry to the `routes` array, after the `SummonsesCounter` entry:

```ts
  {
    path: "/multi-summonses-counter",
    name: "MultiSummonsesCounter",
    component: MultiSummonsesCounter,
    meta: {
      icon: "/summonses_counter.png",
      title: "Multi Summonses Counter",
    },
  },
```

Note: `icon` deliberately reuses the existing asset — `public/` has no
`multi_summonses_counter.png` yet, and a working duplicate beats a broken
image. Note also that `requiresGuest` is **not** included; see Global
Constraints.

- [ ] **Step 6: Typecheck and build**

```bash
deno task build
```

Expected: vue-tsc reports no errors and vite writes `dist/`.

- [ ] **Step 7: Confirm the existing page is untouched**

```bash
git diff --stat src/components/SummonsesCounter.vue \
                src/composables/useSummonsesCount.ts
```

Expected: no output.

- [ ] **Step 8: Manual verification against the running backend**

In one terminal:

```bash
cd /home/fernando-yu/Documents/sim/simsim-tools
just dev server feat/multi-summonses-counter
```

In another:

```bash
cd /home/fernando-yu/Documents/sim/simsim-tools
just dev front feat/multi-summonses-counter
```

Then, in the browser:

1. The home screen shows a fourth card, "Multi Summonses Counter" (sharing the
   existing summonses icon), and the navbar shows the matching link.
2. Open it, drop a PDF whose page states a quantity greater than one, and press
   Count Summonses. The file's Count reflects the printed quantity, not 1, and
   the page is **not** listed under Removed Pages.
3. Open the original Summonses Counter, drop the same file, and confirm it
   still behaves exactly as before — that page counts it as removed, which is
   the pre-existing behavior this feature deliberately leaves alone.
4. Drop a multi-page document that has no legible `Page X of Y` footer. When
   the footer is unreadable the loop scans forward to the next page matching
   `[0-9].*summons` and counts whatever it finds there. Check both failure
   directions: if a continuation page repeats the quantity, the old tool
   over-counted by 1 and the new one over-counts by that page's printed N;
   and if the OCR instead breaks the line between the digit and the word
   (`"3\nsummonses"`), that page parses fine on its own but does not match
   the forward-scan pattern, so it is silently skipped with no entry in
   Removed Pages — watch for a missing page with no corresponding count.
5. Drop a PDF that the OLD Summonses Counter counts successfully, and confirm
   the new tool counts the same pages and moves none of them into Removed.
   The new regex requires the digit to sit immediately next to the word
   (only whitespace and at most one period between them), whereas the old
   tool's first pattern matched a `1` anywhere earlier on the line. Forms
   like `"1) summonses"` or `"case 1 abc summons"` were counted by the old
   tool and are rejected by the new one — confirm none of your test file's
   pages hit that gap, or note it if they do.

- [ ] **Step 9: Commit**

```bash
git add src/composables/useMultiSummonsesCount.ts \
        src/components/MultiSummonsesCounter.vue \
        src/router/routes.ts
git commit -m "feat(summonses): add multi summonses counter page"
```

---

## Done

Both worktrees hold committed work on `feat/multi-summonses-counter`. Push each
and open its PR:

```bash
git push -u origin feat/multi-summonses-counter
gh pr create --title "feat: add multi summonses counter" --base main
```

The backend PR should merge first — the frontend page is inert without its
endpoint.

## Known follow-ups (not in scope here)

- Add `public/multi_summonses_counter.png` and point the route's `meta.icon` at
  it, so the two home cards are visually distinct.
- The OCR helpers, the page-walk loop, and the counter markup now live in two
  places each. A fix to a crop region or the skip-ahead logic must be applied
  twice, and nothing enforces it.
- The page-walk loop remains untested; that needs real PDFs and tesseract.
- RESOLVED: the manual pass produced the evidence this was gated on. A real
  page OCR'd as `'i. (2: summonses)\n\nings,\n'` and was rejected, so
  `_QUANTITY` was widened to `(\d+)\D*summons(?:es)?\b` — any run of
  non-digits may separate the number from the word.
- Residual risk from that widening: `\D` crosses newlines, so a number on a
  nearby line can attach to a later `summonses` that has no number of its own
  (`'Page 2 of 5\n\nsummonses'` parses as 5). It cannot cross another digit,
  so the nearest preceding number always wins, and the ceiling of 99 filters
  absurd captures. If a real page is ever miscounted this way, the tighter
  pattern is `(\d+)[^\d\n]*\n?[^\d\n]*summons(?:es)?\b`, which allows at
  most one line break inside the gap.
