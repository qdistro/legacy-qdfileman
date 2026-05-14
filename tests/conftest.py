"""Shared fixtures and cleanup for QFileMan tests.

Runs under Qt's offscreen platform plugin by default so tests don't pop
real windows on the active desktop. Override with
``QT_QPA_PLATFORM=xcb pytest`` if you need an on-screen run.
"""

import gc
import os

# Default to offscreen rendering. Must be set before QApplication is
# constructed, which happens lazily on first qtbot use.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(autouse=True)
def _cleanup_after_test():
    """Clean up after every test to prevent memory leaks.

    Runs multiple processEvents+gc rounds to ensure deleteLater()
    calls are processed and C++ objects are freed.
    """
    yield
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
            gc.collect()
            app.processEvents()


@pytest.fixture
def tmp_dir(tmp_path):
    """Create a temporary directory with some files for testing."""
    test_dir = tmp_path / "test_files"
    test_dir.mkdir()

    # Create some test files with predictable content for sorting tests
    # file1.txt - smallest (8 bytes)
    (test_dir / "file1.txt").write_text("content1")
    # file2.txt - medium (8 bytes)
    (test_dir / "file2.txt").write_text("content2")
    # file3.md - different extension for type sorting
    (test_dir / "file3.md").write_text("# Markdown")

    # Create subdirectory (for navigation tests)
    subdir = test_dir / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested content")

    # Create hidden file (for hidden toggle tests)
    (test_dir / ".hidden").write_text("hidden")

    return test_dir


@pytest.fixture
def nested_tmp_dir(tmp_path):
    """Create a 2-level temp directory for navigation tests."""
    parent = tmp_path / "parent_dir"
    parent.mkdir()
    (parent / "parent_file.txt").write_text("parent")

    child = parent / "child_dir"
    child.mkdir()
    (child / "child_file.txt").write_text("child")

    return parent


@pytest.fixture
def tmp_tree(tmp_path):
    """Realistic sample tree used by search/preferences/theme tests.

    Mirrors the fixture used in the sibling qfileman variant so ported
    tests can be reused with minimal edits.
    """
    root = tmp_path / "tree"
    root.mkdir()
    (root / "file1.txt").write_text("hello\n", encoding="utf-8")
    (root / "file2.py").write_text("print('hi')\n", encoding="utf-8")
    sub = root / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested\n", encoding="utf-8")
    (root / ".hidden").write_text("secret\n", encoding="utf-8")
    dot_dir = root / ".dotdir"
    dot_dir.mkdir()
    (dot_dir / "inside.txt").write_text("hidden dir file\n", encoding="utf-8")
    return root
