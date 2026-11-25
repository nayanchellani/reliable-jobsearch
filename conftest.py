"""conftest.py – test configuration for the job aggregator.

Adds:
- asyncio marker so @pytest.mark.asyncio is recognised without warnings.
- pytest_pyfunc_call hook so async test functions run via asyncio.run().
- sys.path adjustment so tests find the stubs in tests/stubs/ first,
  giving offline test runs pydantic/httpx/bs4 shims without polluting the
  project root or shadowing real installed packages in production.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
import os

import pytest

# ── stub path ──────────────────────────────────────────────────────────────────
# Insert tests/stubs/ at the front of sys.path so our minimal shims are found
# when the real packages are not installed, but only during testing.
_STUBS = os.path.join(os.path.dirname(__file__), "tests", "stubs")
if _STUBS not in sys.path:
    sys.path.insert(0, _STUBS)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "asyncio: mark test as async (auto-run with asyncio.run)")


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    """Run async test functions synchronously via asyncio.run()."""
    if inspect.iscoroutinefunction(pyfuncitem.function):
        funcargs = {name: pyfuncitem.funcargs[name] for name in pyfuncitem._fixtureinfo.argnames if name in pyfuncitem.funcargs}
        asyncio.run(pyfuncitem.obj(**funcargs))
        return True  # prevent default call
    return None  # fall through to default for sync tests
