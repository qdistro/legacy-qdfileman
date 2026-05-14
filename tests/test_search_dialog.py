"""Tests for SearchDialog."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QListWidgetItem

from qfileman.search_dialog import SearchDialog


def _result_paths(dlg):
    return [
        dlg.results.item(i).data(Qt.ItemDataRole.UserRole)
        for i in range(dlg.results.count())
    ]


def test_search_dialog_name_pattern(qapp, tmp_tree):
    dlg = SearchDialog(tmp_tree)
    try:
        dlg.pattern_edit.setText("*.py")
        dlg._run_search()
        paths = _result_paths(dlg)
        assert len(paths) == 1
        assert paths[0].endswith("file2.py")
        assert "1 match" in dlg.status_label.text()
    finally:
        dlg.deleteLater()


def test_search_dialog_content_filter(qapp, tmp_tree):
    dlg = SearchDialog(tmp_tree)
    try:
        dlg.content_edit.setText("hello")
        dlg._run_search()
        paths = _result_paths(dlg)
        assert len(paths) == 1
        assert paths[0].endswith("file1.txt")
    finally:
        dlg.deleteLater()


def test_search_dialog_hidden_toggle(qapp, tmp_tree):
    dlg = SearchDialog(tmp_tree, show_hidden=False)
    try:
        dlg.pattern_edit.setText("*")
        dlg._run_search()
        paths_visible = _result_paths(dlg)
        assert not any(p.endswith(".hidden") for p in paths_visible)

        dlg.cb_hidden.setChecked(True)
        dlg._run_search()
        paths_with_hidden = _result_paths(dlg)
        assert any(p.endswith(".hidden") for p in paths_with_hidden)
    finally:
        dlg.deleteLater()


def test_search_dialog_path_chosen_signal(qapp, tmp_tree):
    received = []
    dlg = SearchDialog(tmp_tree)
    try:
        dlg.path_chosen.connect(received.append)
        dlg.pattern_edit.setText("file1.txt")
        dlg._run_search()
        assert dlg.results.count() == 1
        dlg._on_result_activated(dlg.results.item(0))
        assert len(received) == 1
        assert received[0].endswith("file1.txt")
    finally:
        dlg.deleteLater()


def test_search_dialog_empty_pattern_defaults_to_star(qapp, tmp_tree):
    dlg = SearchDialog(tmp_tree)
    try:
        dlg.pattern_edit.setText("")  # whitespace fallback
        dlg._run_search()
        # Should still produce results (all visible files)
        assert dlg.results.count() > 0
    finally:
        dlg.deleteLater()


def test_search_dialog_zero_matches_status(qapp, tmp_tree):
    dlg = SearchDialog(tmp_tree)
    try:
        dlg.pattern_edit.setText("*.no_such_ext")
        dlg._run_search()
        assert dlg.results.count() == 0
        assert "0 match" in dlg.status_label.text()
    finally:
        dlg.deleteLater()
