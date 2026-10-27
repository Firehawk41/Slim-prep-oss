# slim-prep

The sample preparation module of SLIM, an open-source LIMS for an ISO 17025 analytical chemistry lab
(portfolio demo). It takes the lab's prep book out of Excel: who prepped what, weighings, calculated
dilution factors, spikes with their standards, the pipettes used and the run list. When a batch is ready
it goes to [slim-data](https://github.com/Firehawk41/slim-data-oss), which decides the results.

**Status:** skeleton (P-01). The design is next; see `docs/PREP_BOOK.md` and `docs/DECISIONS.md`.
**OSS sandbox only:** demo data, never a real lab's databases (`slim_prep/persistence/oss_guard.py`).

```bash
pip install -e ".[dev]" && pytest          # Postgres: TEST_DATABASE_URL=postgresql+psycopg2://...
ruff check . && ruff format --check .
```
