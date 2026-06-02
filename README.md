# QFileMan

Qt file manager with plugin support, inspired by qnotebook and qterminator.

## Role in qdistro

qfileman is the first-party file manager for qdistro. Its job is to provide a
modifiable PyQt file surface that can eventually participate in qdistro's silo,
permission, and handoff model without depending on a large external desktop
environment.

Today it is still mostly a standalone Qt file manager. Treat qdistro policy
integration, launcher assets, and hardened path handling as active follow-up
areas when packaging it for daily-driver images.

## Features

- Sidebar tree view paired with a list/grid file pane
- **Split panes**: open additional panes side by side or stacked (Ctrl+Shift+L / Ctrl+Shift+D); close the active pane with Ctrl+W. Each pane keeps its own path, history, sort, and filter.
- Sort by name, size, date (newest first), or extension; toggle hidden files
- Back/forward history and parent-directory navigation
- **Find** dialog (Ctrl+F): glob-pattern search and optional substring content filter, rooted at the current directory
- **Preferences** dialog (Ctrl+,): persistent settings for hidden files, view mode, sort, theme, icon size, and more
- **Theme**: system / light / dark, applied at startup from config
- Plugin system with multiple plugin types:
  - MenuProvider: adds context menu items
  - NavigationHook: hooks into navigation events (can veto a move)
  - FileFilter: drops files from the listing
- Built-in plugins: bookmarks, file info, quick navigation, filter

## Installation

```bash
pip install -e .
```

## Usage

```bash
qfileman                    # Open file manager in home directory
qfileman /path/to/directory # Open file manager in specific directory
qfileman --no-plugins       # Disable plugins
```

## Plugin Development

Place Python modules in:
- Built-in: `qfileman/plugins/builtin/`
- User: `~/.config/qfileman/plugins/`

Example plugin:

```python
from qfileman.plugin import MenuProvider

class MyPlugin(MenuProvider):
    name = "my_plugin"
    description = "My custom plugin"
    version = "1.0"
    category = "File"

    def get_menu_items(self, file_item):
        return [("My Action", lambda path: print(f"Selected: {path}"))]
```

## Testing

```bash
pip install -e ".[test]"
QT_QPA_PLATFORM=offscreen pytest tests/
```

`just lint` runs `ruff check` over the package and tests.

## Known limitations

- The sidebar tree view uses `QFileSystemModel`, which populates lazily. After
  several navigations the highlighted tree node can lag behind the file list;
  click the tree entry to resync.
- Bookmarks, hidden-file toggle, and other settings are persisted via TOML
  (`~/.config/qfileman/config.toml`). `tomli_w` is a required dependency; if it
  is somehow missing at runtime, `Config.save()` will log a warning instead of
  raising and your changes won't survive a restart.
- `_go_back` / `_go_forward` use an in-memory history; nothing is persisted
  across restarts.
- No internationalisation yet — all strings are English. The plugin API and
  config keys are stable; UI strings are not.

## License

GPL-3.0-only. See [LICENSE](LICENSE).
