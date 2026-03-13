# Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class POSDailySummary(Document):
	def before_save(self):
		total_qty = 0
		grand_total = 0
		for row in self.pos_transactions:
			total_qty += row.qty or 0
			grand_total += row.amount or 0
	
		self.total_quantity = total_qty
		self.grand_total = grand_total
			
	def on_cancel(self):
		# ketika POS daily summary di batalkan maka update seluruh field end_day_processed pos closing yang ada di pos daily 
		for row in self.pos_transactions:
			frappe.db.set_value(
				"POS Closing Entry",
				row.pos_closing_entry,
				"end_day_processed",
				0
			)

@frappe.whitelist()
def end_day_from_shift(posting_date):
	from resto.api import end_shift
	from resto.api import get_end_day_report_v2
	user = frappe.session.user

	end_shift()

	shift_names = frappe.get_all(
		"POS Closing Entry",
		filters={
			"posting_date": posting_date,
			"docstatus": 1,
			"end_day_processed": ["in", [0, None]]
		},
		pluck="name"
	)

	if not shift_names:
		frappe.throw("No POS Closing Entry found to process End Day")

	summary_name = frappe.db.exists("POS Daily Summary", {
		"posting_date": posting_date,
		"created_by": user
	})

	if summary_name:
		summary = frappe.get_doc("POS Daily Summary", summary_name)
		summary.pos_transactions = []
	else:
		summary = frappe.new_doc("POS Daily Summary")
		summary.posting_date = posting_date
		summary.created_by = user

	for shift_name in shift_names:
		summary.append("pos_transactions", {
			"pos_closing_entry": shift_name
		})

		frappe.db.set_value(
			"POS Closing Entry",
			shift_name,
			"end_day_processed",
			1
		)

	summary.insert(ignore_permissions=True)
	summary.submit()

	# ================================
	# GENERATE END DAY REPORT
	# ================================
	pos_opening = frappe.db.get_value(
		"POS Closing Entry",
		shift_names[0],
		"pos_opening_entry"
	)

	outlet = frappe.db.get_value(
		"POS Opening Entry",
		pos_opening,
		"branch"
	)

	frappe.form_dict.posting_date = posting_date
	frappe.form_dict.outlet = outlet
	frappe.form_dict.print = 1   # kalau mau auto print

	report = get_end_day_report_v2()

	return {
		"summary": summary.name,
		"report": report
	}


@frappe.whitelist()
def get_pos_closing_entries(posting_date, branch):
	entries = frappe.get_all(
		"POS Closing Entry",
		filters={
			"posting_date": posting_date,
			"docstatus": 1,
			"end_day_processed": ["in", [0, None]],
			"branch": branch
		},
		fields=["name", "pos_opening_entry", "total_qty", "grand_total"]
	)

	return entries