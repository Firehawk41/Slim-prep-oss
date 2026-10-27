# slim-prep — Claude context

> **Read first.** Jamie is the **designer**; Claude writes the code, then explains it until Jamie can
> defend every decision in an interview. Raise any design change as a new decision (with a
> recommendation) before building it; push back when you disagree. **Short replies; Jamie is
> token-constrained.** Read slim-data-oss's CLAUDE.md for the ecosystem's rules; this repo follows them.

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
| `docs/DECISIONS.md` | **Authoritative.** P-01…; append, never edit history. |

## Status

| # | Step | State |
|---|---|---|
| P0 | Prep book layout from Jamie | ✅ evaporation tab + standards (`docs/PREP_BOOK.md`) |
| P1 | Design doc + decisions, signed off | ✅ |
| P2 | Skeleton: packaging, OSS guard, Alembic (own version table), architecture test, CI | ✅ (P-01) |
| P3 | Domain: rules (methods, recipes, shelf life), standards book, batch / cups / weighings, figures | ✅ |
| P4 | Persistence: append-only tables, `as_of`, audit; service `record_standard` / `record_batch` | ✅ |
| P5 | Handoff to slim-data (`PrepBatch`, dilution per cup, run order) | ✅ `send_to_results` (P-18, D-95), `send_correction` (P-20, D-96), run list + CSV (P-21) |
| P6 | Host screens in slim-lims-oss | |
| P7 | Demo scenarios, `verify`, README, walkthrough | |

slim-data D-93 (dilution below 1) and D-94 (MDL from the kept cups) ✅.

## File map

```
slim_prep/
├── domain/        # pure (stdlib + pydantic): base (Frozen, Dec), units (Concentration), rules (PrepRules:
│                  #   methods, recipes, shelf life, lists), standards (Stock, Standard, make_standard),
│                  #   prep (PrepBatch, Cup, Weighing, SpikeLine, figures), run_list (plan_run, run_list_csv: P-21),
│                  #   problems (PrepRefused), actor (Role)
├── persistence/   # oss_guard, db (make_engine = the only create_engine), migrate, migrations/, tables,
│                  #   types, append_only, audit; rules (publish_rules, current_rules), books (stocks,
│                  #   standards, batches: versioned, as_of, made_from, batches_using)
└── service/       # books: record_standard (from the book), record_batch (checks, figures, records);
                   #   handoff: results_batch, send_to_results (registers in slim-data), send_correction, sent_version;
                   #   run_list: run_list_for (recorded batches → the planned run)
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
- slim-prep depends on slim-data (git, on D-95's branch until merged, then `@main`); never the reverse.
- Portable schema (SQLite + Postgres): enums as ints, JSON via SQLAlchemy `JSON`, no ARRAY, no FKs into
  other modules' tables. Repositories flush; the caller commits.
- Every push: ruff, full tests, coverage gate.
