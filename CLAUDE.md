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
| `docs/PREP_BOOK.md` | The lab's Excel prep book as Jamie described it: the design's input. |
| `docs/DECISIONS.md` | **Authoritative.** P-01…; append, never edit history. |

## Status

| # | Step | State |
|---|---|---|
| P0 | Prep book layout from Jamie | ◐ evaporation tab (`docs/PREP_BOOK.md`) |
| P1 | Design doc + decisions, signed off | next |
| P2 | Skeleton: packaging, OSS guard, Alembic (own version table), architecture test, CI | ✅ (P-01) |
| P3 | Domain: batch, cups, weighings, dilution, spikes, equipment, run list | |
| P4 | Persistence: append-only tables, `as_of`, audit | |
| P5 | Handoff to slim-data (`PrepBatch`, dilution per cup, run order) | |
| P6 | Host screens in slim-lims-oss | |
| P7 | Demo scenarios, `verify`, README, walkthrough | |

Needs slim-data first: D-93 (dilution below 1), D-94 (MDL from the kept cups' average dilution).

## File map

```
slim_prep/
├── domain/        # pure (stdlib + pydantic): empty until P3
├── persistence/   # oss_guard, db (make_engine = the only create_engine), migrate, migrations/, tables
└── service/       # what the host calls: empty until P5
tests/             # conftest (SQLite per test, or TEST_DATABASE_URL); architecture, OSS guard, migrations
.github/workflows/ci.yml  # ruff + {SQLite, Postgres 16} × {3.11, 3.12} + 95% branch coverage on domain
```

Run: `pip install -e ".[dev]" && pytest`; `ruff check . && ruff format --check .`.

## Rules for the build

- `domain/` imports only stdlib + pydantic; enforced by `tests/test_architecture.py`.
- Values are Decimals, never floats; compare unrounded, round once at the end (as slim-data).
- Prep layouts, limits and equipment lists are lab **data**, never `if demo:` branches. Demo values are
  invented, never a real lab's.
- Portable schema (SQLite + Postgres): enums as ints, JSON via SQLAlchemy `JSON`, no ARRAY, no FKs into
  other modules' tables. Repositories flush; the caller commits.
- Every push: ruff, full tests, coverage gate.
