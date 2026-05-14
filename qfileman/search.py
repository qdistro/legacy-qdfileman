"""File search across a directory tree.

Ported from the dual qfileman implementation under qdistro-org2; same
public surface (``by_name`` / ``by_content``) with logging added for
unreadable files so journal-line assertions can see them.
"""

from __future__ import annotations

import fnmatch
import logging
import os
from pathlib import Path
from typing import Iterator


log = logging.getLogger(__name__)


class FileSearch:
    """Search a directory tree by filename pattern and/or file content."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def by_name(
        self,
        pattern: str = "*",
        hidden: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[Path]:
        """Yield paths whose basename matches ``pattern`` (glob syntax)."""
        for dirpath, dirnames, filenames in self._walk(self.root, max_depth):
            if not hidden:
                # Drop hidden subdirs from traversal in-place so os.walk skips them.
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if not hidden and name.startswith("."):
                    continue
                if fnmatch.fnmatch(name, pattern):
                    yield dirpath / name

    def by_content(
        self,
        query: str,
        pattern: str = "*",
        hidden: bool = False,
        case_sensitive: bool = False,
        max_depth: int | None = None,
    ) -> Iterator[tuple[Path, int, str]]:
        """Yield ``(path, line_no, line_text)`` for files containing ``query``."""
        needle = query if case_sensitive else query.lower()
        for dirpath, dirnames, filenames in self._walk(self.root, max_depth):
            if not hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if not hidden and name.startswith("."):
                    continue
                if not fnmatch.fnmatch(name, pattern):
                    continue
                fp = dirpath / name
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    log.warning("search: could not read %s: %s", fp, e)
                    continue
                for i, line in enumerate(text.splitlines(), 1):
                    haystack = line if case_sensitive else line.lower()
                    if needle in haystack:
                        yield (fp, i, line)

    @staticmethod
    def _walk(
        root: Path, max_depth: int | None
    ) -> Iterator[tuple[Path, list[str], list[str]]]:
        """``os.walk`` with optional depth cap measured from ``root``."""
        root = root.resolve()
        for dirpath, dirnames, filenames in os.walk(root):
            dp = Path(dirpath)
            if max_depth is not None:
                try:
                    depth = len(dp.relative_to(root).parts)
                except ValueError:
                    depth = 0
                if depth > max_depth:
                    dirnames.clear()
                    continue
            yield (dp, dirnames, filenames)
