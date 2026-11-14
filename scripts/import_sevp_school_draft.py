"""Download and parse DHS's California / F-1 / Higher Education result pages.

This software-data importer uses the site's education filter, not school-name
keywords. Saved HTML snapshots permit offline reproduction and source review.
"""

import argparse
import csv
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import urlopen

from bs4 import BeautifulSoup

BASE = "https://studyinthestates.dhs.gov/school-search"
FILTERS = {
    "field_location_state_value": "33",
    "field_education_level_value": "1",
    "field_f_1_school_value[1]": "1",
}
SOURCE = BASE + "?" + urlencode(FILTERS)
CODE_GUIDE = "https://studyinthestates.dhs.gov/assets/updating_school_accreditations_and_recognitions_user_guide.pdf"
SJSU_SOURCE = "https://www.sjsu.edu/igateways/about/index.php"
APU_SOURCE = "https://www.apu.edu/san-diego/"
# International Gateways is part of SJSU, but has a separate SEVIS record.
# This draft display grouping preserves both source records and their flags.
AFFILIATIONS = {"SFR214F01885": "SFR214F00627", "SND214F00410": "LOS214F00364"}
AFFILIATION_SOURCES = {"SFR214F01885": SJSU_SOURCE, "SND214F00410": APU_SOURCE}
ALLOWED_TYPES = {"community_college", "public_university", "private_college_university"}
COLLEGE_DIRECTORY = (
    "https://www.cccco.edu/Students/Find-a-College/College-Alphabetical-Listing/"
)
DISTRICT_COLLEGES = {
    "SFR214F00596000": "Porterville College",
    "SFR214F00296000": "Laney College",
    "SFR214F00296004": "Berkeley City College",
    "SFR214F00296002": "College of Alameda",
    "SFR214F00296003": "Merritt College",
    "LOS214F00341003": "Santa Ana College",
    "LOS214F00341001": "Santiago Canyon College",
    "SFR214F00219000": "Coalinga College",
    "SFR214F00219001": "Lemoore College",
}
# Hold a conflicting extra Merritt record listed under Redwoods in DHS.
RELATIONSHIP_HOLD = {"SFR214F00608014"}
PROGRAM_CAMPUS = re.compile(
    r"extension|continuing education|intensive english|american english institute|"
    r"american language|language and culture|international academy",
    re.IGNORECASE,
)
FIELDS = [
    "school_group_key",
    "school_name",
    "source_school_name",
    "campus_name",
    "city",
    "address",
    "state",
    "f1_eligible",
    "m1_eligible",
    "sevp_campus_code",
    "source_school_key",
    "source_is_main_campus",
    "campus_role",
    "relationship_source_url",
    "education_type",
    "school_detail_url",
    "source_url",
    "source_checked",
]
SCHOOL_FIELDS = [
    "school_group_key",
    "school_name",
    "institution_type",
    "classification_source_url",
    "classification_data_year",
    "ipeds_unitid",
    "source_school_name",
    "source_school_keys",
    "main_campus_code",
    "campus_count",
    "hierarchy_status",
    "hierarchy_source_url",
    "source_checked",
]


def page_url(number):
    return SOURCE + ("&page=" + str(number) if number else "")


def read_page(path):
    tree = BeautifulSoup(path.read_bytes(), "html.parser")
    total = int(tree.select_one("#results-total").get_text())
    state = [
        x.get("value")
        for x in tree.select(
            "select[name='field_location_state_value'] option[selected]"
        )
    ]
    education = [
        x.get("value")
        for x in tree.select(
            "select[name='field_education_level_value'] option[selected]"
        )
    ]
    f1 = [
        x.get("value")
        for x in tree.select("input[name='field_f_1_school_value[1]'][checked]")
    ]
    if state != ["33"] or education != ["1"] or f1 != ["1"]:
        raise ValueError(f"Required filters not selected in {path}")
    nodes = tree.select(".view-content .views-row")
    rows = []
    for node in nodes:
        anchor = node.select_one(".views-field-field-campus-name a")
        detail = urljoin(BASE, anchor.get("href"))
        code = urlparse(detail).path.rstrip("/").split("/")[-1].upper()
        campus = node.select_one(".views-field-field-campus-name strong").get_text(
            strip=True
        )
        address = node.select_one(
            ".views-field-field-location-zip .field-content"
        ).get_text(strip=True)
        match = re.search(r",\s*([^,]+),+\s*CA\s+\d{5}(?:-\d{4})?\s*$", address)
        if not match:
            raise ValueError(f"Cannot parse California city for {code}: {address}")
        city = match.group(1).strip()
        main_flags = node.select("i.main-campus-Y, i.main-campus-N")
        if len(main_flags) != 1:
            raise ValueError(f"Missing/ambiguous DHS main-campus marker: {code}")
        source_main = "Y" if "main-campus-Y" in main_flags[0].get("class", []) else "N"
        has_f1 = node.select_one("span.f-1-Y") is not None
        m1 = "Y" if node.select_one("span.m-1-Y") else "N"
        if not has_f1 or not re.fullmatch(r"[A-Z]{3}\d{3}[FM]\d{6,8}", code):
            raise ValueError(f"Invalid F-1 result: {code}")
        source_key = code[:-3] if len(code) == 15 else code
        group_key = AFFILIATIONS.get(source_key, source_key)
        if code in DISTRICT_COLLEGES:
            group_key = code
        rows.append(
            {
                "school_group_key": group_key,
                "school_name": anchor.get_text(strip=True),
                "source_school_name": anchor.get_text(strip=True),
                "campus_name": campus,
                "city": city,
                "address": address,
                "state": "CA",
                "f1_eligible": "Y",
                "m1_eligible": m1,
                "sevp_campus_code": code,
                "source_school_key": source_key,
                "source_is_main_campus": source_main,
                "campus_role": "main"
                if code in DISTRICT_COLLEGES
                else "program_center"
                if source_key == "SFR214F01885"
                else "center_or_satellite"
                if source_key in AFFILIATIONS
                else "main"
                if source_main == "Y"
                else "center_or_satellite",
                "relationship_source_url": COLLEGE_DIRECTORY
                if code in DISTRICT_COLLEGES
                else AFFILIATION_SOURCES.get(source_key, SOURCE),
                "education_type": "Higher Education",
                "school_detail_url": detail,
                "source_url": SOURCE,
                "source_checked": "2026-11-13",
            }
        )
    return total, rows, tree


def group_schools(campuses):
    groups = {}
    for campus in campuses:
        groups.setdefault(campus["school_group_key"], []).append(campus)
    # Several independent colleges can share a district/system source name.
    # Distinguish their own SEVIS groups using the main campus name.
    name_groups = {}
    for key, members in groups.items():
        for name in {c["source_school_name"] for c in members}:
            name_groups.setdefault(name, set()).add(key)
    schools = []
    for key, members in groups.items():
        source_names = sorted({c["source_school_name"] for c in members})
        primary_names = {
            c["source_school_name"] for c in members if c["source_school_key"] == key
        }
        if key not in DISTRICT_COLLEGES and (
            len(primary_names) != 1
            or any(
                c["source_school_key"] != key
                and c["source_school_key"] not in AFFILIATIONS
                for c in members
            )
        ):
            raise ValueError(f"School names conflict in source group {key}")
        source_name = next(iter(primary_names)) if primary_names else source_names[0]
        mains = [c for c in members if c["campus_role"] == "main"]
        if len(mains) > 1:
            raise ValueError(
                f"Multiple main campuses require an explicit review: {key}"
            )
        name = (
            mains[0]["campus_name"]
            if len(name_groups[source_name]) > 1 and mains
            else source_name
        )
        status = "source_grouped" if mains else "main_not_in_filtered_results"
        if key in DISTRICT_COLLEGES:
            name = DISTRICT_COLLEGES[key]
            status = "college_identity_mapping_pending_teammate_review"
        elif (
            "district" in source_name.casefold()
            and mains
            and "college" in mains[0]["campus_name"].casefold()
            and "district" not in mains[0]["campus_name"].casefold()
        ):
            name = mains[0]["campus_name"]
        keys = sorted({c["source_school_key"] for c in members})
        if any(k in AFFILIATIONS for k in keys):
            status = "affiliation_pending_teammate_review"
        if any(len(c["sevp_campus_code"]) != 15 for c in members):
            status = "source_code_needs_review"
        for campus in members:
            campus["school_name"] = name
        schools.append(
            {
                "school_group_key": key,
                "school_name": name,
                "source_school_name": source_name,
                "source_school_keys": "|".join(keys),
                "main_campus_code": mains[0]["sevp_campus_code"] if mains else "",
                "campus_count": len(members),
                "hierarchy_status": status,
                "hierarchy_source_url": COLLEGE_DIRECTORY
                if key in DISTRICT_COLLEGES
                else next(
                    (AFFILIATION_SOURCES[k] for k in keys if k in AFFILIATION_SOURCES),
                    CODE_GUIDE,
                ),
                "source_checked": "2026-11-13",
            }
        )
    schools.sort(key=lambda r: (r["school_name"].casefold(), r["school_group_key"]))
    if len({s["school_name"].casefold() for s in schools}) != len(schools):
        raise ValueError("School selector still has ambiguous duplicate names")
    return schools


def write_csv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--campuses-output", type=Path)
    parser.add_argument(
        "--scope", type=Path, help="Reviewed three-category institution allowlist"
    )
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    args.snapshots.mkdir(parents=True, exist_ok=True)

    def fetch(number):
        path = args.snapshots / f"page-{number:03}.html"
        with urlopen(page_url(number), timeout=40) as response:
            content = response.read()
        if b"results-total" not in content:
            raise ValueError(
                "DHS result page was not returned; do not save the response"
            )
        path.write_bytes(content)
        return path

    if args.download:
        fetch(0)
    total, first, _ = read_page(args.snapshots / "page-000.html")
    if not first:
        raise ValueError("Empty first result page")
    page_count = (total + len(first) - 1) // len(first)
    if args.download:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, range(1, page_count)))
    rows = []
    hashes = {}
    for number in range(page_count):
        path = args.snapshots / f"page-{number:03}.html"
        page_total, page_rows, _ = read_page(path)
        if page_total != total:
            raise ValueError("Result count changed during download; retry the snapshot")
        rows.extend(page_rows)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(rows) != total or len({r["sevp_campus_code"] for r in rows}) != total:
        raise ValueError("Missing or duplicate results across pages")
    source_campus_count = len(rows)
    scope_path = args.scope or args.output.parent / "institution_scope.csv"
    with scope_path.open(encoding="utf-8") as stream:
        scope_rows = list(csv.DictReader(stream))
    scope = {r["school_group_key"]: r for r in scope_rows}
    if len(scope) != len(scope_rows) or not scope:
        raise ValueError("Missing or duplicate reviewed institution scope keys")
    if any(
        r["institution_type"] not in ALLOWED_TYPES or r["decision"] != "include"
        for r in scope_rows
    ):
        raise ValueError("Scope allowlist contains an unapproved institution category")
    rows = [
        r
        for r in rows
        if r["school_group_key"] in scope
        and r["campus_role"] != "program_center"
        and r["sevp_campus_code"] not in RELATIONSHIP_HOLD
        and not PROGRAM_CAMPUS.search(r["campus_name"])
    ]
    schools = group_schools(rows)
    if {s["school_group_key"] for s in schools} != set(scope):
        raise ValueError(
            "An allowlisted school has no eligible campus; refresh classification before publishing"
        )
    for school in schools:
        evidence = scope[school["school_group_key"]]
        for field in (
            "institution_type",
            "classification_source_url",
            "classification_data_year",
            "ipeds_unitid",
        ):
            school[field] = evidence[field]
    rows.sort(
        key=lambda r: (
            r["school_name"].casefold(),
            r["campus_role"] != "main",
            r["campus_name"].casefold(),
            r["sevp_campus_code"],
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    campuses_output = args.campuses_output or args.output.with_name(
        "sevp_campuses_ca_draft.csv"
    )
    campuses_output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.resolve() == campuses_output.resolve():
        raise ValueError("School and campus outputs must use different paths")
    write_csv(args.output, SCHOOL_FIELDS, schools)
    write_csv(campuses_output, FIELDS, rows)
    summary = {
        "scope": "Community colleges, public universities, and private colleges/universities only; linked California F-1 campuses",
        "source_url": SOURCE,
        "source_checked": "2026-11-13",
        "campus_rows": len(rows),
        "unfiltered_dhs_higher_education_campus_rows": source_campus_count,
        "institution_type_counts": {
            category: sum(s["institution_type"] == category for s in schools)
            for category in sorted(ALLOWED_TYPES)
        },
        "institution_scope_file": scope_path.name,
        "institution_scope_sha256": hashlib.sha256(scope_path.read_bytes()).hexdigest(),
        "relationship_hold_codes": sorted(RELATIONSHIP_HOLD),
        "school_options": len(schools),
        "school_options_with_multiple_campuses": sum(
            s["campus_count"] > 1 for s in schools
        ),
        "school_options_without_main_in_filtered_results": sum(
            not s["main_campus_code"] for s in schools
        ),
        "school_file": args.output.name,
        "campus_file": campuses_output.name,
        "distinct_source_school_names": len({r["source_school_name"] for r in rows}),
        "result_pages": page_count,
        "snapshot_sha256": hashes,
        "verification_status": "needs_verification",
        "nonstandard_code_lengths": [
            r["sevp_campus_code"] for r in rows if len(r["sevp_campus_code"]) != 15
        ],
        "notes": [
            "DHS supplies F-1 eligibility; a reviewed evidence-linked allowlist supplies the three-category product scope.",
            "Classification draws on the dated IPEDS HD2024 directory and explicit college/district sources; it is separate from current SEVP certification.",
            "Unresolved institutional classifications remain outside the active selector; this is not a claim of complete statewide coverage.",
            "Standalone graduate/professional/arts/religious/training institutions and separate extension/language programs are excluded from this product scope.",
            "One school selector entry per school group; campuses reference their parent school_group_key.",
            "DHS main-campus markers are preserved; program affiliation is recorded separately.",
            "SEVIS campus suffix groups form the initial draft hierarchy; distinct colleges sharing a district name remain separate schools.",
            "APU's San Diego site is grouped under Azusa Pacific University using its official campus page; SJSU's separate International Gateways program is excluded by the narrowed scope.",
            "Campus codes are preserved from official profile URL paths; irregular lengths are listed for review, not silently corrected.",
            "school_group_key is a draft import join key; application school_id format remains to be aligned with BE.",
            "Certification is separate from verification of a school's workflow.",
            "November live search snapshot; not historical August certification evidence.",
        ],
    }
    args.output.with_suffix(".source.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "snapshot_sha256"}, indent=2
        )
    )


if __name__ == "__main__":
    main()
