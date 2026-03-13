# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):

    filters = filters or {}

    columns = [
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 150},

        {"label": "Bill", "fieldname": "pos_invoice", "fieldtype": "Link", "options": "POS Invoice", "width": 160},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 110},

        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data", "width": 200},

        {"label": "Qty", "fieldname": "qty", "fieldtype": "Float", "width": 80},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency", "width": 120},

        {"label": "Discount", "fieldname": "discount", "fieldtype": "Currency", "width": 120},
        {"label": "Service", "fieldname": "service", "fieldtype": "Currency", "width": 120},
        {"label": "Tax", "fieldname": "tax", "fieldtype": "Currency", "width": 120},

        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 140},

        {"label": "Quick Notes", "fieldname": "quick_notes", "fieldtype": "Data", "width": 200},
        {"label": "Add Ons", "fieldname": "add_ons", "fieldtype": "Data", "width": 200},
    ]

    conditions = []

    if filters.get("pos_invoice"):
        conditions.append("pi.name = %(pos_invoice)s")

    if filters.get("item_code"):
        conditions.append("pii.item_code = %(item_code)s")

    if filters.get("from_date"):
        conditions.append("pi.posting_date >= %(from_date)s")

    if filters.get("to_date"):
        conditions.append("pi.posting_date <= %(to_date)s")

    condition_sql = ""
    if conditions:
        condition_sql = " AND " + " AND ".join(conditions)

    data = frappe.db.sql(
        f"""
        SELECT
            pi.posting_date,
            pi.branch,
            pi.name AS pos_invoice,
            pi.status,

            pii.item_code,
            pii.item_name,

            GROUP_CONCAT(DISTINCT pii.quick_notes SEPARATOR ', ') AS quick_notes,
            GROUP_CONCAT(DISTINCT pii.add_ons SEPARATOR ', ') AS add_ons,

            SUM(pii.qty) AS qty,
            SUM(pii.amount) AS amount,

            pi.discount_amount AS discount,

            SUM(
                CASE 
                    WHEN stc.description LIKE '%%Service%%'
                    THEN stc.tax_amount_after_discount_amount
                    ELSE 0
                END
            ) AS service,

            SUM(
                CASE 
                    WHEN stc.description LIKE '%%VAT%%'
                    OR stc.description LIKE '%%Tax%%'
                    THEN stc.tax_amount_after_discount_amount
                    ELSE 0
                END
            ) AS tax,

            pi.grand_total

        FROM
            `tabPOS Invoice` pi

        LEFT JOIN
            `tabPOS Invoice Item` pii
            ON pii.parent = pi.name

        LEFT JOIN
            `tabSales Taxes and Charges` stc
            ON stc.parent = pi.name

        WHERE
            pi.docstatus = 1
            {condition_sql}

        GROUP BY
            pi.posting_date,
            pi.branch,
            pi.name,
            pii.item_code

        ORDER BY
            pi.posting_date DESC
        """,
        filters,
        as_dict=1
    )

    return columns, data