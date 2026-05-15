// Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Sales Report"] = {
    filters: [
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.now_date(),
            reqd: 1,
        },
        {
            fieldname: "branch",
            label: __("Branch"),
            fieldtype: "Link",
            options: "Branch",
            default: frappe.defaults.get_user_default("branch") || "",
        },
    ],

    onload(report) {
        const setRange = (from, to) => {
            report.set_filter_value("from_date", from);
            report.set_filter_value("to_date", to);
        };

        report.page.add_inner_button(__("Hari Ini"), () => {
            const today = frappe.datetime.now_date();
            setRange(today, today);
        });

        report.page.add_inner_button(__("Minggu Ini"), () => {
            setRange(frappe.datetime.week_start(), frappe.datetime.now_date());
        });

        report.page.add_inner_button(__("Bulan Ini"), () => {
            setRange(frappe.datetime.month_start(), frappe.datetime.now_date());
        });

        report.page.add_inner_button(__("Print Lengkap (PDF)"), () => {
            const filters = report.get_values();
            if (!filters.from_date || !filters.to_date) {
                frappe.msgprint(__("Pilih From Date dan To Date terlebih dahulu"));
                return;
            }
            if (!filters.branch) {
                frappe.msgprint(__("Pilih Branch terlebih dahulu untuk Print Lengkap"));
                return;
            }
            const url =
                "/api/method/resto.api.print_daily_sales_full_pdf" +
                "?from_date=" + encodeURIComponent(filters.from_date) +
                "&to_date=" + encodeURIComponent(filters.to_date) +
                "&branch=" + encodeURIComponent(filters.branch);
            window.open(url, "_blank");
        });
    },
};
