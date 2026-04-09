frappe.ui.form.on("POS Invoice", {
    refresh(frm) {

        if (!frm.is_new() && frm.doc.docstatus === 1) {
            frm.add_custom_button("Print Bill", () => {

                frappe.call({
                    method: "resto.api.print_receipt_now",
                    args: {
                        invoice_name: frm.doc.name,
                        branch: frm.doc.branch
                    },
                    freeze: true,
                    freeze_message: "Printing...",
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.msgprint("Print berhasil");
                        }
                    }
                });

            });
        }
    }
});