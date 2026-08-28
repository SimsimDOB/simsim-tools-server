# Multi Summonses Counter — Design

Date: 2026-08-23
Branch: `feat/multi-summonses-counter` (both repos)
Status: approved, not yet implemented

## Problem

The existing Summonses Counter adds a fixed `1` for every page whose OCR'd
top-right region matches a summons pattern:

```python
# summonses_count_service.py
if re.search(r"1.*summons", summonses_str) or re.search(
    r"[0-9].*summons[^es]", summonses_str
):
    count += 1
```

A page that states a quantity — `"3 summonses"` — is therefore counted as one
summons. Worse, it is not counted at all: the first branch requires a literal
`1`, and the second requires a character after `summons` that is neither `e`
nor `s`, which the plural spelling fails. Such pages fall through to the `else`
and are reported as removed.

The frontend already accepts many *files*; the limitation is many *summonses
per page*.

## Goal

A second tool — **Multi Summonses Counter** — that reads the quantity printed
on each matching page and sums it. The existing counter keeps its current
behavior, unchanged.

## Confirmed requirements

1. **Quantity semantics.** A page states a quantity as a digit followed by the
   plural word: `"2 summonses"`, `"3 summonses"`. Count that number, not 1.
2. **Once per document.** The quantity appears on a document's first page only.
   The existing `Page X of Y` skip-ahead walk carries over unchanged; there is
   no double-counting risk.
3. **The old tool is untouched.** Not extended, not flagged, not refactored.
   The new tool is a parallel page with its own endpoint and its own service.
4. **Same result columns** as the existing page: File Name / Count / Removed /
   Removed Pages, plus a total.

## Approach: full copy (decided)

Considered and rejected:

- **Shared OCR helpers, separate counting loops.** Move `__page_to_image`,
  `__crop_summonses`, `__crop_pages`, `__get_skip_pages` into a shared module
  imported by both services; likewise extract the Vue markup into a
  presentational component. Rejected in favor of zero edits to the working
  tool.
- **One service with a mode flag.** Rejected: it modifies the existing code
  path, which requirement 3 forbids.

### Accepted debt

The four OCR helpers, the page-walk loop, and the counter's Tailwind markup
will exist in two places. A future fix to a crop region or to the skip-ahead
logic must be applied twice, and nothing enforces that. This is a deliberate
trade for not touching a tool that currently works.

## Backend — `simsim-tools-server`

### New files

- `src/simsim_tools_server/services/multi_summonses_count_service.py`
- `src/simsim_tools_server/api/v1/endpoints/multi_summonses_count.py`

### Modified

- `src/simsim_tools_server/api/router.py` — one `include_router` line.

### The counting rule

The service is a copy of `summonses_count_service.py`. The only behavioral
change is in the per-page branch:

```python
_MAX_QUANTITY = 99
_QUANTITY = re.compile(r"(\d+)\D*summons(?:es)?\b", re.IGNORECASE)


def parse_summons_quantity(text: str) -> int | None:
    """Read the summons quantity from a page's OCR'd text.

    Returns None when no quantity is legible, or when the value exceeds
    _MAX_QUANTITY (OCR joining two numbers is the realistic failure mode,
    and it is invisible in a bare total).
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

The loop then does `count += quantity` where the original did `count += 1`.
A `None` result takes the `else` branch: the page is recorded in
`removed_pages` and logged at WARNING with the raw OCR string, so a systematic
OCR failure is visible rather than silent.

Any run of non-digits may separate the number from the word — real OCR
yields list markers, brackets and colons (`'i. (2: summonses)'`) and
sometimes a line break. `\D` never crosses another digit, so the nearest
preceding number wins. This matches the permissiveness of the forward-scan
pattern the page-walk loop already uses (`[0-9].*summons`).

The `\b` anchor also removes the original's dependence on a trailing
character, so text ending exactly at `"2 summons"` now parses.

### Semantics note

`count` becomes a count of *summonses* while `removed_count` remains a count
of *pages*. The two columns are no longer commensurable — 4 summonses and 2
removed does not imply a 6-page document. Accepted, per requirement 4.

### Response shape

Unchanged from the existing endpoint, including the per-file `try`/`except`
so one unreadable PDF does not sink the batch:

```json
{
  "total_count": 12,
  "details": [
    {"filename": "a.pdf", "count": 7, "removed_count": 2, "removed_pages": "3, 9"},
    {"filename": "b.pdf", "error": "..."}
  ]
}
```

## Frontend — `simsim-tools`

### New files

- `src/composables/useMultiSummonsesCount.ts` — copy of
  `useSummonsesCount.ts`, posting to `/v1/multi-summonses-count`.
- `src/components/MultiSummonsesCounter.vue` — copy of
  `SummonsesCounter.vue`; heading and composable import swapped.

### Modified

- `src/router/routes.ts` — one entry:

```ts
{
  path: "/multi-summonses-counter",
  name: "MultiSummonsesCounter",
  component: MultiSummonsesCounter,
  meta: {
    icon: "/summonses_counter.png",
    title: "Multi Summonses Counter",
  },
}
```

`Navbar.vue` and `Home.vue` both derive from `routes`, so the nav link and the
home card appear with no further change.

### Two decisions

- **Icon.** `public/` has no asset for the new tool. `meta.icon` points at the
  existing `summonses_counter.png` so the page ships working; the home screen
  will show two identical cards until a `multi_summonses_counter.png` is added
  and the one line updated.
- **`requiresGuest`.** The existing summonses route carries
  `meta: { requiresGuest: true }`, but nothing reads it — there is no
  navigation guard, `router/index.ts` does not reference it, and the other
  routes lack it. Treated as vestigial and not copied.

## Testing

### Backend (TDD — parser tests written first)

`parse_summons_quantity` is pure and is the only piece with real logic.

`tests/services/test_multi_summonses_count_service.py`:

| Input (OCR text is lowercased upstream) | Expected |
| --- | --- |
| `"1 summons\n"` | `1` |
| `"1. summonses\n"` | `1` |
| `"3 summonses\n"` | `3` |
| `"12 summonses"` | `12` |
| `"3summonses"` | `3` |
| `"2 summons"` (string ends here) | `2` |
| `"summonses\n"` | `None` |
| `""` | `None` |
| `"3 sumnonses"` (OCR noise) | `None` |
| `"400 summonses"` | `None` (ceiling) |

`tests/api/test_multi_summonses_count.py`, service mocked:

- two files sum into `total_count`;
- one file raising still yields an `error` entry for it *and* a real count for
  the other.

### Not tested, deliberately

The page-walk loop and the crop regions. Both need real PDFs and a tesseract
binary, which is out of scope. A regression in the skip-ahead logic would not
be caught by this suite.

### Frontend

No test runner exists in that repo. Verification is `deno task build`
(vue-tsc typecheck + vite build) plus a manual pass: drop a multi-summons PDF,
confirm the per-file count and the total.

## Delivery

Two worktrees on the branch `feat/multi-summonses-counter`, one per repo, and
two PRs, per the workspace convention.
