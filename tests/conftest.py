"""Global test configuration and cleanup fixtures."""

from __future__ import annotations

import threading
import time

import pytest


@pytest.fixture(autouse=True, scope="session")
def _cleanup_threads():
    """Yield control to the test session, then join lingering non-daemon threads.

    Some dependencies (chromadb, prometheus, sentence-transformers) may spawn
    non-daemon background threads that prevent the process from exiting after
    all tests pass.  This fixture waits briefly for them to finish on their own,
    then forcibly marks any survivors as daemon so the interpreter can shut down.
    """
    yield

    main_thread = threading.main_thread()
    deadline = time.monotonic() + 5  # wait up to 5 seconds

    for t in threading.enumerate():
        if t is main_thread or t.daemon:
            continue
        remaining = deadline - time.monotonic()
        if remaining > 0:
            t.join(timeout=remaining)

    # If any non-daemon threads are still alive, force them to daemon so
    # the process can exit.
    for t in threading.enumerate():
        if t is main_thread or t.daemon:
            continue
        t.daemon = True
