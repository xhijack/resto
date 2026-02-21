// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.listview_settings["KS Printing"] = {
    onload(listview) {

        listview.page.add_action_item("🔄 Reprint Kitchen", async function () {

            let selected = listview.get_checked_items();

            if (!selected.length) {
                frappe.msgprint("Please select record");
                return;
            }

            for (let row of selected) {

                await frappe.call({
                    method: "resto.api.reprint_ks_printing",
                    args: {
                        log_name: row.name
                    }
                });
            }

            frappe.msgprint("Reprint triggered");
        });
    }
};