"""Optional-dependency import guards.

playwright and pyarrow are deliberately not in requirements.txt; the code
paths that need them must fail with a one-line install hint, not a raw
ModuleNotFoundError. Absence is simulated by poisoning sys.modules (a None
entry makes any import of that module raise ImportError), so these tests
pass whether or not the optional deps are actually installed.
"""

import asyncio
import sys
from pathlib import Path

import pytest


def _poison(monkeypatch, *modules: str) -> None:
    """Make `import <module>` raise ImportError even if it is installed."""
    for mod in modules:
        monkeypatch.setitem(sys.modules, mod, None)


def test_session_open_without_playwright(monkeypatch, tmp_path):
    from paperscope.systematic_review.acquire.session import Session

    _poison(monkeypatch, "playwright", "playwright.async_api")
    session = Session(tmp_path / "session-state.json")
    with pytest.raises(RuntimeError, match=r"pip install playwright"):
        asyncio.run(session.open())


def test_cluster_load_vectors_without_pyarrow(monkeypatch, tmp_path):
    from paperscope.systematic_review.methodological_audit.cluster import _load_vectors

    _poison(monkeypatch, "pyarrow", "pyarrow.parquet")
    with pytest.raises(RuntimeError, match=r"pip install pyarrow"):
        _load_vectors(tmp_path / "corpus.parquet")
