"""Settings read only from the environment or a git-ignored .env (CLAUDE.md §3)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)

CRUSTDATA_BASE = "https://api.crustdata.com"
CRUSTDATA_VERSION = "2025-11-01"
MODEL = "claude-sonnet-5-5"
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache"
FIXTURES_DIR = ROOT / "fixtures"


def crustdata_key() -> str:
    return os.environ.get("CRUSTDATA_API_KEY", "")


def anthropic_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def flag(name: str, default: bool = False) -> bool:
    """Boolean setting from the environment or .env: 1/true/yes/on."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def founder_email_enabled() -> bool:
    """U8 (D22): the founder email draft is optional and off by default."""
    return flag("PROOFROOM_FOUNDER_EMAIL")
