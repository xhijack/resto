# Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import nowtime


@frappe.whitelist()
def end_day(docname, report_date, branch):
	doc = frappe.get_doc("Sales Report", docname)

	entries = frappe.get_all(
		"POS Closing Entry",
		filters={
			"posting_date": report_date,
			"branch": branch
		},
		fields=["name", "owner", "start_time", "end_time", "closing_amount", "opening_amount"]
	)

	if not entries:
		frappe.throw("Data Not Found.")
	
	doc.set("pos_closing_entries", [])

	for e in entries:
		doc.append("pos_closing_entries", {
			"pos_closing_entry": e.name,
			"cashier": e.owner,
			"start_time": e.start_time,
			"end_time": e.end_time,
			"closing_amount": e.closing_amount,
			"opening_amount": e.opening_amount
		})

	doc.created_by = frappe.session.user
	doc.end_time = nowtime()
	doc.status = "Draft"

	doc.save(ignore_permissions=True)

	return doc.name
