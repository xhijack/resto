// Stock Usage Tool - Excel-like per-item RM + Selling/Cost + BOM Tree
frappe.provide("resto.stock_usage");

(function () {
  // STYLES
  const STYLES = `
    <style id="sut-inline-style">
      .sut-wrap {
        padding: 16px;
      }

      .sut-item-block {
        border: 1px solid var(--border-color);
        border-radius: 6px;
        margin-bottom: 10px;
        overflow: hidden;
        background: var(--background-color);
        padding: 10px;
      }

      .sut-item-head {
        display: grid;
        grid-template-columns: 160px 1fr 100px 100px 120px 140px;
        gap: 0;
        background: var(--secondary-background-color, #fafafa);
        border-bottom: 1px solid var(--border-color);
      }

      .sut-item-head > div {
        padding: 8px 10px;
        border-right: 1px solid var(--border-color);
        color: var(--text-color);
      }

      .sut-item-head > div:last-child {
        border-right: none;
      }

      .sut-head-title {
        font-weight: 600;
        background: var(--secondary-background-color, #f0f0f0);
        color: var(--text-color);
      }

      .sut-val {
        background: var(--background-color);
        color: var(--text-color);
      }

      .sut-rm-toolbar {
        display: flex;
        gap: 6px;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        padding: 6px 8px;
        background: var(--background-color);
        color: var(--text-color);
      }

      .sut-summary {
        display: flex;
        justify-content: space-between;
        padding: 6px 8px;
        font-size: 12px;
        color: var(--text-muted);
        border-top: 1px solid var(--border-color);
        background: var(--background-color);
      }

      .sut-global-actions {
        display: flex;
        gap: 8px;
        justify-content: flex-end;
        padding: 10px;
        background: var(--background-color);
        margin: 12px 0;
        color: var(--text-color);
      }

      .sut-fg-summary {
        margin-top: 6px;
      }

      #sut-fg,
      #sut-rm-summary {
        display: flex;
        flex-direction: column;
        gap: 8px;
        justify-content: center;
        padding: 10px;
        border: 1px solid var(--border-color);
        border-radius: 6px;
        background: var(--background-color);
        margin: 12px 0;
      }

      #sut-fg-summary .datatable {
        font-size: 12px;
      }

      #sut-fg-summary .dt-cell {
        font-weight: 600;
        color: var(--text-color);
      }

      #sut-fg-summary .dt-header {
        display: none;
      }

      #sut-fg .sut-total-cell,
      #sut-fg .sut-total-label {
        display: block;
        width: 100%;
        padding: 4px 6px;
        font-weight: 600;
        color: var(--text-color);
      }

      .sut-fg-summary {
        display: none; /* hide old separate summary block */
      }

      /* compact filter card */
      #filters.frappe-card {
        padding: 12px !important;
      }

      .sut-compact .frappe-control {
        margin-bottom: 6px;
      }

      .sut-compact .form-section .section-body {
        padding-top: 4px;
        padding-bottom: 4px;
      }

      @media (max-width: 980px) {
        .sut-item-head {
          grid-template-columns: 140px 1fr 90px 90px 110px 120px;
        }
      }

      #filters .frappe-control {
        display: inline-block;
        vertical-align: top;
        margin-right: 15px;
        width: auto;
      }

      .sut-table {
        width: 100%;
        border-collapse: collapse;
        font-family: var(--font-stack, "Helvetica Neue", Arial, sans-serif);
        font-size: 13px;
        color: var(--text-color);
        background-color: var(--background-color);
        border: 1px solid var(--border-color);
        min-width: max-content;
      }

      .sut-table thead th {
        color: var(--header-color, var(--text-color, #000));
        font-weight: 600;
        padding: 6px 8px;
        border-bottom: 1px solid var(--border-color);
        border-right: 1px solid var(--border-color);
        white-space: nowrap;
      }

      .sut-table tbody td {
        padding: 4px 8px;
        border-bottom: 1px solid var(--border-color);
        border-right: 1px solid var(--border-color);
        vertical-align: middle;
        color: var(--text-color);
      }

      .sut-table input[type="text"] {
        border: none;
        padding: 0;
        margin: 0;
        background: transparent;
        font-size: inherit;
        font-family: inherit;
        width: 100%;
        text-align: right;
        color: var(--text-color);
      }

      .sut-table input[type="checkbox"] {
        cursor: pointer;
      }

      .sut-fg-table {
        width: 100%;
        border-collapse: collapse;
        font-family: var(--font-stack, "Helvetica Neue", Arial, sans-serif);
        font-size: 13px;
        color: var(--text-color);
        background-color: var(--background-color);
        border: 1px solid var(--border-color);
        min-width: max-content;
      }

      .sut-fg-table thead th {
        color: var(--text-color);
        font-weight: 600;
        padding: 6px 8px;
        border: 1px solid var(--border-color);
        white-space: nowrap;
      }

      .sut-fg-table tbody td {
        padding: 4px 8px;
        border-bottom: 1px solid var(--border-color);
        border-right: 1px solid var(--border-color);
        vertical-align: middle;
      }

      .sut-fg-table tbody tr:hover td {
        background-color: var(--hover-color, #f4f5f7);
        color: var(--hover-text-color, #000);
      }

      .sut-fg-table .sut-total-row td {
        font-weight: bold;
      }

      #sut-fg {
        overflow-x: auto;
      }

      .td-input {
        color: var(--text-color, #333);
      }

    </style>

  `;

  // ===== Helpers =====
  const COL_N = {
    code: 'Item Code',
    name: 'Item Name',
    req_qty: 'Required Qty',
    act_qty: 'Actual Qty',
    diff_qty: 'Different Qty',
    uom: 'Stock UOM',
    actual_qty: 'Available (WH)',
    wh: 'Warehouse',
    remarks: 'Remarks',
    unit_cost: 'Unit Cost',
    cost: 'Cost',
  };

  function getColMap(dt){
    return {
      code: dtColIndexByName(dt, COL_N.code),
      name: dtColIndexByName(dt, COL_N.name),
      req_qty: dtColIndexByName(dt, COL_N.req_qty),
      act_qty: dtColIndexByName(dt, COL_N.act_qty),
      diff_qty: dtColIndexByName(dt, COL_N.diff_qty),
      uom: dtColIndexByName(dt, COL_N.uom),
      actual_qty: dtColIndexByName(dt, COL_N.actual_qty),
      wh: dtColIndexByName(dt, COL_N.wh),
      remarks: dtColIndexByName(dt, COL_N.remarks),
      unit_cost: dtColIndexByName(dt, COL_N.unit_cost),
      cost: dtColIndexByName(dt, COL_N.cost),
    };
  }
  function dtDataColIndexByName(dt, name){
    const cols = dt && typeof dt.getColumns === 'function' ? dt.getColumns() : [];
    const dataCols = cols.filter(c => c && c.id !== '_checkbox' && c.id !== '_rowIndex');
    for (let i = 0; i < dataCols.length; i++) {
      if ((dataCols[i] && dataCols[i].name) === name) return i;
    }
    return -1;
  }

  const getCellTxt = (dt, r, ci, fb='') => cellToText(safeGetCell(dt, r, ci, fb));
  function flt(v){ if(v===undefined||v===null) return 0; const n=parseFloat(v); return isNaN(n)?0:n; }
  const DEFAULT_CUR=(frappe.boot?.sysdefaults?.currency)||"IDR";
  function fmtFloat(v,p=2){ const n=flt(v); return n.toLocaleString(undefined,{minimumFractionDigits:p,maximumFractionDigits:p}); }
  function fmtCurrency(v){
    const n=flt(v);
    if(DEFAULT_CUR==="IDR"){
      return new Intl.NumberFormat("id-ID",{style:"currency",currency:"IDR",minimumFractionDigits:0})
        .format(n).replace("IDR","Rp");
    }
    return new Intl.NumberFormat(undefined,{style:"currency",currency:DEFAULT_CUR}).format(n);
  }

  function dtRowCount(dt){ return (dt&&dt.datamanager&&typeof dt.datamanager.getRowCount==='function')?dt.datamanager.getRowCount():0; }
  function dtColCount(dt){ return (dt&&typeof dt.getColumns==='function')?dt.getColumns().length:0; }

  function dtColIndexByName(dt, name){
    const cols = dt && typeof dt.getColumns === 'function' ? dt.getColumns() : [];
    for (let i = 0; i < cols.length; i++) {
      if ((cols[i] && cols[i].name) === name) return i;
    }
    return -1;
  }

  function stripTags(s){
    if (typeof s !== "string") return s;
    return s.replace(/<[^>]*>/g, "");
  }

  function cellToText(v){
    if (v == null) return "";
    if (typeof v === "object") {
      const html = v.html ?? v.content ?? "";
      return stripTags(String(html)).trim();
    }
    return stripTags(String(v)).trim();
  }

  function safeGetCell(dt, r, c, fallback = "") {
    try {
      if (!dt || r == null || c == null) return fallback;
      if (typeof dt.getCell === 'function') {
        const raw = dt.getCell(r, c);
        const val = cellToText(raw);
        return (val === undefined || val === null) ? fallback : val;
      }
      const rowObj = dt.datamanager && typeof dt.datamanager.getRow === 'function' ? dt.datamanager.getRow(r) : null;
      if (rowObj && Array.isArray(rowObj.data)) {
        const raw = rowObj.data[c];
        const val = cellToText(raw);
        return (val === undefined || val === null) ? fallback : val;
      }
      return fallback;
    } catch (e) {
      return fallback;
    }
  }

  function dtToArray(dt){
    const rows = dtRowCount(dt), cols = dtColCount(dt), out = [];
    for (let i = 0; i < rows; i++) {
      const row = [];
      for (let j = 0; j < cols; j++) {
        const raw = dt.getCell?.(i, j);
        row.push(cellToText(raw));
      }
      out.push(row);
    }
    return out;
  }

  function aggregateRawMaterials(posBreakdown, defaultWarehouse = "-") {
    const rmAgg = {};

    (posBreakdown || []).forEach(item => {
      // kalau bentuknya FG dengan rm_items
      if (item.rm_items) {
        item.rm_items.forEach(rm => processRM(rm, item.source_warehouse || defaultWarehouse));
      } else {
        // kalau langsung flat RM
        processRM(item, defaultWarehouse);
      }
    });

    function processRM(rm, whValue) {
      const code = rm.item_code;
      if (!code) return;

      if (!rmAgg[code]) {
        rmAgg[code] = {
          item_code: code,
          item_name: rm.item_name || "",
          stock_uom: rm.stock_uom || rm.uom || "",
          act_qty: rm.act_qty || 0,
          actual_qty: rm.actual_qty || "",
          wh: rm.wh || whValue || "-",
          total_required_qty: 0,
          total_cost: 0,
          unit_cost: rm.unit_cost || 0
        };
      }

      let reqQty = Number(rm.required_qty);
      let cost = Number(rm.cost);

      if (!isNaN(reqQty)) {
        rmAgg[code].total_required_qty += reqQty;
      }
      if (!isNaN(cost)) {
        rmAgg[code].total_cost += cost;
      }
    }

    return Object.values(rmAgg);
  }


  resto.stock_usage.Page = class {
    constructor(wrapper) {
      this.wrapper = $(wrapper);
      this.groups = [];
      this.make_page();
      this.make_filters();
      this.bind_global_actions();
    }

    make_page() {
      this.page = frappe.ui.make_app_page({
        parent: this.wrapper,
        title: "Stock Usage Tool",
        single_column: true
      });

      if (!document.getElementById("sut-inline-style")) {
        $(STYLES).appendTo(document.head || document.body);
      }

      this.$body = $(`
        <div class="sut-wrap">
          <div class="frappe-card p-2 sut-compact" id="filters"></div>

          <div class="sut-global-actions">
            <button class="btn btn-default btn-sm" id="recalc-all">Recalculate All</button>
            <button class="btn btn-default btn-sm" id="clear-all">Clear All</button>
            <button class="btn btn-primary btn-sm" id="save-pos-cons">Save POS Consumption</button>
          </div>
          <div id="sut-rm-summary" class="mb-2"></div>
          <div id="sut-fg" class="mb-2"></div>
          <div id="sut-groups"></div>
        </div>
      `);
      this.page.body.append(this.$body);
    }

    make_filters() {
      const me = this;

      this.fg = new frappe.ui.FieldGroup({
        body: this.$body.find('#filters'),
        fields: [
          { fieldtype: 'Section Break', label: '' },

          { fieldname: 'pos_closing_entry', label: 'POS Closing Entry', fieldtype: 'Link', options: 'POS Closing Entry', reqd: 1 },
          { fieldtype: 'Column Break' },

          { fieldname: 'company', label: 'Company', fieldtype: 'Link', options: 'Company', reqd: 1, default: frappe.defaults.get_default("Company") },
          { fieldtype: 'Column Break' },

          { fieldname: 'posting_date', label: 'Posting Date', fieldtype: 'Date', reqd: 1, default: frappe.datetime.get_today() },
          { fieldtype: 'Column Break' },

          { fieldname: 'source_warehouse', label: 'Source Warehouse', fieldtype: 'Link', options: 'Warehouse', reqd: 1 },
          { fieldtype: 'Column Break' },
          {
            fieldname: 'btn_load',
            fieldtype: 'HTML',
            options: `<div style="margin-top:24px;">
                        <button class="btn btn-primary" id="btn_load">Get Items</button>
                      </div>`
          }
        ]
      });

      this.fg.make();

      // Pasang event click untuk button HTML
      $('#btn_load').on('click', () => me.load_from_pos());

      const src = this.fg.fields_dict.source_warehouse;
      src && (src.df.onchange = async () => { await this.bulk_update_availability_all(); this.update_all_cost_summary(); });
    }


    bind_global_actions() {
      this.$body.on('click', '#clear-all', () => this.clear_all());
      this.$body.on('click', '#recalc-all', () => this.recalc_all());
      this.$body.on('click', '#save-pos-cons', () => this.save_pos_consumption());
    }

    // Compute FG cost/margin from DT if available; fallback to rm_items
    get_fg_cost(idx){
      const g = this.groups?.[idx];
      if (!g) return { unit_cost: 0, total_cost: 0, margin_val: 0, margin_pct: 0 };
      let total_cost = 0;
      if (g.dt){
        const COL = getColMap(g.dt);
        const n = dtRowCount(g.dt);
        for (let i = 0; i < n; i++) {
          total_cost += flt(getCellTxt(g.dt, i, COL.cost, 0));
        }
      } else {
        total_cost = (g.meta?.rm_items || []).reduce((acc, x) => acc + flt(x.unit_cost) * flt(x.required_qty), 0);
      }
      const qty = flt(g.meta?.qty || 0) || 1;
      const unit_cost = total_cost / qty;
      const selling = flt(g.meta?.selling_amount || 0);
      const margin_val = selling - total_cost;
      const margin_pct = selling ? (total_cost / selling) * 100 : 0; // Margin% = Cost / Amount
      return { unit_cost, total_cost, margin_val, margin_pct };
    }

    // Compute FG totals (qty, cost, margin, etc.) for all groups
    compute_fg_totals(){
      let total_qty = 0, total_cost = 0, total_sell = 0;
      for (let i = 0; i < this.groups.length; i++){
        const meta = this.groups[i]?.meta || {};
        const c = this.get_fg_cost(i);
        total_qty += flt(meta.qty || 0);
        total_cost += flt(c.total_cost || 0);
        total_sell += flt(meta.selling_amount || 0);
      }
      const unit_cost = total_qty ? (total_cost / total_qty) : 0;
      const avg_sell_rate = total_qty ? (total_sell / total_qty) : 0;
      const avg_margin_unit = avg_sell_rate - unit_cost;
      const margin_val = total_sell - total_cost;
      const margin_pct = total_sell ? (total_cost / total_sell) * 100 : 0; // Cost/Amount
      return { total_qty, total_cost, total_sell, unit_cost, avg_sell_rate, avg_margin_unit, margin_val, margin_pct };
    }

    // ===== FG SUMMARY (totals under FG table) =====
    render_fg_summary(){
      const t = this.compute_fg_totals();
      const $sum = this.$body.find('#sut-fg-summary').empty();
      if (this.fgSumDT && typeof this.fgSumDT.destroy === 'function') this.fgSumDT.destroy();
      this.fgSumDT = new frappe.DataTable($sum.get(0), {
        columns: [{ name: 'Total', editable: false }],
        data: [
          [`Total Qty: ${fmtFloat(t.total_qty, 2)}`],
          [`Total Unit Cost: ${fmtCurrency(t.unit_cost)}`],
          [`Total Cost: ${fmtCurrency(t.total_cost)}`],
          [`Total Margin: ${fmtCurrency(t.margin_val)}`],
          [`Margin %: ${fmtFloat(t.margin_pct, 1)}%`],
        ],
        serialNoColumn: false,
        checkboxColumn: false,
        layout: 'fluid'
      });
    }

    // ===== FG TOTAL ROW (inside FG table) =====
    update_fg_total_row() {
      if (!this.fgDT) return;
      const t = this.compute_fg_totals();
      const idxTotal = this.groups.length; // last row
      const row = [
        '',
        `<div class="sut-total-label">Total</div>`,
        ``,
        `<div class="sut-total-cell">${fmtFloat(t.total_qty, 2)}</div>`,
        ``,
        `<div class="sut-total-cell">x̄ ${fmtCurrency(t.avg_sell_rate)}</div>`,
        `<div class="sut-total-cell">Σ ${fmtCurrency(t.total_sell)}</div>`,
        `<div class="sut-total-cell">x̄ ${fmtCurrency(t.unit_cost)}</div>`,
        `<div class="sut-total-cell">Σ ${fmtCurrency(t.total_cost)}</div>`,
        `<div class="sut-total-cell">x̄ ${fmtCurrency(t.avg_margin_unit)}</div>`,
        `<div class="sut-total-cell">${fmtFloat(t.margin_pct, 1)}%</div>`,
      ];
      // If table has fewer rows, append; else update
      const currentRows = this.fgDT.datamanager?.getRowCount?.() || 0;
      if (currentRows <= idxTotal) {
        this.fgDT.refresh?.([...this.fgDT.getData(), row]);
      } else {
        this.fgDT.updateRow?.(idxTotal, row);
      }
      // No longer mark last row as TOTAL visually
    }

    // ===== FG TABLE (single table with expand arrow) =====
    render_fg_table(items) {
      const t = this.compute_fg_totals();

      // table header
      let html = `
        <div><b>Finished Goods Item</b></div>
        <table class="sut-table sut-fg-table">
          <thead>
            <tr>
              <th>Item Code</th>
              <th>Item Name</th>
              <th>Menu</th>
              <th>Category</th>
              <th style="text-align:right;">Qty</th>
              <th>Stock UOM</th>
              <th style="text-align:right;">Selling Rate</th>
              <th style="text-align:right;">Amount</th>
              <th style="text-align:right;">Unit Cost</th>
              <th style="text-align:right;">Cost</th>
              <th style="text-align:right;">Margin</th>
              <th style="text-align:right;">Margin %</th>
            </tr>
          </thead>
          <tbody>
      `;

      // table body rows
      (items || []).forEach((meta, i) => {
        const c = this.get_fg_cost(i);
        html += `
          <tr style="cursor:pointer;user-select:none;" class="sut-exp" data-row="${i}">
            <td>${frappe.utils.escape_html(meta.item_code || '')}</td>
            <td>${frappe.utils.escape_html(meta.item_name || '')}</td>
            <td>${frappe.utils.escape_html(meta.resto_menu || '')}</td>
            <td>${frappe.utils.escape_html(meta.category || '')}</td>
            <td style="text-align:right;">${meta.qty || 0}</td>
            <td>${frappe.utils.escape_html(meta.stock_uom || '')}</td>
            <td style="text-align:right;">${fmtCurrency(meta.selling_rate)}</td>
            <td style="text-align:right;">${fmtCurrency(meta.selling_amount)}</td>
            <td style="text-align:right;">${fmtCurrency(c.unit_cost)}</td>
            <td style="text-align:right;">${fmtCurrency(c.total_cost)}</td>
            <td style="text-align:right;">${fmtCurrency(c.margin_val)}</td>
            <td style="text-align:right;">${fmtFloat(c.margin_pct, 1)}%</td>
          </tr>
        `;
      });

      // total row
      html += `
        <tr class="sut-total-row">
          <td><b>Total</b></td>
          <td></td>
          <td></td>
          <td></td>
          <td style="text-align:right;"><b>${fmtFloat(t.total_qty, 2)}</b></td>
          <td></td>
          <td style="text-align:right;"><b>x̄ ${fmtCurrency(t.avg_sell_rate)}</b></td>
          <td style="text-align:right;"><b>Σ ${fmtCurrency(t.total_sell)}</b></td>
          <td style="text-align:right;"><b>x̄ ${fmtCurrency(t.unit_cost)}</b></td>
          <td style="text-align:right;"><b>Σ ${fmtCurrency(t.total_cost)}</b></td>
          <td style="text-align:right;"><b>x̄ ${fmtCurrency(t.avg_margin_unit)}</b></td>
          <td style="text-align:right;"><b>${fmtFloat(t.margin_pct, 1)}%</b></td>
        </tr>
      `;

      html += `</tbody></table>`;

      // render to container
      const $fg = this.$body.find('#sut-fg').empty().append(html);

      // click handler for expand arrow
      const me = this;
      $fg.off('click.sut-exp').on('click.sut-exp', '.sut-exp', async function () {
        const i = parseInt($(this).attr('data-row'), 10);
        if (isNaN(i)) return;

        // const isClosed = $(this).html() === '&#9654;';
        // $('.sut-exp').html('&#9654;'); // collapse all
        // if (isClosed) $(this).html('&#9660;');

        const g = me.groups[i];
        if (!g) return;

        const isVisible = g.$block && g.$block.is(':visible');

        $('.sut-item-block').hide();

        // if (g && g.$block) {
        //   $('.sut-item-block').hide();
        //   g.$block.show();
        //   return;
        // }

        if (!isVisible) {
          const meta = g.meta || g;
          const wh = me.fg.get_value('source_warehouse')
          const rowsRM = (meta.rm_items || []).map(x => {
            const rq = flt(x.required_qty);
            const adj = 0;
            const finalq = rq + adj;
            const uc = flt(x.unit_cost);
            const wh2 = cellToText(wh);

            return {
              code: cellToText(x.item_code),
              name: cellToText(x.item_name),
              req_qty: rq,
              act_qty: 0,
              diff_qty: 0,
              uom: cellToText(x.stock_uom),
              actual_qty: flt(x.actual_qty),
              wh: wh2,
              remarks: '',
              unit_cost: uc,
              cost: uc * finalq
            };
          });
          g.$block = me.render_item_block(meta, rowsRM, i);
          await me.bulk_update_availability_group(i);
          me.update_group_summary(i);
        } else {
          g.$block = null
        }    
      });
    }

    // ===== RM SUMMARY =====
    render_rm_summary(rows, idx) {
      console.log("ROWS Render RM SUMMARY", rows)
      const defaultWh = this.fg ? this.fg.get_value('source_warehouse') : "-";
      const me = this;
      const prev = this.groups[idx] || {};

      const aggregatedRM = aggregateRawMaterials(rows, defaultWh);
      console.log("=== render_rm_summary ===");
      console.log("aggregatedRM", aggregatedRM);

      if (prev.meta && Array.isArray(prev.meta.rm_items)) {
        aggregatedRM.forEach(r => {
          const match = prev.meta.rm_items.find(x => x.item_code === r.item_code);
          r.act_qty = match ? parseFloat(match.act_qty || 0) : 0;
          r.diff_qty = r.act_qty - (parseFloat(r.total_required_qty) || 0);
          r.total_cost = r.act_qty * (parseFloat(r.unit_cost) || 0);
        });
      } else {
        aggregatedRM.forEach(r => {
          r.act_qty = r.act_qty || 0;
          r.diff_qty = r.act_qty - (parseFloat(r.total_required_qty) || 0);
          r.total_cost = r.act_qty * (parseFloat(r.unit_cost) || 0);
        });
      }

      this.groups[idx] = {
        ...prev,
        original_rows: aggregatedRM,
        rows: aggregatedRM,  
        $block: null,
        meta: {
          ...(prev.meta || {}),
          rm_items: aggregatedRM.map(r => ({
            item_code: r.item_code,
            item_name: r.item_name,
            uom: r.stock_uom,
            required_qty: r.total_required_qty,
            unit_cost: r.unit_cost,
            act_qty: r.act_qty || 0
          }))
        }
      };

      const summaryRemain = {};
      aggregatedRM.forEach(r => {
        summaryRemain[r.item_code] = parseFloat(r.act_qty || 0);
      });
      this.summaryRemain = summaryRemain;

      const $block = $(`
        <div data-idx="${idx}">
          <div class="sut-rm-toolbar">
            <div><b>Summary Raw Material Items</b></div>
            <div style="display:flex; align-items:center; gap:4px;">
              <button class="btn btn-default btn-sm" data-action="recalc">Recalculate</button>
            </div>
          </div>
          <table class="sut-table" id="sut-dt-${idx}" border="1">
            <thead>
              <tr>
                <th style="text-align:center;">Code</th>
                <th style="text-align:center;">Name</th>
                <th style="text-align:right;">Req Qty</th>
                <th style="text-align:right;">Act Qty</th>
                <th style="text-align:right;">Diff Qty</th>
                <th style="text-align:center;">UOM</th>
                <th style="text-align:right;">Avail</th>
                <th style="text-align:center;">WH</th>
                <th style="text-align:right;">Unit Cost</th>
                <th style="text-align:right;">Cost</th>
                <th style="text-align:center;"><input type="checkbox" class="check-all"></th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
          <div class="sut-summary">
            <div>Lines: <b id="sut-lines-${idx}">0</b></div>
            <div>
              Total Required Qty: <b id="sut-total-qty-${idx}">0</b> &nbsp; | &nbsp;
              Total RM Cost: <b id="sut-total-cost-${idx}">0</b>
            </div>
          </div>
        </div>
      `);

      this.$body.find(".sut-item-block").hide();
      this.$body.find("#sut-rm-summary").empty().append($block);
      $block.show();

      this.groups[idx].$block = $block;

      console.log('this.groups[idx]', this.groups[idx])

      const renderTable = () => {
        const $tbody = $block.find("tbody");
        $tbody.empty();
        this.groups[idx].rows.forEach((row, r) => {
          if (!row.item_code) return; 
          console.log("rows", row)
          $tbody.append(`
            <tr data-row="${r}">
              <td style="text-align:center;">${row.item_code || ""}</td>
              <td style="text-align:center;">${row.item_name || ""}</td>
              <td style="text-align:right;">${row.total_required_qty || 0}</td>
              <td class="td-input">
                <input
                  type="text"
                  class="td-input"
                  value="${row.act_qty || 0}"
                  data-col="act_qty"
                  oninput="this.value = this.value.replace(/[^0-9.]/g, '')"
                  style="
                    width:100%;
                    font-size:inherit;
                    font-family:inherit;
                    text-align:right;
                    border: 1px solid #ccc; 
                    padding: 2px 4px; 
                    border-radius: 4px;
                  "
                />
              </td>

              <td style="text-align:right;">${row.diff_qty || 0}</td>
              <td style="text-align:center;">${row.stock_uom || row.uom || ""}</td>
              <td style="text-align:right;">${row.actual_qty || 0}</td>
              <td style="text-align:center;">${defaultWh || ""}</td>
              <td style="text-align:right;">${fmtCurrency(row.unit_cost || 0)}</td>
              <td style="text-align:right;">${fmtCurrency(row.total_cost || 0)}</td>
              <td style="text-align:center;"><input type="checkbox" class="check-row"></td>
            </tr>
          `);
        });

        $block.find(`#sut-lines-${idx}`).text(this.groups[idx].rows.length);
        const total = this.groups[idx]?.rows?.reduce((sum, row) => {
          const qty = Number(row.total_required_qty) || 0;
          return sum + qty;
        }, 0) || 0;
        const totalCost = this.groups[idx]?.rows?.reduce((sum, r) => sum + (parseFloat(r.total_cost) || 0), 0);

        const group = this.groups[idx];
        const $grpBlock = group.$block;

        $grpBlock.off("input blur", "input[data-col]"); 

        $grpBlock.on("input blur", "input[data-col]", function () {
          const $input = $(this);
          const rowIndex = parseInt($input.closest("tr").data("row"));
          const val = parseFloat($input.val()) || 0;

          const group = me.groups[idx];

          const aggRow = group.rows[rowIndex];
          if (aggRow) {
            aggRow.act_qty = val;
            aggRow.diff_qty = val - (parseFloat(aggRow.total_required_qty) || 0);
            aggRow.total_cost = val * (parseFloat(aggRow.unit_cost) || 0);
          }

          if (!group.meta) group.meta = {};
          if (!group.meta.rm_items) group.meta.rm_items = [];
          group.meta.rm_items[rowIndex] = {
            ...group.meta.rm_items[rowIndex],
            act_qty: val
          };

          me.summaryRemain[aggRow.item_code] = group.rows.map(r => ({
            row_id: r.item_code,  
            act_qty: parseFloat(r.act_qty) || 0
          }));

          me.groups.forEach(g => {
            if (g && g.$block) {
              g.$block.hide();
              g.$block = null;
            }
          });

          $input.closest("tr").find("td:eq(4)").text(aggRow.diff_qty);
          $input.closest("tr").find("td:eq(9)").text(fmtCurrency(aggRow.total_cost));

          const updatedTotalCost = group.rows.reduce((sum, r) => sum + (parseFloat(r.total_cost) || 0), 0);
          $block.find(`#sut-total-cost-${idx}`).text('Rp ' + updatedTotalCost.toLocaleString('id-ID'));
        });

        $block.find(`#sut-total-qty-${idx}`).text(total); 
        $block.find(`#sut-total-cost-${idx}`).text(totalCost);

      };
      renderTable();
    }

    // ===== LOAD =====
    async load_from_pos() {
      const pos_closing_entry = this.fg.get_value('pos_closing_entry');
      const company = this.fg.get_value('company');
      const wh = this.fg.get_value('source_warehouse');
      if (!pos_closing_entry || !company || !wh) {
        frappe.msgprint(__('Please fill POS Closing Entry, Company, and Source Warehouse.'));
        return;
      }

      frappe.dom.freeze(__('Loading...'));
      try {
        const r = await frappe.call({
          method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.get_pos_breakdown',
          args: { pos_closing_entry, company, warehouse: this.fg.get_value("source_warehouse") }
        });
        const items = (r.message?.items) || [];

        // Reset containers
        this.groups = [];
        this.$body.find('#sut-groups').empty();

        // Keep meta by index for later expansion; do not render RM tables yet
        for (let i = 0; i < items.length; i++) {
          this.groups[i] = { meta: items[i] };
        }

        // Render single FG table with expand arrows
        this.render_fg_table(items);
        this.render_rm_summary(items)

        frappe.show_alert({ message: __('Loaded'), indicator: 'green' });
      } catch (e) {
        console.error(e);
        const msg = (e && (e.message || e._server_messages)) ? (e.message || e._server_messages) : e;
        frappe.msgprint({ title: 'Error', message: String(msg), indicator: 'red' });
      } finally {
        frappe.dom.unfreeze();
      }
    }

    // ===== RENDER 1 ITEM =====
    render_item_block(meta, rows, idx) {
      const me = this; 
      const defaultWh = this.fg ? this.fg.get_value('source_warehouse') : "-";

      rows = rows || [];
      const allRM = this.groups
        .filter(g => g && g.meta && Array.isArray(g.meta.rm_items))
        .map(g => g.meta.rm_items)
        .flat();

      rows.forEach((r, i) => {
        const planned = parseFloat(r.req_qty || 0);
        const arr = me.summaryRemain[r.code] || [];
        const match = arr.find(x => x.row_id === r.code || x.idx === i);
        const totalAct = match ? match.act_qty : 0;
        const totalPlanned = allRM
            .filter(x => x.item_code === r.code)
            .reduce((sum, x) => sum + (parseFloat(x.required_qty) || 0), 0);

        r.act_qty = totalPlanned > 0 ? (planned / totalPlanned) * totalAct : 0;
        r.diff_qty = r.act_qty - planned;
        r.cost = r.act_qty * (parseFloat(r.unit_cost) || 0);
      });

      const $block = $(`
        <div class="sut-item-block" data-idx="${idx}">
          <div class="sut-rm-toolbar">
            <div>Raw Material <b>${meta.item_name}</b></div>
            <div style="display:flex; align-items:center; gap:4px;">
              <button class="btn btn-default btn-sm" data-action="recalc">Recalculate</button>
              <button class="btn btn-default btn-sm" data-action="add">Add</button>
              <button class="btn btn-default btn-sm" data-action="remove">Remove</button>
            </div>
          </div>
          <div style="overflow-x:auto; width:100%;">
            <table class="sut-table" border="1">
              <thead>
                <tr>
                  <th style="text-align:center;">Code</th>
                  <th style="text-align:center;">Name</th>
                  <th style="text-align:right;">Req Qty</th>
                  <th style="text-align:right;">Act Qty</th>
                  <th style="text-align:right;">Diff Qty</th>
                  <th style="text-align:center;">UOM</th>
                  <th style="text-align:right;">Avail</th>
                  <th style="text-align:center;">WH</th>
                  <th style="text-align:center;">Remarks</th>
                  <th style="text-align:right;">Unit Cost</th>
                  <th style="text-align:right;">Cost</th>
                  <th style="text-align:center;"><input type="checkbox" class="check-all"></th>
                </tr>
              </thead>
              <tbody></tbody>
            </table>
          </div>
          <div class="sut-summary">
            <div>Lines: <b id="sut-rm-lines-${idx}">0</b></div>
            <div>
              Total Required Qty: <b id="sut-total-rm-qty-${idx}">0</b> &nbsp; | &nbsp;
              Total RM Cost: <b id="sut-total-rm-cost-${idx}">0</b>
            </div>
          </div>
        </div>
      `);

      this.$body.find(".sut-item-block").hide();
      this.$body.find("#sut-groups").append($block);
      $block.show();

      this.groups[idx] = { meta, rows, $block };
      const group = this.groups[idx];

      const renderTable = () => {
        const $tbody = $block.find("tbody");
        $tbody.empty();

        group.rows.forEach((row, rIdx) => {
          const $tr = $('<tr>').attr('data-row', rIdx);

          // ===== Code (Link Field ke Item) =====
          const $tdCode = $('<td style="text-align:center;"></td>');
          const code_control = frappe.ui.form.make_control({
              parent: $tdCode[0],
              df: {
                  fieldtype: 'Link',
                  options: 'Item',
                  in_place_edit: true,
              },
              render_input: true,
          });

          $(code_control.wrapper).addClass("sut-table-input"); 
          $(code_control.wrapper).find('input')
            .removeClass("form-control input-sm")   
            .addClass("td-input")
            .css({
              'text-align': 'left',
              'border': '1px solid #ccc',
              'padding': '2px 4px',
              'border-radius': '4px'
            });

          if (row.code) {
            code_control.set_value(row.code);
          }

          code_control.$input.on('change', async function () {
            const val = $(this).val();
            row.code = val;

            if (val) {
              const item = await frappe.db.get_doc('Item', val);
              // update langsung row
              row.name = item.item_name;
              row.uom = item.stock_uom;
              row.unit_cost = parseFloat(item.valuation_rate || 0);
              row.cost = row.unit_cost * row.act_qty;

              const rm_item_obj = group.meta.rm_items[rIdx];
              if (rm_item_obj) {
                rm_item_obj.item_name = item.item_name;
                rm_item_obj.uom = item.stock_uom;
                rm_item_obj.unit_cost = parseFloat(item.valuation_rate || 0);
              }
              renderTable(); 
            }
          });

          $tr.append($tdCode);

          // ===== Name =====
          const $tdName = $(`<td class="td-left">
            <span>${row.name || ''}</span>
          </td>`);
          $tr.append($tdName);

          // ===== Req Qty =====
          const $tdReq = $(`<td style="text-align:right;">
            <input 
              type="text" 
              class="td-input" 
              style="border: 1px solid #ccc; padding: 2px 4px; border-radius: 4px;"
              oninput="this.value = this.value.replace(/[^0-9.]/g, '')"
              value="${row.req_qty.toFixed(2)}" 
            />
          </td>`);
          $tdReq.find('input').on('input', function () {
            row.req_qty = parseFloat($(this).val()) || 0;
            row.diff_qty = row.act_qty - row.req_qty;
            row.cost = row.act_qty * row.unit_cost;
            renderTable();
          });
          $tr.append($tdReq);

          // ===== Act Qty =====
          const $tdAct = $(`<td style="text-align:right;">
            <input 
              type="text" 
              class="td-input" 
              style="border: 1px solid #ccc; padding: 2px 4px; border-radius: 4px;"
              oninput="this.value = this.value.replace(/[^0-9.]/g, '')"
              value="${row.act_qty.toFixed(2)}" 
            />
          </td>`);
          $tdAct.find('input').on('input', function () {
            row.act_qty = parseFloat($(this).val()) || 0;
            row.diff_qty = row.act_qty - row.req_qty;
            row.cost = row.act_qty * row.unit_cost;
            renderTable();
          });
          $tr.append($tdAct);

          // ===== Diff Qty =====
          $tr.append(`<td style="text-align:right;">${row.diff_qty.toFixed(2)}</td>`);

          // ===== UOM =====
          const $tdUOM = $(`<td style="text-align:center;">
            <span>${row.uom || ''}</span>
          </td>`);
          $tr.append($tdUOM);

          // ===== Avail =====
          const $tdAvail = $(`<td style="text-align:right;">
            <span>${row.actual_qty || 0}</span>
          </td>`);
          $tr.append($tdAvail);

          // ===== WH =====
          const $tdWH = $(`<td style="text-align:center;">
            <span>${row.wh || ''} </span>
          </td>`);
          $tr.append($tdWH);

          // ===== Remarks =====
          const $tdRemarks = $(`<td style="text-align:center;">
            <input 
              type="text" 
              class="td-input" 
              style="text-align:left; border: 1px solid #ccc; padding: 2px 4px; border-radius: 4px;" 
              value="${row.remarks || ''}" 
            />
          </td>`);
          $tdRemarks.find('input').on('input', function () { row.remarks = $(this).val(); });
          $tr.append($tdRemarks);

          const $tdCost = $(`
            <td style="text-align:right;">
              <span>${fmtCurrency(row.unit_cost || 0)}</span>
            </td>
          `);
          $tr.append($tdCost);


          // ===== Cost =====
          $tr.append(`<td style="text-align:right;">${fmtCurrency(row.cost)}</td>`);

          // ===== Checkbox =====
          $tr.append('<td style="text-align:center;"><input type="checkbox" class="check-row"></td>');

          $tbody.append($tr);
      });


        $block.find(`#sut-rm-lines-${idx}`).text(group.rows.length);
        $block.find(`#sut-total-rm-qty-${idx}`).text(
          group.rows.reduce((a,b) => a + (parseFloat(b.req_qty)||0), 0)
        );
        $block.find(`#sut-total-rm-cost-${idx}`).text(
          'Rp ' + group.rows.reduce((a,b) => a + (parseFloat(b.cost)||0), 0).toLocaleString('id-ID')
        );
      };

      $block.on("click", "[data-action]", (e) => {
        const action = $(e.currentTarget).data("action");
        const group = me.groups[idx];

        if (action === "add") {
          const wh = this.fg.get_value("source_warehouse") || "";

          group.rows.push({
              code: "", name: "", req_qty: 1, act_qty: 0, diff_qty: 1,
              uom: "", actual_qty: 0, wh, remarks: "", unit_cost: 0, cost: 0
          });

          group.meta.rm_items.push({
              item_code: "",
              item_name: "",
              required_qty: 1,
              act_qty: 0,
              uom: "",
              actual_qty: 0,
              wh,
              remarks: "",
              unit_cost: 0,
              cost: 0
          });

          renderTable();
        } else if (action === "remove") {
          const $checked = $block.find(".check-row:checked");
          const toRemove = $checked.closest("tr").map((_, el) => parseInt($(el).data("row"))).get();
          group.rows = group.rows.filter((_, rIdx) => !toRemove.includes(rIdx));
          group.meta.rm_items = group.meta.rm_items.filter((_, rIdx) => !toRemove.includes(rIdx))
          renderTable();
        } else if (action === "recalc") {
          group.rows.forEach(r => {
            r.diff_qty = r.act_qty - r.req_qty;
            r.cost = r.act_qty * r.unit_cost;
          });
          renderTable();
        } 
        // else if (action === "save") {
        //   group.rows.forEach(r => {
        //     if (!r.code) return; 

        //     let exist = group.meta.rm_items.find(x => x.item_code === r.code);
        //     if (exist) {
        //         exist.item_name = r.name || "";
        //         exist.uom = r.uom || "";
        //         exist.required_qty = r.req_qty || 0;
        //         exist.act_qty = r.act_qty || 0;
        //         exist.unit_cost = r.unit_cost || 0;
        //         exist.total_cost = r.cost || 0;
        //         exist.remarks = r.remarks || "";
        //         exist.wh = r.wh || "";
        //     } else {
        //         group.meta.rm_items.push({
        //             item_code: r.code,
        //             item_name: r.name || "",
        //             uom: r.uom || "",
        //             required_qty: r.req_qty || 0,
        //             act_qty: r.act_qty || 0,
        //             unit_cost: r.unit_cost || 0,
        //             total_cost: r.cost || 0,
        //             remarks: r.remarks || "",
        //             wh: r.wh || ""
        //         });
        //     }
        //   });

        //   this.summaryRemain = {};
        //   group.meta.rm_items.forEach(r => {
        //     this.summaryRemain[r.item_code] = r.act_qty;
        //   });

        //   // 🔴 jangan lempar group.meta.rm_items
        //   // this.render_rm_summary(group.meta.rm_items, idx);

        //   // ✅ lempar semua rm_items dari seluruh groups
        //   const allRM = this.groups
        //     .filter(g => g.meta && Array.isArray(g.meta.rm_items))
        //     .map(g => g.meta.rm_items)
        //     .flat();

        //   this.render_rm_summary(allRM);
        //   console.log("Render rm Items", allRM)
        //   frappe.msgprint("Raw Material changes saved!");
        // }

      });

      renderTable();
    }

    update_group_summary(idx) {
      const dt = this.groups[idx]?.dt;
      const n = dtRowCount(dt);
      let total_qty = 0, total_cost = 0;
      const COL = getColMap(dt);
      for (let i = 0; i < n; i++) {
        total_qty += flt(getCellTxt(dt, i, COL.diff_qty, 0));
        total_cost += flt(getCellTxt(dt, i, COL.cost, 0));
      }
      this.$body.find(`#sut-lines-${idx}`).text(n);
      this.$body.find(`#sut-total-qty-${idx}`).text(fmtFloat(total_qty, 2));
      this.$body.find(`#sut-total-cost-${idx}`).text(fmtCurrency(total_cost));
      // refresh FG totals summary
      this.render_fg_summary();
      // also update FG table row visuals if present
      if (this.fgDT) {
        const meta = this.groups[idx]?.meta || {};
        const c = this.get_fg_cost(idx);
        const row = [
          `<span class="sut-exp" data-row="${idx}" style="cursor:pointer;user-select:none;">&#9660;</span>`,
          frappe.utils.escape_html(meta.item_code || ''),
          frappe.utils.escape_html(meta.item_name || ''),
          meta.qty || 0,
          frappe.utils.escape_html(meta.stock_uom || ''),
          fmtCurrency(meta.selling_rate),
          fmtCurrency(meta.selling_amount),
          fmtCurrency(c.unit_cost),
          fmtCurrency(c.total_cost),
          fmtCurrency(c.margin_val),
          fmtFloat(c.margin_pct, 1) + '%',
        ];
        this.fgDT.updateRow?.(idx, row);
      }
      // refresh TOTAL row at bottom
      this.update_fg_total_row();
      // (RM in-table total row removed)
    }

    update_all_cost_summary() {
      for (let i = 0; i < this.groups.length; i++) this.update_group_summary(i);
    }

    // ===== RECALC =====
    async recalc_group(idx) {
      const g = this.groups[idx];
      const pce = this.fg.get_value('pos_closing_entry');
      const company = this.fg.get_value('company');
      if (!pce || !company) return;

      const r = await frappe.call({
        method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.get_pos_breakdown',
        args: { pos_closing_entry: pce, company, warehouse: this.fg.get_value("source_warehouse") }
      });
      const found = (r.message.items || []).find(x => x.item_code === g.meta.item_code);
      if (!found) {
        // Still recalculate cost for current rows before updating summary
        // Recompute Cost from current Final Qty × Unit Cost
        const dt = g.dt;
        const COL = getColMap(dt);
        const n = dtRowCount(dt);
        for (let i = 0; i < n; i++) {
          const qty = flt(getCellTxt(dt, i, COL.diff_qty, 0));
          const uc  = flt(getCellTxt(dt, i, COL.unit_cost, 0));
          dt.updateCell?.(i, COL.cost, qty * uc);
        }
        this.update_group_summary(idx);
        return;
      }

      // Keep current DT rows intact; only recompute Cost based on edited Final Qty × Unit Cost
      const COL = getColMap(g.dt);
      const n = dtRowCount(g.dt);
      for (let i = 0; i < n; i++) {
        const qty = flt(getCellTxt(g.dt, i, COL.diff_qty, 0));
        const uc  = flt(getCellTxt(g.dt, i, COL.unit_cost, 0));
        console.log(`Recalculating Cost for row ${i}: Qty=${qty}, Unit Cost=${uc}`);
        g.dt.updateCell?.(i, COL.cost, qty * uc);
      }
      await this.bulk_update_availability_group(idx);
      this.update_group_summary(idx);
      // refresh FG totals summary
      this.render_fg_summary();

      // refresh meta numbers (header removed)
      g.meta.selling_rate = flt(found.selling_rate);
      g.meta.selling_amount = flt(found.selling_amount);

      // also update FG table row visuals if present
      if (this.fgDT) {
        const meta2 = this.groups[idx].meta;
        const c = this.get_fg_cost(idx);
        const row = [
          `<span class="sut-exp" data-row="${idx}" style="cursor:pointer;user-select:none;">&#9660;</span>`,
          frappe.utils.escape_html(meta2.item_code || ''),
          frappe.utils.escape_html(meta2.item_name || ''),
          meta2.qty || 0,
          frappe.utils.escape_html(meta2.stock_uom || ''),
          fmtCurrency(meta2.selling_rate),
          fmtCurrency(meta2.selling_amount),
          fmtCurrency(c.unit_cost),
          fmtCurrency(c.total_cost),
          fmtCurrency(c.margin_val),
          fmtFloat(c.margin_pct, 1) + '%',
        ];
        this.fgDT.updateRow?.(idx, row);
      }
      // refresh TOTAL row at bottom
      this.update_fg_total_row();
    }

    async recalc_all() { 
      for (let i = 0; i < this.groups.length; i++) await this.recalc_group(i);

      // Refresh FG summary table after recalculation
      const items = this.groups.map(g => g.meta || {}); // <- fallback ke objek kosong
      this.render_fg_table(items);
      this.render_rm_summary(items);
      this.update_fg_total_row();
    }

    clear_all() { 
      const me = this;
      me.groups.forEach(g => {
        if (g && g.$block) {
          g.$block.hide();
          g.$block = null;
        }
      });
    }

    // ===== Availability =====
    async bulk_update_availability_group(idx) {
      const g = this.groups[idx]; if (!g) return;
      const dt = g.dt;
      const wh_fallback = cellToText(this.fg.get_value('source_warehouse'));
      const n = dtRowCount(dt);
      const payload = [];
      const COL = getColMap(dt);

      for (let i = 0; i < n; i++){
        const it = getCellTxt(dt, i, COL.code, '');
        const wh = getCellTxt(dt, i, COL.wh, '') || wh_fallback;
        if (it && wh) payload.push({ item_code: it, warehouse: wh });
      }
      if (!payload.length) return;
      console.log(`Bulk updating availability for ${payload.length} items in group ${idx}`);
      const res = await frappe.call({
        method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.get_availability_bulk',
        args: { rows: payload }
      });
      const map = res.message || {};
      for (let i = 0; i < n; i++){
        const it = getCellTxt(dt, i, COL.code, '');
        const wh = getCellTxt(dt, i, COL.wh, '') || wh_fallback;
        const key = `${it}::${wh}`;
        const qty = (map[key] ?? 0);
        dt.updateCell?.(i, COL.actual_qty, qty);
      }
    }

    async bulk_update_availability_all() {
      for (let i = 0; i < this.groups.length; i++) await this.bulk_update_availability_group(i);
    }

    syncInputsToGroups() {
      this.groups.forEach((g, idx) => {
        if (!g || !g.$block) return;
        g.$block.find('tbody tr').each((rIdx, tr) => {
          const val = parseFloat($(tr).find('input[data-col="act_qty"]').val()) || 0;
          if (g.rows[rIdx]) {
            g.rows[rIdx].act_qty = val;
            g.rows[rIdx].diff_qty = val - (parseFloat(g.rows[rIdx].total_required_qty) || 0);
            g.rows[rIdx].total_cost = val * (parseFloat(g.rows[rIdx].unit_cost) || 0);
          }
          if (g.meta && g.meta.rm_items && g.meta.rm_items[rIdx]) {
            g.meta.rm_items[rIdx].act_qty = val;
          }
        });
      });
    }

    // ===== Submit =====
    // ===== GET PAYLOAD =====
    get_payload() {
      const rm_breakdown_map = new Map();
      const menu_summaries = [];

      this.groups.forEach(g => {
        if (!g) return;
        const rm_items = g.meta.rm_items || [];
        rm_items.forEach((r, i) => {
          const tableRow = g.rows[i];
          if (tableRow) {
            r.item_code = tableRow.code || '';
            r.item_name = tableRow.name || '';
            r.required_qty = parseFloat(tableRow.req_qty || 0);
            r.act_qty = parseFloat(tableRow.act_qty || 0);
            r.actual_qty = parseFloat(tableRow.actual_qty || 0);
            r.uom = tableRow.uom || '';
            r.wh = tableRow.wh || '';
            r.unit_cost = parseFloat(tableRow.unit_cost || 0);
            r.cost = parseFloat(tableRow.cost || 0);
            r.remarks = tableRow.remarks || '';
          }
        });
      });

      for (const g of this.groups) {
        if (!g) continue;

        const meta = g.meta || {};
        const rm_items = Array.isArray(meta.rm_items) ? meta.rm_items : [];
        const rows_detail = [];
        let rm_value_total = 0;

        rm_items.forEach((r, i) => {
          const rm_item = r.item_code;
          console.log("ROW PAYLOAD ", r)
          if (!rm_item) return;

          const arr = this.summaryRemain[rm_item] || [];
          const totalAct = arr[i]?.act_qty || 0;  
          const act = parseFloat((parseFloat(r.act_qty || 0)).toFixed(2));  
          const planned = parseFloat((parseFloat(r.required_qty || 0)).toFixed(2));
          const diffq = parseFloat((act - planned).toFixed(2));
          const uc = parseFloat(r.unit_cost || 0);
          const uom = r.uom || r.stock_uom || '';
          const cost = act * uc;
          rm_value_total += cost;

          const key = rm_item;
          const ex = rm_breakdown_map.get(key) || {
            rm_item,
            planned_qty: 0,
            uom,
            actual_qty: totalAct,
            diff_qty: 0,
            valuation_rate_snapshot: uc
          };
          ex.planned_qty += planned;
          ex.diff_qty += diffq;
          if (!ex.valuation_rate_snapshot) ex.valuation_rate_snapshot = uc;
          rm_breakdown_map.set(key, ex);

          rows_detail.push({
            rm_item,
            name: r.item_name || '',
            planned,
            act,
            diffq,
            uom,
            uc,
            cost,
            avail: r.actual_qty,
            remarks: r.remarks,
            wh: r.wh
          });
        });

        // Summary menu
        const menuName = meta.resto_menu || meta.item_name || meta.item_code;
        const category = meta.category || "Uncategorized";
        const sellItem = meta.sell_item || meta.item_name || meta.item_code;

        menu_summaries.push({
          menu: menuName,
          category,
          sell_item: sellItem,
          qty_sold: parseFloat(meta.qty || 0),
          sales_amount: parseFloat(meta.selling_amount || 0),
          rm_value_total,
          margin_amount: parseFloat(meta.selling_amount || 0) - rm_value_total,
          raw_material_breakdown: rows_detail
        });
      }

      const rm_breakdown = Array.from(rm_breakdown_map.values());

      console.log("Menu Summaries", menu_summaries);
      console.log("RM Breakdown", rm_breakdown);

      return { menu_summaries, rm_breakdown };
    }

    async save_pos_consumption() {
      const pos_closing_entry = this.fg.get_value('pos_closing_entry');

      console.log("POS Closing Entry", pos_closing_entry)
      const warehouse = this.fg.get_value('source_warehouse');
      const company = this.fg.get_value('company');

      if (!pos_closing_entry || !warehouse) {
        frappe.msgprint(__('Please fill POS Closing Entry, Company, and Source Warehouse.'));
        return;
      }
      if (!this.groups.length) {
        frappe.msgprint(__('No data to save. Please load from POS Closing Entry first.'));
        return;
      }
      const { menu_summaries, rm_breakdown } = this.get_payload();

      console.log("=== FULL RM BREAKDOWN PAYLOAD ===");
      console.log(JSON.stringify(rm_breakdown, null, 2));

      console.log("=== FULL MENU SUMMARIES PAYLOAD ===");
      console.log(JSON.stringify(menu_summaries, null, 2));

      try {
        const _all = (rm_breakdown || []).map(r => String(r.rm_item||'').trim()).filter(Boolean);
        console.log('RM uniq items before validation:', Array.from(new Set(_all)));
      } catch (e) {}
      const rmItemsAll = (rm_breakdown || [])
        .map(r => String(r.rm_item || '').trim())
        .filter(Boolean);
      const uniqItems = Array.from(new Set(rmItemsAll));
      if (uniqItems.length) {
        try {
          const chk = await frappe.call({
            method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.get_unit_cost_bulk',
            args: { item_codes: uniqItems }
          });
          const known = chk?.message || {};
          const bad = (rm_breakdown || []).filter(r => {
            const code = String(r.rm_item || '').trim();
            return code && !(code in known);
          });
          if (bad.length) {
            const html = ['<div style="max-height:260px;overflow:auto"><ol>']
              .concat(bad.slice(0, 10).map(b => `<li><b>${frappe.utils.escape_html(String(b.rm_item))}</b> (UOM: ${frappe.utils.escape_html(String(b.uom||''))})</li>`))
              .concat(['</ol>', bad.length > 10 ? `<div>...and ${bad.length-10} more</div>` : '', '</div>'])
              .join('');
            frappe.msgprint({
              title: __('Some RM rows have invalid Item Code (not found). Please fix Item Code cells in RM table.'),
              message: html,
              indicator: 'red'
            });
            return;
          }
        } catch (err) {
          // If validation fails for any reason, do not block saving; just log it
          console.warn('RM item existence check failed:', err);
        }
      }
      if (!menu_summaries.length) {
        frappe.msgprint(__('Nothing to save. Make sure items are loaded.'));
        return;
      }
      if (!rm_breakdown.length) {
        frappe.show_alert({ message: __('Warning: RM breakdown is empty. Saving menu summary only.'), indicator: 'orange' });
      }
      try {
        // Log a sample of the RM and menu summaries payload
        console.log('Sending to create_pos_consumption. RM sample:', (rm_breakdown||[]).slice(0,20));
        console.log('Menu summaries sample:', (menu_summaries||[]).slice(0,5));
      } catch (err) {}
      frappe.dom.freeze(__('Saving POS Consumption...'));
      try {
        const resp = await frappe.call({
          method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.create_pos_consumption',
          args: { pos_closing: pos_closing_entry, company: company,warehouse: warehouse, notes: '', menu_summaries, rm_breakdown }
        });
        const name = resp.message;
        frappe.msgprint({
          title: __('Saved'),
          message: __('POS Consumption {0} has been created.', [`<a href="/app/pos-consumption/${name}" target="_blank">${name}</a>`]),
          indicator: 'green'
        });
        frappe.set_route('Form', 'POS Consumption', name);
      } catch (e) {
        console.error(e);
        const msg = (e && (e.message || e._server_messages)) ? (e.message || e._server_messages) : e;
        frappe.msgprint({ title: 'Error', message: String(msg), indicator: 'red' });
      } finally {
        frappe.dom.unfreeze();
      }
    }
  };

  frappe.pages['stock-usage-tool'].on_page_load = function (wrapper) {
    resto.stock_usage.page = new resto.stock_usage.Page(wrapper);
  };
})();