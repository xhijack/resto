// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on('Resto Menu', {
  refresh(frm) {
    frm.add_custom_button('Buat Branch Menu', () => {
      const d = new frappe.ui.Dialog({
        title: 'Buat Branch Menu',
        fields: [
          {
            label: 'Branch',
            fieldname: 'branch',
            fieldtype: 'Link',
            options: 'Branch', // ganti jika nama Doctype branch-mu berbeda
            reqd: 1,
          },
          {
            label: 'Price List',
            fieldname: 'price_list',
            fieldtype: 'Link',
            options: 'Price List',
            reqd: 1,
            default: frm.doc.price_list || undefined,
          },
        ],
        primary_action_label: 'Buat',
        primary_action(values) {
          d.hide();
          frappe.call({
            method: 'resto.resto_sopwer.doctype.resto_menu.resto_menu.make_branch_menu',
            args: {
              source_name: frm.doc.name,
              branch: values.branch,
              price_list: values.price_list,
            },
            freeze: true,
            freeze_message: 'Membuat ke Branch Menu...',
            callback(r) {
              if (r.message) {
                frappe.show_alert({ message: 'Branch Menu dibuat', indicator: 'green' });
                frappe.set_route('Form', 'Branch Menu', r.message);
              }
            }
          });
        },
      });

      d.show();
    });
  },
});



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
