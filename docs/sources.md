# Official sources
## CRC Fall 2026 - Fee Payment Deadline

- Verification status: needs_verification
- Source: https://crc.losrios.edu/admissions/financial-aid-and-fees/tuition-and-fees/fee-payment-deadlines
- Section: Fall 2026 Payment Deadlines
- Date checked: 2026-11-11
- Checked by: Hayley Nguyen
- Second checker: Ryan Mejia
- Second check date: 11/12/26

### Rule

For CRC Fall 2026:
- Enrollment on or before July 24, 2026: payment is due on August 7, 2026.
- Enrollment on or after July 25, 2026: payment is due the next day after enrollment.

Supporting source text for the second condition:
“The next day after enrollment date”

### Important exception (FOOTNOTE)

Students who enroll on or after July 25 will not be dropped for non-payment. However, unpaid fees remianing after the term ends will result in a hold on future enrollment until payment is received.

### Agreed demo scenario

- Arrival date: 2026-08-11
- Enrollment date: 2026-08-13
- Simulated date: 2026-08-14
- Calculated payment deadline: 2026-08-14
- Expected reminder, if unpaid: "Payment due today"

### Implementation notes

Calculate the deadline from the enrollment date.
Payment completion should be tracked separately.
This rule does not determine DMV readiness.
The source does not specify an exact payment cutoff time.

### SOURCE URLS

https://crc.losrios.edu/admissions/financial-aid-and-fees/tuition-and-fees/fee-payment-deadlines
