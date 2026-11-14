"""School search tests use synthetic CSV rows; no live directory or network is needed."""

import csv
import json

import pytest
from fastapi.testclient import TestClient

from student_workflow.api import app
from student_workflow.schools import load_schools

client = TestClient(app)


@pytest.fixture
def catalog(monkeypatch, tmp_path):
    path = tmp_path / "schools.csv"
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination)
        writer.writerow(["school_id", "institution", "city", "state"])
        writer.writerows(
            [
                ["test_one", "Example School One (sample)", "Example City", "CA"],
                ["test_two", "Example School Two (sample)", "Other City", "CA"],
            ]
        )
    monkeypatch.setenv("SCHOOLS_PATH", str(path))
    monkeypatch.delenv("RULES_PATH", raising=False)
    return path


def test_school_search_matches_names_without_case_or_surrounding_spaces(catalog):
    response = client.get("/schools", params={"q": " SCHOOL ONE "})

    assert response.status_code == 200
    assert [school["school_id"] for school in response.json()] == ["test_one"]
    assert response.json()[0]["school_verified"] is False


def test_school_search_matches_city_and_respects_limit(catalog):
    response = client.get("/schools", params={"q": "city", "limit": 1})

    assert response.status_code == 200
    assert [school["school_id"] for school in response.json()] == ["test_one"]


def test_empty_school_query_lists_supplied_entries(catalog):
    assert len(client.get("/schools").json()) == 2


def test_school_search_returns_no_invented_match(catalog):
    response = client.get("/schools", params={"q": "not in the directory"})

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("limit", [0, 101])
def test_invalid_school_search_limit_is_rejected(catalog, limit):
    assert client.get("/schools", params={"limit": limit}).status_code == 422


def test_missing_school_directory_reports_unavailability(monkeypatch, tmp_path):
    monkeypatch.setenv("SCHOOLS_PATH", str(tmp_path / "missing.csv"))

    assert client.get("/schools").status_code == 503


def test_invalid_school_directory_reports_unavailability(catalog):
    catalog.write_text(
        "school_id,institution,city,state\nbad,Example (sample),City,NY\n"
    )

    assert client.get("/schools").status_code == 503


def test_duplicate_school_ids_are_rejected(catalog):
    catalog.write_text(
        "school_id,institution,city,state\n"
        "duplicate,Example One (sample),City,CA\n"
        "duplicate,Example Two (sample),City,CA\n"
    )

    with pytest.raises(ValueError, match="duplicate school IDs"):
        load_schools(catalog)


def test_generic_marker_cannot_identify_a_directory_school(catalog):
    catalog.write_text(
        "school_id,institution,city,state\n_generic,Example (sample),City,CA\n"
    )

    with pytest.raises(ValueError, match="reserved"):
        load_schools(catalog)


@pytest.mark.parametrize(
    "contents",
    [
        "school_id,institution,city\n",
        "school_id,institution,city,state,state\n",
        'school_id,institution,city,state\n"unfinished',
    ],
)
def test_malformed_school_csv_reports_unavailability(catalog, contents):
    catalog.write_text(contents)

    assert client.get("/schools").status_code == 503


def test_school_search_computes_verification_from_rules(catalog, monkeypatch, tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "test_checkin",
                        "title": "Check-in (sample)",
                        "priority": "Recommended",
                        "rule_ids": ["test_rule"],
                    }
                ],
                "rules": [
                    {
                        "rule_id": "test_rule",
                        "statement": "Test evidence (sample)",
                        "layer": "school",
                        "school_id": "test_one",
                        "high_risk": False,
                        "verification_status": "verified",
                        "source_url": "https://example.org",
                        "evidence": "Test evidence (sample)",
                        "last_verified": "2026-08-01",
                        "verified_by": "First Checker",
                        "second_checker": "Second Checker",
                    }
                ],
            }
        )
    )
    monkeypatch.setenv("RULES_PATH", str(path))

    response = client.get("/schools")

    assert response.status_code == 200
    assert [school["school_verified"] for school in response.json()] == [True, False]
