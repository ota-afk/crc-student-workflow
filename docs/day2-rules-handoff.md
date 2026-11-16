# Day 2 rules handoff

Prepared November 14, 2026, against main `fd73804f3a240211a6015e199b8a517c04604ed0`.

## Included

`data/rules/rules.json` contains 8 tasks and 9 rules. It retains all six demo task IDs, adds the DSO-confirmation task for team review, and preserves the existing CRC fee rule and its checker metadata.

| Task | Priority | Scope / dependency |
| --- | --- | --- |
| Retrieve I-94 | Recommended | Shared; completed in the demo. |
| Check the I-901 payment record | Recommended | Shared; completed in the demo; not a new arrival fee. |
| School check-in | Required | CRC instructions for CRC; generic DSO guidance otherwise. |
| Prepare residency evidence | Recommended | California REAL ID path. |
| Apply for a California REAL ID card | Recommended | Depends on residency evidence. |
| Open a U.S. bank account | Optional | Provider requirements apply. |
| Ask the DSO to confirm SEVIS registration | Recommended | Official DHS driver's-license guidance. |
| Pay CRC tuition and fees | Required | CRC Fall 2026 only. |

Official URLs, excerpts, dates and verification states are in the rules file; publisher names, page titles and display guidance are in `docs/sources.md`. Every rule remains needs_verification pending human review. Recommendations are labeled, sourced and scoped, and add no hard blockers. Ready means encoded dependencies are satisfied, not that an agency has accepted an application.

## Validation

Validation completed November 14: `ruff check .` passed; the full pytest suite passed **85 tests**, including 5 real-rules integration cases in `tests/test_eng_rules.py`. The new cases check CRC versus generic/no-school fallback, preservation of completed demo tasks, the residency-to-DMV dependency, and the absence of a hard DSO-confirmation or example timing block.

All nine evidence excerpts match retained official HTML/PDF sources. The CRC fee rule is identical to the main baseline.

## Follow-up owners

- **Reviewers:** check source excerpts and task wording, including the added DSO task. Update human checker fields only after the checks are actually completed.
- **FE/AI:** show official recommendation/source labels and apply DSO referral behavior. Recommendations displayed beside REAL ID must retain the DHS source's driver's-license context. These UI behaviors are not implemented by the data change.
- **BE:** add optional enrollment_date and a separate deadline field. For the agreed demo, August 13 enrollment means August 14 payment due under the existing CRC rule. Missing enrollment_date must not fall back to arrival_date. No executable wait/deadline field is added here.
- **Day 3:** connect the resolver to the workflow API and add visit details. The current API still serves the mock; updating rules.json makes the data available to the resolver but does not switch the dashboard to live data.
