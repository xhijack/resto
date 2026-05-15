// Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on("Resto Print Rule", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Test Print"), () => {
				frappe.call({
					method: "resto.printing.dispatcher.test_print_rule",
					args: { rule_name: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending test print…"),
					callback(r) {
						if (r.message && r.message.ok) {
							frappe.show_alert({
								message: __("Test print queued on {0} (job {1}).", [
									r.message.printer_name,
									r.message.job_id,
								]),
								indicator: "green",
							});
						} else {
							frappe.msgprint({
								title: __("Test Print Failed"),
								message: (r.message && r.message.error) || __("Unknown error."),
								indicator: "red",
							});
						}
					},
				});
			}, __("Actions"));
		}
	},

	printer_resolver(frm) {
		frm.refresh_field("printer_name");
		frm.refresh_field("kitchen_station");
	},
});
