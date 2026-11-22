

import pytest as _pytest


@_pytest.fixture(autouse=True)
def _no_health_cnn(monkeypatch):
    """Unit tests run without the ML team's CNN unless a test turns it on explicitly."""
    monkeypatch.setenv("CUTIEFARM_HEALTH", "0")
