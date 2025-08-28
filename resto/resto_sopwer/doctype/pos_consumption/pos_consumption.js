// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt

frappe.ui.form.on('POS Consumption', {
    refresh(frm) {
        const grid = frm.fields_dict['menu_items'].grid;

        const render_buttons = () => {
            grid.grid_rows.forEach(row => {
                const $td = $(row.row).find('[data-fieldname="show_rm"]');
                if ($td.length && $td.find('.show-rm-btn').length === 0) {
                    $td.html(`<button type="button" class="btn btn-xs btn-primary show-rm-btn" data-rowname="${row.doc.name}">Open Raw Material</button>`);
                }
            });

            grid.wrapper.find('.show-rm-btn').off('click').on('click', function(e) {
                e.preventDefault();
                e.stopImmediatePropagation();

                const rowname = $(this).data('rowname');
                const row = frm.doc.menu_items.find(r => r.name === rowname);

                let rm_data = [];
                try {
                    rm_data = JSON.parse(row.raw_material_breakdown || '[]');
                } catch(e) {
                    console.error('JSON parsing error:', e);
                    rm_data = [];
                }

                const totalCost = rm_data.reduce((sum, rm) => sum + (parseFloat(rm.cost) || 0), 0);

                let html = `
                    <div style="overflow-x:auto; max-width:100%;">
                        <table class="table table-bordered">
                            <thead>
                                <tr>
                                    <th style="white-space: nowrap;">RM Item</th>
                                    <th style="white-space: nowrap;">Required Qty</th>
                                    <th style="white-space: nowrap;">Actual Qty</th>
                                    <th style="white-space: nowrap;">Different Qty</th>
                                    <th style="white-space: nowrap;">UOM</th>
                                    <th style="white-space: nowrap;">Available Qty</th>
                                    <th style="white-space: nowrap;">Warehouse</th>
                                    <th style="white-space: nowrap;">Remarks</th>
                                    <th style="white-space: nowrap;">Unit Cost</th>
                                    <th style="white-space: nowrap;">Cost</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${rm_data.map(rm => `
                                    <tr>
                                        <td style="white-space: nowrap;">${rm.rm_item || ''}</td>
                                        <td style="white-space: nowrap; text-align:right;">${rm.planned || 0}</td>
                                        <td style="white-space: nowrap; text-align:right;">${rm.act || 0}</td>
                                        <td style="white-space: nowrap; text-align:right;">${rm.diffq || 0}</td>
                                        <td style="white-space: nowrap;">${rm.uom || ''}</td>
                                        <td style="white-space: nowrap; text-align:right;">${rm.avail || 0}</td>
                                        <td style="white-space: nowrap;">${rm.wh || ''}</td>
                                        <td style="white-space: nowrap;">${rm.remarks || ''}</td>
                                        <td style="white-space: nowrap; text-align:right;">${formatCurrency(rm.uc)}</td>
                                        <td style="white-space: nowrap; text-align:right;">${formatCurrency(rm.cost)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                            <tfoot>
                                <tr style="font-weight:bold;">
                                    <td colspan="9" style="text-align:right;">Total</td>
                                    <td style="text-align:right;">${formatCurrency(totalCost)}</td>
                                </tr>
                            </tfoot>

                        </table>
                    </div>`;

                let d = new frappe.ui.Dialog({
                    title: `Raw Material - ${row.menu}`,
                    fields: [{ fieldtype: 'HTML', fieldname: 'rm_table', options: html }],
                    primary_action_label: 'Close',
                    primary_action() { d.hide(); }
                });

                d.show();
                d.$wrapper.find('.modal-content').css({
                    'width': '95vw',
                    'margin': '0 auto',
                    'left': '50%',
                    'transform': 'translateX(-50%)'
                });


            });
        };

        render_buttons();
        grid.on_grid_after_render = render_buttons;
    }
});

const formatCurrency = (value) => {
    return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR' }).format(value || 0);
}
