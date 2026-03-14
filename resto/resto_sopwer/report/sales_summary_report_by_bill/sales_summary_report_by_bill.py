# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):

    filters = filters or {}

    columns = [
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date"},
        {"label": "Branch", "fieldname": "branch", "fieldtype": "Link", "options": "Branch"},

        {"label": "Bill", "fieldname": "pos_invoice", "fieldtype": "Link", "options": "POS Invoice"},
        {"label": "Status", "fieldname": "status", "fieldtype": "Data"},

        {"label": "Total Qty", "fieldname": "qty", "fieldtype": "Float"},
        {"label": "Total", "fieldname": "amount", "fieldtype": "Currency"},

        {"label": "Discount", "fieldname": "discount", "fieldtype": "Currency"},
        {"label": "Service", "fieldname": "service", "fieldtype": "Currency"},
        {"label": "Tax", "fieldname": "tax", "fieldtype": "Currency"},

        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency"},
        {"label": "Payment Type", "fieldname": "payment_type", "fieldtype": "Data"},
    ]

    conditions = []

    if filters.get("pos_invoice"):
        conditions.append("pi.name = %(pos_invoice)s")

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

            pi.total_qty AS qty,
            pi.total AS amount,

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

            pi.grand_total,

            (
                SELECT GROUP_CONCAT(DISTINCT sip.mode_of_payment SEPARATOR ', ')
                FROM `tabSales Invoice Payment` sip
                WHERE sip.parent = pi.name
                AND sip.amount > 0
            ) AS payment_type

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
            pi.name

        ORDER BY
            pi.posting_date DESC
        """,
        filters,
        as_dict=1
    )

    return columns, data