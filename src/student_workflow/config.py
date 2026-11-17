"""Read configuration when needed so tests and local tools can override data paths."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


def use_mock() -> bool:
    return os.getenv('USE_MOCK', 'true').lower() == 'true'


def mock_path() -> Path:
    default = ROOT / 'data' / 'mock' / 'workflow.mock.json'
    return Path(os.getenv('MOCK_PATH', str(default)))


def rules_path() -> Path:
    # Read on every call (like mock_path), so tests can point it at a temporary file.
    default = ROOT / 'data' / 'rules' / 'rules.json'
    return Path(os.getenv('RULES_PATH', str(default)))


def schools_path() -> Path:
    default = ROOT / 'data' / 'schools' / 'sevp_schools_ca.csv'
    return Path(os.getenv('SCHOOLS_PATH', str(default)))


def api_key() -> str:
    # '' = no key set, so the X-API-Key check is off (local development and tests only).
    return os.getenv('API_KEY', '').strip()


def rate_limit() -> str:
    # slowapi's format, e.g. '60/minute'. Read on every request, so tests can lower it.
    return os.getenv('RATE_LIMIT', '60/minute').strip()


def cors_origins() -> list[str]:
    raw = os.getenv('CORS_ORIGINS', 'http://localhost:8501')
    return [origin.strip() for origin in raw.split(',') if origin.strip()]


def resend_api_key() -> str:
    # '' = reminders are switched off; the route answers 503 rather than pretending to send.
    return os.getenv('RESEND_API_KEY', '').strip()


def reminder_from() -> str:
    # Resend's shared test sender until the team verifies its own domain.
    return os.getenv('REMINDER_FROM', 'Flyover <onboarding@resend.dev>').strip()


def reminder_recipients() -> set[str]:
    """Who the public demo may email: a comma-separated allow-list set on Render.

    Empty = nobody, so a stranger on the public link can never make the app email anyone.
    """
    raw = os.getenv('REMINDER_RECIPIENTS', '')
    return {address.strip().lower() for address in raw.split(',') if address.strip()}
