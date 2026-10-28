# slim-prep — Claude context

> **Read first.** Jamie is the **designer**; Claude writes the code, then explains it until Jamie can
> defend every decision in an interview. Raise any design change as a new decision (with a
> recommendation) before building it; push back when you disagree. **Short replies; Jamie is
> token-constrained.** Log who decided what in slim-lims-oss `docs/DEV_DIARY.md`. Read slim-data-oss's CLAUDE.md for the ecosystem's rules; this repo follows them.

## What this is

The **prep module** of SLIM (slim-data D-86; roadmap phase 1 in slim-lims-oss `docs/ROADMAP.md`): the
lab's prep book, out of Excel and into the LIMS. Prep batches, weighings, calculated dilution factors,
spikes with standard lot and expiry, pipettes and balance, who and when, the run list. Hands each batch
to slim-data's batch API. A **library**: slim-lims-oss calls it, owns the transaction and provides the
screens. **OSS sandbox only:** demo data, never a real lab's databases (`persistence/oss_guard.py`).

## Documents

| File | What |
|---|---|
| `docs/PREP_BOOK.md` | The lab's Excel prep book and standards spreadsheet as Jamie described them. |
| `docs/DESIGN.md` | **Signed off** 2026-10-27: P-02…P-17. |
| `docs/DECISIONS.md` | **Authoritative.** P-01…P-22; append, never edit history. |
| `docs/WALKTHROUGH.md` | The guided tour: what to show and the decision behind each part. |

## Status

P0–P7 done and merged (prep book layout, design P-02…P-17, skeleton, domain, persistence, handoff to
slim-data, host screens in slim-lims-oss, demo scenario and `verify`). Decisions P-01…P-22 in
`docs/DECISIONS.md`. Open: the walkthrough with Jamie (on Render); review items **B1–B10** in slim-lims-oss
`docs/REVIEW_2026-10-28.md` (TR port, corrections keep code / method / analysis / rules version, grid
lines and field parsing, prep time entered, batch code pattern, `Actor` with identity source, CSV cells).
Working defaults (batches, quiet runs, reviews with the checklist): slim-lims-oss CLAUDE.md.

## File map

```
slim_prep/
├── domain/        # pure (stdlib + pydantic): base (Frozen, Dec), units (Concentration), rules (PrepRules:
│                  #   methods, recipes, shelf life, lists), standards (Stock, Standard, make_standard),
│                  #   prep (PrepBatch, Cup, Weighing, SpikeLine, figures), run_list (plan_run, run_list_csv: P-21),
│                  #   problems (PrepRefused), actor (Role)
├── persistence/   # oss_guard, db (make_engine = the only create_engine), migrate, migrations/, tables,
│                  #   types, append_only, audit; rules (publish_rules, current_rules), books (stocks,
│                  #   standards, batches: versioned, as_of, list_*, made_from, batches_using)
├── demo.py        # DEMO_RULES, demo_stock: invented, the host seeds them
└── service/       # books: record_standard (from the book), record_batch (checks, figures, records);
                   #   handoff: results_batch, send_to_results (registers in slim-data), send_correction, sent_version;
                   #   run_list: run_list_for (recorded batches → the planned run);
                   #   verify: remake every standard, recheck every batch, compare with slim-data (P7)
tests/             # factories (demo rules, chain, batch); domain/; conftest (SQLite per test, or TEST_DATABASE_URL); architecture, OSS guard, migrations
.github/workflows/ci.yml  # ruff + {SQLite, Postgres 16} × {3.11, 3.12} + 95% branch coverage on domain
```

Run: `pip install -e ".[dev]" && pytest`; `ruff check . && ruff format --check .`.

## Rules for the build

- `domain/` imports only stdlib + pydantic; enforced by `tests/test_architecture.py`.
- Values are Decimals, never floats; compare unrounded, round once at the end (as slim-data).
- Prep layouts, limits and equipment lists are lab **data**, never `if demo:` branches. Demo values are
  invented, never a real lab's.
- Table names start `prep_book_` (P-19): the database is shared with slim-data.
- slim-prep depends on slim-data (git, `@main`); never the reverse.
- Portable schema (SQLite + Postgres): enums as ints, JSON via SQLAlchemy `JSON`, no ARRAY, no FKs into
  other modules' tables. Repositories flush; the caller commits.
- Every push: ruff, full tests, coverage gate.
