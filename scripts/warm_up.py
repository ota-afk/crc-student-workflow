"""Wake both live services before recording or judging (STU-D05-BE).

A free Render service sleeps after 15 idle minutes, and the first request then takes about a
minute. Run this a few minutes before the demo so judges never see that wait.

    uv run --env-file .env.smoke python scripts/warm_up.py

.env.smoke (git-ignored, see docs/deploy.md) needs API_URL and DASHBOARD_URL. Only the public
health pages are called, so no API key is needed.
"""

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

logger = logging.getLogger("warm_up")

WAKE_UP_SECONDS = 180  # generous: a free service usually needs about a minute
TIMEOUT_SECONDS = 30  # per request, so a hung service doesn't stall the loop forever


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(message)s")
    targets = {
        "API": (os.getenv("API_URL", ""), "/health"),
        "Dashboard": (os.getenv("DASHBOARD_URL", ""), "/_stcore/health"),
    }
    missing = [name for name, (url, _path) in targets.items() if not url.strip()]
    if missing:
        # Fail loudly: warming "nothing" would look like success right before the demo.
        logger.error(
            "FAIL: set API_URL and DASHBOARD_URL (missing: %s)", ", ".join(missing)
        )
        return 1
    checks = [
        (name, url.strip().rstrip("/") + path) for name, (url, path) in targets.items()
    ]
    # Both at once (one thread each), so the dashboard doesn't wait for the API to wake first.
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        awake = list(pool.map(lambda check: wake(*check), checks))
    return 0 if all(awake) else 1


def wake(name: str, url: str) -> bool:
    """Ask until the service answers 200, or give up after WAKE_UP_SECONDS."""
    started = time.monotonic()
    while time.monotonic() - started < WAKE_UP_SECONDS:
        try:
            if requests.get(url, timeout=TIMEOUT_SECONDS).status_code == 200:
                logger.info(
                    "ok  %s is awake (%.0f s)", name, time.monotonic() - started
                )
                return True
        except requests.RequestException:
            pass  # still waking up: try again
        time.sleep(3)
    logger.error(
        "FAIL: %s did not answer within %d seconds: %s", name, WAKE_UP_SECONDS, url
    )
    return False


if __name__ == "__main__":
    sys.exit(main())
