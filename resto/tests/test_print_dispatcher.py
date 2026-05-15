"""Tests for resto.print_engine.dispatcher.dispatch_kitchen_payload.

Covers:
- No rule → None (legacy fallback path is safe)
- Enabled rule + valid PF → bytes produced
- Render error → None (logged, fallback path is safe)
- Branch extraction from entry.branch and entry.pos_invoice
- Context shape (unprinted_items pre-filtered)
"""
import frappe
from unittest.mock import patch
from frappe.tests.utils import FrappeTestCase
from resto.print_engine.dispatcher import dispatch_kitchen_payload, _build_kitchen_context


PF_NAME = "_Test Dispatcher PF"


def _ensure_pf(name: str, html: str):
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


def _make_rule(**overrides) -> str:
	defaults = {
		"doctype": "Resto Print Rule",
		"rule_name": overrides.pop("rule_name", frappe.generate_hash(length=10)),
		"action_key": "kitchen_receipt",
		"print_format": PF_NAME,
		"printer_resolver": "From Payload",
		"enabled": 1,
		"priority": 0,
	}
	defaults.update(overrides)
	doc = frappe.get_doc(defaults)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestDispatchKitchenPayload(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		_ensure_pf(PF_NAME, "{{ esc_init() }}KITCHEN={{ payload.kitchen_station }}")
		frappe.db.delete("Resto Print Rule")
		frappe.db.commit()

	def tearDown(self):
		frappe.db.delete("Resto Print Rule")
		frappe.db.commit()
		super().tearDown()

	def test_no_rule_returns_none(self):
		entry = {"kitchen_station": "Dapur", "printer_name": "p1", "items": []}
		self.assertIsNone(dispatch_kitchen_payload(entry))

	def test_rule_enabled_returns_bytes(self):
		_make_rule(rule_name="R-default")
		entry = {"kitchen_station": "Dapur", "printer_name": "p1", "items": []}
		out = dispatch_kitchen_payload(entry)
		self.assertIsInstance(out, bytes)
		self.assertIn(b"KITCHEN=Dapur", out)
		self.assertTrue(out.startswith(b"\x1b@"))

	def test_render_error_returns_none(self):
		# PF with emoji → encoding error → dispatcher logs + returns None
		_ensure_pf(PF_NAME, "{{ esc_init() }}🍔")
		_make_rule(rule_name="R-bad")
		entry = {"kitchen_station": "Dapur", "printer_name": "p1", "items": []}
		# Suppress error logging during this test to keep output clean
		with patch("frappe.log_error"):
			self.assertIsNone(dispatch_kitchen_payload(entry))

	def test_pf_not_found_returns_none(self):
		# Make rule pointing to PF, then delete PF
		_make_rule(rule_name="R-x")
		frappe.delete_doc("Print Format", PF_NAME, force=True)
		entry = {"kitchen_station": "Dapur", "printer_name": "p1", "items": []}
		with patch("frappe.log_error"):
			self.assertIsNone(dispatch_kitchen_payload(entry))

	def test_disabled_rule_returns_none(self):
		_make_rule(rule_name="R-off", enabled=0)
		entry = {"kitchen_station": "Dapur", "printer_name": "p1", "items": []}
		self.assertIsNone(dispatch_kitchen_payload(entry))


class TestBuildKitchenContext(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
	def test_unprinted_items_filtered(self):
		entry = {
			"kitchen_station": "Dapur",
			"items": [
				{"qty": 1, "item_name": "A", "is_print_kitchen": 0},
				{"qty": 1, "item_name": "B", "is_print_kitchen": 1},  # already printed
				{"qty": 2, "item_name": "C", "is_print_kitchen": 0},
			],
		}
		ctx = _build_kitchen_context(entry)
		self.assertEqual(len(ctx["unprinted_items"]), 2)
		self.assertEqual(ctx["unprinted_items"][0]["item_name"], "A")
		self.assertEqual(ctx["unprinted_items"][1]["item_name"], "C")

	def test_context_keys_present(self):
		entry = {"kitchen_station": "Bar", "items": [], "pos_invoice": ""}
		ctx = _build_kitchen_context(entry, title_prefix="[REPRINT] ")
		for key in ("payload", "unprinted_items", "invoice", "header", "title_prefix"):
			self.assertIn(key, ctx)
		self.assertEqual(ctx["title_prefix"], "[REPRINT] ")
		self.assertEqual(ctx["header"]["station_name"], "Bar")

	def test_header_date_defaults_to_now(self):
		entry = {"kitchen_station": "X", "items": []}
		ctx = _build_kitchen_context(entry)
		self.assertTrue(ctx["header"]["date"])
		self.assertNotEqual(ctx["header"]["date"], "-")

	def test_header_uses_provided_transaction_date(self):
		entry = {"kitchen_station": "X", "items": [], "transaction_date": "2026-05-15 10:00:00"}
		ctx = _build_kitchen_context(entry)
		self.assertEqual(ctx["header"]["date"], "2026-05-15 10:00:00")


class TestExtractBranch(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
	def test_branch_from_entry(self):
		from resto.print_engine.dispatcher import _extract_branch
		self.assertEqual(_extract_branch({"branch": "BR-01"}), "BR-01")

	def test_branch_none_when_missing(self):
		from resto.print_engine.dispatcher import _extract_branch
		self.assertIsNone(_extract_branch({}))

	def test_branch_from_pos_invoice_when_no_direct_branch(self):
		from resto.print_engine.dispatcher import _extract_branch
		# Non-existent invoice → returns None gracefully
		self.assertIsNone(_extract_branch({"pos_invoice": "NONEXISTENT-INV"}))
