"""Shared test config.

Ensures the tests directory is importable so `from probe import cmd` works
regardless of pytest's import mode, then re-exports `cmd` as the `probe`
fixture for tests that prefer fixture injection.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402

from probe import cmd  # noqa: E402


@pytest.fixture(name="probe")
def probe_fixture():
    """Expose the command builder as a fixture: probe("ok") -> shell cmd."""
    return cmd
