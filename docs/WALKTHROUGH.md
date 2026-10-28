# slim-prep walkthrough

For Jamie: each part, what to show, and the decision behind it (the question an interviewer would ask).
Open the demo (slim-lims-oss, after `scripts/seed_demo.py`) as the supervisor persona, then **Prep**.

## 1. The rules are data (P-02, P-15–P-17)
- **Show:** the prep book page names the rules it runs under ("demo prep rules").
- **Why:** labs differ (evaporation weighs a cap, dilute-and-shoot tares the vial; shelf lives; how
  often a check standard runs). Code holds no lab's practice, so another lab is a different rules file,
  not a fork. Quality publishes them (a supervisor until there is a quality role); every standard and
  batch records the version it was made under, so a change never rewrites history.

## 2. The standards book (P-14–P-16)
- **Show:** the 20 ppm and 50 ppb standards: concentration and expiry calculated; "From" names the source.
- **Why:** ISO 17025 traceability: any result → its spike → the standard → the stock lot. Expiry is the
  recipe step's shelf life, capped at the source's by default (the lab may lift the cap). An expired
  source is refused at entry, not found at audit.

## 3. The batch grid (P-03–P-07)
- **Show:** "New prep batch": the next code in the lab's series (PREP-0002) is filled in; "Choose the
  samples" lists only samples checked in that ordered the analysis (P-23). Then batch PREP-0001: one row
  per cup, as the Excel tab, with the prep and pour-out times entered and the pour-out analyst chosen
  from the staff list (P-25, P-27). The batch page shows net, solution, dilution (0.06: evaporation
  concentrates) and spike level, unrounded.
- **Why:** typing a dilution is the classic transcription error; here it follows from the weighings.
  Picking samples instead of typing them removes the other one, and every sample is checked against its
  request again when recorded and sent. A grid the rules refuse comes back with every problem and the
  entries kept. A correction stays under the batch's own rules; moving to newer ones is its own step (P-24).

## 4. Sending to results (P-18, slim-data D-95)
- **Show:** "Sent to results: version 1"; in Results, the batch's readings carry 0.06.
- **Why:** the prep book is the source of the dilution. The instrument file may leave it at 1; any
  other value that disagrees is refused (a sequence mix-up would otherwise reach a report).

## 5. A correction (P-20, slim-data D-96)
- **Show:** version 2, "Sample 1 cup 2: final weight misread"; the correction sent; in Results, the
  released result waiting for its correction.
- **Why:** nothing is overwritten. The corrected dilution reaches the readings when the batch is
  evaluated (the readings themselves never change), slim-data re-evaluates, and a released result goes
  through its correction flow and an amended report. `verify` still replays every old version exactly.

## 6. The run list (P-21) and check standards (slim-data D-97)
- **Show:** "Run list (CSV)": a check standard between matrices and after every 10 samples.
- **Why:** slim-prep plans the run; slim-data judges what actually ran (the file's order), so a failed
  check standard flags only the samples it brackets. An analyst may overrule a failed check with a
  reason, if the lab's policy says so: auditable, and four-eyes still applies.

## 7. verify (P-22)
- **Show:** `python -m slim_lims.cli verify`: results replayed, audit chain, "Prep book: … all hold."
- **Why:** the record proves itself: every standard remade, every batch rechecked, and slim-data
  holding the dilutions the prep book sent.

## Boundaries
slim-prep owns the prep records; quality owns the rules (through a port slim-quality can take over);
slim-data owns results. No module writes another's tables (slim-prep's are all `prep_book_*`, P-19).
