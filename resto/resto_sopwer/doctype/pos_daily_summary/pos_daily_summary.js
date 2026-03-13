// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("POS Daily Summary", {
	refresh(frm) {
        // calculate_totals(frm);
        // tambahkan button get pos closing yang end_day_processed = 0
        frm.add_custom_button("Get POS Closing Entries", function() {
            frappe.msgprint("Masih dalam tahap pengembangan. Fitur ini akan segera hadir.");
            // frappe.call({
            //     method: "resto.resto.resto_sopwer.doctype.pos_daily_summary.pos_daily_summary.get_pos_closing_entries",
            //     args: {
            //         posting_date: frm.doc.posting_date,
            //         branch: frm.doc.branch
            //     },
            //     callback: function(r) {
            //         if (r.message) {
            //             frm.clear_table("pos_transaction");
            //             r.message.forEach(function(entry) {
            //                 let row = frm.add_child("pos_transaction");
            //                 row.pos_closing_entry = entry.name;
            //                 row.qty = entry.total_qty;
            //                 row.amount = entry.grand_total;
            //             });
            //             frm.refresh_field("pos_transaction");
            //             calculate_totals(frm);
            //         }
            //     }
            // });
        });
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