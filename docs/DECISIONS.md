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
