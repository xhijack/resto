// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Daily Summary", {
	refresh(frm) {
        calculate_totals(frm);
	},

    pos_transaction_add: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    pos_transaction_remove: function(frm, cdt, cdn) {
        calculate_totals(frm);
    },
    pos_transaction_change: function(frm, cdt, cdn) {
        calculate_totals(frm);
    }
});

function calculate_totals(frm) {
    let total_qty = 0;
    let grand_total = 0;

    frm.doc.pos_transaction.forEach(row => {
        total_qty += row.qty || 0;
        grand_total += row.amount || 0;
    });

    frm.set_value("total_quantity", total_qty);
    frm.set_value("grand_total", grand_total);
}