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
        {"label": "Sales Type", "fieldname": "sales_type", "fieldtype": "Data", "width": 120},
        {"label": "Menu Category", "fieldname": "menu_category", "fieldtype": "Data", "width": 120},
        {"label": "Menu Category Detail", "fieldname": "menu_category_detail", "fieldtype": "Data", "width": 150},
        {"label": "Menu", "fieldname": "menu", "fieldtype": "Data", "width": 140},
        {"label": "Menu Short Name", "fieldname": "menu_short_name", "fieldtype": "Data", "width": 120},
        {"label": "Menu Custom Name", "fieldname": "menu_custom_name", "fieldtype": "Data", "width": 140},
        {"label": "Menu Code", "fieldname": "menu_code", "fieldtype": "Data", "width": 120},
        {"label": "Menu Tag", "fieldname": "menu_tag", "fieldtype": "Data", "width": 120},
        {"label": "Menu Info", "fieldname": "menu_info", "fieldtype": "Data", "width": 150},
        {"label": "Order Mode", "fieldname": "order_mode", "fieldtype": "Data", "width": 120},
        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 90},
        {"label": "Unit Price", "fieldname": "unit_price", "fieldtype": "Currency", "width": 110},
        {"label": "Subtotal", "fieldname": "subtotal", "fieldtype": "Currency", "width": 120},
        {"label": "Menu Discount Total", "fieldname": "menu_discount_total", "fieldtype": "Currency", "width": 130},
        {"label": "Bill Discount Total", "fieldname": "bill_discount_total", "fieldtype": "Currency", "width": 130},
        {"label": "Net Sales Total", "fieldname": "net_sales_total", "fieldtype": "Currency", "width": 120},
        {"label": "Service Charge Total", "fieldname": "service_charge_total", "fieldtype": "Currency", "width": 160},
        {"label": "Tax Total", "fieldname": "tax_total", "fieldtype": "Currency", "width": 120},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 130},
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
        SELECT name, consolidated_invoice, order_type, posting_date,
               posting_time, branch, customer, pos_profile,
               total, base_total, net_total, base_net_total,
               discount_amount, base_discount_amount,
               total_taxes_and_charges, rounding_adjustment,
               grand_total, owner, remarks, company
        FROM `tabPOS Invoice`
        WHERE {conditions_str}
        ORDER BY posting_date DESC, posting_time DESC
    """,
    values={
        "from_date": getdate(from_date),
        "to_date": getdate(to_date),
        "branch": branch,
        "company": company
    }, as_dict=True)

    # Mapping owner ke full_name
    user_map = {u.name: u.full_name for u in frappe.get_all("User", fields=["name", "full_name"])}

    data = []
    for inv in pos_invoices:
        # Ambil item menu child table
        items = frappe.get_all(
            "POS Invoice Item",
            filters={"parent": inv.name, "parenttype": "POS Invoice"},
            fields=[
                "item_name", "item_code",
                "item_group", "description", "resto_menu",
                "qty", "rate", "base_amount", "discount_amount", "net_amount",
            ]
        )

        # Ambil taxes
        taxes = frappe.get_all(
            "Sales Taxes and Charges",
            filters={"parent": inv.name, "parenttype": "POS Invoice", "parentfield": "taxes"},
            fields=["account_head", "base_tax_amount_after_discount_amount"]
        )
        service_total = sum(t.base_tax_amount_after_discount_amount or 0 for t in taxes if t.account_head and "service" in t.account_head.lower())
        vat_total = sum(t.base_tax_amount_after_discount_amount or 0 for t in taxes if t.account_head and "vat" in t.account_head.lower())

        # Jika tidak ada item, buat baris kosong tapi tetap menampilkan info invoice
        if not items:
            data.append({
                "sales_type": "",
                "menu_category": "",
                "menu_category_detail": "",
                "menu": "",
                "menu_short_name": "",
                "menu_custom_name": "",
                "menu_code": "",
                "menu_tag": "",
                "menu_info": "",
                "order_mode": "",
                "qty": 0,
                "unit_price": 0,
                "subtotal": 0,
                "menu_discount_total": 0,
                "bill_discount_total": inv.base_discount_amount or 0,
                "net_sales_total": 0,
                "service_charge_total": service_total,
                "tax_total": vat_total,
                "grand_total": inv.grand_total or 0,
            })
        else:
            for item in items:
                menu_code = None
                short_name = None
                if item.resto_menu:
                    menu_code = frappe.db.get_value("Resto Menu", item.resto_menu, "menu_code")
                    short_name = frappe.db.get_value("Resto Menu", item.resto_menu, "short_name")

                data.append({
                    "sales_type": "",
                    "menu_category": item.item_group or "",
                    "menu_category_detail": item.item_group2 or "",
                    "menu": item.item_name or "",
                    "menu_short_name": short_name or "",
                    "menu_custom_name": item.custom_item_name or "",
                    "menu_code": menu_code or "",
                    "menu_tag": item.item_tag or "",
                    "menu_info": "",
                    "order_mode": "POS",
                    "qty": item.qty or 0,
                    "unit_price": item.rate or 0,
                    "subtotal": item.base_amount or 0,
                    "menu_discount_total": item.discount_amount or 0,
                    "bill_discount_total": inv.base_discount_amount or 0,
                    "net_sales_total": item.net_amount or 0,
                    "service_charge_total": service_total,
                    "tax_total": vat_total,
                    "grand_total": inv.grand_total or 0,
                })

    return data
