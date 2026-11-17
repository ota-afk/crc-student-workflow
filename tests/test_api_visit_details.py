"""API-level test for cited visit details (STU-D05-BE-before-you-go), on made-up rules."""

import json

from fastapi.testclient import TestClient

from student_workflow.api import app

client = TestClient(app)

RULES = {
    "tasks": [
        {
            "id": "checkin",
            "title": "Check in (sample)",
            "priority": "Required",
            "rule_ids": ["generic_checkin", "crc_checkin"],
            "before_you_go": {
                "phone": {"text": "CRC phone (sample)", "rule_id": "crc_checkin"},
                "fees": {"text": "Shared fee (sample)", "rule_id": "fee_rule"},
            },
        }
    ],
    "rules": [
        {
            "rule_id": rule_id,
            "statement": f"Sample statement for {rule_id} (sample)",
            "layer": layer,
            "school_id": school_id,
            "high_risk": False,
            "verification_status": "needs_verification",
        }
        for rule_id, layer, school_id in [
            ("generic_checkin", "school", "_generic"),
            ("crc_checkin", "school", "crc"),
            ("fee_rule", "california", None),
        ]
    ],
}


def checkin_for(school_id, monkeypatch, tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(RULES), encoding="utf-8")
    monkeypatch.setenv("RULES_PATH", str(path))
    profile = {
        "student_id": "demo_001",
        "institution": "Sample College (sample)",
        "visa_type": "F-1",
        "arrival_date": "2026-08-11",
        "has_ssn": False,
        "school_id": school_id,
    }
    body = {"as_of": "2026-08-14", "student_profile": profile}
    workflow = client.post("/workflow", json=body).json()
    return workflow["workflow"][0]


def test_post_workflow_returns_visit_details_with_citations(monkeypatch, tmp_path):
    visit = checkin_for("crc", monkeypatch, tmp_path)["before_you_go"]
    assert visit["phone"] == "CRC phone (sample)"
    assert [c["rule_id"] for c in visit["citations"]] == ["fee_rule", "crc_checkin"]


def test_post_workflow_never_sends_another_schools_phone(monkeypatch, tmp_path):
    visit = checkin_for("other_school", monkeypatch, tmp_path)["before_you_go"]
    assert visit["phone"] is None
    assert "CRC phone (sample)" not in json.dumps(visit)
