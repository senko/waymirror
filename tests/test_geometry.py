import unittest

from waymirror.geometry import (
    compute_crop,
    fit_within_bounds,
    normalize_rect,
    parse_geometry,
    resolve_half,
)


class ParseGeometryTests(unittest.TestCase):
    def test_full(self):
        self.assertEqual(parse_geometry("800x600+100+100"), (800, 600, 100, 100))

    def test_no_offset(self):
        self.assertEqual(parse_geometry("640x480"), (640, 480, 0, 0))

    def test_negative_offset(self):
        self.assertEqual(parse_geometry("100x100-5-10"), (100, 100, -5, -10))

    def test_whitespace(self):
        self.assertEqual(parse_geometry("  800x600+0+0 "), (800, 600, 0, 0))

    def test_invalid(self):
        for bad in ["", "abc", "800x", "x600", "800*600", "0x100+0+0"]:
            with self.assertRaises(ValueError):
                parse_geometry(bad)


class ResolveHalfTests(unittest.TestCase):
    def test_left(self):
        self.assertEqual(resolve_half("left", (0, 0, 5120, 1440)),
                         (2560, 1440, 0, 0))

    def test_right(self):
        self.assertEqual(resolve_half("right", (0, 0, 5120, 1440)),
                         (2560, 1440, 2560, 0))

    def test_odd_width_splits_cleanly(self):
        left = resolve_half("left", (0, 0, 1001, 100))
        right = resolve_half("right", (0, 0, 1001, 100))
        self.assertEqual(left[0] + right[0], 1001)  # no lost column
        self.assertEqual(right[2], left[0])          # right starts where left ends

    def test_offset_monitor(self):
        self.assertEqual(resolve_half("right", (1920, 0, 1000, 800)),
                         (500, 800, 2420, 0))

    def test_bad_side(self):
        with self.assertRaises(ValueError):
            resolve_half("up", (0, 0, 100, 100))


class ComputeCropTests(unittest.TestCase):
    def test_scale_1(self):
        # 5120x1440 buffer, region 800x600+100+100
        self.assertEqual(
            compute_crop(5120, 1440, (0, 0, 5120, 1440), (800, 600, 100, 100)),
            (100, 100, 5120 - 900, 1440 - 700),
        )

    def test_left_half(self):
        self.assertEqual(
            compute_crop(5120, 1440, (0, 0, 5120, 1440), (2560, 1440, 0, 0)),
            (0, 0, 2560, 0),
        )

    def test_right_half(self):
        self.assertEqual(
            compute_crop(5120, 1440, (0, 0, 5120, 1440), (2560, 1440, 2560, 0)),
            (2560, 0, 0, 0),
        )

    def test_hidpi_scale_2(self):
        # logical monitor 2560x1440, buffer is 2x => 5120x2880
        # region 1280x720+0+0 -> crop doubles
        self.assertEqual(
            compute_crop(5120, 2880, (0, 0, 2560, 1440), (1280, 720, 0, 0)),
            (0, 0, 2560, 1440),
        )

    def test_offset_monitor(self):
        # monitor at logical origin (1920,0); region at (1920,0)
        self.assertEqual(
            compute_crop(1000, 800, (1920, 0, 1000, 800), (500, 800, 1920, 0)),
            (0, 0, 500, 0),
        )

    def test_no_monitor_rect_assumes_origin(self):
        # geometry is (w, h, x, y): a 100x100 region at offset (200, 200)
        self.assertEqual(
            compute_crop(1000, 1000, None, (100, 100, 200, 200)),
            (200, 200, 700, 700),
        )


class FitWithinBoundsTests(unittest.TestCase):
    def test_fits_unchanged(self):
        self.assertEqual(fit_within_bounds(800, 600, 5120, 1408), (800, 600))

    def test_height_capped_shrinks_width(self):
        # the reported bug: 2560x1440 desired, work area 1408 tall
        self.assertEqual(fit_within_bounds(2560, 1440, 5120, 1408), (2503, 1408))

    def test_width_capped_shrinks_height(self):
        self.assertEqual(fit_within_bounds(2000, 1000, 1000, 5000), (1000, 500))

    def test_unconstrained_bounds(self):
        self.assertEqual(fit_within_bounds(800, 600, 0, 0), (800, 600))

    def test_ratio_preserved(self):
        w, h = fit_within_bounds(2560, 1440, 5120, 1408)
        self.assertAlmostEqual(w / h, 2560 / 1440, places=2)


class NormalizeRectTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(normalize_rect(100, 100, 300, 250), (200, 150, 100, 100))

    def test_direction_independent(self):
        forward = normalize_rect(100, 100, 300, 250)
        for x0, y0, x1, y1 in [
            (300, 250, 100, 100),  # bottom-right -> top-left
            (300, 100, 100, 250),  # top-right -> bottom-left
            (100, 250, 300, 100),  # bottom-left -> top-right
        ]:
            self.assertEqual(normalize_rect(x0, y0, x1, y1), forward)

    def test_origin_makes_coords_global(self):
        # same local drag, monitor at logical (1920, 0)
        self.assertEqual(
            normalize_rect(100, 100, 300, 250, origin=(1920, 0)),
            (200, 150, 2020, 100),
        )

    def test_clamped_to_bounds(self):
        # drag spills past the right/bottom edges and into negatives
        self.assertEqual(
            normalize_rect(-10, -10, 5000, 5000, bounds=(2560, 1440)),
            (2560, 1440, 0, 0),
        )

    def test_click_is_zero_sized(self):
        self.assertEqual(normalize_rect(42, 42, 42, 42), (0, 0, 42, 42))

    def test_rounds_floats(self):
        # gesture coordinates arrive as floats; corners round independently
        # left=100 top=101 right=301 bottom=250 -> w=201 h=149 at (100, 101)
        self.assertEqual(
            normalize_rect(100.4, 100.6, 300.6, 250.4), (201, 149, 100, 101)
        )


if __name__ == "__main__":
    unittest.main()
