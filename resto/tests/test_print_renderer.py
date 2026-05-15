"""Tests for resto.print_engine.renderer.render_print_format.

Critical invariants:
- str → bytes via Latin-1 preserves ESC/POS control bytes 1:1
- Missing Print Format raises PrintFormatNotFoundError
- Non-Latin-1 char raises PrintFormatEncodingError (caller falls back)
- Jinja helpers from hooks.py are callable from template body
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from resto.print_engine.renderer import (
	PrintFormatEncodingError,
	PrintFormatNotFoundError,
	render_print_format,
)


def _make_pf(name: str, html: str):
	if frappe.db.exists("Print Format", name):
		frappe.delete_doc("Print Format", name, force=True)
	frappe.get_doc({
		"doctype": "Print Format",
		"name": name,
		"doc_type": "POS Invoice",
		"print_format_type": "Jinja",
		"raw_printing": 1,
		"html": html,
		"module": "Resto Sopwer",
		"standard": "No",
	}).insert(ignore_permissions=True)


class TestRenderPrintFormat(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
	def test_raises_on_missing_print_format(self):
		with self.assertRaises(PrintFormatNotFoundError):
			render_print_format("_Test Nonexistent PF")

	def test_raises_on_empty_name(self):
		with self.assertRaises(PrintFormatNotFoundError):
			render_print_format("")

	def test_renders_plain_text(self):
		_make_pf("_Test PF Plain", "HELLO {{ name }}")
		out = render_print_format("_Test PF Plain", {"name": "WORLD"})
		self.assertEqual(out, b"HELLO WORLD")

	def test_preserves_esc_pos_bytes_via_helper(self):
		# {{ esc_init() }} should expand to \x1b@ — bytes 0x1b 0x40
		_make_pf("_Test PF Esc", "{{ esc_init() }}{{ esc_align_center() }}TEST{{ esc_cut_full() }}")
		out = render_print_format("_Test PF Esc", {})
		self.assertEqual(out, b"\x1b@\x1ba\x01TEST\x1dV\x00")

	def test_preserves_high_bytes(self):
		_make_pf("_Test PF Drawer", "{{ esc_drawer() }}")
		out = render_print_format("_Test PF Drawer", {})
		# \xFA is the high byte — must survive
		self.assertEqual(out, b"\x1bp\x00\x19\xfa")

	def test_jinja_loop(self):
		_make_pf(
			"_Test PF Loop",
			"{% for it in items %}{{ it.qty }}x{{ it.name }}\n{% endfor %}",
		)
		out = render_print_format("_Test PF Loop", {
			"items": [{"qty": 2, "name": "Nasi"}, {"qty": 1, "name": "Es"}],
		})
		self.assertEqual(out, b"2xNasi\n1xEs\n")

	def test_non_latin1_raises_encoding_error(self):
		# Emoji is outside 0-255 → encoding fails
		_make_pf("_Test PF Emoji", "header 🍔 footer")
		with self.assertRaises(PrintFormatEncodingError):
			render_print_format("_Test PF Emoji", {})

	def test_fmt_idr_helper(self):
		_make_pf("_Test PF Idr", "Total: {{ fmt_idr(12345) }}")
		out = render_print_format("_Test PF Idr", {})
		self.assertEqual(out, "Total: Rp 12.345".encode("latin-1"))

	def test_two_col_helper(self):
		_make_pf("_Test PF TwoCol", "{{ two_col('Total', 'Rp 100', 20) }}")
		out = render_print_format("_Test PF TwoCol", {})
		self.assertEqual(len(out), 20)
		self.assertTrue(out.startswith(b"Total"))
		self.assertTrue(out.endswith(b"Rp 100"))
