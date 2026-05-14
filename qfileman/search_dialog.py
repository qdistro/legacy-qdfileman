"""Non-blocking search dialog that wraps :class:`qfileman.search.FileSearch`.

The dialog exposes glob-pattern search and an optional substring content
filter. Double-clicking a result emits :pyattr:`path_chosen` so the main
window can navigate to the result's parent directory and select it.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from qfileman.search import FileSearch


log = logging.getLogger(__name__)

# Hard cap on result rows so a pathological query doesn't hang the UI.
_MAX_RESULTS = 500


class SearchDialog(QDialog):
    """Modal-but-non-blocking search dialog rooted at a given directory."""

    path_chosen = pyqtSignal(str)

    def __init__(self, root: str | Path, parent=None, show_hidden: bool = False) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find")
        self.resize(560, 420)
        self._root = Path(root)
        self._show_hidden = show_hidden
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.pattern_edit = QLineEdit("*")
        self.pattern_edit.setToolTip("Glob pattern, e.g. *.py")
        form.addRow("Filename pattern:", self.pattern_edit)

        self.content_edit = QLineEdit()
        self.content_edit.setPlaceholderText("(optional) only files containing this text")
        form.addRow("Content contains:", self.content_edit)

        self.cb_case = QCheckBox("Case sensitive")
        self.cb_hidden = QCheckBox("Include hidden files")
        self.cb_hidden.setChecked(self._show_hidden)
        opts = QHBoxLayout()
        opts.addWidget(self.cb_case)
        opts.addWidget(self.cb_hidden)
        opts.addStretch(1)
        form.addRow("", self._wrap(opts))
        layout.addLayout(form)

        self.root_label = QLabel(f"Searching in: {self._root}")
        self.root_label.setWordWrap(True)
        layout.addWidget(self.root_label)

        controls = QHBoxLayout()
        self.search_btn = QPushButton("Search")
        self.search_btn.setDefault(True)
        self.search_btn.clicked.connect(self._run_search)
        controls.addWidget(self.search_btn)
        controls.addStretch(1)
        self.status_label = QLabel("")
        controls.addWidget(self.status_label)
        layout.addLayout(controls)

        self.results = QListWidget()
        self.results.itemActivated.connect(self._on_result_activated)
        layout.addWidget(self.results, 1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    @staticmethod
    def _wrap(inner_layout):
        from PyQt6.QtWidgets import QWidget

        w = QWidget()
        w.setLayout(inner_layout)
        return w

    def _run_search(self) -> None:
        """Execute the configured search and populate the result list."""
        self.results.clear()
        pattern = self.pattern_edit.text().strip() or "*"
        content = self.content_edit.text()
        hidden = self.cb_hidden.isChecked()
        case_sensitive = self.cb_case.isChecked()

        # FileSearch internally swallows per-file OSErrors and continues,
        # so we don't need an outer try/except here.
        searcher = FileSearch(self._root)
        count = 0
        if content:
            for fp, line_no, line_text in searcher.by_content(
                content,
                pattern=pattern,
                hidden=hidden,
                case_sensitive=case_sensitive,
            ):
                item = QListWidgetItem(f"{fp}  :{line_no}:  {line_text.strip()}")
                item.setData(Qt.ItemDataRole.UserRole, str(fp))
                self.results.addItem(item)
                count += 1
                if count >= _MAX_RESULTS:
                    break
        else:
            for fp in searcher.by_name(pattern, hidden=hidden):
                item = QListWidgetItem(str(fp))
                item.setData(Qt.ItemDataRole.UserRole, str(fp))
                self.results.addItem(item)
                count += 1
                if count >= _MAX_RESULTS:
                    break

        suffix = " (truncated)" if count >= _MAX_RESULTS else ""
        self.status_label.setText(f"{count} match{'es' if count != 1 else ''}{suffix}")

    def _on_result_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if path:
            self.path_chosen.emit(path)
