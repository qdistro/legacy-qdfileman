"""Archive plugin for QFileMan.

Adds *Extract Here*, *Extract To...*, and *Create Archive...* entries
to the context menu. Each operation shells out to whichever external
tool fits the format (``tar``, ``unzip``, ``7z``); none of them are
implemented in-process, mirroring how Krusader, Dolphin, and Midnight
Commander handle archives.

Format detection is by extension, which is good enough for the common
case and trivially testable. ``detect_format`` and the ``*_argv``
builders are pure functions so they can be exercised without spawning
a process.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

from qfileman.plugin import MenuProvider


log = logging.getLogger(__name__)


EXTRACT_EXTS = (
    ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz",
    ".tar.zst", ".zip", ".7z", ".rar",
)


def detect_format(path: str) -> str | None:
    """Return a short format key for ``path`` or ``None`` if unrecognized.

    Returned keys: ``"tar"``, ``"tar.gz"``, ``"tar.bz2"``, ``"tar.xz"``,
    ``"tar.zst"``, ``"zip"``, ``"7z"``, ``"rar"``.
    """
    lower = path.lower()
    # Check the longest suffixes first so ``foo.tar.gz`` isn't read as ``.gz``.
    pairs = (
        (".tar.gz", "tar.gz"), (".tgz", "tar.gz"),
        (".tar.bz2", "tar.bz2"), (".tbz2", "tar.bz2"),
        (".tar.xz", "tar.xz"), (".txz", "tar.xz"),
        (".tar.zst", "tar.zst"),
        (".tar", "tar"),
        (".zip", "zip"),
        (".7z", "7z"),
        (".rar", "rar"),
    )
    for suffix, key in pairs:
        if lower.endswith(suffix):
            return key
    return None


def extract_argv(path: str, dest_dir: str) -> list[str] | None:
    """Build an argv to extract ``path`` into ``dest_dir``. None if unknown."""
    fmt = detect_format(path)
    if fmt is None:
        return None
    if fmt.startswith("tar"):
        # ``tar`` auto-detects the compression with -a/--auto-compress,
        # but ``-xf`` alone has handled all the listed variants for years.
        return ["tar", "-xf", path, "-C", dest_dir]
    if fmt == "zip":
        return ["unzip", "-o", path, "-d", dest_dir]
    if fmt == "7z":
        return ["7z", "x", f"-o{dest_dir}", "-y", path]
    if fmt == "rar":
        # ``unrar`` is the canonical extractor; ``7z`` can also read rar.
        return ["unrar", "x", "-o+", path, dest_dir + os.sep]
    return None


def create_argv(archive_path: str, sources: Sequence[str]) -> list[str] | None:
    """Build an argv that packs ``sources`` into ``archive_path``. None if unknown."""
    fmt = detect_format(archive_path)
    if fmt is None:
        return None
    sources = list(sources)
    if fmt == "tar":
        return ["tar", "-cf", archive_path, *sources]
    if fmt == "tar.gz":
        return ["tar", "-czf", archive_path, *sources]
    if fmt == "tar.bz2":
        return ["tar", "-cjf", archive_path, *sources]
    if fmt == "tar.xz":
        return ["tar", "-cJf", archive_path, *sources]
    if fmt == "tar.zst":
        return ["tar", "--zstd", "-cf", archive_path, *sources]
    if fmt == "zip":
        return ["zip", "-r", archive_path, *sources]
    if fmt == "7z":
        return ["7z", "a", archive_path, *sources]
    # rar creation requires a non-free binary; intentionally not offered.
    return None


def is_archive(path: str) -> bool:
    return detect_format(path) is not None


class ArchivePlugin(MenuProvider):
    name = "archive"
    description = "Extract and create archives (tar, zip, 7z, rar)"
    version = "1.0"
    category = "Tools"

    def get_menu_items(self, path):
        if not path:
            return []
        items: list = []
        if os.path.isfile(path) and is_archive(path):
            items.append(("Extract Here", self._extract_here))
            items.append(("Extract To...", self._extract_to))
        # Creating an archive is offered for any path — single file, directory,
        # or even a path that doesn't exist (lets you cancel out of the dialog).
        items.append(("Create Archive...", self._create_archive))
        return items

    # ----------------------------------------------------------------- actions
    def _extract_here(self, path: str) -> None:
        dest = os.path.dirname(path) or "."
        argv = extract_argv(path, dest)
        if argv is None:
            self._warn(f"Don't know how to extract: {path}")
            return
        self._run(f"Extract {os.path.basename(path)}", argv, cwd=dest)

    def _extract_to(self, path: str) -> None:
        from PyQt6.QtWidgets import QFileDialog

        dest = QFileDialog.getExistingDirectory(
            None, "Extract To", os.path.dirname(path) or os.getcwd()
        )
        if not dest:
            return
        argv = extract_argv(path, dest)
        if argv is None:
            self._warn(f"Don't know how to extract: {path}")
            return
        self._run(f"Extract {os.path.basename(path)}", argv, cwd=dest)

    def _create_archive(self, path: str) -> None:
        from PyQt6.QtWidgets import QFileDialog, QInputDialog

        base_dir = os.path.dirname(path) or os.getcwd()
        default_name = os.path.basename(path.rstrip(os.sep)) or "archive"
        formats = [
            "tar.gz", "tar.xz", "tar.bz2", "tar.zst", "tar", "zip", "7z",
        ]
        fmt, ok = QInputDialog.getItem(
            None, "Create Archive", "Format:", formats, 0, False
        )
        if not ok:
            return
        suggested = os.path.join(base_dir, f"{default_name}.{fmt}")
        archive_path, _ = QFileDialog.getSaveFileName(
            None, "Save Archive As", suggested
        )
        if not archive_path:
            return
        source = os.path.basename(path.rstrip(os.sep))
        argv = create_argv(archive_path, [source])
        if argv is None:
            self._warn(f"Unsupported archive format: {archive_path}")
            return
        self._run(f"Create {os.path.basename(archive_path)}", argv, cwd=base_dir)

    # ------------------------------------------------------------- plumbing
    def _run(self, title: str, argv: list[str], cwd: str) -> None:
        from qfileman.plugins.builtin._runner import (
            missing_tools, run_command_dialog,
        )

        missing = missing_tools([argv[0]])
        if missing:
            self._warn(f"Required tool not found on PATH: {missing[0]}")
            return
        run_command_dialog(title, argv, cwd=cwd)

    @staticmethod
    def _warn(message: str) -> None:
        from PyQt6.QtWidgets import QMessageBox
        log.warning(message)
        QMessageBox.warning(None, "Archive", message)
