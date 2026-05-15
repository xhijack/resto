# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RestoPrintRule(Document):
	def validate(self):
		self._validate_resolver_requirements()
		self._validate_print_format_type()
		self._validate_filter_jinja()

	def _validate_resolver_requirements(self):
		resolver = (self.printer_resolver or "").strip()
		if resolver == "Static" and not (self.printer_name or "").strip():
			frappe.throw(_("Printer Name is required when Printer Resolver = Static."))
		if resolver == "Kitchen Station" and not self.kitchen_station:
			frappe.throw(_("Kitchen Station is required when Printer Resolver = Kitchen Station."))

	def _validate_print_format_type(self):
		if not self.print_format:
			return
		pf_type = frappe.db.get_value("Print Format", self.print_format, "print_format_type")
		if pf_type and pf_type not in ("Jinja", "Raw Commands"):
			frappe.throw(
				_("Print Format '{0}' must be Jinja or Raw Commands type (found: {1}).").format(
					self.print_format, pf_type
				)
			)

	def _validate_filter_jinja(self):
		expr = (self.filter_condition_jinja or "").strip()
		if not expr:
			return
		# Syntax-only check. Undefined-variable errors are normal here (real
		# context only exists at print time), so we use parse() not render().
		from jinja2 import TemplateSyntaxError
		try:
			frappe.utils.jinja.get_jenv().parse(expr)
		except TemplateSyntaxError as e:
			frappe.throw(_("Filter Condition (Jinja) syntax error: {0}").format(str(e)))
