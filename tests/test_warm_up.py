"""Tests for the warm-up script (STU-D05-BE), with requests.get replaced: no real network."""

import importlib.util
from pathlib import Path

import requests

# scripts/ is not a package, so load the script from its file.
_PATH = Path(__file__).resolve().parents[1] / "scripts" / "warm_up.py"
_SPEC = importlib.util.spec_from_file_location("warm_up", _PATH)
warm_up = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(warm_up)


class Answer:
    status_code = 200


def test_both_services_awake_passes(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example")
    monkeypatch.setenv("DASHBOARD_URL", "https://dashboard.example")
    called = []
    monkeypatch.setattr(
        warm_up.requests, "get", lambda url, timeout: called.append(url) or Answer()
    )
    assert warm_up.main() == 0
    assert sorted(called) == [
        "https://api.example/health",
        "https://dashboard.example/_stcore/health",
    ]


def test_service_that_never_answers_fails(monkeypatch):
    def unreachable(url, timeout):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(warm_up.requests, "get", unreachable)
    monkeypatch.setattr(warm_up.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(warm_up, "WAKE_UP_SECONDS", 0.01)
    assert warm_up.wake("API", "https://api.example/health") is False


def test_missing_url_fails_loudly(monkeypatch):
    monkeypatch.setenv("API_URL", "https://api.example")
    monkeypatch.setenv("DASHBOARD_URL", "")
    assert warm_up.main() == 1
