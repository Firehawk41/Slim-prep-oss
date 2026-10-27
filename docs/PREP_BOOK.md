# The prep book as the lab keeps it today (input to the design)

Jamie, 2026-10-27. The lab's Excel prep book; the OSS version is invented from this (D-86).

## Evaporation tab

`Date · Analyst: Pour Out · Analyst: Prep · Customer · Chemical · Sample ID · Time Code · Cup # ·
Tare (G) · Cap (G) · Gross (G) · Net (G) · Spike Volume (uL) · Spike Level (ppt) · Final (G) ·
Dilution · Average · Number of Elements · Additional Elements · 100 uL Pipette used · 1000 uL Pipette used`

- One row per cup; a sample has several cups.
- **Time Code** = turnaround (TAT): from the TR.
- **Customer, Chemical, Sample ID, Number of / Additional Elements**: from the TR.
- **Net = Gross − Tare − Cap.** The cap is weighed with the sample but left out afterwards: lids get
  mixed up once the sample is evaporated.
- **Final** = cup + made-up solution (evaporation has no taring), so the solution is Final − Tare.
- **Dilution = Final ÷ Net** (Jamie). Evaporation concentrates, so it can be below 1. *To settle in the
  design: Final ÷ Net or (Final − Tare) ÷ Net, given Final includes the cup.*
- **Average** = average dilution of the sample's cups; MDL = IDL × average dilution. In SLIM: average
  only when both cups are kept, else the kept cup's (slim-data D-94).
- **Spike**: one multi-element standard; some elements (e.g. S) are spiked separately with their own
  standard. Standards will be registered in the quality module.
- **Pipettes**: which 100 µL and 1000 µL pipettes were used.

## Other preps

Dilute-and-shoot: same idea; no pre-weighed cups (the vial is tared), no Pour Out analyst. Labs set
their own columns per prep method: the layout is lab data, not code.
