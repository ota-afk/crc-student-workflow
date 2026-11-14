# Day 2 school list — three-category scope

The confirmed Day 2 scope is limited to these three institution types:
1. Community colleges.
2. Public universities.
3. Private colleges and universities.

The active draft contains **195 school options linked to 330 campus records**: 106 community-college options, 32 public universities, and 57 private colleges/universities. It supersedes the 419-option / 669-campus broader higher-education draft.

The app reads only `data/schools/sevp_schools_ca.csv`. The scope allowlist, school metadata, campus table and source JSON support research/imports; they are not additional onboarding selectors.

## What is included

DHS's California / Higher Education / F-1 results supply the campus eligibility snapshot. Institutional type is a separate, evidence-linked decision. The allowlist is in `data/schools/institution_scope.csv`. It uses the official NCES IPEDS HD2024 directory for public/private control, degree-granting status, undergraduate offerings and institutional category, with explicit name crosswalks and college-published or Chancellor's Office sources where needed.

The product scope excludes independent graduate-only, professional, arts, music, theology and training institutions, separate extension/language-program entries, and out-of-state institutions' California sites. Research and professional departments within an included university remain part of that university. General universities with religious affiliations are not excluded merely because they have a religious affiliation.

Classification is a dated product-scope review, not an accreditation judgment or legal determination. There are **62 unresolved classification candidates held outside the selector**. The active list does not claim complete statewide coverage. A missing school must not automatically be treated as ineligible for F-1 enrollment. The full disposition audit is saved locally in `reference/institution-types/scope_review.csv`.

## School → campus relationship

- `sevp_schools_ca_draft.csv`: one row per school option, including `institution_type` and classification evidence.
- `sevp_campuses_ca_draft.csv`: campus addresses and roles, linked to the school by `school_group_key`.
- `institution_scope.csv`: the evidence-linked inclusion file used by the importer.
- `sevp_schools_ca_draft.source.json`: source links, snapshots, counts and review limitations.

### BE-compatible school directory (PR #13 alignment)

`data/schools/sevp_schools_ca.csv` is the file BE reads by default. It has exactly `school_id,institution,city,state`, with one row per school. CRC's row is `crc,Cosumnes River College,Sacramento,CA`. This was checked against BE PR #13 commit `3cf3b017c28d962a190c48a2b231717789187d92`: its actual loader accepts all 195 rows, and name search returns CRC with verification still false.

Application `school_id` values are internal identifiers, separate from SEVP codes. They are pinned in `institution_scope.csv` and carried into the school metadata and campus tables. Keep these IDs stable when display names or campus addresses change; new entries require explicit unique assignments. `_generic` is reserved and never appears in the directory.

The four-column directory uses each school's sourced main-campus city. Other cities, such as Elk Grove for CRC, remain in the linked campus table; BE's current `/schools` endpoint does not search those additional campus cities or expose a campus-selection endpoint. That integration remains BE/FE work. The metadata CSV and scope allowlist are research/import inputs; do not point `SCHOOLS_PATH` at them because the BE loader rejects extra columns.

Current onboarding remains school name and city only. The parent/child campus relationship is retained as research data. Campus selection is a proposed later enhancement requiring BE/FE contract agreement, deferred until after Day 3.

The narrowed list needs a “My school is not listed” path. BE reports that a profile without school_id receives shared and generic guidance; FE still needs to provide that choice. This note does not claim that UI is implemented or that an omitted school is ineligible.

**CRC is one school with two children:** Cosumnes River College — Main Campus in Sacramento, and Elk Grove Center — Center / Satellite Campus in Elk Grove. Original source names, campus codes and addresses are preserved.

SEVIS school registration is not always the same as an individual academic institution. Independent colleges sharing a district must remain separate. The public college directory supplies explicit identity mappings for Porterville, the four Peralta colleges, Santa Ana/Santiago Canyon, and Coalinga/Lemoore. Their original district SEVIS codes and main-of-registration flags are retained separately. Product `campus_role=main` can therefore differ from `source_is_main_campus`, with the college identity mapping marked pending teammate review.

Azusa Pacific University's San Diego site is linked under APU using its official regional-campus page; its separate main-of-SEVIS-record marker is preserved. SJSU's separate International Gateways language-program record is excluded by the narrowed scope. One extra Merritt record listed under Redwoods is held because the official college directory places Merritt under Peralta; no speculative reassignment is made.

`school_group_key` remains an import/source join key. Use the separate `school_id` column for the application's school selection and school-specific rules. Campus selection fields still need alignment with BE/FE. School listing and institutional classification do not verify school-specific check-in workflows. All review states remain `needs_verification` pending the teammate check.

## Official sources and dates

- [DHS California / Higher Education / F-1 search](https://studyinthestates.dhs.gov/school-search?field_location_state_value=33&field_education_level_value=1&field_f_1_school_value%5B1%5D=1): 669 original campus results checked November 13, 2026.
- [NCES IPEDS HD2024 directory](https://nces.ed.gov/ipeds/datacenter/data/HD2024.zip) and [official dictionary](https://nces.ed.gov/ipeds/datacenter/data/HD2024_Dict.zip): **2024** institutional classification, downloaded November 13, 2026. This is not a 2026 enrollment census.
- [California community-college directory](https://www.cccco.edu/Students/Find-a-College/College-Alphabetical-Listing/) and [district directory](https://www.cccco.edu/Students/Find-a-College/Community-College-Districts/).
- [Peralta international-office FAQ](https://www.peralta.edu/international/faq), [Rancho Santiago district](https://rsccd.edu/about/), and [West Hills district policy](https://westhillscollege.com/district/administration/board-of-trustees/policies-and-procedures/documents/1100thewesthillscommunitycollegedistrict.pdf).
- [APU San Diego Regional Campus](https://www.apu.edu/san-diego/).
- [Minerva institutional description](https://www.minerva.edu/about/) and [Deep Springs college-published evaluation](https://www.deepsprings.edu/next/wp-content/uploads/2024/07/Deep-Springs-College-2017-Comprehensive-Evaluation-Visit-Report.pdf). The Deep Springs classification source is dated **2017** and is flagged for review.
- [DHS campus-code guide](https://studyinthestates.dhs.gov/assets/updating_school_accreditations_and_recognitions_user_guide.pdf), page 25: the last three school-code digits identify the campus within a SEVIS record.

Raw DHS pages and the downloaded directory/dictionary are retained locally. November sources do not establish historical certification on the simulated August demo date.

## Reproduction and review updates

The seven-file directory update was uploaded in Draft PR #14 at commit 81a1a0e. This follow-up addresses its review. The narrowed three-category scope is confirmed; FE implementation of the missing-school option remains pending. Keep the existing importer name `scripts/import_sevp_school_draft.py`; the plan called it `scripts/import_schools.py`. This is a naming difference, not a second importer.

Raw snapshots are local research files excluded through `reference/` in .gitignore. Teammates without those snapshots can fetch live data:

```sh
uv run --locked python scripts/import_sevp_school_draft.py --download --snapshots reference/school-search-refresh --scope data/schools/institution_scope.csv --output data/schools/sevp_schools_ca_draft.csv --campuses-output data/schools/sevp_campuses_ca_draft.csv --directory-output data/schools/sevp_schools_ca.csv
```

This fetches data on the day it is run; it does not reproduce the November 13 snapshot or its hashes. The importer records the actual download date. The dated inclusion/classification evidence remains unchanged until separately reviewed. Review changed campuses, IDs and counts before committing a refresh; newly discovered schools are not automatically classified or included.

For someone who has the original snapshots, reproduce them offline:

```sh
uv run --locked python scripts/import_sevp_school_draft.py --snapshot-date 2026-11-13 --snapshots reference/school-search-2026-11-13-higher-education --scope data/schools/institution_scope.csv --output data/schools/sevp_schools_ca_draft.csv --campuses-output data/schools/sevp_campuses_ca_draft.csv --directory-output data/schools/sevp_schools_ca.csv
```

Offline runs require an explicit snapshot date to avoid labeling old source files as newly checked. The importer uses Beautiful Soup and standard-library modules, verifies the three DHS filters, result counts, unique campus codes, allowlist types and parent links, and preserves the existing internal IDs. School-specific workflow verification, generic fallback and enrollment/deadline support remain separate work.
