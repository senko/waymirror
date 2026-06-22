# waymirror

Mirror a **region of a Wayland screen into an ordinary window** — so any meeting
app (Google Meet, Teams, Jitsi, Slack, …) can share *that window* and show your
selected region.

This is useful when your screencast app only lets you share either a whole screen
or a single window, but you want to share *part* of your screen - for example, if
you have a ultra-widescreen monitor.

It's the answer to "this app only lets me share a whole screen or a window, but I
want to share *part* of my screen." Point waymirror at a region; share the
waymirror window.

## How it works


Waymirror:

1. opens an **xdg-desktop-portal** `ScreenCast` session and gets a **PipeWire**
   stream of a monitor (the compositor shows its own picker for *which* monitor;
   you can't hand it a region, so we capture the whole monitor),
2. **crops** the stream to your region with GStreamer's `videocrop`
   (HiDPI-aware — the crop is computed from the negotiated buffer size vs. the
   monitor's logical size),
3. renders the result into a borderless **GTK4** window via `gtk4paintablesink`.

Pipeline: `pipewiresrc → videoconvert → videocrop → gtk4paintablesink`.

Because it relies on the desktop portal, waymirror works on **GNOME** and other
portal-supporting compositors (KDE, wlroots-based). It also runs under X11
sessions that provide the portal, but it's built for Wayland.

## Requirements

The heavy lifting is done by **system** components (PyGObject, GStreamer plugins,
the GObject-Introspection typelibs, GTK4). These are **not** installable from PyPI
in a working way, so install them from your distribution first.

**Debian / Ubuntu** (verified on Debian 13 "trixie"):

```bash
sudo apt install \
  python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-pipewire gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-gl gstreamer1.0-gtk4
```

**Fedora** (package names may vary by release):

```bash
sudo dnf install \
  python3-gobject gtk4 \
  gstreamer1-plugins-base gstreamer1-plugins-good \
  pipewire-gstreamer gstreamer1-plugins-rs
```

**Arch**:

```bash
sudo pacman -S \
  python-gobject gtk4 \
  gst-plugins-base gst-plugins-good gst-plugin-pipewire gst-plugins-rs
```

The pieces you need, whatever the package names: **PyGObject**, **GTK 4** +
typelib, **GStreamer** core + typelibs, and the elements `pipewiresrc`,
`videoconvert`, `videocrop`, `appsink`, and `gtk4paintablesink` (the last comes
from the GStreamer **Rust** plugins / `gstreamer1.0-gtk4`; the rest are in the
base/good plugins already listed above). waymirror checks these at startup and
tells you exactly what's missing.

## Install

Because the bindings live on the system, install waymirror into an environment
that can see them. The easiest is pipx with system site packages:

```bash
pipx install --system-site-packages waymirror
```

With `uv` from source / for development:

```bash
git clone https://github.com/senko/waymirror
cd waymirror
uv venv --python /usr/bin/python3 --system-site-packages
uv pip install -e .
```

> The `--system-site-packages` flag (and `--python /usr/bin/python3` for uv) is
> what lets the venv use the distro's `gi`/GStreamer. A plain isolated venv won't
> find them.

Prefer pip to build the bindings instead? Install the build headers for your
distro and use the `bindings` extra: `pip install "waymirror[bindings]"` (you
still need the native GStreamer plugins).

## Usage

```bash
waymirror                     # draw the region on screen (interactive picker)
waymirror 800x600+100+100     # explicit region (+X+Y optional, defaults to +0+0)
waymirror left                # exact left half of the selected monitor
waymirror right               # exact right half
waymirror right --no-cursor   # hide the mouse pointer in the mirror
waymirror --help
```

Run with **no region** and waymirror freezes a snapshot of the monitor and shows
it full-screen, so you can **drag a rectangle** over the part you want to mirror
(Esc cancels). On the first run the portal asks which monitor to capture; after
that the choice is remembered, so the picker comes straight up.

With `left`/`right`, waymirror reads the monitor size from the portal and splits
it in two — you don't need to know the resolution.

The first run shows the portal picker (choose the monitor your region is on); the
choice is remembered via a restore token in `~/.config/waymirror/restore-token`,
so later runs don't prompt.

### The window

- **No title bar**, opens at exactly the region size.
- Locked to the region's **aspect ratio**; if it's resized (eg. to accomodate
  the GNOME title bar), it keeps the aspect rate automatically.
- Quit with **`q`**, **`Esc`**, or `Ctrl-C`. Run several at once for several
  regions.
- Move the window with `Super+drag`.
- `-v` / `WAYMIRROR_DEBUG=1` for verbose logging.

## Desktop integration (optional)

waymirror is a CLI tool, but you can register a launcher entry + icon so GNOME
shows a proper name and icon for the window — in the dock/overview *and* in the
meeting app's window picker. It's a separate, opt-in command (installs into your
user XDG directories, no root needed):

```bash
waymirror-setup install      # ~/.local/share/applications + .../icons
waymirror-setup uninstall
```

## Development

```bash
uv venv --python /usr/bin/python3 --system-site-packages
uv pip install -e ".[dev]"
python -m unittest discover -s tests    # or: pytest
python -m waymirror left                # run without installing
```

## License

MIT — see [LICENSE](LICENSE).

