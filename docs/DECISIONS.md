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

- **P-18 Handing a batch to slim-data** (Jamie, 2026-10-27; slim-data D-95). `send_to_results`
  registers the batch's current version in slim-data: samples, prep method, spike amounts in the
  analysis's unit (only the elements it measures), and each cup's dilution: sample cups → CUP 1, 2…,
  spike cups → SPIKE 1…, in cup-number order. One spike amount per sample and element. Sent once,
  recorded in `prep_book_sent_batches`; a correction after sending is the next slice (D-95 point 4).
  slim-prep depends on slim-data (never the reverse).
- **P-19 Table names start `prep_book_`** (2026-10-27, found building P-18). The database is shared and
  slim-data already has `prep_batches`; migrations 0002–0003 were renamed in place (never released).
  `tests/test_migrations.py` fails on any clash with slim-data's tables.

- **P-20 Sending a correction after handoff** (Jamie, 2026-10-27; slim-data D-96). A batch corrected
  after it was sent goes with `send_correction`: its changed cup dilutions and spike amounts become the
  next versions in slim-data, with the correction's reason; every send is a row in
  `prep_book_sent_batches` (code + version). The samples, cups and spiked elements must be as sent;
  anything else is a new batch. The host then re-evaluates in slim-data; released results it changes go
  through slim-data's correction flow and an amended report.

- **P-21 The planned run list** (Jamie, 2026-10-27; P-13). slim-prep plans what goes on the instrument
  (as the lab's raw-data generator does today, from the prep book); slim-data judges check standards
  against the *actual* order in the instrument file, the evidence (the plan only feeds the instrument).
  1. The lab's rule is data (`PrepRules.run_list`): a check standard between matrices (chemical + prep
     method) and after every N samples of one matrix, counting samples prepped, not cups or spikes; the
     count restarts at each matrix; opening and closing items (demo: calibration blank + check standard;
     check standard). Demo N = 10, Jamie's practice.
  2. Spikes go together at the end of their matrix block, before its check standard, or each after its
     sample: per prep method (`spikes_at_block_end`; demo dilute-and-shoot: after its sample).
  3. Samples run in the order the analyst gives; a new matrix starts wherever the next sample's differs.
  4. Export: a plain CSV sample list (position, label, type, batch, sample, cup, dilution). A
     Qtegra-specific format can come later; the lab's private capture workbook is not copied (OSS).
  - Rejected: the run list in slim-data (it plans nothing; it reads what was run); hard-coded spacing.

- **P-22 `verify` for the prep book** (2026-10-28, P7; as slim-data's D-76). Read-only: every standard
  version is remade from its recipe step and its source as they stood when it was recorded (same
  concentration, elements, expiry); every batch version still passes its rules and its spike lines say
  what the standards book said then; every batch sent to results: slim-data holds the cup dilutions of
  the version last sent. The host's `cli verify` runs it beside slim-data's.

## The 2026-10-28 review (slim-lims-oss `docs/REVIEW_2026-10-28.md`, B1–B10)

Proposed by Claude in one design turn, agreed by Jamie (2026-10-28), who added the picker to P-23.
Guards: `tests/test_review_guards.py` here, `tests/test_prep.py` in slim-lims-oss.

- **P-23 The TR port; samples are picked, not typed** (B1). slim-prep asks the host about each sample
  through `SampleLookup` (`domain/ports.py`, as slim-data's `ReferenceLookup`): its state (not received,
  open, cancelled, closed), the analyses ordered for it and its chemical (name and matched SLIM ID). Every
  sample is checked when a batch is recorded, corrected and sent: it exists, is open, and ordered the
  batch's analysis. The send check catches a request cancelled in between (it replaces the host's own
  check, D-99). The run list groups by the matched chemical, so "IPA" and "isopropanol" are one matrix.
  The new-batch screen lists the open samples that ordered the analysis (`open_samples`) to tick, instead
  of typed IDs (Jamie: "essential … reduces friction"). What no software catches is the wrong bottle with
  the right label on the screen: that stays the bench's label check (barcodes later, slim-samples).
  - Rejected: slim-prep reading the TR tables (modules never read another's tables); checking only at send
    (the analyst finds out at the bench, not later).
- **P-24 A correction keeps what makes the batch that batch** (B2, B9). Code (the key), method, analysis
  and rules version stay; `record_batch` refuses a correction that changes them. A correction is checked
  against the batch's own rules, not the lab's current ones; `move_to_rules(code, rules_id, reason)`
  rechecks the batch under other rules and records it as a new version, with a reason (a button on the
  batch page when newer rules exist).
- **P-25 Times are entered, zoned and bounded** (B4). The prep and pour-out times are entered (the screen
  offers now, in lab time) and must carry a zone (`AwareDatetime`; the host reads a bare time as the
  lab's). Never in the future; the pour-out not after the prep; a new batch's prep no more than
  `PrepRules.entry_window_days` back (demo 7; None: no bound).
- **P-26 Batch codes** (B6, B8). Every code is safe anywhere it goes: letters, digits, `.`, `_`, `-`,
  starting with a letter or digit (no CSV formula, no path in a file name). The lab's series is rules
  data, `PrepRules.batch_prefix` + 4 digits (demo `PREP-0001`); the screen offers the next free code. A new
  batch whose code is already a batch in results is refused; if an instrument file takes the code between
  recording and sending, the send says so plainly. The run-list CSV quotes any cell starting `= + - @`.
  - Rejected: a regex as rules data (harder for quality to write and to read); preventing the file race
    (slim-data would need to know slim-prep: a module rule).
- **P-27 Who, and how the host knows** (B7). The actor carries its identity source (authenticated or
  asserted, as slim-data's D-50); a step records the analyst's initials and the host's id for them; a
  standard records initials and id the same way (it had the id only). The pour-out analyst is chosen
  from the staff list. Records made before this read as before (the new fields are optional).
