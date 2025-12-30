frappe.listview_settings['POS Closing Entry'] = {
    onload(listview) {

        listview.page.add_menu_item(__('End Day'), function () {

            frappe.confirm(
                __('This will create POS Daily Summary for today. Continue?'),
                function () {

                    frappe.call({
                        method: "resto.resto_sopwer.doctype.pos_daily_summary.pos_daily_summary.end_day_from_shift",
                        args: {
                            posting_date: frappe.datetime.get_today()
                        },
                        callback(r) {
                            frappe.msgprint(__('POS Daily Summary created successfully'));
                            listview.refresh();
                        }
                    });

                }
            );

        });

    }
};
