"""Folder-size plugin for QFileMan.

Adds *Folder Size…* — a recursive size walker that pops a sortable
table of the immediate children of the selected directory plus a
grand total at the top. Mirrors Dolphin's "Show Folder Size" and the
classic ``ncdu`` workflow without depending on either.

The walker is :func:`directory_size` — a tight ``os.scandir``-based
loop that recurses without following symlinks (which would risk
loops) and silently skips entries that error out (broken symlinks,
unreadable directories). It's exposed at module level so the
plugin's pure logic can be exercised under tests.
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from qfileman.plugin import MenuProvider


log = logging.getLogger(__name__)


def directory_size(path: str, *, follow_symlinks: bool = False) -> int:
    """Return the total byte size of ``path``, recursing into subdirs.

    Errors from individual ``stat`` / ``scandir`` calls are swallowed
    rather than propagated; that matches the behaviour of ``du`` and
    avoids breaking a long walk because of one permissions-denied
    directory.
    """
    total = 0
    stack: list[str] = [path]
    while stack:
        current = stack.pop()
        try:
            it = os.scandir(current)
        except OSError as e:
            log.debug("scandir(%s): %s", current, e)
            continue
        with it:
            for entry in it:
                try:
                    if entry.is_symlink() and not follow_symlinks:
                        # Count the symlink itself (its lstat size),
                        # not the target.
                        total += entry.stat(follow_symlinks=False).st_size
                        continue
                    if entry.is_dir(follow_symlinks=follow_symlinks):
                        stack.append(entry.path)
                    else:
                        total += entry.stat(
                            follow_symlinks=follow_symlinks
                        ).st_size
                except OSError as e:
                    log.debug("stat(%s): %s", entry.path, e)
    return total


def format_size(n: int) -> str:
    """Return a human-readable byte count, IEC units (1024-based)."""
    if n < 1024:
        return f"{n} B"
    units = ("KiB", "MiB", "GiB", "TiB", "PiB")
    value = float(n)
    for unit in units:
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} EiB"


def child_sizes(path: str) -> list[tuple[str, int, bool]]:
    """Return ``(name, size, is_dir)`` for each immediate child of ``path``.

    Children that error out during stat/scan are skipped silently.
    Sizes for subdirectories are recursive (call :func:`directory_size`).
    Order follows :func:`os.scandir` (unspecified).
    """
    out: list[tuple[str, int, bool]] = []
    try:
        it = os.scandir(path)
    except OSError:
        return out
    with it:
        for entry in it:
            try:
                if entry.is_dir(follow_symlinks=False):
                    out.append((entry.name, directory_size(entry.path), True))
                else:
                    size = entry.stat(follow_symlinks=False).st_size
                    out.append((entry.name, size, False))
            except OSError:
                continue
    return out


class FolderSizePlugin(MenuProvider):
    name = "folder_size"
    description = "Recursive folder size breakdown (du-style)"
    version = "1.0"
    category = "Tools"

    def get_menu_items(self, path):
        if not path or not os.path.isdir(path):
            return []
        return [("Folder Size…", self._show)]

    def _show(self, path: str) -> None:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QDialog, QDialogButtonBox, QLabel, QTreeWidget, QTreeWidgetItem,
            QVBoxLayout,
        )

        children = child_sizes(path)
        total = sum(s for _n, s, _d in children)

        dlg = QDialog()
        dlg.setWindowTitle(f"Size: {os.path.basename(path) or path}")
        dlg.resize(550, 450)
        layout = QVBoxLayout(dlg)
        layout.addWidget(
            QLabel(f"<b>Total:</b> {format_size(total)} ({total:,} bytes)", dlg)
        )
        tree = QTreeWidget(dlg)
        tree.setHeaderLabels(["Name", "Size", "Bytes"])
        tree.setSortingEnabled(True)
        tree.setRootIsDecorated(False)

        for name, size, is_dir in sorted(children, key=lambda c: -c[1]):
            display = name + "/" if is_dir else name
            item = QTreeWidgetItem([display, format_size(size), f"{size:,}"])
            # Right-align numeric columns.
            item.setTextAlignment(1, int(Qt.AlignmentFlag.AlignRight))
            item.setTextAlignment(2, int(Qt.AlignmentFlag.AlignRight))
            # Sort by the bytes column numerically; Qt sorts strings by
            # default, so stash the int as user data on column 2.
            item.setData(2, Qt.ItemDataRole.UserRole, size)
            tree.addTopLevelItem(item)

        # Sort by bytes descending by default.
        tree.sortByColumn(2, Qt.SortOrder.DescendingOrder)
        tree.resizeColumnToContents(0)
        layout.addWidget(tree, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()
