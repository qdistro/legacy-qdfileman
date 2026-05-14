# Guide for AI Agents

## Project Structure

```
qfileman/
├── qfileman/           # Main package
│   ├── __init__.py    # Version info
│   ├── __main__.py    # CLI entry point
│   ├── config.py      # Configuration management
│   ├── file_model.py  # File system model
│   ├── plugin.py      # Plugin system
│   ├── window.py      # Main window UI
│   └── plugins/       # Plugin directory
│       └── builtin/   # Built-in plugins
├── tests/             # Test suite
└── pyproject.toml     # Project configuration
```

## Key Classes

- `FileManagerWindow` (`window.py`): Main Qt window. Owns the menus, toolbar,
  tree-view sidebar, status bar, plugin manager, and the `SplitContainer`
  tree. Toolbar/menu actions are routed to the currently active pane.
- `FilePane` (`pane.py`): One self-contained file-browsing pane. Owns its own
  `FileModel`, navigation history, path edit, and file list. Emits
  `path_changed`, `focused`, and `status_changed`. Multiple panes can coexist
  in a window.
- `SplitContainer` (`split_container.py`): Recursive `QSplitter` that holds
  either `FilePane` leaves or nested `SplitContainer` instances. Methods:
  `add_pane`, `split(target, orientation, factory)`, `remove_pane`,
  `find_panes`. Single-child nested splitters collapse automatically after a
  removal.
- `FileModel` (`file_model.py`): Directory listing, sort, hidden-file filter,
  and FileFilter-plugin pipeline. One per pane.
- `Plugin` / `PluginManager` (`plugin.py`): MenuProvider / NavigationHook /
  FileFilter base classes plus a discovery+lifecycle manager.
- `Config` (`config.py`): TOML-based configuration singleton.

## Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_plugin.py

# Single test
pytest tests/test_plugin.py::test_plugin_base_class
```

## Qt Testing

- Use `QT_QPA_PLATFORM=offscreen` for headless testing
- QApplication must exist before creating Qt widgets
- Clean up Qt objects after tests to prevent fd leaks

## Plugin Types

All three are wired into the running window:

1. **MenuProvider** — items added by `get_menu_items(file_item)` appear in the
   file context menu. Iterated in `FileManagerWindow._show_context_menu`.
2. **NavigationHook** — `on_enter_directory(path)` returning `False` blocks the
   navigation; `on_leave_directory(path)` is called after a successful move.
   Iterated in `FileManagerWindow._update_path`.
3. **FileFilter** — `filter_files(paths) -> paths` runs inside
   `FileModel._load_files` for every listing. Pushed into the model by
   `FileManagerWindow.set_plugin_manager` (which also clears any prior
   filters, so calling it twice is safe).

## Adding a New Plugin

1. Create file in `qfileman/plugins/builtin/<name>.py`
2. Define class extending appropriate base class
3. Implement required methods
4. Add tests in `tests/test_plugin.py`
