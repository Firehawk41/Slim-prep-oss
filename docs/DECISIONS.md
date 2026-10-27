# slim-prep — decisions

Append new decisions; never edit history except to mark a same-day revision. Ecosystem-wide
decisions (D-xx) live in slim-data-oss `docs/DECISIONS.md`; D-86 created this module.

- **P-01 Repository and layers** (Jamie, 2026-10-27: build the skeleton first). slim-prep is a library
  shaped like slim-data: the host (slim-lims-oss) calls it, owns the transaction and provides the screens.
  1. `domain/` is pure (stdlib + pydantic; `tests/test_architecture.py`): weighings, dilution factors
     and spikes are calculated there, testable without a database. 95 % branch coverage on it in CI.
  2. `persistence/` mirrors slim-data's: the OSS guard (`SLIM_PREP_ALLOWED_DB_HOSTS`), `make_engine` as
     the only `create_engine`, its own Alembic version table `alembic_version_slim_prep`, portable
     schema (SQLite + Postgres), no FKs into other modules' tables. Repositories flush; the caller commits.
  3. `service/` is what the host calls. The handoff to slim-data comes with the design (P5); slim-prep
     will depend on slim-data, never the reverse.
  - Rejected: prep tables inside slim-data (D-86: two sets of users and records).

- **P-02…P-17 The design** (Jamie, 2026-10-27, after Q1–Q6; full text in `DESIGN.md` §3–5). In short:
  - P-02 prep methods are data (which weighings and steps a book uses); P-03 batch → sample → cup, one
    cup per row of today's book; P-04 analyst and time per step (pour out, prep).
  - P-05 Net = Gross − Tare − Cap; dilution = (Final − Tare) ÷ Net, calculated, may be below 1.
    Rejected: typing the dilution (today's transcription risk).
  - P-06 a spike goes in its own cup; level = volume × standard concentration ÷ Net, calculated (µL as mg).
  - P-07 balance per batch, overridable per cup; pipettes per cup; plain lists until slim-quality.
  - P-08 blank / CRM in the batch: later, with the standards book. P-09 free-text notes everywhere.
  - P-10 append-only with corrections and `as_of`, as slim-data.
  - P-11 "ready" builds slim-data's `PrepBatch` + each cup's dilution; P-12 prep's dilution beats the
    instrument file's (slim-data D-95, to come); P-13 run order, later.
  - P-14 the standards book: standards by name + prep date, each with its source, a chain to the stock.
  - P-15 recipes (1000 ppm → 20 ppm → 50 ppb) as the lab's defaults; concentration and expiry calculated.
  - P-16 shelf life per recipe step; expiry capped at the source's unless the lab's rules say not
    (default capped); an expired source is refused.
  - P-17 quality publishes the rules (one versioned `PrepRules`), the lab keeps the records; rules come
    through a port so slim-quality can own them later; no module writes another's tables.
    Rejected: rules inside slim-quality now (it doesn't exist; prep would wait on it); rules typed per
    standard (no defaults, no control).
