# Day 2 school list — three-category scope

The user's final scope is:
1. Community colleges.
2. Public universities.
3. Private colleges and universities.

The active draft contains **195 school options linked to 330 campus records**: 106 community-college options, 32 public universities, and 57 private colleges/universities. It supersedes the 419-option / 669-campus broader higher-education draft.

## What is included

DHS's California / Higher Education / F-1 results supply the campus eligibility snapshot. Institutional type is a separate, evidence-linked decision. The allowlist is in `data/schools/institution_scope.csv`. It uses the official NCES IPEDS HD2024 directory for public/private control, degree-granting status, undergraduate offerings and institutional category, with explicit name crosswalks and college-published or Chancellor's Office sources where needed.

The product scope excludes independent graduate-only, professional, arts, music, theology and training institutions, separate extension/language-program entries, and out-of-state institutions' California sites. Research and professional departments within an included university remain part of that university. General universities with religious affiliations are not excluded merely because they have a religious affiliation.

Classification is a dated product-scope review, not an accreditation judgment or legal determination. There are **62 unresolved classification candidates held outside the selector**. The active list does not claim complete statewide coverage. A missing school must not automatically be treated as ineligible for F-1 enrollment. The full disposition audit is saved locally in `reference/institution-types/scope_review.csv`.

## School → campus relationship

- `sevp_schools_ca_draft.csv`: one row per school option, including `institution_type` and classification evidence.
- `sevp_campuses_ca_draft.csv`: campus addresses and roles, linked to the school by `school_group_key`.
- `institution_scope.csv`: the evidence-linked inclusion file used by the importer.
- `sevp_schools_ca_draft.source.json`: source links, snapshots, counts and review limitations.

Onboarding should first select a school, then show only that school's campuses. A sole campus may be selected automatically. The app/contract/UI is not changed by this local data draft.

**CRC is one school with two children:** Cosumnes River College — Main Campus in Sacramento, and Elk Grove Center — Center / Satellite Campus in Elk Grove. Original source names, campus codes and addresses are preserved.

SEVIS school registration is not always the same as an individual academic institution. Independent colleges sharing a district must remain separate. The public college directory supplies explicit identity mappings for Porterville, the four Peralta colleges, Santa Ana/Santiago Canyon, and Coalinga/Lemoore. Their original district SEVIS codes and main-of-registration flags are retained separately. Product `campus_role=main` can therefore differ from `source_is_main_campus`, with the college identity mapping marked pending teammate review.

Azusa Pacific University's San Diego site is linked under APU using its official regional-campus page; its separate main-of-SEVIS-record marker is preserved. SJSU's separate International Gateways language-program record is excluded by the narrowed scope. One extra Merritt record listed under Redwoods is held because the official college directory places Merritt under Peralta; no speculative reassignment is made.

`school_group_key` is an import join key, not an approved application `school_id`. Campus selection fields and IDs still need alignment with BE/FE. School listing and institutional classification do not verify school-specific check-in workflows. All review states remain `needs_verification` pending the teammate check.

## Official sources and dates

- [DHS California / Higher Education / F-1 search](https://studyinthestates.dhs.gov/school-search?field_location_state_value=33&field_education_level_value=1&field_f_1_school_value%5B1%5D=1): 669 original campus results checked November 13, 2026.
- [NCES IPEDS HD2024 directory](https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip) and [official dictionary](https://nces.ed.gov/ipeds/datacenter/data/HD2024_Dict.zip): **2024** institutional classification, downloaded November 13, 2026. This is not a 2026 enrollment census.
- [California community-college directory](https://www.cccco.edu/Students/Find-a-College/College-Alphabetical-Listing/) and [district directory](https://www.cccco.edu/Students/Find-a-College/Community-College-Districts/).
- [Peralta international-office FAQ](https://www.peralta.edu/international/faq), [Rancho Santiago district](https://rsccd.edu/about/), and [West Hills district policy](https://westhillscollege.com/district/administration/board-of-trustees/policies-and-procedures/documents/1100thewesthillscommunitycollegedistrict.pdf).
- [APU San Diego Regional Campus](https://www.apu.edu/san-diego/).
- [Minerva institutional description](https://www.minerva.edu/about/) and [Deep Springs college-published evaluation](https://www.deepsprings.edu/next/wp-content/uploads/2024/07/Deep-Springs-College-2017-Comprehensive-Evaluation-Visit-Report.pdf). The Deep Springs classification source is dated **2017** and is flagged for review.
- [DHS campus-code guide](https://studyinthestates.dhs.gov/assets/updating_school_accreditations_and_recognitions_user_guide.pdf), page 25: the last three school-code digits identify the campus within a SEVIS record.

Raw DHS pages and the downloaded directory/dictionary are retained locally. November sources do not establish historical certification on the simulated August demo date.

## Reproduction and upload

Upload the four files in `data/schools/`, the importer under `scripts/`, and this note under `docs/`. Do not upload the old all-type or broader higher-education drafts as active selectors.

Rebuild from the saved November DHS snapshots:

```sh
uv run --locked python scripts/import_sevp_school_draft.py --snapshots reference/school-search-2026-11-13-higher-education --scope data/schools/institution_scope.csv --output data/schools/sevp_schools_ca_draft.csv --campuses-output data/schools/sevp_campuses_ca_draft.csv
```

The importer uses Beautiful Soup, already in the project dependencies, plus the standard library. It verifies the three DHS filters, complete result counts, unique campus codes, allowlist types, school/campus links and unambiguous display names. It does not automatically classify newly added schools. A later download/refresh requires updating the dated source checks and reviewing the scope file.

No Day 2 GitHub upload or PR has been performed by this local update.
