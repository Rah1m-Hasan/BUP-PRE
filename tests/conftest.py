"""Shared pytest fixtures."""

import pytest


@pytest.fixture(autouse=True)
def clear_cache():
    from app.services.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def reset_mock_interps():
    from app.api import dependencies as deps

    deps.set_mock_interpretations({})
    yield
    deps.set_mock_interpretations({})
