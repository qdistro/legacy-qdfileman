"""Multi-rename plugin for QFileMan.

A batch renaming tool patterned after the Total Commander / Krusader /
Double Commander multi-rename utilities. The user picks a starting
file in the file list and the plugin renames every sibling in the same
directory according to a template.

Template tokens:

* ``[N]``      — original base name (without extension)
* ``[E]``      — original extension (including the dot, or empty)
* ``[C]``      — sequential counter, padded to the configured width
* ``[C:n]``    — sequential counter padded to ``n`` digits

The search/replace pair is applied to the base name *before* the
template is rendered. Setting "Search" to empty disables that step.

The transform — :func:`apply_template` — is a pure function so it can
be tested without touching the filesystem or Qt.
"""

from __future__ import annotations

import logging
import os
import re

from qfileman.plugin import MenuProvider


log = logging.getLogger(__name__)


_COUNTER_TOKEN_RE = re.compile(r"\[C(?::(\d+))?\]")


def apply_template(template: str, original: str, index: int,
                   *, search: str = "", replace: str = "",
                   default_pad: int = 3, regex: bool = False) -> str:
    """Render ``template`` for one file.

    ``original`` is the basename including extension. ``index`` is the
    zero-based position within the batch. ``default_pad`` is the digit
    width used when ``[C]`` appears without an explicit ``:n``.
    """
    base, ext = os.path.splitext(original)
    if search:
        if regex:
            try:
                base = re.sub(search, replace, base)
            except re.error as e:
                log.warning("multi_rename: bad regex %r: %s", search, e)
                # Fall through with unchanged base — the user sees their
                # template applied to the raw name, which is the least
                # surprising failure mode.
        else:
            base = base.replace(search, replace)

    out = template.replace("[N]", base).replace("[E]", ext)

    def _counter(m: re.Match) -> str:
        width = int(m.group(1)) if m.group(1) else default_pad
        return f"{index + 1:0{width}d}"

    return _COUNTER_TOKEN_RE.sub(_counter, out)


def plan_renames(directory: str, names: list[str], template: str, *,
                 search: str = "", replace: str = "",
                 regex: bool = False, default_pad: int = 3) -> list[tuple[str, str]]:
    """Return a list of ``(old_path, new_path)`` pairs for the rename.

    Skips entries that would map to themselves. Does not detect
    collisions among the new names — the rename step does, and surfaces
    the OSError to the caller.
    """
    out: list[tuple[str, str]] = []
    for i, name in enumerate(names):
        new_name = apply_template(
            template, name, i,
            search=search, replace=replace,
            default_pad=default_pad, regex=regex,
        )
        if new_name == name or not new_name:
            continue
        out.append((os.path.join(directory, name), os.path.join(directory, new_name)))
    return out


class MultiRenamePlugin(MenuProvider):
    name = "multi_rename"
    description = "Batch rename files in the current directory"
    version = "1.0"
    category = "File"

    def get_menu_items(self, path):
        if not path:
            return []
        return [("Batch Rename...", self._open_dialog)]

    def _open_dialog(self, path: str) -> None:
        from PyQt6.QtWidgets import (
            QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
            QListWidget, QListWidgetItem, QVBoxLayout, QCheckBox, QMessageBox,
        )

        directory = path if os.path.isdir(path) else os.path.dirname(path) or "."
        try:
            entries = sorted(
                e for e in os.listdir(directory)
                if os.path.isfile(os.path.join(directory, e))
            )
        except OSError as e:
            QMessageBox.warning(None, "Batch Rename", f"List failed: {e}")
            return

        if not entries:
            QMessageBox.information(None, "Batch Rename", "No files to rename.")
            return

        dlg = QDialog()
        dlg.setWindowTitle("Batch Rename")
        dlg.resize(600, 500)
        form = QFormLayout()
        template_edit = QLineEdit("[N][E]", dlg)
        search_edit = QLineEdit("", dlg)
        replace_edit = QLineEdit("", dlg)
        regex_check = QCheckBox("Regex", dlg)
        form.addRow("Template:", template_edit)
        form.addRow("Search:", search_edit)
        form.addRow("Replace:", replace_edit)
        form.addRow("", regex_check)

        preview = QListWidget(dlg)
        for old, new in plan_renames(
            directory, entries, template_edit.text(),
            search=search_edit.text(), replace=replace_edit.text(),
            regex=regex_check.isChecked(),
        ):
            preview.addItem(f"{os.path.basename(old)} → {os.path.basename(new)}")

        def refresh() -> None:
            preview.clear()
            for old, new in plan_renames(
                directory, entries, template_edit.text(),
                search=search_edit.text(), replace=replace_edit.text(),
                regex=regex_check.isChecked(),
            ):
                preview.addItem(f"{os.path.basename(old)} → {os.path.basename(new)}")

        template_edit.textChanged.connect(refresh)
        search_edit.textChanged.connect(refresh)
        replace_edit.textChanged.connect(refresh)
        regex_check.stateChanged.connect(refresh)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dlg,
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        layout = QVBoxLayout(dlg)
        layout.addLayout(form)
        layout.addWidget(QLabel("Preview:", dlg))
        layout.addWidget(preview, 1)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        plan = plan_renames(
            directory, entries, template_edit.text(),
            search=search_edit.text(), replace=replace_edit.text(),
            regex=regex_check.isChecked(),
        )
        failures: list[str] = []
        for old, new in plan:
            try:
                os.rename(old, new)
            except OSError as e:
                failures.append(f"{os.path.basename(old)}: {e}")
        if failures:
            QMessageBox.warning(
                None, "Batch Rename",
                "Some renames failed:\n" + "\n".join(failures),
            )
