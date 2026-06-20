"""xdg-desktop-portal ScreenCast handshake.

Drives the asynchronous D-Bus dance (CreateSession -> SelectSources -> Start ->
OpenPipeWireRemote) on the GLib main loop and hands back a PipeWire fd + node.
"""

import logging

from gi.repository import GLib, Gio

log = logging.getLogger(__name__)

# org.freedesktop.portal.ScreenCast source types / cursor / persist modes
SOURCE_TYPE_MONITOR = 1
CURSOR_MODE_HIDDEN = 1
CURSOR_MODE_EMBEDDED = 2
PERSIST_PERSISTENT = 2

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_OBJ = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"


class PortalScreenCast:
    """Drives the async ScreenCast handshake over D-Bus.

    Calls on_ready(fd, node_id, monitor_rect) on success, where monitor_rect is
    (x, y, w, h) in logical coords (or None if the portal didn't report it), or
    on_error(message) on failure.
    """

    def __init__(self, bus, cursor_mode, on_ready, on_error,
                 restore_token=None, save_token=None):
        self.bus = bus
        self.cursor_mode = cursor_mode
        self.on_ready = on_ready
        self.on_error = on_error
        self.restore_token = restore_token
        self.save_token = save_token  # callable(token) or None
        self.session_handle = None
        self._token_counter = 0
        self._sender = bus.get_unique_name()[1:].replace(".", "_")

    def start(self):
        self._create_session()

    # -- helpers ----------------------------------------------------------
    def _next_token(self):
        self._token_counter += 1
        return f"waymirror{self._token_counter}"

    def _request_path(self, token):
        return f"{PORTAL_OBJ}/request/{self._sender}/{token}"

    def _call_request(self, method, params, on_results):
        """Invoke a portal method that returns a Request, await its Response."""
        token = self._next_token()
        req_path = self._request_path(token)

        # inject our handle_token into the trailing options dict
        opts = params[-1]
        opts["handle_token"] = GLib.Variant("s", token)

        sub_id = [0]

        def on_response(_conn, _sender, _path, _iface, _signal, parameters):
            self.bus.signal_unsubscribe(sub_id[0])
            code, results = parameters.unpack()
            if code != 0:
                self.on_error(f"{method} cancelled or failed (code {code})")
                return
            on_results(results)

        sub_id[0] = self.bus.signal_subscribe(
            PORTAL_BUS, REQUEST_IFACE, "Response", req_path, None,
            Gio.DBusSignalFlags.NONE, on_response,
        )

        sig = "(" + "".join(self._sig(p) for p in params) + ")"
        variant = GLib.Variant(sig, tuple(params))

        def on_call_done(conn, res):
            try:
                conn.call_finish(res)
            except GLib.Error as e:
                self.bus.signal_unsubscribe(sub_id[0])
                self.on_error(f"{method} D-Bus error: {e.message}")

        self.bus.call(
            PORTAL_BUS, PORTAL_OBJ, SCREENCAST_IFACE, method, variant,
            GLib.VariantType("(o)"), Gio.DBusCallFlags.NONE, -1, None,
            on_call_done,
        )

    @staticmethod
    def _sig(param):
        if isinstance(param, dict):
            return "a{sv}"
        if isinstance(param, str):
            # session/request handles are object paths
            return "o" if param.startswith("/") else "s"
        raise TypeError(f"unexpected param type: {param!r}")

    # -- handshake steps --------------------------------------------------
    def _create_session(self):
        log.debug("CreateSession ->")
        opts = {"session_handle_token": GLib.Variant("s", "waymirrorsession")}
        self._call_request("CreateSession", [opts], self._on_session)

    def _on_session(self, results):
        self.session_handle = results["session_handle"]
        log.debug("session=%s; SelectSources ->", self.session_handle)
        opts = {
            "types": GLib.Variant("u", SOURCE_TYPE_MONITOR),
            "multiple": GLib.Variant("b", False),
            "cursor_mode": GLib.Variant("u", self.cursor_mode),
            "persist_mode": GLib.Variant("u", PERSIST_PERSISTENT),
        }
        if self.restore_token:
            opts["restore_token"] = GLib.Variant("s", self.restore_token)
        self._call_request(
            "SelectSources", [self.session_handle, opts], self._on_sources
        )

    def _on_sources(self, _results):
        log.debug("sources selected; Start -> (portal picker may appear)")
        self._call_request(
            "Start", [self.session_handle, "", {}], self._on_start
        )

    def _on_start(self, results):
        log.debug("Start returned; streams negotiated")
        if self.save_token and results.get("restore_token"):
            self.save_token(results["restore_token"])
        streams = results.get("streams") or []
        if not streams:
            self.on_error("portal returned no streams")
            return
        node_id, props = streams[0]
        rect = None
        if "position" in props and "size" in props:
            px, py = props["position"]
            sw, sh = props["size"]
            rect = (px, py, sw, sh)
        self._open_remote(node_id, rect)

    def _open_remote(self, node_id, rect):
        variant = GLib.Variant("(oa{sv})", (self.session_handle, {}))

        def on_done(conn, res):
            try:
                ret, fd_list = conn.call_with_unix_fd_list_finish(res)
            except GLib.Error as e:
                self.on_error(f"OpenPipeWireRemote failed: {e.message}")
                return
            idx = ret.get_child_value(0).get_handle()
            fd = fd_list.get(idx)
            self.on_ready(fd, node_id, rect)

        self.bus.call_with_unix_fd_list(
            PORTAL_BUS, PORTAL_OBJ, SCREENCAST_IFACE, "OpenPipeWireRemote",
            variant, GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, -1,
            None, None, on_done,
        )
