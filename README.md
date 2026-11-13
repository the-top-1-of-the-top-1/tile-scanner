# Tile Scanner

Small overlay that reads the game's `EE.log` and shows which rooms the current map has, rated best, good or avoid. It only reads the log file.

> **Warning:** This program is not official and is not affiliated with or endorsed by DE (Digital Extremes). It is a third-party tool, so use it at your own risk and responsibly.

## Requirements

- Python 3.10 or newer
- Tkinter (included with the Windows installer from python.org)
- No pip packages

Linux only: install Tkinter if missing.

```
# Debian / Ubuntu
sudo apt install python3-tk
# Arch
sudo pacman -S tk
```

## Run

Windows:

```
py "disrup-supp scanner.py"
```

Linux:

```
python3 "disrup-supp scanner.py"
```

Start it before or after the mission loads. Press ENTER in the terminal to stop it.

## Notes

- The log is found automatically. On Linux it must be a Steam/Proton install.
- Only the host's log has all the data. Rooms that cannot be told apart are shown with `?`.
- The overlay is draggable. On Wayland it may not stay on top; X11 works.
