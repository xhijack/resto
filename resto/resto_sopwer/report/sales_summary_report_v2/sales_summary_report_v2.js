// Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.query_reports["Sales Summary Report v2"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_end(),
            reqd: 1
        }
    ]
};

