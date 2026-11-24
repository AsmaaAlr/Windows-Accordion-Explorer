[README.md](https://github.com/user-attachments/files/35327415/README.md)
# Accordion Explorer

A dark-mode Windows 11 file manager built with Python and PySide6 featuring **macOS Finder-style inline expandable folder accordions**, multi-tab browsing, split dual-pane mode, custom folder colors, and a resizable rich media preview pane.

![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%20Windows%2010-0078D4)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![UI](https://img.shields.io/badge/GUI-PySide6-41CD52)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Key Features

- **Inline Expandable Folder Accordions:** Single-click any folder in **Details** view to expand its contents inline without losing your current directory context; double-click to navigate into it.
- **Native Windows 11 Window Management:** Dark DWM title bar, merged tab strip, and full support for **Windows 11 Aero Snap**, **Snap Layouts** (hover over Maximize), and keyboard snap shortcuts (`Win + Left/Right/Up/Down`).
- **All 8 Explorer View Modes:** Extra large icons, Large icons, Medium icons, Small icons, List, Details, Tiles, and Content (`Ctrl + Mouse Wheel` to cycle views), with native Windows Shell thumbnails for images, videos, and PDFs.
- **Resizable Details & Rich Preview Pane (`Alt + Shift + P`):**
  - Live previews for images, video frames, PDFs, ZIP archive contents, and text/code files.
  - One-click **Copy text** button to copy the full contents of text/code files directly to your clipboard.
  - Built-in Windows MCI audio player with play/pause and seek bar.
  - Drag the left splitter handle to resize the preview pane freely.
- **Custom Folder Colors:** Right-click any folder (or multi-selection) and choose **Folder Color** to apply 10 preset colors or any custom RGB/hex color—synced across Details, Icons, Sidebar pins, and Preview panes.
- **Split Dual-Pane View (`F6`):** Work side-by-side with independent tab strips, breadcrumbs, and drag-and-drop between panes.
- **Smart Navigation & Selection:** Returning to a parent folder (`↑`, `Backspace`, `Alt + Up`, `Alt + Left`, or clicking a breadcrumb ancestor) automatically selects, highlights, and scrolls to the folder you just exited.
- **Full File Operations:** Multi-tab support (`Ctrl + T`, `Ctrl + W`), slow double-click / `F2` inline rename, bidirectional external drag-and-drop, 3-way conflict resolution (*Replace / Keep Both / Skip*), Recycle Bin integration, ZIP extraction, recursive subfolder search, kind filtering, and `Ctrl + Z` / `Ctrl + Y` undo/redo.

---

## Installation & Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/accordion-explorer.git
   cd accordion-explorer
   ```

2. **Install the dependency:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Accordion Explorer:**
   ```bash
   python accordion_explorer.py
   ```
   *(On Windows, you can also run with `pythonw accordion_explorer.py` to launch without a console window.)*

---

## Keyboard Shortcuts

| Shortcut | Action |
| :--- | :--- |
| `Single-click folder` | Expand / collapse folder inline (Details view) |
| `Double-click folder` | Open folder in current tab |
| `Ctrl + T` / `Ctrl + W` | Open new tab / Close current tab |
| `F6` | Toggle Split Dual-Pane view |
| `Alt + Shift + P` | Toggle Details & Preview pane |
| `F2` or `Slow double-click` | Inline rename selected file or folder |
| `Backspace` / `Alt + Up` | Go up to parent folder (highlights exited folder) |
| `Alt + Left` / `Alt + Right` | Navigate Back / Forward |
| `Ctrl + L` | Edit address bar path directly |
| `Ctrl + Z` / `Ctrl + Y` | Undo / Redo file move, copy, rename, or create |
| `Del` / `Shift + Del` | Move to Recycle Bin / Permanently delete |
| `Alt + Enter` | Open native Windows Properties dialog |
| `Ctrl + Mouse Wheel` | Cycle through view modes |

---

## Configuration Files

User preferences are stored locally in your user home directory and are automatically excluded from Git via `.gitignore`:
- `~/.accordion_explorer_pins.json` — Pinned sidebar folders
- `~/.accordion_explorer_folder_colors.json` — Custom folder colors

---

## License

MIT License — see [LICENSE](LICENSE) for details.
