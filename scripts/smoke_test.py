"""Smoke test a running API: every endpoint, then the demo path (STU-D04-BE).

Used twice: CI starts a real server and runs this (the plan's end-to-end test), and after a
deploy we run it against the live URL. It stops at the first failure with exit code 1.

    uv run --env-file .env.smoke python scripts/smoke_test.py

.env.smoke (git-ignored) holds API_URL and API_KEY for the API under test. It is a separate
file from .env, so pointing the smoke test at the live API never changes local runs.
The API under test must have USE_MOCK=false: the demo must never show sample data.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

logger = logging.getLogger("smoke_test")

# The demo student from the mock file, so this script and the dashboard demo use the same one.
MOCK = Path(__file__).resolve().parents[1] / "data" / "mock" / "workflow.mock.json"
# ENG's task IDs on the demo path. If ENG renames them, this test fails loudly, as it should.
DMV = "task_dmv_id"
RESIDENCY = "task_proof_of_residency"
# A free Render service sleeps after 15 idle minutes and takes about a minute to wake up.
WAKE_UP_SECONDS = 120
# Per request, so a hung server fails the test instead of hanging it.
TIMEOUT_SECONDS = 30


class SmokeError(Exception):
    """One check failed; the message says which and why."""


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    url = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
    key = os.getenv("API_KEY", "").strip()
    try:
        run_checks(url, key)
    except (SmokeError, requests.RequestException) as error:
        logger.error("FAIL: %s", error)
        return 1
    logger.info("All checks passed against %s", url)
    return 0


def run_checks(url: str, key: str) -> None:
    session = requests.Session()
    # Empty key = the API runs without the key check (local only), so send no header.
    if key:
        session.headers["X-API-Key"] = key

    wait_for_health(url)
    if key:
        # A keyless request must be refused, or the deployed API is open to anyone. It is a
        # valid request, so an API without the key check answers 200 and the message says so.
        response = requests.post(
            f"{url}/workflow", json=demo_request(), timeout=TIMEOUT_SECONDS
        )
        expect(
            response.status_code == 401, f"no key gave {response.status_code}, not 401"
        )
        logger.info("ok  requests without the key are refused (401)")
    else:
        logger.warning("API_KEY is empty: the key check is not tested")

    schools = get_json(session, f"{url}/schools?q=sacramento&limit=5")
    expect(isinstance(schools, list) and schools, "school search returned no schools")
    logger.info("ok  GET /schools (%d results)", len(schools))

    demo = get_json(session, f"{url}/workflow")
    # The dashboard on main shows GET /workflow, so sample data here would reach the demo.
    expect(
        demo["is_mock"] is False, "GET /workflow returned mock data: set USE_MOCK=false"
    )
    logger.info("ok  GET /workflow (live data)")

    request = demo_request()
    workflow = post_json(session, f"{url}/workflow", request)
    expect(workflow["is_mock"] is False, "POST /workflow returned mock data")
    expect(status_of(workflow, DMV) == "Blocked", "the demo DMV task is not Blocked")
    logger.info("ok  POST /workflow: DMV is Blocked")

    # Each step sends back the profile the last answer returned: the server stores nothing.
    resolved = post_json(session, f"{url}/tasks/{DMV}/resolve", request)
    expect(resolved["email_draft"] is None, "resolve returned an email draft")
    workflow = resolved["workflow"]
    expect(
        status_of(workflow, RESIDENCY) == "In Progress", "residency is not In Progress"
    )
    expect(status_of(workflow, DMV) == "Blocked", "resolve unblocked DMV on its own")
    logger.info("ok  POST /tasks/%s/resolve: residency is In Progress", DMV)

    next_request = {
        "as_of": request["as_of"],
        "student_profile": workflow["student_profile"],
    }
    workflow = post_json(session, f"{url}/tasks/{RESIDENCY}/complete", next_request)
    expect(
        status_of(workflow, DMV) == "Ready", "DMV is not Ready after residency is done"
    )
    logger.info("ok  POST /tasks/%s/complete: DMV is Ready", RESIDENCY)


def wait_for_health(url: str) -> None:
    deadline = time.monotonic() + WAKE_UP_SECONDS
    while True:
        try:
            response = requests.get(f"{url}/health", timeout=TIMEOUT_SECONDS)
            if response.status_code == 200 and response.json() == {"status": "ok"}:
                logger.info("ok  GET /health")
                return
        except requests.RequestException:
            pass  # not up yet (still starting, or asleep on a free host): try again
        if time.monotonic() > deadline:
            raise SmokeError(f"/health did not answer within {WAKE_UP_SECONDS} seconds")
        time.sleep(3)


def demo_request() -> dict:
    mock = json.loads(MOCK.read_text(encoding="utf-8"))
    return {"as_of": mock["as_of"], "student_profile": mock["student_profile"]}


def get_json(session: requests.Session, url: str) -> dict | list:
    return checked(session.get(url, timeout=TIMEOUT_SECONDS))


def post_json(session: requests.Session, url: str, payload: dict) -> dict:
    return checked(session.post(url, json=payload, timeout=TIMEOUT_SECONDS))


def checked(response: requests.Response) -> dict | list:
    # Show the API's own reason, not just a code, so a failure is easy to act on.
    expect(
        response.status_code == 200,
        f"{response.request.method} {response.url} gave {response.status_code}: "
        f"{response.text[:200]}",
    )
    return response.json()


def status_of(workflow: dict, task_id: str) -> str | None:
    # None = the task is missing from the workflow, which fails the check that uses it.
    return next((t["status"] for t in workflow["workflow"] if t["id"] == task_id), None)


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


if __name__ == "__main__":
    sys.exit(main())
