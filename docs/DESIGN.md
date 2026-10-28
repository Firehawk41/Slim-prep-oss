# slim-prep — design

Input: `docs/PREP_BOOK.md` (Jamie's prep book and standards spreadsheet). Signed off by Jamie
2026-10-27 ("go until you need input") after Q1–Q6 were answered; the decisions are in `DECISIONS.md`.

## 1. Purpose and boundaries

The prep book, out of Excel: what was prepped, by whom, when, with which weighings, spikes and
equipment, and the dilution factor that follows. When a batch is ready it goes to slim-data.

- **In:** prep batches, cups, weighings, calculated dilution, spikes (standard, lot, expiry), pipettes
  and balance, analysts and times, notes / deviations, the run order.
- **Not in:** sample custody and storage (slim-samples, phase 4), the standards and equipment registers
  (slim-quality, phase 5), results (slim-data), TR data (the host).

## 2. Place in the ecosystem

```
slim-lims-oss (host: screens, transaction, TR data, staff)
   ├── slim-prep  ── hands a ready batch to ──►  slim-data (results)
   └── slim-data
```
slim-prep depends on slim-data's domain types for the handoff; slim-data never imports slim-prep.
TR data (customer, chemical, sample ID, TAT, analyses ordered) and staff come through ports the host
implements, as in slim-data (`ReferenceLookup`, `StaffDirectory`).

## 3. Model

- **P-02 Prep methods are data.** A `PrepMethod` (versioned, published like a ruleset) lists the fields
  its book uses and how they're calculated: evaporation = pre-weighed cup, cap weight, Pour Out analyst,
  2 cups; dilute-and-shoot = tared vial, one analyst. Labs add their own; no `if method == ...` in code.
- **P-03 Batch → sample → cup.** A `PrepBatch` (code, method version, analysis) holds samples; each
  sample holds cups (`Cup #` → slim-data replicate 1, 2). One cup = one row of today's book.
- **P-04 Who and when per step.** Each step (pour out, prep) records its analyst and time; the method
  says which steps it has.
- **P-05 Weighings, entered in grams as Decimals** (never floats): Tare, Cap, Gross, Final. Calculated,
  never typed:
  - Net = Gross − Tare − Cap (Cap = 0 when the method has none).
  - Solution = Final − Tare (Tare = 0 for a tared vial: the balance reads the solution directly).
  - **Dilution = Solution ÷ Net** = (Final − Tare) ÷ Net (Jamie, Q1).
  - Below 1 is fine (evaporation, slim-data D-93). The average across kept cups is slim-data's (D-94).
- **P-06 Spikes.** A spike line per cup: standard, lot, expiry, volume (µL), level (ppt). Several lines
  when an element (e.g. S) is spiked separately. An expired standard is refused at entry. Lot and expiry
  name a standard from the standards book (P-14), whose concentration and expiry are snapshotted on
  the line. The spike goes in its own spiked cup (Jamie, Q2), slim-data's SPIKE reading. **Spike level is
  calculated** (Jamie, Q2b), never typed: added = volume × standard concentration ÷ the spiked cup's
  Net, in the sample's terms (10 µL of 1 ppm into 10 g = 1 ppb = 1000 ppt). The standard is taken as
  1 g/mL. That is slim-data's `SpikeAddition.added`.
- **P-07 Equipment** (100 µL / 1000 µL pipette, balance) chosen from a lab list (data). The balance is
  set once per batch ("all weights from balance X unless noted", today's book) and can be overridden per
  cup. The equipment register and calibration-due checks belong to slim-quality (phase 5); until then the
  list is plain data here.
- **P-08 QC in the batch:** method blank, CRM (prepped like a sample) and their expected values, which
  feed slim-data's `prep_batch_qc` (D-87). Not rows in today's book (Jamie, Q4): to design with the
  standards book (P-14).
- **P-14 The standards book, a second section of slim-prep.** Today a separate spreadsheet holds the
  calibration standards (header in `PREP_BOOK.md`). One entry per standard made: name, prep date,
  expiry, analyst, pipettes, and its **source** (another standard, by name + prep date, or a purchased
  stock). That makes a chain from every spike back to the stock: the traceability ISO 17025 asks for.
  A standard is identified by name + prep date, as today. Spike lines and check standards name one;
  an expired one is refused. Purchased stocks and CRMs are registered in slim-quality later; until then
  a stock is a name, lot, concentration, elements and expiry typed here.
- **P-15 Recipes: the lab's standard dilution chains** (Jamie, Q5: "standardized"). A recipe is a named
  chain from a stock, e.g. 1000 ppm → 20 ppm → 50 ppb; each step says its source (the stock or the step
  before), the volume taken (µL), the final volume (mL) and its shelf life. Making a standard = a recipe
  step + the actual source + date, analyst, pipettes. Its concentration (source's × volume ÷ final
  volume) and expiry are calculated, never typed. Recipes are the lab's defaults, saved as rules (P-17).
- **P-16 Shelf life and expiry are the lab's rules** (Jamie, Q6). Each recipe step has its own shelf
  life (demo: 20 ppm 3 months, 50 ppb 1 week), independent of the stock's. Expiry = prep date + shelf
  life, capped at the source's expiry unless the lab's rules say otherwise (default: capped). A source
  already expired on the prep date is refused.
- **P-17 Boundaries: quality sets the rules, the lab keeps the records.** Recipes, shelf lives, prep
  method layouts and equipment lists are one versioned **prep policy** (`PrepRules`), published like a
  slim-data ruleset; every standard and batch records the version it was made under. Only a `quality`
  role publishes (the host's role; supervisor until it exists); analysts may draft a change for quality
  to approve. slim-prep reads the rules through a port, so slim-quality can supply them later without
  prep changing. No module writes another's tables: quality reads prep's records and raises findings in
  its own; corrections go through slim-prep's correction flow, with a reason.
- **P-09 Notes and deviations** on any cup or batch, free text: the escape hatch Excel gives today.

## 4. Persistence and history

- **P-10 Append-only, as slim-data:** rows are never updated or deleted (triggers); a correction is a
  new version with a reason and who made it; `as_of` shows any past state. Portable schema, own Alembic
  version table, no FKs into other modules' tables. Repositories flush; the host commits.

## 5. Handoff to slim-data

- **P-11 "Ready" sends the batch:** slim-prep builds slim-data's `PrepBatch` (code, analysis, prep
  method, samples, spikes, QC expected values) and each cup's dilution. After that, a correction to a
  weighing is a new version, and slim-data re-evaluates (its correction flow).
- **P-12 Dilution from prep beats the file.** Today the dilution comes from the instrument file
  (`dilution_factor` / Qtegra's Dilution Factor). When a batch came from slim-prep, its cups' dilutions
  win; a file that disagrees is flagged at import. Needs a slim-data decision (D-95) when we get there.
- **P-13 Run order:** the batch's cups in run order, exportable as the instrument's sample list. This
  unlocks CCV bracketing in slim-data (D-87 point 4). Later step.

## 6. Build order

P3 domain (methods, batch, cups, calculations) → P4 persistence → P5 handoff (+ slim-data D-95) →
P6 host screens (a grid like today's book) → P7 demo scenarios, `verify`, walkthrough.

## 7. Parked

Balance integration (weights read from the balance), equipment calibration checks and the standards
register (slim-quality), label printing, the instrument sample-list export format.
