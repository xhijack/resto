# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):

    filters = filters or {}

    columns = [
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date"},
        {"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch"},
        {"label": "Bill", "fieldname": "pos_invoice", "fieldtype": "Link", "options": "POS Invoice"},
        
        {"label": "Item Code", "fieldname": "item_code", "fieldtype": "Link", "options": "Item"},
        {"label": "Item Name", "fieldname": "item_name", "fieldtype": "Data"},

        {"label": "Total Qty", "fieldname": "qty", "fieldtype": "Float"},
        {"label": "Rate", "fieldname": "rate", "fieldtype": "Currency"},
        {"label": "Amount", "fieldname": "amount", "fieldtype": "Currency"},
        
        {"label": "Status", "fieldname": "status", "fieldtype": "Data"},
        {"label": "Quick Notes", "fieldname": "quick_notes", "fieldtype": "Data"},
        {"label": "Add Ons", "fieldname": "add_ons", "fieldtype": "Data"},
    ]

    conditions = []

    if filters.get("item_code"):
        conditions.append("pii.item_code = %(item_code)s")

    if filters.get("branch"):
        conditions.append("pi.branch = %(branch)s")

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
            pii.item_code,
            pii.item_name,
            pi.status,

            SUM(pii.qty) AS qty,
            pii.rate AS rate,
            SUM(pii.amount) AS amount,
            
            GROUP_CONCAT(
                DISTINCT CASE 
                    WHEN TRIM(pii.quick_notes) <> '' 
                    THEN pii.quick_notes 
                END
                SEPARATOR ', '
            ) AS quick_notes,

            GROUP_CONCAT(
                DISTINCT CASE 
                    WHEN TRIM(pii.add_ons) <> '' 
                    THEN pii.add_ons 
                END
                SEPARATOR ', '
            ) AS add_ons

        FROM
            `tabPOS Invoice Item` pii

        INNER JOIN
            `tabPOS Invoice` pi
            ON pi.name = pii.parent

        WHERE
            pi.docstatus = 1
            {condition_sql}

        GROUP BY
            pii.item_code,
            pii.item_name

        ORDER BY
            amount DESC
        """,
        filters,
        as_dict=1
    )

    return columns, data