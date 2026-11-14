# Official sources
## CRC Fall 2026 - Fee Payment Deadline

- Verification status: needs_verification
- Source: https://crc.losrios.edu/admissions/financial-aid-and-fees/tuition-and-fees/fee-payment-deadlines
- Section: Fall 2026 Payment Deadlines
- Date checked: 2026-11-11
- Checked by: Hayley Nguyen
- Second checker: Ryan Mejia
- Second check date: 2026-11-12

### Rule

For CRC Fall 2026:
- Enrollment on or before July 24, 2026: payment is due on August 7, 2026.
- Enrollment on or after July 25, 2026: payment is due the next day after enrollment.

Supporting source text for the second condition:
“The next day after enrollment date”

### Important exception (FOOTNOTE)

Students who enroll on or after July 25 will not be dropped for non-payment. However, unpaid fees remaining after the term ends will result in a hold on future enrollment until payment is received.

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

## Day 2 task sources — November 14, 2026

These entries support the expanded `data/rules/rules.json`. Each rule retains its URL, evidence excerpt and check metadata in that file. All rules remain **needs_verification** pending human source review. The existing CRC fee entry and rule above are preserved.

The eight new excerpts were matched against retained official source text retrieved November 13. The DSO wording and ID-application excerpt were checked against those snapshots again November 14; this is not a new website retrieval. November information is not archived proof of August policy.

| Rule ID | Publisher / source | Scope |
| --- | --- | --- |
| rule_i94_retrieval_guidance | [USAGov — Form I-94 arrival-departure record](https://www.usa.gov/arrival-departure-record) | Retrieve or print an existing admission record; not a provisional I-94 purchase. |
| rule_i901_payment_record | [ICE — I-901 SEVIS Fee FAQ](https://www.ice.gov/sevis/i901/faq) | Review payment evidence; continuing and transfer exceptions may apply. |
| rule_generic_f1_arrival_reporting | [DHS, Study in the States — Maintaining Status](https://studyinthestates.dhs.gov/students/study/maintaining-status) | General DSO contact guidance; school-specific procedures are unverified. |
| rule_crc_arrival_reporting | [CRC — International Students Office](https://crc.losrios.edu/student-resources/support-services/international-students-office) | Report promptly after arrival; check-in does not prove SEVIS activation. |
| rule_california_real_id_residency | [California DMV — REAL ID Checklist](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/real-id-checklist/) | Two printed residency documents for REAL ID; follow the checklist exceptions. |
| rule_california_id_application | [California DMV — Identification (ID) Cards](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/identification-id-cards/) | Application and office steps; use the REAL ID checklist for that path. |
| rule_bank_account_identification_guidance | [CFPB — Checklist for Opening an Account](https://files.consumerfinance.gov/f/documents/cfpb_adult-fin-ed_checklist-for-opening-an-account.pdf) | Provider requirements vary, including acceptance without an SSN. |
| rule_dso_sevis_confirmation_referral | [DHS, Study in the States — Driving in the United States](https://studyinthestates.dhs.gov/students/study/driving-in-the-united-states) | Official driving guidance: confirm Active status with the DSO before a driver’s-license application. Not a REAL ID-card prerequisite. |

### Recommendations and source display

Only include recommendations explicitly supported by an official source. Display **Official recommendation**, the publisher, source page title/link, applicable context, check date and verification status. Task priority is separate from this label. Personal experiences, forum posts and platform-inferred advice are excluded.

The DSO recommendation concerns driver's-license applications. If shown beside the REAL ID task, identify it as related driving guidance. It does not create a hard blocker or guarantee DMV/SAVE acceptance. The rule keeps high_risk=true so individual status questions can be referred to the DSO; AI referral and FE display still need integration.

The student profile's has_ssn=false does not distinguish SSN-ineligible from SSN-pending. These rules do not determine SSN or immigration eligibility.
