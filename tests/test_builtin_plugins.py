"""Tests for the additional built-in plugins.

These tests stick to the pure-logic surface — argv builders, format
detection, hashing, and rename-template rendering — so they don't need
``rsync``, ``scp``, ``tar`` or any other external tool to be installed
on the box running the suite.
"""

from __future__ import annotations

import hashlib
import os

import pytest

from qfileman.plugin import MenuProvider, PluginManager
from qfileman.plugins.builtin import archive as archive_mod
from qfileman.plugins.builtin import checksum as checksum_mod
from qfileman.plugins.builtin import multi_rename as mr_mod
from qfileman.plugins.builtin import remote_copy as rc_mod
from qfileman.plugins.builtin import rsync_sync as rs_mod


# ---------------------------------------------------------------------------
# Discovery: every new plugin must be findable by the manager.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "archive", "remote_copy", "rsync_sync", "checksum", "multi_rename",
])
def test_new_plugins_discovered(name):
    pm = PluginManager()
    pm.discover()
    assert name in pm.available_plugins()


@pytest.mark.parametrize("name", [
    "archive", "remote_copy", "rsync_sync", "checksum", "multi_rename",
])
def test_new_plugins_load(name):
    pm = PluginManager()
    pm.discover()
    plugin = pm.load(name)
    assert plugin is not None
    assert isinstance(plugin, MenuProvider)


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path, expected", [
    ("foo.tar", "tar"),
    ("foo.tar.gz", "tar.gz"),
    ("foo.TGZ", "tar.gz"),
    ("foo.tar.bz2", "tar.bz2"),
    ("foo.tbz2", "tar.bz2"),
    ("foo.tar.xz", "tar.xz"),
    ("foo.txz", "tar.xz"),
    ("foo.tar.zst", "tar.zst"),
    ("foo.zip", "zip"),
    ("foo.7z", "7z"),
    ("foo.rar", "rar"),
    ("foo.gz", None),  # bare .gz is not an archive in this scheme
    ("plain.txt", None),
])
def test_detect_format(path, expected):
    assert archive_mod.detect_format(path) == expected


def test_extract_argv_tar():
    argv = archive_mod.extract_argv("/a/b.tar.gz", "/dst")
    assert argv == ["tar", "-xf", "/a/b.tar.gz", "-C", "/dst"]


def test_extract_argv_zip():
    argv = archive_mod.extract_argv("/a/b.zip", "/dst")
    assert argv == ["unzip", "-o", "/a/b.zip", "-d", "/dst"]


def test_extract_argv_7z():
    argv = archive_mod.extract_argv("/a/b.7z", "/dst")
    assert argv == ["7z", "x", "-o/dst", "-y", "/a/b.7z"]


def test_extract_argv_unknown():
    assert archive_mod.extract_argv("/a/b.txt", "/dst") is None


def test_create_argv_targz():
    argv = archive_mod.create_argv("/out.tar.gz", ["src"])
    assert argv == ["tar", "-czf", "/out.tar.gz", "src"]


def test_create_argv_zip():
    argv = archive_mod.create_argv("/out.zip", ["a", "b"])
    assert argv == ["zip", "-r", "/out.zip", "a", "b"]


def test_create_argv_unsupported_rar():
    # We deliberately don't offer rar creation.
    assert archive_mod.create_argv("/out.rar", ["src"]) is None


def test_archive_menu_items_for_archive_file(tmp_path):
    archive = tmp_path / "x.tar.gz"
    archive.write_bytes(b"")
    plugin = archive_mod.ArchivePlugin()
    labels = [label for label, _cb in plugin.get_menu_items(str(archive))]
    assert "Extract Here" in labels
    assert "Extract To..." in labels
    assert "Create Archive..." in labels


def test_archive_menu_items_for_plain_file(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("hi")
    plugin = archive_mod.ArchivePlugin()
    labels = [label for label, _cb in plugin.get_menu_items(str(f))]
    assert "Extract Here" not in labels
    assert "Create Archive..." in labels


# ---------------------------------------------------------------------------
# remote_copy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dest, scp, ftp", [
    ("user@host:/tmp/foo", True, False),
    ("host:/tmp/foo", True, False),
    ("ftp://host/dir/", False, True),
    ("ftps://user:pw@host/path", False, True),
    ("/local/path", False, False),
    ("relative/path", False, False),
])
def test_remote_dest_classification(dest, scp, ftp):
    assert rc_mod.is_scp_dest(dest) is scp
    assert rc_mod.is_ftp_dest(dest) is ftp


def test_scp_argv_shape():
    argv = rc_mod.scp_argv("/src/file", "user@host:/dst")
    assert argv[0] == "scp"
    assert "/src/file" in argv
    assert "user@host:/dst" in argv
    assert "-r" in argv[1]  # -rp


def test_sftp_batch_argv_builds_script():
    built = rc_mod.sftp_batch_argv("/src/file", "user@host:/dst/path")
    assert built is not None
    argv, script = built
    assert argv[:3] == ["sftp", "-b", "-"]
    assert argv[-1] == "user@host"
    assert "/src/file" in script
    assert "/dst/path" in script
    assert script.startswith("put ")


def test_sftp_batch_argv_rejects_non_scp_dest():
    assert rc_mod.sftp_batch_argv("/src", "/local/path") is None
    assert rc_mod.sftp_batch_argv("/src", "ftp://host/") is None


def test_lftp_argv_file_upload(tmp_path):
    f = tmp_path / "thing.txt"
    f.write_text("x")
    argv = rc_mod.lftp_argv(str(f), "ftp://host/incoming/")
    assert argv is not None
    assert argv[0] == "lftp"
    assert argv[-1] == "ftp://host"
    # The script is the -e payload.
    script = argv[2]
    assert "cd " in script
    assert "/incoming/" in script
    assert "put" in script
    assert "thing.txt" in script


def test_lftp_argv_rejects_non_ftp():
    assert rc_mod.lftp_argv("/src", "user@host:/dst") is None


# ---------------------------------------------------------------------------
# rsync_sync
# ---------------------------------------------------------------------------

def test_rsync_argv_basic_copy():
    argv = rs_mod.rsync_argv("/src/", "/dst/")
    assert argv[0] == "rsync"
    # Flags that deliver "resumable copy":
    for flag in ("--partial", "--append-verify", "--inplace", "-a"):
        assert flag in argv, f"missing {flag}: {argv}"
    assert argv[-2:] == ["/src/", "/dst/"]
    assert "--remove-source-files" not in argv
    assert "--dry-run" not in argv


def test_rsync_argv_move_appends_remove_source():
    argv = rs_mod.rsync_argv("/src/", "/dst/", move=True)
    assert "--remove-source-files" in argv


def test_rsync_argv_dry_run():
    argv = rs_mod.rsync_argv("/src/", "/dst/", dry_run=True)
    assert "--dry-run" in argv


def test_rsync_argv_remote_dest_passes_through():
    argv = rs_mod.rsync_argv("/src/", "user@host:/dst/")
    assert argv[-1] == "user@host:/dst/"


# ---------------------------------------------------------------------------
# checksum
# ---------------------------------------------------------------------------

def test_hash_file_matches_hashlib(tmp_path):
    f = tmp_path / "data.bin"
    payload = b"the quick brown fox" * 1000
    f.write_bytes(payload)
    expected = hashlib.sha256(payload).hexdigest()
    assert checksum_mod.hash_file(str(f), "sha256") == expected


def test_hash_file_md5(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"hello")
    assert checksum_mod.hash_file(str(f), "md5") == hashlib.md5(b"hello").hexdigest()


def test_checksum_menu_items_only_for_files(tmp_path):
    plugin = checksum_mod.ChecksumPlugin()
    f = tmp_path / "a"
    f.write_text("x")
    labels = [lbl for lbl, _cb in plugin.get_menu_items(str(f))]
    assert "MD5 Sum" in labels
    # Directories: no items.
    assert plugin.get_menu_items(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# multi_rename
# ---------------------------------------------------------------------------

def test_apply_template_name_and_ext():
    assert mr_mod.apply_template("[N][E]", "foo.txt", 0) == "foo.txt"


def test_apply_template_counter_default_pad():
    assert mr_mod.apply_template("[C]_[N][E]", "foo.txt", 4) == "005_foo.txt"


def test_apply_template_counter_custom_pad():
    assert mr_mod.apply_template("[C:2]_[N][E]", "foo.txt", 0) == "01_foo.txt"


def test_apply_template_search_replace():
    out = mr_mod.apply_template(
        "[N][E]", "draft_thing.txt", 0, search="draft_", replace="",
    )
    assert out == "thing.txt"


def test_apply_template_regex():
    out = mr_mod.apply_template(
        "[N][E]", "img_001.jpg", 0,
        search=r"^img_(\d+)$", replace=r"photo_\1", regex=True,
    )
    assert out == "photo_001.jpg"


def test_apply_template_bad_regex_falls_through():
    # Unbalanced paren — should not raise, just leave base unchanged.
    out = mr_mod.apply_template(
        "[N][E]", "a.txt", 0, search="(", replace="x", regex=True,
    )
    assert out == "a.txt"


def test_plan_renames_skips_identity():
    plan = mr_mod.plan_renames(
        "/d", ["a.txt", "b.txt"], "[N][E]",
    )
    assert plan == []


def test_plan_renames_uses_counter_index():
    plan = mr_mod.plan_renames(
        "/d", ["a.txt", "b.txt"], "[C:2]_[N][E]",
    )
    assert plan == [
        ("/d/a.txt", "/d/01_a.txt"),
        ("/d/b.txt", "/d/02_b.txt"),
    ]


def test_plan_renames_real_filesystem(tmp_path):
    (tmp_path / "draft_one.txt").write_text("x")
    (tmp_path / "draft_two.txt").write_text("y")
    names = sorted(os.listdir(tmp_path))
    plan = mr_mod.plan_renames(
        str(tmp_path), names, "[N][E]", search="draft_", replace="",
    )
    new_basenames = sorted(os.path.basename(new) for _old, new in plan)
    assert new_basenames == ["one.txt", "two.txt"]
