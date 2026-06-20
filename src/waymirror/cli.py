"""Command-line entry point for waymirror."""

import argparse
import logging
import os
import sys
import textwrap

from . import __version__
from .geometry import parse_geometry
from .preflight import check as preflight_check


def build_parser():
    parser = argparse.ArgumentParser(
        prog="waymirror",
        description="Mirror a region of a Wayland screen into a normal window, "
                    "so meeting apps can share it as a window (sharp), not a "
                    "blurred camera feed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            REGION can be:
              WxH+X+Y   an explicit rectangle in the compositor's global logical
                        coordinates, e.g. 800x600+100+100. The +X+Y offset is
                        optional and defaults to +0+0.
              left      the exact left half of the selected monitor
              right     the exact right half of the selected monitor
              (omitted) mirror the whole selected monitor

            With left/right you don't need to know the screen size; waymirror
            reads it from the portal and splits the monitor in two.

            Examples:
              waymirror 800x600+100+100     # explicit region
              waymirror left                # left half of the monitor
              waymirror right --no-cursor   # right half, hide the pointer
              waymirror                     # whole monitor

            Controls: press q or Esc to quit (the window has no title bar).
            """
        ),
    )
    parser.add_argument(
        "region", nargs="?", metavar="REGION",
        help="WxH+X+Y, 'left', 'right', or omit for the whole monitor "
             "(see below)",
    )
    parser.add_argument(
        "--no-cursor", action="store_true",
        help="do not include the mouse cursor in the mirror",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="verbose logging (also enabled by WAYMIRROR_DEBUG=1)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    verbose = args.verbose or bool(os.environ.get("WAYMIRROR_DEBUG"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="waymirror: %(message)s",
    )

    error = preflight_check()
    if error:
        print(error, file=sys.stderr)
        return 1

    geometry = None
    half = None
    if args.region:
        token = args.region.lower()
        if token in ("left", "right"):
            half = token
        else:
            try:
                geometry = parse_geometry(args.region)
            except ValueError as e:
                parser.error(str(e))

    # import the GTK app only after preflight, so a missing-dependency message
    # beats a raw ImportError.
    from .app import WayMirrorApp

    app = WayMirrorApp(geometry, half, show_cursor=not args.no_cursor)
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
