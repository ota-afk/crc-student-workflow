"""Shared test setup (STU-D03-BE): every test starts with the same API settings.

config.py loads the developer's own .env on import, so without this an API_KEY or a low
RATE_LIMIT set there would make the tests pass on one laptop and fail on another.
"""

import pytest

from student_workflow.api import limiter


@pytest.fixture(autouse=True)
def clean_api_settings(monkeypatch):
    # autouse=True: runs before every test without being named in it.
    monkeypatch.setenv("API_KEY", "")  # key check off unless a test turns it on
    # High, so only the 429 test (which lowers it) ever reaches the limit.
    monkeypatch.setenv("RATE_LIMIT", "1000/minute")
    limiter.reset()  # the in-memory request counts would otherwise carry over between tests
