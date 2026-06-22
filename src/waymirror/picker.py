"""On-screen region picker.

Captures the monitor via the ScreenCast portal, grabs a single frame, freezes it
into an *opaque* fullscreen window, and lets the user drag a rectangle on that
still image. Returns the selection as a (w, h, x, y) region in global logical
coordinates -- the same shape parse_geometry produces -- so the rest of
waymirror is unchanged.

Why a frozen frame and not a transparent overlay: GNOME/Mutter unredirects
fullscreen windows (scans them out directly, skipping compositing), so a
transparent fullscreen overlay renders solid black. A non-fullscreen window
would composite, but Wayland won't tell a client its window's on-screen
position, so the drag couldn't be mapped back to screen coordinates. Drawing on
an opaque, fullscreen still sidesteps both: it always displays, and fullscreen
makes window coords equal monitor coords.

We grab that frame from the ScreenCast path (which the mirror itself relies on)
rather than the Screenshot portal. A non-interactive Screenshot request
(`interactive: false`) fails with portal error code 2 on GNOME 48 -- it won't
silently grant a full-screen grab to an app with no registered desktop identity,
and it doesn't prompt either -- and interactive mode would put GNOME's own
selector in front of ours. Grabbing one frame *before* showing the window also
avoids a capture-of-itself feedback loop.

The picker shares the portal restore token with the app, so the monitor is only
chosen once; it closes its own session after the grab so the mirror's capture is
the only one left running.
"""

import logging

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstVideo", "1.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gst, GstVideo, Gtk  # noqa: E402

from .geometry import normalize_rect
from .portal import (
    CURSOR_MODE_EMBEDDED,
    PortalScreenCast,
    load_restore_token,
    save_restore_token,
)

log = logging.getLogger(__name__)

# smallest selection (logical px) we treat as a real drag rather than a click
_MIN_SIZE = 8

_CSS = b"""
.waymirror-selection {
    background: rgba(53, 132, 228, 0.18);
    border: 2px solid rgba(53, 132, 228, 0.95);
}
.waymirror-hint {
    background: rgba(0, 0, 0, 0.70);
    color: white;
    padding: 8px 16px;
    border-radius: 9px;
    margin-top: 24px;
}
"""

_HINT = "Drag to select a region  ·  Esc to cancel"


def _grab_frame(fd, node_id):
    """Pull one RGBA frame from the PipeWire node into a Gdk.Texture.

    Returns (texture, pipeline) -- keep the pipeline alive until the texture is
    no longer needed, then set it to NULL.
    """
    pipeline = Gst.parse_launch(
        f"pipewiresrc fd={fd} path={node_id} ! videoconvert ! "
        "video/x-raw,format=RGBA ! appsink name=sink max-buffers=1 drop=true"
    )
    sink = pipeline.get_by_name("sink")
    pipeline.set_state(Gst.State.PLAYING)
    sample = sink.emit("try-pull-sample", 5 * Gst.SECOND)
    if sample is None:
        pipeline.set_state(Gst.State.NULL)
        raise RuntimeError("no frame from the screencast within 5s")

    info = GstVideo.VideoInfo.new_from_caps(sample.get_caps())
    buf = sample.get_buffer()
    ok, mapinfo = buf.map(Gst.MapFlags.READ)
    if not ok:
        pipeline.set_state(Gst.State.NULL)
        raise RuntimeError("could not read the captured frame")
    try:
        data = GLib.Bytes.new(mapinfo.data)  # copies out of the mapped buffer
    finally:
        buf.unmap(mapinfo)
    texture = Gdk.MemoryTexture.new(
        info.width, info.height, Gdk.MemoryFormat.R8G8B8A8, data, info.stride[0]
    )
    return texture, pipeline


class _Picker:
    def __init__(self, min_size):
        self.min_size = min_size
        self.result = None
        self._loop = None
        self._window = None
        self._pipeline = None
        self._portal = None
        self._done = False

    def run(self):
        if Gdk.Display.get_default() is None:
            log.error("no display; cannot show the region picker")
            return None
        self._install_css()
        self._loop = GLib.MainLoop()
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self._portal = PortalScreenCast(
            bus, CURSOR_MODE_EMBEDDED, self._on_stream_ready, self._on_error,
            restore_token=load_restore_token(), save_token=save_restore_token,
        )
        self._portal.start()
        self._loop.run()
        return self.result

    @staticmethod
    def _install_css():
        provider = Gtk.CssProvider()
        try:
            provider.load_from_string(_CSS.decode())  # GTK 4.12+
        except AttributeError:
            provider.load_from_data(_CSS)  # older GTK4
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _on_error(self, message):
        log.error("%s", message)
        self._finish(None)

    def _on_stream_ready(self, fd, node_id, monitor_rect):
        try:
            texture, self._pipeline = _grab_frame(fd, node_id)
        except (RuntimeError, GLib.Error) as e:
            self._on_error(str(e))
            return
        # one frame is enough; close our capture so only the mirror's remains
        self._portal.close()

        if monitor_rect:
            mx, my, mw, mh = monitor_rect
        else:
            mx, my = 0, 0
            mw, mh = texture.get_width(), texture.get_height()
        self._show_window(texture, (mx, my), (mw, mh))

    def _show_window(self, texture, origin, bounds):
        monitor = self._monitor_at(origin)

        win = Gtk.Window()
        win.set_decorated(False)
        if monitor is not None:
            win.fullscreen_on_monitor(monitor)
        else:
            win.fullscreen()

        overlay = Gtk.Overlay()

        picture = Gtk.Picture()
        picture.set_paintable(texture)
        picture.set_content_fit(Gtk.ContentFit.FILL)
        picture.set_can_shrink(True)
        overlay.set_child(picture)

        fixed = Gtk.Fixed()
        fixed.set_can_target(False)
        selection = Gtk.Box()
        selection.add_css_class("waymirror-selection")
        selection.set_can_target(False)
        selection.set_visible(False)
        fixed.put(selection, 0, 0)
        overlay.add_overlay(fixed)

        hint = Gtk.Label(label=_HINT)
        hint.add_css_class("waymirror-hint")
        hint.set_halign(Gtk.Align.CENTER)
        hint.set_valign(Gtk.Align.START)
        hint.set_can_target(False)
        overlay.add_overlay(hint)

        win.set_child(overlay)

        state = {"start": None}

        def show_rect(x0, y0, x1, y1):
            x, y = min(x0, x1), min(y0, y1)
            w, h = abs(x1 - x0), abs(y1 - y0)
            selection.set_size_request(max(1, round(w)), max(1, round(h)))
            fixed.move(selection, round(x), round(y))
            selection.set_visible(True)

        drag = Gtk.GestureDrag()

        def on_begin(_g, sx, sy):
            state["start"] = (sx, sy)
            show_rect(sx, sy, sx, sy)

        def on_update(_g, ox, oy):
            if state["start"]:
                sx, sy = state["start"]
                show_rect(sx, sy, sx + ox, sy + oy)

        def on_end(_g, ox, oy):
            if not state["start"]:
                return
            sx, sy = state["start"]
            state["start"] = None
            region = normalize_rect(
                sx, sy, sx + ox, sy + oy, origin=origin, bounds=bounds
            )
            if region[0] < self.min_size or region[1] < self.min_size:
                self._finish(None)  # a click / tiny drag cancels
            else:
                self._finish(region)

        drag.connect("drag-begin", on_begin)
        drag.connect("drag-update", on_update)
        drag.connect("drag-end", on_end)
        overlay.add_controller(drag)

        keys = Gtk.EventControllerKey()

        def on_key(_c, keyval, _kc, _state):
            if keyval == Gdk.KEY_Escape:
                self._finish(None)
                return True
            return False

        keys.connect("key-pressed", on_key)
        win.add_controller(keys)
        win.connect("close-request", lambda *_: self._finish(None) or True)

        self._window = win
        win.present()

    @staticmethod
    def _monitor_at(origin):
        """The Gdk.Monitor whose logical origin matches the captured monitor."""
        ox, oy = origin
        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            geo = mon.get_geometry()
            if geo.x == ox and geo.y == oy:
                return mon
        return monitors.get_item(0) if monitors.get_n_items() else None

    def _finish(self, result):
        if self._done:
            return
        self._done = True
        self.result = result
        if self._window is not None:
            self._window.destroy()
        if self._pipeline is not None:
            self._pipeline.set_state(Gst.State.NULL)
        if self._portal is not None:
            self._portal.close()
        if self._loop is not None:
            self._loop.quit()


def pick_region(min_size=_MIN_SIZE):
    """Show the picker; return (w, h, x, y) in global logical coords, or None.

    None means the user cancelled -- Esc, closed the window, just clicked
    without dragging a meaningful rectangle, or the capture failed.
    """
    Gst.init(None)
    Gtk.init()
    return _Picker(min_size).run()
