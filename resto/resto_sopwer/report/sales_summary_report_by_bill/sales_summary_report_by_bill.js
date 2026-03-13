// Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Summary Report by Bill"] = {
	filters: [
        {
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date",
            default: frappe.datetime.month_start()
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date",
            default: frappe.datetime.month_end()
        },
        {
            fieldname: "pos_invoice",
            label: "Bill",
            fieldtype: "Link",
            options: "POS Invoice"
        }
    ]
};
