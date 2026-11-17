# Day 3: internal before-you-go handoff

For BE/FE and source reviewers. Use [the student guide](day3-student-guide.md) for outward-facing wording; do not show field names, integration notes or acceptance checks to students.

Sources consulted November 13–16, 2026. **Independent review pending.** Use the current official office calendar to plan a visit.

## California REAL ID card — task_dmv_id

Scope: an F-1 student's first REAL ID card in California. The passport route below is one accepted identity option.

| Existing field | Content | Official source |
| --- | --- | --- |
| warnings | Conditional documents, kept outside the counted checklist: for the passport route, an unexpired foreign passport, valid U.S. visa and approved I-94, following the original/certified-copy instructions; legal name-change evidence if your current name differs from your identity document. DMV’s list includes other accepted identity options. | [DMV: Non-U.S. Citizens](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/what-is-real-id/real-id-info-non-u-s-citizens/) |
| warnings | Retrieve your latest electronic I-94 through the official CBP I-94 service and print it if needed. | [USAGov I-94 instructions](https://www.usa.gov/arrival-departure-record) |
| required_documents | Two different printed California residency documents showing your first/last name and the application address. Examples: a lease signed by both landlord and tenant, a utility/mobile bill or a bank record. Follow the checklist’s PO Box and relationship-document exceptions where applicable. | [DMV: REAL ID Checklist](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/real-id-checklist/) |
| fees | Regular original ID card: $40. Reduced-fee and no-fee categories have separate eligibility rules. | [DMV: Licensing Fees](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/licensing-fees/) |
| hours | Choose a field office and check its calendar for your visit date. | [California DMV office finder](https://www.dmv.ca.gov/portal/locations/) |
| appointment_rules | Complete the application online or use the DMV field-office paper option. A first REAL ID requires an in-person visit. The REAL ID FAQ offers appointments or local wait-time checks. | [DMV: DL/ID application](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/dl-id-online-app-edl-44/); [DMV: REAL ID FAQ](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/what-is-real-id/) |
| phone | DMV customer service 1-800-777-0133, weekdays 8 a.m. to 5 p.m. TTY 1-800-368-4327. The contact page links to live chat. | [DMV: Contact Us](https://www.dmv.ca.gov/portal/contacting-dmv/) |
| official_url | REAL ID document checklist | [Open checklist](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/real-id-checklist/) |

If you already have a Social Security number (SSN), provide it to DMV. DMV describes an exemption for legally present applicants who are ineligible for an SSN. Ask DMV how its SSN requirement applies to your REAL ID application. [DMV SSN guidance](https://www.dmv.ca.gov/portal/driver-education-and-safety/educational-materials/fast-facts/social-security-number-ffdl-8/)

The [student guide](day3-student-guide.md#apply-for-an-ssn-or-check-an-application) lists the phone, TTY, office search, online applications and appointment links. It includes exact questions for a first SSN application, an SSN status check and a REAL ID application with an SSN question. The rules file provides these as cited details in the DMV guide. The sample questions are suggested wording for students.

Official recommendation: use DMV’s full document checklist before visiting. [DMV REAL ID FAQ](https://www.dmv.ca.gov/portal/driver-licenses-identification-cards/real-id/what-is-real-id/).

The DSO task keeps its [DHS driver’s-license source](https://studyinthestates.dhs.gov/students/study/driving-in-the-united-states) and the November 13 check date recorded in the Day 2 sources. It supplies no mandatory REAL ID waiting period or hard prerequisite. A Ready task or completed checklist does not guarantee DMV acceptance.

## CRC arrival check-in — task_school_checkin, school_id=crc

Report to CRC's International Student Advisor as soon as you arrive. [CRC: International Students Office](https://crc.losrios.edu/student-resources/support-services/international-students-office).

| Existing field | Content | Official source / limit |
| --- | --- | --- |
| required_documents | Unknown; keep the list empty and show Not verified. | Public admission documents are not an arrival check-in checklist. [Admission steps / welcome packet](https://crc.losrios.edu/admissions/get-started-and-apply/international-student-admission-steps) |
| fees | Unknown; null. | No separate arrival check-in fee established; do not display Free. |
| hours | Unknown; null. | Advisor check-in hours are not established. |
| appointment_rules | Call (916) 691-7411 if you’d like to schedule an in-person or phone appointment. The advisor’s exact check-in location and arrival deadline are not confirmed by the public pages. | [CRC: Admission Steps](https://crc.losrios.edu/admissions/get-started-and-apply/international-student-admission-steps) |
| phone | (916) 691-7411 | [CRC international appointment contact](https://crc.losrios.edu/admissions/get-started-and-apply/international-student-admission-steps) |
| official_url | International student admission and contact page | [Open CRC page](https://crc.losrios.edu/admissions/get-started-and-apply/international-student-admission-steps) |

Email: **crc-internationalstudents@crc.losrios.edu**. CRC directs admitted students to the welcome packet for arrival information. [CRC source](https://crc.losrios.edu/admissions/get-started-and-apply/international-student-admission-steps).

## Integration handoff

- The [rules file](../data/rules/rules.json) uses the cited visit-details format from BE PR #23. Each populated `before_you_go` item has `text` and `rule_id`. Each referenced rule records a source, evidence, date and verification status.
- BE resolves the guide items using their rule scopes and includes the selected rules in the task’s sources. CRC arrival details are CRC-specific. Keep the base task rule references and prerequisites as supplied in PR #18.
- The REAL ID `required_documents` list holds only the residency evidence everyone needs. The passport-route and name-change documents depend on the student's situation, so they sit in `warnings` and are not counted as missing. FE can move them back into the checklist once students can mark an item not applicable. Showing "Not verified" next to each individual fact is tracked as a separate FE follow-up.
- CRC document requirements, fees and advisor hours use an empty list or null. The student guide gives the Welcome Packet and contact details for follow-up. Retain source attribution and the pending review note when displaying content.
- BE PR #23 supplies the loader. Before the Day 3 rules reach students, FE needs to read `citations` and show “Not verified” beside each unverified visit detail.

For AI integration, route questions about obtaining an SSN or checking a pending SSN application to the SSA contact details. Route questions about the REAL ID exemption or acceptable documentation to DMV. A student’s `has_ssn` field records whether they have a number. It cannot establish eligibility. The flags on these contact and general DMV rules stay false while AI adds question-specific routing. PR #15 currently uses the task-level flag for DSO referrals.

## Acceptance checks after integration

These are expected results for manual checks, not completed UI tests. Use a synthetic profile: CRC, F-1, arrival August 11, 2026; simulated date August 14; I-94 and I-901 record tasks completed. Do not infer SSN eligibility from has_ssn=false.

| Check | Expected result |
| --- | --- |
| Open the DMV task before residency evidence is marked done | Blocked, with the residency task identified as the missing prerequisite. |
| Mark residency evidence done while school check-in and DSO confirmation remain incomplete | DMV becomes Ready under the encoded dependencies; sources still show needs_verification. |
| Open the CRC check-in guide | Unknown documents, fee, advisor hours and exact meeting location remain explicit; no Free or No documents required claim. |
| Switch to another school or no selected school | CRC-specific contact/visit details disappear; generic guidance remains school-unverified. |
| Read an official recommendation | Its publisher, page link, scope and check date are visible; it adds no hard blocker. |
| Open SSN and REAL ID help | The student can reach the agency by phone or TTY, open the official appointment or location page, and copy a question appropriate to their situation. DMV live chat is linked from the contact page. |
| Open office hours guidance | DMV’s office finder is available for the student to check their selected office’s calendar. The August demo has no fixed November hours. |

For any failed check, record the screen, expected result and actual result in the relevant integration PR. Keep source review separate from UI completion.
