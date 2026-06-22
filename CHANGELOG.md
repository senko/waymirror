# Changelog

## 0.2.0

- Run with no region to select one interactively: waymirror freezes a snapshot
  of the monitor full-screen and you drag the rectangle to mirror (Esc cancels).
  Replaces the previous "no region = whole monitor" default.

## 0.1.0

- Initial release.
- Mirror a region of a Wayland screen into an ordinary GTK4 window via the
  xdg-desktop-portal ScreenCast portal + PipeWire + GStreamer.
- `REGION` accepts `WxH+X+Y`, `left`, `right`, or nothing (whole monitor).
- Borderless, exact-size window locked to the region's aspect ratio (no
  letterbox bars even when the compositor caps the height to the work area).
- `q`/`Esc` to quit; `--no-cursor`; persistent portal restore token.
- Optional desktop integration via the `waymirror-setup install` command
  (launcher entry + icon in the user's XDG directories).
