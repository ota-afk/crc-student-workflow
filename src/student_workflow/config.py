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


def cors_origins() -> list[str]:
    raw = os.getenv('CORS_ORIGINS', 'http://localhost:8501')
    return [origin.strip() for origin in raw.split(',') if origin.strip()]
