"""Checksum plugin for QFileMan.

Adds MD5 / SHA-1 / SHA-256 entries that hash the selected file with
``hashlib`` (no subprocess) and show the digest in a dialog with a
copy-to-clipboard button. Big files are streamed in chunks rather
than slurped into memory.
"""

from __future__ import annotations

import hashlib
import logging
import os

from qfileman.plugin import MenuProvider


log = logging.getLogger(__name__)


_CHUNK = 1 << 20  # 1 MiB


def hash_file(path: str, algorithm: str = "sha256") -> str:
    """Return the hex digest of ``path`` using ``algorithm``.

    ``algorithm`` is anything :func:`hashlib.new` accepts. Raises
    ``OSError`` if the file can't be read.
    """
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


class ChecksumPlugin(MenuProvider):
    name = "checksum"
    description = "Compute MD5 / SHA-1 / SHA-256 of a file"
    version = "1.0"
    category = "Tools"

    def get_menu_items(self, path):
        if not path or not os.path.isfile(path):
            return []
        return [
            ("MD5 Sum", lambda p: self._show(p, "md5")),
            ("SHA-1 Sum", lambda p: self._show(p, "sha1")),
            ("SHA-256 Sum", lambda p: self._show(p, "sha256")),
        ]

    def _show(self, path: str, algorithm: str) -> None:
        from PyQt6.QtWidgets import (
            QApplication, QDialog, QDialogButtonBox, QLabel, QLineEdit,
            QPushButton, QVBoxLayout,
        )
        try:
            digest = hash_file(path, algorithm)
        except OSError as e:
            log.warning("hash %s failed: %s", path, e)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Checksum", f"Read failed: {e}")
            return

        dlg = QDialog()
        dlg.setWindowTitle(f"{algorithm.upper()} — {os.path.basename(path)}")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(path, dlg))
        field = QLineEdit(digest, dlg)
        field.setReadOnly(True)
        field.selectAll()
        layout.addWidget(field)
        copy_btn = QPushButton("Copy", dlg)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(digest))
        layout.addWidget(copy_btn)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()
