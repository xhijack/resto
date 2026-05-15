"""Tests for resto.print_engine.resolver.resolve_print_rule.

Covers:
- No rule for action_key → None
- Disabled rule → ignored
- Branch-specific preferred over default
- Higher priority wins
- filter_condition_jinja gates rule selection
- Jinja syntax error → rule skipped (logged), not raised
"""
import frappe
from frappe.tests.utils import FrappeTestCase
from resto.print_engine.resolver import resolve_print_rule


PF_NAME = "_Test Print Rule PF"


def _ensure_print_format():
	if frappe.db.exists("Print Format", PF_NAME):
		return
	frappe.get_doc({
		"doctype": "Print Format",
		"name": PF_NAME,
		"doc_type": "POS Invoice",
		"print_format_type": "Jinja",
		"raw_printing": 1,
		"html": "{{ esc_init() }}TEST",
		"module": "Resto Sopwer",
		"standard": "No",
	}).insert(ignore_permissions=True)


def _ensure_branch(name: str) -> str:
	if frappe.db.exists("Branch", name):
		return name
	frappe.get_doc({"doctype": "Branch", "branch": name}).insert(ignore_permissions=True)
	return name


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


class TestResolvePrintRule(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		_ensure_print_format()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		# Wipe any rules left over from prior tests in this class.
		frappe.db.delete("Resto Print Rule")
		frappe.db.commit()

	def tearDown(self):
		frappe.db.delete("Resto Print Rule")
		frappe.db.commit()
		super().tearDown()

	def test_returns_none_when_no_rule(self):
		self.assertIsNone(resolve_print_rule("kitchen_receipt"))

	def test_returns_none_when_action_key_missing(self):
		_make_rule(rule_name="R1")
		self.assertIsNone(resolve_print_rule(""))

	def test_ignores_disabled_rule(self):
		_make_rule(rule_name="R-disabled", enabled=0)
		self.assertIsNone(resolve_print_rule("kitchen_receipt"))

	def test_picks_default_rule(self):
		_make_rule(rule_name="R-default")
		rule = resolve_print_rule("kitchen_receipt")
		self.assertIsNotNone(rule)
		self.assertEqual(rule.rule_name, "R-default")
		self.assertIsNone(rule.branch)

	def test_branch_specific_preferred_over_default(self):
		branch_name = _ensure_branch("_Test Br A")
		_make_rule(rule_name="R-default")
		_make_rule(rule_name="R-branch", branch=branch_name)
		rule = resolve_print_rule("kitchen_receipt", branch=branch_name)
		self.assertEqual(rule.rule_name, "R-branch")

	def test_falls_back_to_default_when_no_branch_match(self):
		_ensure_branch("_Test Br A")
		_make_rule(rule_name="R-default")
		_make_rule(rule_name="R-branch-other", branch="_Test Br A")
		rule = resolve_print_rule("kitchen_receipt", branch="_Test Br Nonexistent")
		# Branch doesn't match the specific rule, falls back to default.
		self.assertEqual(rule.rule_name, "R-default")

	def test_higher_priority_wins(self):
		_make_rule(rule_name="R-lo", priority=1)
		_make_rule(rule_name="R-hi", priority=10)
		rule = resolve_print_rule("kitchen_receipt")
		self.assertEqual(rule.rule_name, "R-hi")

	def test_filter_condition_passes(self):
		_make_rule(
			rule_name="R-cond",
			filter_condition_jinja="{{ payload.kitchen_station == 'Dapur' }}",
		)
		rule = resolve_print_rule(
			"kitchen_receipt",
			context={"payload": {"kitchen_station": "Dapur"}},
		)
		self.assertEqual(rule.rule_name, "R-cond")

	def test_filter_condition_fails(self):
		_make_rule(
			rule_name="R-cond",
			filter_condition_jinja="{{ payload.kitchen_station == 'Bar' }}",
		)
		rule = resolve_print_rule(
			"kitchen_receipt",
			context={"payload": {"kitchen_station": "Dapur"}},
		)
		self.assertIsNone(rule)

	def test_filter_condition_render_error_skips_rule(self):
		_make_rule(rule_name="R-good")
		# Force a render error: rule with bad filter but lower priority shouldn't be picked.
		# Frappe validate() also runs the same render check, so we bypass via direct insert.
		bad_doc = frappe.get_doc({
			"doctype": "Resto Print Rule",
			"rule_name": "R-bad",
			"action_key": "kitchen_receipt",
			"print_format": PF_NAME,
			"printer_resolver": "From Payload",
			"enabled": 1,
			"priority": 100,
		})
		bad_doc.insert(ignore_permissions=True)
		# Patch the bad filter directly in the DB to bypass validate.
		frappe.db.set_value(
			"Resto Print Rule", "R-bad",
			"filter_condition_jinja", "{{ undefined_var.broken( }}",
		)
		frappe.db.commit()

		rule = resolve_print_rule("kitchen_receipt", context={})
		# Even with higher priority, bad rule is skipped; falls to R-good.
		self.assertEqual(rule.rule_name, "R-good")

	def test_action_key_filter(self):
		_make_rule(rule_name="R-kitchen", action_key="kitchen_receipt")
		_make_rule(rule_name="R-bill", action_key="bill")
		rule = resolve_print_rule("bill")
		self.assertEqual(rule.rule_name, "R-bill")
