"""GTK4 application: portal stream -> crop -> window."""

import logging

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gio, Gst, Gtk  # noqa: E402

from .geometry import compute_crop, fit_within_bounds, resolve_half
from .portal import (
    CURSOR_MODE_EMBEDDED,
    CURSOR_MODE_HIDDEN,
    PortalScreenCast,
    load_restore_token,
    save_restore_token,
)

log = logging.getLogger(__name__)

APP_ID = "hr.dobarkod.waymirror"


class WayMirrorApp(Gtk.Application):
    def __init__(self, geometry, half, show_cursor):
        # NON_UNIQUE so several windows (different regions) can coexist.
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        self.geometry = geometry  # (w, h, x, y) or None
        self.half = half  # "left"/"right", resolved once monitor size is known
        self.show_cursor = show_cursor
        self.window = None
        self.picture = None
        self.pipeline = None
        self.portal = None
        # target display size (logical px), known once we have the region; keeps
        # the window the right shape (see _on_compute_size).
        self.desired_w = None
        self.desired_h = None

    # -- lifecycle --------------------------------------------------------
    def do_activate(self):
        if self.window:
            self.window.present()
            return

        self.picture = Gtk.Picture()
        # COVER fills the whole window keeping aspect, so there are never any
        # letterbox bars; with the aspect-locked window below, the cropped-off
        # sliver is sub-pixel.
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.set_can_shrink(True)

        self.window = Gtk.ApplicationWindow(application=self)
        self.window.set_decorated(False)  # no title bar / window chrome
        self.window.set_child(self.picture)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.window.add_controller(keys)

        # keep the window locked to the content's aspect ratio: when GNOME caps
        # the height to the work area (top bar), shrink the width to match.
        self.window.connect("realize", self._on_window_realize)

        # the window is shown from _on_stream_ready, once we know the region
        # size (left/right need the monitor size).
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 2, self._quit)   # SIGINT
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, 15, self._quit)  # SIGTERM

        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        cursor_mode = CURSOR_MODE_EMBEDDED if self.show_cursor else CURSOR_MODE_HIDDEN
        self.portal = PortalScreenCast(
            bus, cursor_mode, self._on_stream_ready, self._on_portal_error,
            restore_token=load_restore_token(), save_token=save_restore_token,
        )
        self.portal.start()

    def do_shutdown(self):
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        Gtk.Application.do_shutdown(self)

    # -- window sizing ----------------------------------------------------
    def _set_target(self, w, h):
        self.desired_w = w
        self.desired_h = h

    def _present_window(self):
        if self.geometry:
            w, h, x, y = self.geometry
            self.window.set_title(f"waymirror {w}x{h}+{x}+{y}")
        else:
            self.window.set_title("waymirror")
        if self.desired_w and self.desired_h:
            self.window.set_default_size(self.desired_w, self.desired_h)
        else:
            self.window.set_default_size(960, 540)
        self.window.present()

    def _on_window_realize(self, widget):
        surface = widget.get_surface()  # GdkToplevel once realized
        if surface is not None:
            surface.connect("compute-size", self._on_compute_size)

    def _on_compute_size(self, _toplevel, size):
        if not self.desired_w or not self.desired_h:
            return
        bounds_w, bounds_h = size.get_bounds()
        w, h = fit_within_bounds(self.desired_w, self.desired_h, bounds_w, bounds_h)
        size.set_size(w, h)
        log.debug("compute-size bounds=(%s,%s) -> %dx%d", bounds_w, bounds_h, w, h)

    # -- input ------------------------------------------------------------
    def _on_key(self, _controller, keyval, _keycode, _state):
        if keyval in (Gdk.KEY_q, Gdk.KEY_Q, Gdk.KEY_Escape):
            self.quit()
            return True
        return False

    def _quit(self, *_):
        self.quit()
        return GLib.SOURCE_REMOVE

    # -- stream -----------------------------------------------------------
    def _on_portal_error(self, message):
        log.error("%s", message)
        self.quit()

    def _on_stream_ready(self, fd, node_id, monitor_rect):
        log.debug("streaming node %s (fd %s), monitor=%s", node_id, fd, monitor_rect)

        # resolve left/right into a concrete region now that we know the monitor
        if self.half:
            if not monitor_rect:
                self._on_portal_error(
                    "portal did not report monitor size; use WxH+X+Y "
                    "instead of left/right"
                )
                return
            self.geometry = resolve_half(self.half, monitor_rect)

        # pick the display target (logical size) and show the window
        if self.geometry:
            self._set_target(self.geometry[0], self.geometry[1])
        elif monitor_rect:
            self._set_target(monitor_rect[2], monitor_rect[3])
        self._present_window()

        self.pipeline = Gst.Pipeline.new("waymirror")
        src = Gst.ElementFactory.make("pipewiresrc")
        src.set_property("fd", fd)
        src.set_property("path", str(node_id))
        conv = Gst.ElementFactory.make("videoconvert")
        crop = Gst.ElementFactory.make("videocrop")
        # gtk4paintablesink negotiates GPU memory (DMABuf/GLMemory), but
        # videocrop can only crop raw system-memory frames -- force that here.
        rawfilter = Gst.ElementFactory.make("capsfilter")
        rawfilter.set_property("caps", Gst.Caps.from_string("video/x-raw"))
        sink = Gst.ElementFactory.make("gtk4paintablesink")
        for el in (src, conv, crop, rawfilter, sink):
            self.pipeline.add(el)
        src.link(conv)
        conv.link(crop)
        crop.link(rawfilter)
        rawfilter.link(sink)

        self.picture.set_paintable(sink.get_property("paintable"))

        # crop must be computed from the *negotiated* buffer size (HiDPI aware),
        # so wait for caps on the cropper's sink pad, then set it once.
        if self.geometry:
            crop_pad = crop.get_static_pad("sink")
            crop_pad.add_probe(
                Gst.PadProbeType.EVENT_DOWNSTREAM,
                self._configure_crop, crop, monitor_rect,
            )

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_gst_error)
        bus.connect("message::eos", lambda *_: self._quit())

        self.pipeline.set_state(Gst.State.PLAYING)

    def _configure_crop(self, pad, info, crop, monitor_rect):
        event = info.get_event()
        if event.type != Gst.EventType.CAPS:
            return Gst.PadProbeReturn.OK
        s = event.parse_caps().get_structure(0)
        ok_w, cw = s.get_int("width")
        ok_h, ch = s.get_int("height")
        if not (ok_w and ok_h):
            return Gst.PadProbeReturn.OK

        left, top, right, bottom = compute_crop(cw, ch, monitor_rect, self.geometry)
        crop.set_property("left", left)
        crop.set_property("top", top)
        crop.set_property("right", right)
        crop.set_property("bottom", bottom)
        log.debug(
            "buffer %dx%d, crop l=%d t=%d r=%d b=%d", cw, ch, left, top, right, bottom
        )
        return Gst.PadProbeReturn.REMOVE

    def _on_gst_error(self, _bus, message):
        err, debug = message.parse_error()
        log.error("gstreamer error: %s", err.message)
        if debug:
            log.debug("%s", debug)
        self.quit()
