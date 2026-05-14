"""File system model for QFileMan."""

import logging
import os
import shutil
from pathlib import Path
from datetime import datetime


log = logging.getLogger(__name__)


class FileItem:
    """Represents a file or directory in the file manager."""

    def __init__(self, path):
        self.path = Path(path)
        self._stat = None  # cached lazily on first stat-backed access

    def _cached_stat(self):
        """Return ``path.stat()``, caching on first call.

        Multiple property reads (``size`` plus ``modified``) on the same
        item are common during sort + status-line rendering; caching keeps
        directory listings O(n) stat calls instead of O(n*k).
        """
        if self._stat is None:
            self._stat = self.path.stat()
        return self._stat

    @property
    def name(self):
        return self.path.name

    @property
    def is_dir(self):
        return self.path.is_dir()

    @property
    def is_file(self):
        return self.path.is_file()

    @property
    def is_symlink(self):
        return self.path.is_symlink()

    @property
    def size(self):
        if self.is_dir:
            return 0
        try:
            return self._cached_stat().st_size
        except OSError:
            return 0

    @property
    def modified(self):
        try:
            return datetime.fromtimestamp(self._cached_stat().st_mtime)
        except OSError:
            return None

    @property
    def extension(self):
        return self.path.suffix.lower()

    def __repr__(self):
        return f"FileItem({self.path})"


class FileModel:
    """Model that provides file listing and operations."""

    def __init__(self, current_path=None):
        self._current_path = Path(current_path or os.path.expanduser("~"))
        self._files = None  # None means "not yet loaded"
        self._show_hidden = False
        self._sort_by = "name"
        self._sort_order = "asc"
        self._filters = []

    @property
    def current_path(self):
        return self._current_path

    @property
    def show_hidden(self) -> bool:
        """Whether dotfiles are included in :meth:`get_files`."""
        return self._show_hidden

    @property
    def sort_by(self) -> str:
        """The current sort key (``name`` / ``size`` / ``date`` / ``type``)."""
        return self._sort_by

    @property
    def sort_order(self) -> str:
        """The current sort direction (``asc`` / ``desc``)."""
        return self._sort_order

    def apply_state(
        self,
        *,
        show_hidden: bool | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
    ) -> None:
        """Mutate several view fields at once and refresh once.

        Each of :meth:`set_show_hidden` and :meth:`set_sort` refreshes the
        listing on its own. When the caller wants to update more than one
        of these at the same time, use this method to avoid redundant
        refreshes.
        """
        if show_hidden is not None:
            self._show_hidden = bool(show_hidden)
        if sort_by is not None:
            self._sort_by = sort_by
        if sort_order is not None:
            self._sort_order = sort_order
        self.refresh()

    def set_path(self, path):
        """Change current directory."""
        p = Path(path)
        if p.is_dir():
            self._current_path = p
            self._files = None  # Invalidate cache
            return True
        return False

    def go_up(self):
        """Go to parent directory. Returns False at filesystem root."""
        parent = self._current_path.parent
        if parent != self._current_path:
            self._current_path = parent
            self._files = None
            return True
        return False

    def go_home(self):
        """Go to home directory."""
        self._current_path = Path(os.path.expanduser("~"))
        self._files = None

    def refresh(self):
        """Refresh file listing."""
        self._files = self._load_files()

    def _load_files(self):
        """Load files from current directory."""
        files = []
        try:
            entries = list(self._current_path.iterdir())
        except PermissionError as e:
            log.warning("permission denied listing %s: %s", self._current_path, e)
            return []
        except OSError as e:
            log.warning("error listing %s: %s", self._current_path, e)
            return []

        for entry in entries:
            if not self._show_hidden and entry.name.startswith("."):
                continue
            files.append(FileItem(entry))

        # Pipe paths through each registered FileFilter, then rebuild the
        # FileItem list once at the end. Each filter consumes and returns
        # path strings; intermediate FileItem reconstruction would be
        # wasted work since the items themselves carry no filter state.
        if self._filters:
            paths = [str(fi.path) for fi in files]
            for f in self._filters:
                paths = f.filter_files(paths)
            files = [FileItem(p) for p in paths]

        files = self._sort_files(files)
        return files

    def _sort_files(self, files):
        """Sort files by current sort settings."""
        reverse = self._sort_order == "desc"

        def sort_key(f):
            if self._sort_by == "name":
                return f.name.lower()
            elif self._sort_by == "size":
                return f.size
            elif self._sort_by == "date":
                return f.modified.timestamp() if f.modified else 0
            elif self._sort_by == "type":
                return (f.extension, f.name.lower())
            return f.name.lower()

        return sorted(files, key=sort_key, reverse=reverse)

    def get_files(self):
        """Get list of files in current directory."""
        if self._files is None:
            self.refresh()
        return self._files

    def set_show_hidden(self, show):
        """Set whether to show hidden files."""
        self._show_hidden = show
        self.refresh()

    def set_sort(self, sort_by, sort_order=None):
        """Set sort options."""
        self._sort_by = sort_by
        if sort_order:
            self._sort_order = sort_order
        self.refresh()

    def add_filter(self, file_filter):
        """Register a FileFilter-style object.

        ``file_filter`` must expose a ``filter_files(paths) -> paths`` method
        (the contract of :class:`qfileman.plugin.FileFilter`). Plain functions
        are not accepted.
        """
        if not hasattr(file_filter, "filter_files"):
            raise TypeError(
                "add_filter requires an object with a filter_files() method; "
                f"got {type(file_filter).__name__}"
            )
        self._filters.append(file_filter)
        self.refresh()

    def clear_filters(self):
        """Clear all filters."""
        self._filters = []
        self.refresh()

    # File operations
    def create_directory(self, name):
        """Create a directory in current path."""
        try:
            (self._current_path / name).mkdir()
            self.refresh()
            return True
        except OSError as e:
            log.warning("create_directory(%s) failed: %s", name, e)
            return False

    def delete(self, path):
        """Delete a file or directory."""
        p = Path(path)
        try:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            self.refresh()
            return True
        except OSError as e:
            log.warning("delete(%s) failed: %s", path, e)
            return False

    def rename(self, old_path, new_name):
        """Rename a file or directory."""
        old = Path(old_path)
        new = old.parent / new_name
        try:
            old.rename(new)
            self.refresh()
            return True
        except OSError as e:
            log.warning("rename(%s -> %s) failed: %s", old_path, new_name, e)
            return False

    def copy(self, source, dest):
        """Copy a file or directory."""
        src = Path(source)
        dst = Path(dest)
        try:
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            self.refresh()
            return True
        except OSError as e:
            log.warning("copy(%s -> %s) failed: %s", source, dest, e)
            return False

    def move(self, source, dest):
        """Move a file or directory."""
        src = Path(source)
        dst = Path(dest)
        try:
            shutil.move(src, dst)
            self.refresh()
            return True
        except OSError as e:
            log.warning("move(%s -> %s) failed: %s", source, dest, e)
            return False
