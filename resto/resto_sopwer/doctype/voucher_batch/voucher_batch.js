// Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Voucher Batch", {
    refresh(frm) {
        if (frm.is_new() || frm.doc.is_generated) {
            return;
        }
        frm.add_custom_button(__("Generate Vouchers"), () => {
            frappe.confirm(
                __(
                    "Generate {0} vouchers? Tindakan ini tidak bisa diundo. Setelah generate, kode-kode terdaftar di Voucher List dan batch ini terkunci.",
                    [frm.doc.voucher_count]
                ),
                () => {
                    frappe.dom.freeze(__("Generating vouchers..."));
                    frm.call("generate_vouchers")
                        .then((r) => {
                            if (r.exc) return;
                            frappe.show_alert({
                                message: __(
                                    "{0} voucher berhasil di-generate. Filter Voucher List by batch_id = {1}.",
                                    [frm.doc.voucher_count, frm.doc.name]
                                ),
                                indicator: "green",
                            }, 7);
                            frm.reload_doc();
                        })
                        .always(() => frappe.dom.unfreeze());
                }
            );
        }, null, "primary");
    },
});
