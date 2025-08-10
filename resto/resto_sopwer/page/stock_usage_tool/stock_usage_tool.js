// Stock Usage Tool - Excel-like per-item RM + Selling/Cost + BOM Tree
frappe.provide("resto.stock_usage");

(function () {
  // ===== Helpers =====
  // Column label mapping to avoid magic strings
  const COL_N = {
    code: 'Item Code',
    name: 'Item Name',
    req_qty: 'Req Qty',
    uom: 'Stock UOM',
    avail: 'Available (WH)',
    wh: 'Warehouse',
    remarks: 'Remarks',
    unit_cost: 'Unit Cost',
    cost: 'Cost',
  };
  // Map visible column indexes by conventional names for a datatable
  function getColMap(dt){
    return {
      code: dtColIndexByName(dt, COL_N.code),
      name: dtColIndexByName(dt, COL_N.name),
      req_qty: dtColIndexByName(dt, COL_N.req_qty),
      uom: dtColIndexByName(dt, COL_N.uom),
      avail: dtColIndexByName(dt, COL_N.avail),
      wh: dtColIndexByName(dt, COL_N.wh),
      remarks: dtColIndexByName(dt, COL_N.remarks),
      unit_cost: dtColIndexByName(dt, COL_N.unit_cost),
      cost: dtColIndexByName(dt, COL_N.cost),
    };
  }

  // Safe getter for cell text value
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

  // --- Datatable utils ---
  function dtRowCount(dt){ return (dt&&dt.datamanager&&typeof dt.datamanager.getRowCount==='function')?dt.datamanager.getRowCount():0; }
  function dtColCount(dt){ return (dt&&typeof dt.getColumns==='function')?dt.getColumns().length:0; }

  // Find visible column index by header name (works even with serial/checkbox columns enabled)
  function dtColIndexByName(dt, name){
    const cols = dt && typeof dt.getColumns === 'function' ? dt.getColumns() : [];
    for (let i = 0; i < cols.length; i++) {
      if ((cols[i] && cols[i].name) === name) return i;
    }
    return -1;
  }

  // Strip tags quickly
  function stripTags(s){
    if (typeof s !== "string") return s;
    return s.replace(/<[^>]*>/g, "");
  }

  // Convert various datatable cell shapes → plain text
  function cellToText(v){
    if (v == null) return "";
    if (typeof v === "object") {
      const html = v.html ?? v.content ?? "";
      return stripTags(String(html)).trim();
    }
    return stripTags(String(v)).trim();
  }

  // Safe accessor using datatable.getCell, normalized to text
  function safeGetCell(dt, r, c, fallback = "") {
    try {
      if (!dt || r == null || c == null) return fallback;
      const raw = dt.getCell?.(r, c);
      const val = cellToText(raw);
      return (val === undefined || val === null) ? fallback : val;
    } catch (e) {
      return fallback;
    }
  }

  function dtToArray(dt){
    const rows = dtRowCount(dt), cols = dtColCount(dt), out = [];
    for (let i = 0; i < rows; i++) {
      const row = [];
      for (let j = 0; j < cols; j++) {
        row.push(safeGetCell(dt, i, j, ""));
      }
      out.push(row);
    }
    return out;
  }


  const STYLES = `
    <style id="sut-inline-style">
      .sut-wrap{padding:16px;}
      .sut-item-block{border:1px solid var(--border-color); border-radius:6px; margin-bottom:10px; overflow:hidden; background:#fff;}
      .sut-item-head{display:grid; grid-template-columns: 160px 1fr 100px 100px 120px 140px; gap:0; background:#fafafa; border-bottom:1px solid var(--border-color);}
      .sut-item-head > div{padding:8px 10px; border-right:1px solid var(--border-color);}
      .sut-item-head > div:last-child{border-right:none;}
      .sut-head-title{font-weight:600; background:#f0f0f0;}
      .sut-val{background:#fff;}
      .sut-rm-toolbar{display:flex; gap:6px; align-items:center; justify-content:flex-end; padding:6px 8px; border-top:1px dashed var(--border-color); background:#fff;}
      .sut-summary{display:flex; justify-content:space-between; padding:6px 8px; font-size:12px; color:#666; border-top:1px dashed var(--border-color);}
      .sut-global-actions{display:flex; gap:8px; justify-content:flex-end; padding:10px; border:1px solid var(--border-color); border-radius:6px; background:#fff; margin:12px 0;}

      .sut-fg-summary{margin-top:6px;}
      #sut-fg-summary .datatable{font-size:12px;}
      #sut-fg-summary .dt-cell{font-weight:600;}
      #sut-fg-summary .dt-header{display:none;}
      #sut-fg .sut-total-cell{ display:block; width:100%; padding:4px 6px; border-radius:0; font-weight:600; }
      #sut-fg .sut-total-label{ display:block; width:100%; padding:4px 6px; font-weight:600; }
      .sut-fg-summary{ display:none; } /* hide old separate summary block */

      /* compact filter card */
      #filters.frappe-card{padding:12px !important;}
      .sut-compact .frappe-control{margin-bottom:6px;}
      .sut-compact .form-section .section-body{padding-top:4px; padding-bottom:4px;}
      @media (max-width: 980px){
        .sut-item-head{grid-template-columns: 140px 1fr 90px 90px 110px 120px;}
      }
    </style>
      // Remove any leftover background color for total row cells
      // (No such line as "#sut-fg .sut-total-row .dt-cell{ background:#fff0a6 !important; }" remains)
  `;

  resto.stock_usage.Page = class {
    constructor(wrapper) {
      this.wrapper = $(wrapper);
      this.groups = []; // [{meta, dt, $block}]
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
            <button class="btn btn-primary btn-sm" id="submit-se">Submit & Generate Stock Entry</button>
          </div>

          <div id="sut-fg" class="mb-2"></div>
          <div id="sut-fg-summary" class="sut-fg-summary"></div>
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

          { fieldname: 'pos_closing_entry', label: 'POS Closing Entry', fieldtype: 'Link', options: 'POS Closing Entry', reqd: 1,
            get_query: () => ({ filters: { docstatus: 1 } })
          },
          { fieldtype: 'Column Break' },

          { fieldname: 'company', label: 'Company', fieldtype: 'Link', options: 'Company', reqd: 1, default: frappe.defaults.get_default("Company") },
          { fieldtype: 'Column Break' },

          { fieldname: 'posting_date', label: 'Posting Date', fieldtype: 'Date', reqd: 1, default: frappe.datetime.get_today() },
          { fieldtype: 'Column Break' },

          { fieldname: 'source_warehouse', label: 'Source Warehouse', fieldtype: 'Link', options: 'Warehouse', reqd: 1 },
          { fieldtype: 'Column Break' },
          { fieldname: 'btn_load', fieldtype: 'Button', label: 'Get Items', primary: 1, click: () => me.load_from_pos() }
        ]
      });
      this.fg.make();

      const src = this.fg.fields_dict.source_warehouse;
      src && (src.df.onchange = async () => { await this.bulk_update_availability_all(); this.update_all_cost_summary(); });
    }

    bind_global_actions() {
      this.$body.on('click', '#clear-all', () => this.clear_all());
      this.$body.on('click', '#recalc-all', () => this.recalc_all());
      this.$body.on('click', '#submit-se', () => this.submit_se());
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
      // Build rows for Finished Goods
      // Columns: ▶ | Item Code | Item Name | Qty | UOM | Selling Rate | Amount | Unit Cost | Cost | Margin | Margin %
      const rows = (items || []).map((meta, i) => {
        const c = this.get_fg_cost(i);
        return [
          `<span class="sut-exp" data-row="${i}" style="cursor:pointer;user-select:none;">&#9654;</span>`,
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
      });

      // Append TOTAL row with only summary columns colored
      const t = this.compute_fg_totals();
      rows.push([
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
      ]);

      // Render/replace datatable
      if (this.fgDT && typeof this.fgDT.destroy === 'function') {
        this.fgDT.destroy();
      }
      const $fg = this.$body.find('#sut-fg').empty();

      this.fgDT = new frappe.DataTable($fg.get(0), {
        columns: [
          { name: '', width: 34, editable: false },
          { name: 'Item Code', width: 160, editable: false },
          { name: 'Item Name', width: 240, editable: false },
          { name: 'Qty', width: 90, align: 'right', editable: false },
          { name: 'Stock UOM', width: 90, editable: false },
          { name: 'Selling Rate', width: 120, align: 'right', editable: false },
          { name: 'Amount', width: 120, align: 'right', editable: false },
          { name: 'Unit Cost', width: 120, align: 'right', editable: false },
          { name: 'Cost', width: 120, align: 'right', editable: false },
          { name: 'Margin', width: 120, align: 'right', editable: false },
          { name: 'Margin %', width: 90, align: 'right', editable: false },
        ],
        data: rows,
        serialNoColumn: true,
        checkboxColumn: false,
        layout: 'fluid'
      });

      // No longer add highlight to TOTAL row

      // Ensure TOTAL row is up to date
      this.update_fg_total_row();

      // Click handler for expand arrow
      const me = this;
      $fg.off('click.sut-exp').on('click.sut-exp', '.sut-exp', async function (e) {
        const i = parseInt($(this).attr('data-row'), 10);
        if (isNaN(i)) return;

        // Toggle arrow ▶/▼
        const isClosed = $(this).html() === '&#9654;';
        $('.sut-exp').html('&#9654;'); // collapse all
        if (isClosed) $(this).html('&#9660;');

        // If block already rendered, just show it and hide others
        const g = me.groups[i];
        if (g && g.$block) {
          $('.sut-item-block').hide();
          g.$block.show();
          return;
        }

        // Not rendered yet: build rows from meta.rm_items and render
        const meta = me.groups[i]?.meta || me.groups[i];
        const wh = me.fg.get_value('source_warehouse');
        const rowsRM = (meta.rm_items || []).map(x => [
          cellToText(x.item_code), cellToText(x.item_name), flt(x.required_qty), cellToText(x.stock_uom),
          0, cellToText(wh), '', flt(x.unit_cost), flt(x.unit_cost) * flt(x.required_qty)
        ]);
        me.render_item_block(meta, rowsRM, i);
        await me.bulk_update_availability_group(i);
        me.update_group_summary(i);
      });
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
          args: { pos_closing_entry, company }
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

        frappe.show_alert({ message: __('Loaded'), indicator: 'green' });
      } catch (e) {
        console.error(e);
        frappe.msgprint({ title: 'Error', message: e.message || e, indicator: 'red' });
      } finally {
        frappe.dom.unfreeze();
      }
    }

    // ===== RENDER 1 ITEM =====
    render_item_block(meta, rows, idx) {
      // idx is the FG row index; show only one detail block at a time

      const $block = $(`
        <div class="sut-item-block" data-idx="${idx}">
          <div class="sut-rm-toolbar">
            <button class="btn btn-default btn-sm" data-action="recalc">Recalculate</button>
            <button class="btn btn-default btn-sm" data-action="add">Add</button>
            <button class="btn btn-default btn-sm" data-action="remove">Remove</button>
          </div>
          <div id="sut-dt-${idx}"></div>
          <div class="sut-summary">
            <div>Lines: <b id="sut-lines-${idx}">0</b></div>
            <div>
              Total Required Qty: <b id="sut-total-qty-${idx}">0</b> &nbsp; | &nbsp;
              Total RM Cost: <b id="sut-total-cost-${idx}">0</b>
            </div>
          </div>
        </div>
      `);

      // Hide other blocks (single-detail behavior)
      this.$body.find('.sut-item-block').hide();

      this.$body.find('#sut-groups').append($block);
      $block.show();

      // Datatable columns:
      // 0 Item Code | 1 Item Name | 2 Req Qty | 3 Stock UOM | 4 Available | 5 Warehouse | 6 Remarks | 7 Unit Cost | 8 Cost
      const dt = new frappe.DataTable($block.find(`#sut-dt-${idx}`).get(0), {
        columns: [
          { name: COL_N.code, width: 160, editable: true },
          { name: COL_N.name, width: 220, editable: false },
          { name: COL_N.req_qty, width: 110, align: 'right', editable: true },
          { name: COL_N.uom, width: 90, editable: false },
          { name: COL_N.avail, width: 120, align: 'right', editable: false },
          { name: COL_N.wh, width: 180, editable: true },
          { name: COL_N.remarks, width: 200, editable: true },
          { name: COL_N.unit_cost, width: 110, align: 'right', editable: false },
          { name: COL_N.cost, width: 120, align: 'right', editable: false },
        ],
        data: rows || [],
        serialNoColumn: true,
        checkboxColumn: true,
        layout: 'fluid',
        events: {
          onEdit: async (cell, r, c, val) => {
            const columns = dt.getColumns?.() || [];
            if (!columns.length || r == null || c == null) return;
            const col = columns[c]?.name;
            if (!col) return;

            // Use shared column map and getCellTxt helper
            const COL = getColMap(dt);
            const get = (r, ci) => getCellTxt(dt, r, ci);

            if (col === COL_N.code && val) {
                console.log(`Item Code changed: ${val}`);
                const code = cellToText(val);
                const res = await frappe.db.get_value('Item', code, ['item_name', 'stock_uom']);
                if (res?.message) {
                    dt.updateCell?.(r, COL.name, res.message.item_name || '');
                    dt.updateCell?.(r, COL.uom, res.message.stock_uom || '');
                }
                const uc = await frappe.call({
                    method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.get_unit_cost',
                    args: { item_code: code }
                });
                const unit_cost = flt(uc?.message);
                dt.updateCell?.(r, COL.unit_cost, unit_cost);
                // Auto compute cost on item selection using current Req Qty
                const qty_now = flt(get(r, COL.req_qty));
                dt.updateCell?.(r, COL.cost, qty_now * unit_cost);
            }

            if (col === COL_N.code || col === COL_N.wh) {
                console.log(`Checking availability for ${col}: ${val}`);
                const item_code = get(r, COL.code);
                const wh = get(r, COL.wh) || this.fg.get_value('source_warehouse');
                if (item_code && wh) {
                    const a = await frappe.call({
                        method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.get_available_qty',
                        args: { item_code, warehouse: wh }
                    });
                    dt.updateCell?.(r, COL.avail, a?.message ?? 0);
                }
            }

            this.update_group_summary(idx);
          }
        }
      });

      // Remove button enable/disable logic (robust)
      const $removeBtn = $block.find('[data-action="remove"]');
      const updateRemoveState = () => {
        let count = 0;
        if (dt.rowmanager && typeof dt.rowmanager.getCheckedRows === 'function') {
          const rows = dt.rowmanager.getCheckedRows();
          count = (rows && rows.length) ? rows.length : 0;
        } else {
          // Fallback: count checked checkboxes in the datatable DOM
          count = $block.find('.datatable .dt-cell--checkbox input[type="checkbox"]:checked').length;
        }
        $removeBtn.prop('disabled', count === 0);
      };
      updateRemoveState();
      // Observe checkbox changes inside this block (broader selector, slight delay)
      $block.on('change click', '.datatable input[type="checkbox"]', () => setTimeout(updateRemoveState, 0));

      // simpan grup pada index eksplisit
      this.groups[idx] = { meta, dt, $block };

      this.update_group_summary(idx);

      // toolbar events
      $block.on('click', '[data-action]', async (e) => {
        const action = $(e.currentTarget).data('action');
        if (action === 'add') {
          const cur = dtToArray(dt);
          const wh = cellToText(this.fg.get_value('source_warehouse')) || '';
          cur.push(['', '', 1, '', 0, wh, '', 0, 0]);
          dt.refresh(cur);
          try { dt.scrollToRow && dt.scrollToRow(cur.length - 1); } catch(e) {}
          updateRemoveState();
          // Optional immediate feedback: keep summary in sync
          this.update_group_summary(idx);
        } else if (action === 'remove') {
          let checked = [];
          if (dt.rowmanager && typeof dt.rowmanager.getCheckedRows === 'function') {
            checked = dt.rowmanager.getCheckedRows();
          }
          if (!checked.length) {
            frappe.prompt(
              [{ fieldname: 'rows', fieldtype: 'Data', label: 'Row indexes (comma separated)', reqd: 1, description: 'Contoh: 2,3,5' }],
              (v) => {
                const cur = dt.getData?.() || [];
                const idxs = String(v.rows).split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n));
                idxs.sort((a,b)=>b-a).forEach(n => { const i0 = n-1; if (i0>=0 && i0<cur.length) cur.splice(i0,1); });
                dt.refresh(cur);
                updateRemoveState();
                this.update_group_summary(idx);
              },
              __('Remove Rows')
            );
            return;
          }
          const cur = dt.getData?.() || [];
          checked.sort((a,b)=>b-a).forEach(i => { if (i>=0 && i<cur.length) cur.splice(i,1); });
          dt.refresh(cur);
          updateRemoveState();
          this.update_group_summary(idx);
        } else if (action === 'recalc') {
          await this.recalc_group(idx);
        }
      });
    }

    update_group_summary(idx) {
      const dt = this.groups[idx]?.dt;
      const n = dtRowCount(dt);
      let total_qty = 0, total_cost = 0;
      const COL = getColMap(dt);
      for (let i = 0; i < n; i++) {
        total_qty += flt(getCellTxt(dt, i, COL.req_qty, 0));
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
        args: { pos_closing_entry: pce, company }
      });
      const found = (r.message.items || []).find(x => x.item_code === g.meta.item_code);
      if (!found) {
        // Still recalculate cost for current rows before updating summary
        // Recompute Cost from current Req Qty × Unit Cost
        const dt = g.dt;
        const COL = getColMap(dt);
        const n = dtRowCount(dt);
        for (let i = 0; i < n; i++) {
          const qty = flt(getCellTxt(dt, i, COL.req_qty, 0));
          const uc  = flt(getCellTxt(dt, i, COL.unit_cost, 0));
          dt.updateCell?.(i, COL.cost, qty * uc);
        }
        this.update_group_summary(idx);
        return;
      }

      // Keep current DT rows intact; only recompute Cost based on edited Req Qty × Unit Cost
      const COL = getColMap(g.dt);
      const n = dtRowCount(g.dt);
      for (let i = 0; i < n; i++) {
        const qty = flt(getCellTxt(g.dt, i, COL.req_qty, 0));
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
      const items = this.groups.map(g => g.meta);
      this.render_fg_table(items);
      this.update_fg_total_row();
    }
    clear_all() { this.groups = []; this.$body.find('#sut-groups').empty(); }

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
        dt.updateCell?.(i, COL.avail, qty);
      }
    }

    async bulk_update_availability_all() {
      for (let i = 0; i < this.groups.length; i++) await this.bulk_update_availability_group(i);
    }

    // ===== Submit =====
    get_all_items_payload() {
      const out = [];
      for (const g of this.groups) {
        const dt = g.dt;
        const n = dtRowCount(dt);
        const COL = getColMap(dt);
        for (let i = 0; i < n; i++) {
          const item_code = getCellTxt(dt, i, COL.code, '');
          const qty = flt(getCellTxt(dt, i, COL.req_qty, 0));
          if (!item_code || !qty) continue;
          out.push({
            item_code,
            item_name: getCellTxt(dt, i, COL.name, ''),
            qty,
            stock_uom: getCellTxt(dt, i, COL.uom, ''),
            warehouse: getCellTxt(dt, i, COL.wh, ''),
            remarks: getCellTxt(dt, i, COL.remarks, ''),
            unit_cost: flt(getCellTxt(dt, i, COL.unit_cost, 0)),
            cost: flt(getCellTxt(dt, i, COL.cost, 0)),
            parent_item_code: g.meta.item_code
          });
        }
      }
      return out;
    }

    async submit_se() {
      const pos_closing_entry = this.fg.get_value('pos_closing_entry');
      const company = this.fg.get_value('company');
      const posting_date = this.fg.get_value('posting_date');
      const source_warehouse = this.fg.get_value('source_warehouse');
      const stock_entry_type = 'Material Issue'; // default since field removed
      const remarks = '';

      if (!pos_closing_entry || !company || !posting_date || !source_warehouse) {
        frappe.msgprint(__('Please complete all required fields.'));
        return;
      }

      const items = this.get_all_items_payload();
      if (!items.length) {
        frappe.msgprint(__('No raw materials to post.'));
        return;
      }

      frappe.confirm(__('Generate Stock Entry for {0}?', [frappe.utils.escape_html(pos_closing_entry)]), async () => {
        frappe.dom.freeze(__('Creating Stock Entry...'));
        try {
          const resp = await frappe.call({
            method: 'resto.resto_sopwer.page.stock_usage_tool.stock_usage_tool.create_stock_entry_from_pos_usage',
            args: {
              pos_closing_entry, company, posting_date, stock_entry_type,
              source_warehouse, remarks, items
            }
          });
          const se_name = resp.message;
          frappe.msgprint({
            title: __('Success'),
            message: __('Stock Entry {0} has been submitted.', [`<a href="/app/stock-entry/${se_name}" target="_blank">${se_name}</a>`]),
            indicator: 'green'
          });
          frappe.set_route('Form', 'Stock Entry', se_name);
        } catch (e) {
          console.error(e);
          frappe.msgprint({ title: 'Error', message: e.message || e, indicator: 'red' });
        } finally {
          frappe.dom.unfreeze();
        }
      });
    }
  };

  // Page hook (base code)
  frappe.pages['stock-usage-tool'].on_page_load = function (wrapper) {
    resto.stock_usage.page = new resto.stock_usage.Page(wrapper);
  };
})();