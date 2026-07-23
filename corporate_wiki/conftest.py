import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Prevent login-throttle state (or anything else cached) from leaking
    between tests — the default cache backend is process-wide LocMemCache.
    """
    cache.clear()
    yield
    cache.clear()
