// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sales Report", {
	refresh(frm) {
        if (!frm.doc.__islocal) return

        frm.add_custom_button("End Day", () => {
            frappe.call({
                method: "resto_sopwer.resto_sopwer.doctype.sales_report.sales_report.end_day",
                args: {
                    docname: frm.doc.name,
                    report_date: frm.doc.report_date,
                    branch: frm.doc.branch
                },
                callback: function(r) {
                    frm.reload_doc()
                }
            })
        })
	},
});
