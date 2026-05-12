# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": "Date",
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 120
        },
        {
            "label": "Total Pax",
            "fieldname": "total_pax",
            "fieldtype": "Int",
            "width": 120
        },
        {
            "label": "Total Qty",
            "fieldname": "total_qty",
            "fieldtype": "Float",
            "width": 120
        },
        {
            "label": "Discount",
            "fieldname": "discount",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": "Tax",
            "fieldname": "tax",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": "Service",
            "fieldname": "service",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": "Entertain",
            "fieldname": "entertain",
            "fieldtype": "Currency",
            "width": 150
        },
        {
            "label": "Grand Total",
            "fieldname": "grand_total",
            "fieldtype": "Currency",
            "width": 180
        }
    ]


def get_data(filters):

    conditions = ["docstatus = 1"]

    if filters.get("from_date"):
        conditions.append(
            f"posting_date >= '{filters.get('from_date')}'"
        )

    if filters.get("to_date"):
        conditions.append(
            f"posting_date <= '{filters.get('to_date')}'"
        )

    where_clause = " AND ".join(conditions)

    invoices = frappe.db.sql(f"""
        SELECT
            posting_date,

            SUM(COALESCE(pax, 0)) as total_pax,

            SUM(COALESCE(total_qty, 0)) as total_qty,

            SUM(COALESCE(total_taxes_and_charges, 0)) as tax,

            SUM(COALESCE(grand_total, 0)) as grand_total

        FROM `tabPOS Invoice`
        WHERE {where_clause}

        GROUP BY posting_date

        ORDER BY posting_date DESC
    """, as_dict=True)

    data = []

    for row in invoices:

        # ======================
        # SERVICE
        # ======================

        service = frappe.db.sql("""
            SELECT
                SUM(base_tax_amount_after_discount_amount)
            FROM `tabSales Taxes and Charges`
            WHERE parenttype = 'POS Invoice'
            AND account_head LIKE '%%Service%%'
            AND parent IN (
                SELECT name
                FROM `tabPOS Invoice`
                WHERE posting_date = %s
                AND docstatus = 1
            )
        """, (
            row.posting_date,
        ))[0][0] or 0

        # ======================
        # DISCOUNT
        # ======================

        discount = frappe.db.sql("""
            SELECT
                ABS(SUM(base_tax_amount_after_discount_amount))
            FROM `tabSales Taxes and Charges`
            WHERE parenttype = 'POS Invoice'
            AND account_head LIKE '%%Potongan%%'
            AND parent IN (
                SELECT name
                FROM `tabPOS Invoice`
                WHERE posting_date = %s
                AND docstatus = 1
            )
        """, (
            row.posting_date,
        ))[0][0] or 0

        # ======================
        # ENTERTAIN
        # ======================

        entertain = frappe.db.sql("""
            SELECT
                SUM(sip.amount)
            FROM `tabSales Invoice Payment` sip
            INNER JOIN `tabMode of Payment` mop
                ON mop.name = sip.mode_of_payment
            WHERE mop.type = 'General'
            AND sip.parent IN (
                SELECT name
                FROM `tabPOS Invoice`
                WHERE posting_date = %s
                AND docstatus = 1
            )
        """, (
            row.posting_date,
        ))[0][0] or 0

        data.append({
            "posting_date": row.posting_date,
            "total_pax": flt(row.total_pax),
            "total_qty": flt(row.total_qty),
            "discount": flt(discount),
            "tax": flt(row.tax),
            "service": flt(service),
            "entertain": flt(entertain),
            "grand_total": flt(row.grand_total)
        })

    return data