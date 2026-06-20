"""waymirror - mirror a region of a Wayland screen into a normal window.

On Wayland (and GNOME in particular) you cannot read another window's pixels or
create a virtual monitor the way X11 tools do. waymirror instead asks the
xdg-desktop-portal ScreenCast portal for a PipeWire stream of a monitor, crops
it to the region you ask for, and shows it in an ordinary GTK4 window -- which a
meeting app can then share as a *window* (sharp), not as a blurred camera feed.
"""

__version__ = "0.1.0"
