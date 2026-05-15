"""Orchestrator: payload → resolved rule → rendered bytes → CUPS.

Phase 1 surface: kitchen receipt path only (`dispatch_kitchen_payload`).
Returns None when no rule matches → caller MUST fall back to legacy builder.
Returns None on any exception too — logged via `frappe.log_error`.

Test Print: `test_print_rule(rule_name)` (whitelist) renders rule's Print
Format with dummy context and sends to the rule's configured printer.
"""
from __future__ import annotations

from typing import Any, Optional

import frappe

from resto.print_engine.renderer import (
	PrintFormatEncodingError,
	PrintFormatNotFoundError,
	render_print_format,
)
from resto.print_engine.resolver import ResolvedRule, resolve_print_rule


# ---------- Public: kitchen path ----------

def dispatch_kitchen_payload(entry: dict, title_prefix: str = "") -> Optional[bytes]:
	"""Render kitchen receipt via Print Format if an enabled rule matches.

	Returns:
	    bytes — ready for CUPS, OR
	    None  — no matching rule / render failure → caller falls back.
	"""
	try:
		branch = _extract_branch(entry)
		context = _build_kitchen_context(entry, title_prefix)
		rule = resolve_print_rule("kitchen_receipt", branch=branch, context=context)
		if rule is None:
			return None
		return render_print_format(rule.print_format, context)
	except (PrintFormatNotFoundError, PrintFormatEncodingError) as e:
		frappe.log_error(f"Dynamic kitchen print failed: {e}", "RestoPrintDispatcher")
		return None
	except Exception as e:
		frappe.log_error(
			f"Unexpected dispatch error: {e}\n{frappe.get_traceback()}",
			"RestoPrintDispatcher",
		)
		return None


# ---------- Context builders ----------

def _build_kitchen_context(entry: dict, title_prefix: str = "") -> dict:
	"""Shape the Jinja context for a kitchen receipt template.

	Keys exposed:
	    - payload: raw entry dict (unfiltered, for advanced templates)
	    - unprinted_items: pre-filtered items where is_print_kitchen == 0
	    - invoice: POS Invoice metadata (order_type, queue, etc.)
	    - header: dict {date, station_name, table_name, operator_name, pax}
	    - title_prefix: optional caller-provided prefix
	"""
	items = entry.get("items") or []
	unprinted = [it for it in items if int(it.get("is_print_kitchen") or 0) == 0]

	pos_invoice = entry.get("pos_invoice") or ""
	invoice_meta: dict = {}
	if pos_invoice and frappe.db.exists("POS Invoice", pos_invoice):
		invoice_meta = frappe.db.get_value(
			"POS Invoice", pos_invoice,
			["name", "order_type", "queue", "branch", "total_pax", "customer", "customer_name"],
			as_dict=True,
		) or {}

	operator_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user
	transaction_date = entry.get("transaction_date") or frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")

	header = {
		"date": transaction_date,
		"station_name": entry.get("kitchen_station") or "-",
		"table_name": _resolve_table_name(pos_invoice),
		"operator_name": operator_name,
		"pax": invoice_meta.get("total_pax"),
	}

	# Mandarin name lookup for items (optional enrichment).
	mandarin_map = _build_mandarin_map(unprinted)
	for it in unprinted:
		menu = it.get("resto_menu")
		if menu and menu in mandarin_map:
			it.setdefault("mandarin_name", mandarin_map[menu])

	return {
		"payload": entry,
		"unprinted_items": unprinted,
		"invoice": invoice_meta,
		"header": header,
		"title_prefix": title_prefix or "",
	}


def _extract_branch(entry: dict) -> Optional[str]:
	if entry.get("branch"):
		return entry["branch"]
	pos_invoice = entry.get("pos_invoice")
	if pos_invoice and frappe.db.exists("POS Invoice", pos_invoice):
		return frappe.db.get_value("POS Invoice", pos_invoice, "branch") or None
	return None


def _resolve_table_name(pos_invoice: str) -> str:
	if not pos_invoice:
		return "-"
	# Lazy import to avoid cycle with legacy printing.py.
	try:
		from resto.printing import get_table_names_from_pos_invoice
		return get_table_names_from_pos_invoice(pos_invoice) or "-"
	except Exception:
		return "-"


def _build_mandarin_map(items: list) -> dict:
	menu_ids = list({i.get("resto_menu") for i in items if i.get("resto_menu")})
	if not menu_ids:
		return {}
	rows = frappe.get_all(
		"Resto Menu",
		filters={"name": ["in", menu_ids]},
		fields=["name", "custom_mandarin_name"],
	)
	return {r.name: r.custom_mandarin_name for r in rows if r.custom_mandarin_name}


# ---------- Test Print (admin tool) ----------

@frappe.whitelist()
def test_print_rule(rule_name: str) -> dict:
	"""Render rule's Print Format with dummy data and send to configured printer.

	Triggered by `resto_print_rule.js` "Test Print" custom button.
	"""
	if not rule_name:
		return {"ok": False, "error": "rule_name is required"}

	rule_doc = frappe.get_doc("Resto Print Rule", rule_name)
	if not rule_doc.print_format:
		return {"ok": False, "error": "Rule has no Print Format set"}

	printer_name = _resolve_test_printer(rule_doc)
	if not printer_name:
		return {
			"ok": False,
			"error": (
				"Could not resolve a printer for this rule. For Test Print, set "
				"Printer Resolver=Static + Printer Name, or use Kitchen Station resolver."
			),
		}

	context = _build_dummy_kitchen_context(rule_doc)
	try:
		raw = render_print_format(rule_doc.print_format, context)
	except (PrintFormatNotFoundError, PrintFormatEncodingError) as e:
		return {"ok": False, "error": str(e)}
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "RestoPrintRule TestPrint render")
		return {"ok": False, "error": f"Render failed: {e}"}

	try:
		from resto.printing import cups_print_raw
		job_id = cups_print_raw(raw, printer_name)
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "RestoPrintRule TestPrint cups")
		return {"ok": False, "error": f"CUPS dispatch failed: {e}"}

	return {"ok": True, "job_id": job_id, "printer_name": printer_name}


def _resolve_test_printer(rule_doc) -> Optional[str]:
	resolver = (rule_doc.printer_resolver or "").strip()
	if resolver == "Static":
		return (rule_doc.printer_name or "").strip() or None
	if resolver == "Kitchen Station" and rule_doc.kitchen_station:
		return frappe.db.get_value("Kitchen Station", rule_doc.kitchen_station, "printer_name") or None
	# "From Payload" and "Branch Settings" need real context — Test Print can't satisfy them.
	return None


def _build_dummy_kitchen_context(rule_doc) -> dict:
	"""Synthetic context for Test Print so admin can iterate templates without a real order."""
	dummy_items = [
		{
			"qty": 2,
			"item_name": "Nasi Goreng Spesial",
			"short_name": "Nasgor Spesial",
			"resto_menu": "DEMO-MENU-001",
			"add_ons": "Extra Pedas, Telur",
			"quick_notes": "Tanpa bawang",
			"is_print_kitchen": 0,
		},
		{
			"qty": 1,
			"item_name": "Es Teh Manis",
			"short_name": "Es Teh",
			"resto_menu": "DEMO-MENU-002",
			"add_ons": "",
			"quick_notes": "",
			"is_print_kitchen": 0,
		},
	]
	return {
		"payload": {
			"kitchen_station": "Dapur Demo",
			"printer_name": rule_doc.printer_name or "demo-printer",
			"pos_invoice": "DEMO-INV-001",
			"items": dummy_items,
			"transaction_date": frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
		},
		"unprinted_items": dummy_items,
		"invoice": {
			"name": "DEMO-INV-001",
			"order_type": "dine_in",
			"queue": "A-99",
			"branch": rule_doc.branch or "",
			"total_pax": 2,
			"customer_name": "Demo Customer",
		},
		"header": {
			"date": frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
			"station_name": "Dapur Demo",
			"table_name": "T-DEMO",
			"operator_name": frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user,
			"pax": 2,
		},
		"title_prefix": "[TEST] ",
		"is_test_print": True,
	}
