# Official sources
## CRC Fall 2026 - Fee Payment Deadline

- Verification status: verified
- Date verified: 2026-11-12
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

### Structured deadline (STU-D07-due-dates, 2026-11-17)

`rule_crc_fall_2026_payment_deadline` in `rules.json` now also carries both conditions above
as data: `"deadline": {"from": "enrollment_date", "cutoff": "2026-07-24", "due_if_by_cutoff":
"2026-08-07", "days_after": 1}`. No new facts: the same verified rule, written so the app can
work out a student's due date from their enrollment date.

### Implementation notes

Calculate the deadline from the enrollment date.
Payment completion should be tracked separately.
This rule does not determine DMV readiness.
The source does not specify an exact payment cutoff time.

### SOURCE URLS

https://crc.losrios.edu/admissions/financial-aid-and-fees/tuition-and-fees/fee-payment-deadlines

## Day 2 task sources — November 14, 2026

These entries support the expanded `data/rules/rules.json`. Each rule retains its URL, evidence excerpt and check metadata in that file. The Day 2 task rules remain **needs_verification** pending human source review. The CRC payment rule above records its completed checks.

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

## Day 3 before-you-go sources — November 14, 2026

Used by the internal handoff and student guide. Each entry carries the rule ID used in the proposed `before_you_go` blocks. All referenced rules remain `needs_verification`. See `last_checked` for the date recorded on each rule.

| Rule ID | Official source | Supports | Evidence in the rule |
| --- | --- | --- | --- |
| `rule_i94_retrieval_guidance` | [USAGov — Form I-94 arrival-departure record](https://www.usa.gov/arrival-departure-record) | Retrieve an existing electronic I-94 and print it if needed | See your most recent I-94 form and print it, in case you need your record of legal admission to the U.S. |
| `rule_california_real_id_residency` | [California DMV — REAL ID Checklist](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/real-id-checklist/) | Printed residency evidence, examples and address exceptions | To prove that you live in California, you must present TWO DIFFERENT printed documents that show your California mailing address. |
| `rule_crc_arrival_reporting` | [CRC — International Students Office](https://crc.losrios.edu/student-resources/support-services/international-students-office) | Arrival reporting instruction | It is important to report to the CRC International Student Advisor as soon as you arrive. |
| `rule_dmv_real_id_identity` | [California DMV — REAL ID Info: Non-U.S. Citizens](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/what-is-real-id/real-id-info-non-u-s-citizens/) | Identity documents and conditional name changes | Unexpired foreign passport with valid U.S. Visa and approved I-94 form |
| `rule_dmv_id_fee` | [California DMV — Licensing Fees](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/licensing-fees/) | $40 regular original ID and $11 reduced-fee ID for qualifying applicants | ID Card Fees table: Regular ID card / Original / $40 |
| `rule_dmv_office_finder` | [California DMV — Locations](https://www.dmv.ca.gov/portal/locations/) | Select a field office by ZIP code or city and check its calendar | Find a location by zip code or city name |
| `rule_dmv_real_id_visit` | [California DMV — What Is REAL ID?](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/what-is-real-id/) | First-time visit, appointment options, official checklist recommendation | you must visit a DMV office in person when applying for a REAL ID for the first time<br>We strongly recommend visiting our REAL ID Checklist |
| `rule_dmv_id_paper_application` | [California DMV — DL/ID Application](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/dl-id-online-app-edl-44/) | Online preparation and field-office paper option | A new paper version of the driver’s license application is available in field offices |
| `rule_dmv_customer_service` | [California DMV — Contact Us](https://www.dmv.ca.gov/portal/contacting-dmv/) | Customer service phone, hours, TTY and live chat | Chat with a Live Agent<br>1-800-777-0133<br>TTY 1-800-368-4327<br>Monday – Friday, 8 a.m. – 5 p.m. |
| `rule_dmv_id_ssn_guidance` | [California DMV — FFDL 8 (revision January 2020)](https://www.dmv.ca.gov/portal/driver-education-and-safety/educational-materials/fast-facts/social-security-number-ffdl-8/) | SSN-ineligible exemption; no physical card for ordinary noncommercial application | If you are legally present in the U.S., but ineligible for an SSN, you are exempt from the DMV SSN requirement. |
| `rule_ssa_appointment_contact` | [Social Security Administration — Make or change an appointment](https://www.ssa.gov/manage-benefits/make-an-appointment) | SSA phone, TTY, support hours and online appointments | Monday through Friday, 8 a.m. to 7 p.m.<br>Call +1 800-772-1213<br>Schedule an appointment<br>Call TTY +1 800-325-0778 |
| `rule_ssa_office_locator` | [Social Security Administration — Field Office Locator](https://www.ssa.gov/locator) | Find offices and Card Centers, their addresses and contact numbers | Search by address, city, state, or ZIP code<br>Contact numbers<br>Card Center |
| `rule_ssa_first_ssn_application` | [SSA — Request a Social Security number for the first time](https://www.ssa.gov/number-card/request-number-first-time) | First-time application entry and office document step | you can apply online, then go to a local Social Security office to provide your documentation |
| `rule_dmv_real_id_booking` | [California DMV — Appointments](https://www.dmv.ca.gov/portal/appointments/) | First REAL ID service selection | First-time REAL ID Application |
| `rule_crc_international_appointment` | [CRC — International Student Admission Steps](https://crc.losrios.edu/admissions/get-started-and-apply/international-student-admission-steps) | International student email and phone, appointment options, and arrival instructions in the Welcome Packet | Call (916) 691-7411 if you would like to schedule an in-person or phone appointment. |

CRC’s public pages leave the arrival document list, check-in fee, advisor hours and meeting location unconfirmed. The data uses an empty document list and null fee and hours. The student guide directs students to the Welcome Packet and CRC’s official contact details.

### November 16 source audit

- USAGov links directly to CBP’s I-94 site and gives retrieval and printing instructions. CBP identifies the record service on its own site. [USAGov I-94 instructions](https://www.usa.gov/arrival-departure-record) · [CBP official websites](https://www.help.cbp.gov/s/article/Article--1922?language=en_US)
- The I-901 task covers checking an existing receipt. Its excerpt comes from the retained November 13 ICE FAQ. The live fetch returned HTTP 403 on November 16, so the original check date remains on the rule. [ICE I-901 FAQ](https://www.ice.gov/sevis/i901/faq)
- The residency instruction follows the REAL ID checklist. The lease example specifies both signatures. The original $40 rate is from the regular ID row, with a separate reduced-fee category. [DMV checklist](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/real-id-checklist/) · [DMV fee table](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/licensing-fees/)
- CRC’s Fall 2026 table gives a next-day deadline for enrollment starting July 25 and a separate nonpayment exception. The demo date is a hypothetical calculation. The completed human checks are recorded in the CRC entry above. [CRC payment table and footnote](https://crc.losrios.edu/admissions/financial-aid-and-fees/tuition-and-fees/fee-payment-deadlines)

### Student wording

Show the source and consultation date, and keep **This summary is still awaiting an independent review** visible while review is pending. The student guide puts school check-in first for reading. The engine handles dependencies separately.

## Office hours — first check by AI research, November 17, 2026

Recorded in `data/rules/rules.json` under `offices`, each with the source's exact words as
`evidence`. **All are `needs_verification`.** The first check was web research by Claude for
the team (official .edu/.gov pages only); a teammate still has to compare each entry with its
page and record themselves as `second_checker` before any of it is marked verified.

| Office | Hours found | Period | Source |
| --- | --- | --- | --- |
| CRC International Students Office | none published (appointments by phone, (916) 691-7411) | — | https://crc.losrios.edu/student-resources/support-services/international-students-office |
| CRC Admissions and Records (CC 151) | Mon–Thu 8:00–5:00, Fri 8:00–4:30 | Fall 2026, Aug 3 – Dec 22 (dated on page) | https://crc.losrios.edu/admissions/admissions-and-records-office |
| CRC Business Services | Mon–Thu 8:00–5:00, Fri 8:00–4:30 (in person) | undated, seen 2026-11-17 | https://crc.losrios.edu/student-resources/support-services/business-services |
| DMV Sacramento South | Mon, Tue, Thu, Fri 8–5; Wed 9–5 | two-week schedule, Nov 15–28, 2026 | https://www.dmv.ca.gov/portal/field-office/sacramento-south/ |
| DMV Sacramento (Broadway) | Mon, Tue, Thu, Fri 8–5; Wed 9–5 | two-week schedule, Nov 15–28, 2026 | https://www.dmv.ca.gov/portal/field-office/sacramento/ |

Things the second checker should look at:
- The International Student Advisor works in Admissions & Records per the ISO page, but no page
  says the advisor keeps A&R's hours; the check-in task lists both offices for that reason.
- A&R's page doesn't say its hours are in person; that was assumed from its listed room.
- Business Services and DMV hours are undated or current-only; they may differ from August 2026.
- College closures (Labor Day, Veterans Day, Thanksgiving recess) come from the CRC Fall 2026
  Academic Calendar: https://crc.losrios.edu/admissions/academic-calendar-and-deadlines/fall-2026-academic-calendar
- An SSA office (40 Massie Circle) was also found but isn't used: no task in the rules is an SSN
  application.
