"""Startup checks for the system dependencies that aren't pip-installable."""

# element name -> Debian/Ubuntu package that provides it
REQUIRED_ELEMENTS = {
    "pipewiresrc": "gstreamer1.0-pipewire",
    "videoconvert": "gstreamer1.0-plugins-base",
    "videocrop": "gstreamer1.0-plugins-good",
    "gtk4paintablesink": "gstreamer1.0-gtk4",
}


def check():
    """Return None if all good, else a human-readable error string."""
    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst  # noqa: F401
    except (ImportError, ValueError) as e:
        return (
            "Missing the GObject-Introspection / GTK4 / GStreamer Python "
            f"bindings.\n  ({e})\n"
            "These come from your distro, not pip. On Debian/Ubuntu:\n"
            "  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 "
            "gir1.2-gst-plugins-base-1.0\n"
            "See the README for Fedora/Arch."
        )

    Gst.init(None)
    missing = [
        (name, pkg)
        for name, pkg in REQUIRED_ELEMENTS.items()
        if Gst.ElementFactory.find(name) is None
    ]
    if missing:
        lines = ["Missing required GStreamer elements:"]
        lines += [f"  - {name}  (Debian/Ubuntu: {pkg})" for name, pkg in missing]
        lines.append("See the README for the full per-distro package list.")
        return "\n".join(lines)
    return None
