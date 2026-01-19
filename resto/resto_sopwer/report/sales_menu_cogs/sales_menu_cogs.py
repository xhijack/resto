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
        {"label": "Sales Number", "fieldname": "sales_number", "fieldtype": "Link", "options": "POS Invoice"},
        {"label": "Sales Date", "fieldname": "sales_date", "fieldtype": "Date", "width": 120},
        {"label": "Sales Type", "fieldname": "sales_type", "fieldtype": "Data"},
        {"label": "Branch", "fieldname": "branch", "fieldtype": "Data"},
        {"label": "Menu", "fieldname": "menu", "fieldtype": "Data"},
        {"label": "Menu Code", "fieldname": "menu_code", "fieldtype": "Link", "options": "Item"},
        {"label": "Menu Category", "fieldname": "menu_category", "fieldtype": "Data"},
        {"label": "Menu Category Detail", "fieldname": "menu_category_detail", "fieldtype": "Data"},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float"},
        {"label": "Price", "fieldname": "price", "fieldtype": "Currency"},
        {"label": "Total", "fieldname": "total", "fieldtype": "Currency"},
        {"label": "Discount Total", "fieldname": "discount_total", "fieldtype": "Currency"},
        {"label": "COGS Total", "fieldname": "cogs_total", "fieldtype": "Currency"},
        {"label": "COGS Total (%)", "fieldname": "cogs_percent", "fieldtype": "Percent"},
        {"label": "Margin", "fieldname": "margin", "fieldtype": "Currency"},
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

    pos_invoices = frappe.db.sql(f"""
        SELECT name, posting_date, order_type, branch, total, base_total, discount_amount, base_discount_amount, grand_total
        FROM `tabPOS Invoice`
        WHERE {conditions_str}
        ORDER BY posting_date DESC
    """,
    values={
        "from_date": getdate(from_date),
        "to_date": getdate(to_date),
        "branch": branch,
        "company": company
    }, as_dict=True)

    data = []

    for inv in pos_invoices:
        items = frappe.get_all(
            "POS Invoice Item",
            filters={"parent": inv.name, "parenttype": "POS Invoice"},
            fields=[
                "item_name", "item_code", "item_group", "qty", "rate", "base_amount", "discount_amount", "net_amount", "resto_menu"
            ]
        )

        for item in items:
            menu_code = None
            if item.resto_menu:
                menu_code = frappe.db.get_value("Resto Menu", item.resto_menu, "menu_code")
            # Ambil COGS terakhir dari valuation_rate
            valuation_rate = frappe.db.get_value("Bin", {"item_code": item.item_code, "warehouse": item.warehouse}, "valuation_rate") or 0
            total_cogs = valuation_rate * item.qty
            margin = (item.net_amount or 0) - total_cogs
            cogs_percent = (total_cogs / (item.net_amount or 1)) * 100 if item.net_amount else 0

            data.append({
                "sales_number": inv.name,
                "sales_date": inv.posting_date,
                "sales_type": "",
                "branch": inv.branch,
                "menu": item.item_name,
                "menu_code": menu_code,
                "menu_category": item.item_group or "",
                "menu_category_detail": item.item_group2 or "",
                "qty": item.qty,
                "price": item.rate,
                "total": item.net_amount or 0,
                "discount_total": item.discount_amount or 0,
                "cogs_total": total_cogs,
                "cogs_percent": cogs_percent,
                "margin": margin,
            })

    return data
