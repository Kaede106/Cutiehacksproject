import pytest
import sys
from pathlib import Path

# Make `farm` importable however pytest is started (repo root or farm/bot).
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _no_openai(monkeypatch):
    """Tests never talk to OpenAI, even if farm/bot/.env has a key."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
