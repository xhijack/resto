// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Resto Menu Tool", {
    refresh(frm) {
        frm.add_custom_button(__('Clear Menu'), function() {
            frappe.confirm(
                __('This will clear all rows in Branch Menu. Do you want to continue?'),
                function() {
                    // Clear child table rows
                    if (typeof frm.clear_table === 'function') {
                        frm.doc.item_menu = null;
                        frm.clear_table('branch_menu');
                    } else {
                        frm.doc.branch_menu = [];
                        frm.refresh_field && frm.refresh_field('branch_menu');
                    }
                    frm.refresh_field && frm.refresh_field('branch_menu');
                    frm.refresh_field && frm.refresh_field('item_menu');
                    frappe.msgprint(__('Branch menu cleared'));
                }
            );
        });
    },
    item_menu(frm){
        frappe.call({
            method: "resto.resto_sopwer.doctype.resto_menu_tool.resto_menu_tool.get_branches_with_menu",
            args: {
                item_menu: frm.doc.item_menu
            },
            callback: function(r) {
                const branches = r.message || [];
                if (!branches.length) {
                    frappe.msgprint(__("No branches with menu found"));
                    return;
                }

                // Clear existing child table rows
                if (typeof frm.clear_table === 'function') {
                    frm.clear_table("branch_menu");
                } else {
                    frm.doc.branch_menu = [];
                    refresh_field("branch_menu");
                }

                // Insert fetched branches into branch_menu child table
                branches.forEach(b => {
                    const row = frm.add_child("branch_menu");
                    row.branch = b.branch || "";
                    // If the child field is a Check, set 1/0; if it's a Checkbox boolean, that's fine too.
                    row.enabled = b.enabled ? 1 : 0;
                    row.price_list = b.price_list || "";
                    row.rate = b.rate || 0;
                });

                frm.refresh_field("branch_menu");
            },
            error: function(err) {
                console.error(err);
                frappe.msgprint({title: __("Error"), message: __("Failed to fetch branches"), indicator: "red"});
            }
        });
    }
});

frappe.ui.form.on("Resto Menu Detail Tool", {
    price_list(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);

        // Guard: if no item or no price_list, clear rate
        if (!frm.doc.sell_item || !row.price_list) {
            row.rate = 0;
            frm.refresh_field("branch_menu");
            return;
        }

        // Read price from Item Price doctype using frappe.client.get_value
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Item Price",
                filters: {
                    price_list: row.price_list,
                    item_code: frm.doc.sell_item
                },
                fieldname: ["price_list_rate"]
            },
            callback: function(r) {
                if (r.message && r.message.price_list_rate !== undefined) {
                    row.rate = r.message.price_list_rate;
                } else {
                    row.rate = 0;
                }
                frm.refresh_field("branch_menu");
            },
            error: function(err) {
                console.error(err);
                frappe.msgprint({title: __("Error"), message: __("Failed to fetch item price"), indicator: "red"});
            }
        });
    }
});