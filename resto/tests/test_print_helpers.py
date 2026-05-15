"""Unit tests for resto.print_helpers.

Pure-function helpers — no Frappe context needed. Critical invariants:
1. ESC/POS control bytes (\\x1b, \\x1d) survive Latin-1 round-trip → bytes.
2. Bit math for char-size matches legacy `_esc_*` private functions in printing.py.
3. Layout helpers (pad/two_col/wrap) produce exact column widths.
"""
import unittest

from resto.print_helpers import (
    esc_init,
    esc_align_left,
    esc_align_center,
    esc_align_right,
    esc_bold,
    esc_font_a,
    esc_font_b,
    esc_cut_full,
    esc_cut_full_with_feed,
    esc_feed,
    esc_drawer,
    esc_char_size,
    esc_char_size_dotmatrix,
    esc_qr,
    line_separator,
    pad_right,
    pad_left,
    two_col,
    wrap_text,
    fit,
    fmt_idr,
    join_bytes,
)


class TestEscPrimitives(unittest.TestCase):
    """ESC/POS control sequences. Round-trip through Latin-1 must be lossless."""

    def test_esc_init_bytes(self):
        self.assertEqual(esc_init(), "\x1b@")
        self.assertEqual(esc_init().encode("latin-1"), b"\x1b@")

    def test_align_codes(self):
        self.assertEqual(esc_align_left(), "\x1ba\x00")
        self.assertEqual(esc_align_center(), "\x1ba\x01")
        self.assertEqual(esc_align_right(), "\x1ba\x02")

    def test_bold_on_off(self):
        self.assertEqual(esc_bold(True), "\x1bE\x01")
        self.assertEqual(esc_bold(False), "\x1bE\x00")

    def test_font_codes(self):
        self.assertEqual(esc_font_a(), "\x1bM\x00")
        self.assertEqual(esc_font_b(), "\x1bM\x01")

    def test_cut_codes(self):
        self.assertEqual(esc_cut_full(), "\x1dV\x00")
        self.assertEqual(esc_cut_full_with_feed(), "\x1dV\x41")

    def test_feed_clamps_range(self):
        self.assertEqual(esc_feed(0), "\x1bd\x00")
        self.assertEqual(esc_feed(3), "\x1bd\x03")
        self.assertEqual(esc_feed(255), "\x1bd\xff")
        # Out-of-range clamps to [0, 255]
        self.assertEqual(esc_feed(-5), "\x1bd\x00")
        self.assertEqual(esc_feed(300), "\x1bd\xff")

    def test_drawer_kick(self):
        self.assertEqual(esc_drawer(), "\x1bp\x00\x19\xfa")

    def test_char_size_bit_math(self):
        # 0-indexed: 0 = 1x, 7 = 8x. Bit layout: (w << 4) | h.
        self.assertEqual(esc_char_size(0, 0), "\x1d!\x00")
        self.assertEqual(esc_char_size(1, 1), "\x1d!\x11")
        self.assertEqual(esc_char_size(2, 2), "\x1d!\x22")
        self.assertEqual(esc_char_size(7, 7), "\x1d!\x77")
        # Clamping out-of-range
        self.assertEqual(esc_char_size(-1, 0), "\x1d!\x00")
        self.assertEqual(esc_char_size(99, 99), "\x1d!\x77")

    def test_char_size_dotmatrix(self):
        # 1 = normal, 2 = double. Bit layout: ((h-1) << 3) | ((w-1) << 4).
        self.assertEqual(esc_char_size_dotmatrix(1, 1), "\x1b!\x00")
        self.assertEqual(esc_char_size_dotmatrix(2, 1), "\x1b!\x10")
        self.assertEqual(esc_char_size_dotmatrix(1, 2), "\x1b!\x08")
        self.assertEqual(esc_char_size_dotmatrix(2, 2), "\x1b!\x18")
        # >2 clamps to 2
        self.assertEqual(esc_char_size_dotmatrix(5, 5), "\x1b!\x18")

    def test_qr_contains_data(self):
        out = esc_qr("HELLO")
        self.assertIn("HELLO", out)
        # Round-trip through Latin-1 succeeds
        encoded = out.encode("latin-1")
        self.assertIn(b"HELLO", encoded)
        # Contains model-select, size, EC, and print commands
        self.assertIn("\x1d(k", out)

    def test_qr_empty_data(self):
        # Should not raise on empty/None
        self.assertIsInstance(esc_qr(""), str)
        self.assertIsInstance(esc_qr(None), str)


class TestLatin1RoundTrip(unittest.TestCase):
    """Critical: helpers must concatenate with ASCII text and encode cleanly to bytes."""

    def test_concatenation_with_text_encodes(self):
        s = esc_init() + esc_align_center() + "Hello World" + esc_feed(2) + esc_cut_full()
        encoded = s.encode("latin-1")
        self.assertTrue(encoded.startswith(b"\x1b@\x1ba\x01Hello World"))
        self.assertTrue(encoded.endswith(b"\x1dV\x00"))

    def test_high_bytes_preserved(self):
        # \xFA in drawer must round-trip
        s = esc_drawer()
        self.assertEqual(s.encode("latin-1"), b"\x1bp\x00\x19\xfa")

    def test_all_helpers_return_str(self):
        for fn in (
            esc_init, esc_align_left, esc_align_center, esc_align_right,
            esc_font_a, esc_font_b, esc_cut_full, esc_cut_full_with_feed,
            esc_drawer,
        ):
            self.assertIsInstance(fn(), str, f"{fn.__name__} must return str")


class TestLayoutHelpers(unittest.TestCase):

    def test_line_separator_default(self):
        self.assertEqual(line_separator(), "-" * 32)

    def test_line_separator_custom(self):
        self.assertEqual(line_separator("=", 10), "==========")

    def test_line_separator_empty_char(self):
        self.assertEqual(line_separator("", 5), "")

    def test_pad_right_fills(self):
        self.assertEqual(pad_right("AB", 5), "AB   ")

    def test_pad_right_truncates(self):
        self.assertEqual(pad_right("ABCDEF", 4), "ABCD")

    def test_pad_left_fills(self):
        self.assertEqual(pad_left("AB", 5), "   AB")

    def test_pad_left_truncates(self):
        self.assertEqual(pad_left("ABCDEF", 4), "ABCD")

    def test_pad_right_none_input(self):
        self.assertEqual(pad_right(None, 3), "   ")

    def test_two_col_fits(self):
        out = two_col("Total", "Rp 100", width=20)
        self.assertEqual(len(out), 20)
        self.assertTrue(out.startswith("Total"))
        self.assertTrue(out.endswith("Rp 100"))

    def test_two_col_truncates_when_overflow(self):
        out = two_col("VeryLongLeft", "VeryLongRight", width=10)
        self.assertEqual(len(out), 10)

    def test_two_col_none_inputs(self):
        out = two_col(None, None, width=10)
        self.assertEqual(len(out), 10)

    def test_wrap_text_short(self):
        self.assertEqual(wrap_text("hello", 32), ["hello"])

    def test_wrap_text_wraps(self):
        lines = wrap_text("the quick brown fox jumps", 10)
        for line in lines:
            self.assertLessEqual(len(line), 10)
        self.assertEqual(" ".join(lines), "the quick brown fox jumps")

    def test_wrap_text_empty(self):
        self.assertEqual(wrap_text("", 10), [""])
        self.assertEqual(wrap_text(None, 10), [""])

    def test_fit_short_unchanged(self):
        self.assertEqual(fit("hi", 10), "hi")

    def test_fit_truncates_with_ellipsis(self):
        out = fit("supercalifragilistic", 10)
        self.assertEqual(len(out), 10)
        self.assertTrue(out.endswith("…"))

    def test_fit_extreme_narrow(self):
        # width <= 1 just truncates without ellipsis
        self.assertEqual(fit("abc", 1), "a")


class TestFormatters(unittest.TestCase):

    def test_fmt_idr_basic(self):
        self.assertEqual(fmt_idr(12345), "Rp 12.345")

    def test_fmt_idr_zero(self):
        self.assertEqual(fmt_idr(0), "Rp 0")

    def test_fmt_idr_none(self):
        self.assertEqual(fmt_idr(None), "Rp 0")

    def test_fmt_idr_negative(self):
        self.assertEqual(fmt_idr(-1500), "Rp -1.500")

    def test_fmt_idr_rounds_float(self):
        self.assertEqual(fmt_idr(12345.67), "Rp 12.346")

    def test_fmt_idr_invalid(self):
        self.assertEqual(fmt_idr("bad"), "Rp 0")

    def test_join_bytes_concatenates(self):
        self.assertEqual(join_bytes("a", "b", "c"), "abc")

    def test_join_bytes_skips_none(self):
        self.assertEqual(join_bytes("a", None, "c"), "ac")

    def test_join_bytes_empty(self):
        self.assertEqual(join_bytes(), "")


if __name__ == "__main__":
    unittest.main()
