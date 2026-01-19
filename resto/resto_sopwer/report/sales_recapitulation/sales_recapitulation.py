# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
import json
from frappe.utils import add_months, today, getdate

def execute(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)

    if not filters:
        filters = {}

    if not filters.get("from_date"):
        filters["from_date"] = add_months(today(), -1)
    if not filters.get("to_date"):
        filters["to_date"] = today()

    columns = [
        {"label": "Sales Number", "fieldname": "sales_number", "fieldtype": "Link", "options": "POS Invoice", "width": 140},
        {"label": "Bill Number", "fieldname": "bill_number", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
        {"label": "Sales Type", "fieldname": "sales_type", "fieldtype": "Data", "width": 120},
        {"label": "Sales Date", "fieldname": "sales_date", "fieldtype": "Date", "width": 110},
        {"label": "Sales In Time", "fieldname": "sales_in_time", "fieldtype": "Time", "width": 120},
        {"label": "Sales Out Time", "fieldname": "sales_out_time", "fieldtype": "Time", "width": 120},
        {"label": "Branch", "fieldname": "branch", "fieldtype": "Data", "width": 130},
        {"label": "Brand", "fieldname": "brand", "fieldtype": "Data", "width": 120},
        {"label": "City", "fieldname": "city", "fieldtype": "Data", "width": 120},
        {"label": "Area", "fieldname": "area", "fieldtype": "Data", "width": 120},
        {"label": "Visit Purpose", "fieldname": "visit_purpose", "fieldtype": "Data", "width": 140},
        {"label": "Table", "fieldname": "table", "fieldtype": "Data", "width": 90},
        {"label": "Loyalty Member Code", "fieldname": "loyalty_member_code", "fieldtype": "Data", "width": 180},
		{"label": "Loyalty Member Name", "fieldname": "loyalty_member_name", "fieldtype": "Data", "width": 180},
        {"label": "Visitor Type", "fieldname": "visitor_type", "fieldtype": "Data", "width": 120},
        {"label": "Promotion", "fieldname": "promotion", "fieldtype": "Data", "width": 120},
        {"label": "Pax Total", "fieldname": "pax_total", "fieldtype": "Int", "width": 90},
        {"label": "Subtotal", "fieldname": "subtotal", "fieldtype": "Currency", "width": 120},
        {"label": "Menu Discount", "fieldname": "menu_discount", "fieldtype": "Currency", "width": 130},
        {"label": "Bill Discount", "fieldname": "bill_discount", "fieldtype": "Currency", "width": 130},
        {"label": "Voucher Discount", "fieldname": "voucher_discount", "fieldtype": "Currency", "width": 140},
        {"label": "Net Sales", "fieldname": "net_sales", "fieldtype": "Currency", "width": 120},
        {"label": "Service Charge Total", "fieldname": "service_charge_total", "fieldtype": "Currency", "width": 160},
        {"label": "Tax Total", "fieldname": "tax_total", "fieldtype": "Currency", "width": 120},
        {"label": "Voucher Sales Total", "fieldname": "voucher_sales_total", "fieldtype": "Currency", "width": 160},
        {"label": "Rounding Total", "fieldname": "rounding_total", "fieldtype": "Currency", "width": 130},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
        {"label": "Waiter", "fieldname": "waiter", "fieldtype": "Data", "width": 120},
        {"label": "Cashier", "fieldname": "cashier", "fieldtype": "Data", "width": 120},
        {"label": "Additional Info", "fieldname": "additional_info", "fieldtype": "Data", "width": 180},
    ]

    data = get_data(filters)
    return columns, data


def get_data(filters):
    conditions = ["docstatus = 1", "is_pos = 1"]

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if from_date and to_date:
        conditions.append("posting_date BETWEEN %(from_date)s AND %(to_date)s")

    branch = filters.get("branch")
    if branch and branch.strip() and branch.lower() != "all":
        conditions.append("branch = %(branch)s")

    company = filters.get("company")
    if company:
        conditions.append("company = %(company)s")

    conditions_str = " AND ".join(conditions)

    pos_invoices = frappe.db.sql("""
        SELECT name, consolidated_invoice, order_type, posting_date,
               posting_time, branch, customer, pos_profile,
               total, base_total, net_total, base_net_total,
               discount_amount, base_discount_amount,
               total_taxes_and_charges, rounding_adjustment,
               grand_total, owner, remarks, company
        FROM `tabPOS Invoice`
        WHERE {conditions}
        ORDER BY posting_date DESC, posting_time DESC
    """.format(conditions=conditions_str),
    values={
        "from_date": getdate(from_date),
        "to_date": getdate(to_date),
        "branch": branch,
        "company": company
    }, as_dict=True)

    user_map = {u.name: u.full_name for u in frappe.get_all("User", fields=["name", "full_name"])}

    data = []
    for inv in pos_invoices:
        taxes = frappe.get_all(
            "Sales Taxes and Charges",
            filters={"parent": inv.name, "parenttype": "POS Invoice", "parentfield": "taxes"},
            fields=["account_head", "base_tax_amount_after_discount_amount"]
        )

        service_total = sum(t.base_tax_amount_after_discount_amount or 0 for t in taxes if "service" in (t.account_head or "").lower())
        vat_total = sum(t.base_tax_amount_after_discount_amount or 0 for t in taxes if "vat" in (t.account_head or "").lower())

        data.append({
            "sales_number": inv.name,
            "bill_number": inv.consolidated_invoice,
            "sales_type": None,
            "sales_date": inv.posting_date,
            "sales_in_time": inv.posting_time,
            "sales_out_time": None,
            "branch": inv.branch,
            "brand": None,
            "city": None,
            "area": None,
            "visit_purpose": inv.order_type,
            "table": None,
            "loyalty_member_code": None,
			"loyalty_member_name": None,
            "visitor_type": None,
            "promotion": None,
            "pax_total": None,
            "subtotal": inv.base_total,
            "menu_discount": None,
            "bill_discount": inv.base_discount_amount,
            "voucher_discount": None,
            "net_sales": inv.base_net_total,
            "service_charge_total": service_total,
            "tax_total": vat_total,
            "voucher_sales_total": None,
            "rounding_total": inv.rounding_adjustment,
            "grand_total": inv.grand_total,
            "waiter": user_map.get(inv.owner, inv.owner),
            "cashier": user_map.get(inv.owner, inv.owner),
            "additional_info": None,
        })
    return data
