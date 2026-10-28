# slim-prep

The sample-preparation module of SLIM, an open-source LIMS for an ISO 17025 analytical chemistry lab
(portfolio demo). It takes the lab's prep book out of Excel: who prepped what and when, the weighings,
the spike standards and the chain they came from, the pipettes and balance, and the run list. Everything
that follows from the entries (net weight, dilution factor, spike level, a standard's concentration and
expiry) is calculated, never typed. A finished batch goes to
[slim-data](https://github.com/Firehawk41/slim-data-oss), which decides the results.

**OSS sandbox only:** demo data, never a real lab's databases (`slim_prep/persistence/oss_guard.py`).

## What it does

| | |
|---|---|
| **Prep rules** | Versioned data quality publishes: prep-method layouts, standard recipes (1000 ppm → 20 ppm → 50 ppb) with shelf lives, balance and pipette lists, the run-list rule. Nothing lab-specific is code. |
| **Standards book** | Each standard made from a recipe step and its source, concentration and expiry calculated; a chain back to the purchased stock. An expired source is refused. |
| **Prep book** | Batch → sample → cup. Net = Gross − Tare − Cap; dilution = (Final − Tare) ÷ Net (below 1 when evaporation concentrates); spike level = volume × concentration ÷ net. Every problem reported at once. |
| **History** | Append-only (database triggers); a correction is the next version with a reason; any past state by `as_of`. |
| **Handoff** | `send_to_results` registers the batch in slim-data with each cup's dilution; `send_correction` sends a later correction, and slim-data re-evaluates. |
| **Run list** | A check standard between matrices and after every N samples (the lab's rule), spikes where the method says; a CSV sample list. |
| **verify** | Remakes every standard, rechecks every batch, and compares what slim-data holds. |

The screens live in the host app, [slim-lims-oss](https://github.com/Firehawk41/slim-lims-oss) (`/prep`).
Design: `docs/DESIGN.md`; decisions with the options weighed: `docs/DECISIONS.md`; a guided tour:
`docs/WALKTHROUGH.md`.

```bash
pip install -e ".[dev]" && pytest          # Postgres: TEST_DATABASE_URL=postgresql+psycopg2://...
ruff check . && ruff format --check .
```
