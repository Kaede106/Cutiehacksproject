import sys
from pathlib import Path

# Make `farm` importable however pytest is started (repo root or farm/bot).
REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
