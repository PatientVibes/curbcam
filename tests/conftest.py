"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture
def fixed_seed() -> int:
    """Stable seed for any test using stochastic helpers."""
    return 42
