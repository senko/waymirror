"""Optional desktop integration, run via the `waymirror-setup` command.

Installs/removes a .desktop launcher and icon in the user's XDG directories so
GNOME shows a proper name + icon for the waymirror window (in the dock and in
screen-share window pickers). Kept out of the main `waymirror` CLI on purpose.

This is opt-in by necessity: wheels cannot run code at install time, so the
user runs `waymirror-setup install` explicitly.
"""

import argparse
import os
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

APP_ID = "hr.dobarkod.waymirror"
_DESKTOP_NAME = f"{APP_ID}.desktop"
_ICON_NAME = f"{APP_ID}.svg"


def _data_home():
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


def _applications_dir():
    return _data_home() / "applications"


def _icon_dir():
    return _data_home() / "icons" / "hicolor" / "scalable" / "apps"


def _find_exec():
    """Absolute path to the installed `waymirror` command (best effort)."""
    # waymirror-setup lives in the same bin/ dir as the waymirror script
    sibling = Path(sys.argv[0]).resolve().parent / "waymirror"
    if sibling.exists():
        return str(sibling)
    return shutil.which("waymirror") or "waymirror"


def _refresh_caches():
    cmds = [
        ["update-desktop-database", str(_applications_dir())],
        ["gtk-update-icon-cache", "-f", "-t",
         str(_data_home() / "icons" / "hicolor")],
    ]
    for cmd in cmds:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install(_args):
    apps = _applications_dir()
    icons = _icon_dir()
    apps.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    data = files("waymirror") / "data"

    icon_dst = icons / _ICON_NAME
    icon_dst.write_bytes((data / _ICON_NAME).read_bytes())

    template = (data / _DESKTOP_NAME).read_text(encoding="utf-8")
    desktop_dst = apps / _DESKTOP_NAME
    desktop_dst.write_text(template.replace("@EXEC@", _find_exec()), encoding="utf-8")

    _refresh_caches()
    print(f"Installed {desktop_dst}")
    print(f"Installed {icon_dst}")
    return 0


def uninstall(_args):
    removed = []
    for path in (_applications_dir() / _DESKTOP_NAME, _icon_dir() / _ICON_NAME):
        try:
            path.unlink()
            removed.append(str(path))
        except FileNotFoundError:
            pass
    _refresh_caches()
    if removed:
        for p in removed:
            print(f"Removed {p}")
    else:
        print("Nothing to remove.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="waymirror-setup",
        description="Install or remove the waymirror desktop launcher and icon "
                    "in your user XDG directories.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("install", help="install the .desktop entry and icon")
    sub.add_parser("uninstall", help="remove the .desktop entry and icon")
    args = parser.parse_args(argv)
    return {"install": install, "uninstall": uninstall}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
