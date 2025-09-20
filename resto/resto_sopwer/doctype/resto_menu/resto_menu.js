// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Menu Add Ons", {
	item: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item) {
            frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Item Price",
                filters: {
                item_code: row.item,
                price_list: frm.doc.price_list
                },
                fieldname: "price_list_rate"
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, "price", r.message.price_list_rate);
                } else {
                    frappe.model.set_value(cdt, cdn, "price", 0);
                }
            }
            });
        }
    }   
});
