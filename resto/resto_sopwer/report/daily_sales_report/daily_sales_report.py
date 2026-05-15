# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

from resto.services.reporting_service import ReportingService


def execute(filters=None):
    filters = filters or {}
    data = ReportingService().get_daily_sales_summary(
        from_date=filters.get("from_date"),
        to_date=filters.get("to_date"),
        branch=filters.get("branch"),
    )
    return get_columns(), data


def get_columns():
    return [
        {"label": "Tanggal", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": "Cabang", "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 140},
        {"label": "Pax", "fieldname": "total_pax", "fieldtype": "Int", "width": 80},
        {"label": "Bill", "fieldname": "total_bill", "fieldtype": "Int", "width": 80},
        {"label": "Sub Total", "fieldname": "sub_total", "fieldtype": "Currency", "width": 140},
        {"label": "Discount", "fieldname": "discount", "fieldtype": "Currency", "width": 130},
        {"label": "Tax", "fieldname": "tax", "fieldtype": "Currency", "width": 120},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 160},
        {"label": "Void Bill", "fieldname": "void_bill", "fieldtype": "Int", "width": 90},
        {"label": "Void Amount", "fieldname": "void_amount", "fieldtype": "Currency", "width": 140},
        {"label": "Draft Bill", "fieldname": "draft_bill", "fieldtype": "Int", "width": 90},
        {"label": "Draft Amount", "fieldname": "draft_amount", "fieldtype": "Currency", "width": 140},
    ]
