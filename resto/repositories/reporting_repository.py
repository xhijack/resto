import frappe
from frappe.utils import flt


class ReportingRepository:
    # ------------------------------------------------------------------
    # Outlet filter helper
    # ------------------------------------------------------------------

    def detect_outlet_filter(self, outlet_value):
        meta = frappe.get_meta("POS Invoice")
        fields = [f.fieldname for f in meta.fields]
        if "branch" in fields:
            return {"branch": outlet_value}
        if "pos_profile" in fields:
            return {"pos_profile": outlet_value}
        if "set_warehouse" in fields:
            return {"set_warehouse": outlet_value}
        return {"company": outlet_value}

    # ------------------------------------------------------------------
    # get_end_day_report (v1)
    # ------------------------------------------------------------------

    def get_submitted_invoices(self, posting_date, outlet_filter):
        filters = {
            "posting_date": posting_date,
            "docstatus": 1,
            "status": "Consolidated"
        }
        filters.update(outlet_filter)
        return frappe.get_all(
            "POS Invoice",
            filters=filters,
            fields=["name", "net_total", "grand_total", "discount_amount",
                    "total_taxes_and_charges", "order_type"]
        )

    def get_sub_total(self, invoice_names):
        row = frappe.db.sql("""
            SELECT SUM(pii.amount) AS sub_total
            FROM `tabPOS Invoice Item` pii
            JOIN `tabPOS Invoice` pi ON pi.name = pii.parent
            WHERE pi.name IN %(invoices)s
              AND IFNULL(pii.status_kitchen,'') != 'Void Menu'
        """, {"invoices": tuple(invoice_names)}, as_dict=True)[0]
        return int(row.sub_total or 0)

    def get_discount_total(self, invoice_names):
        row = frappe.db.sql("""
            SELECT SUM(discount_amount) AS discount
            FROM `tabPOS Invoice`
            WHERE name IN %(invoices)s
        """, {"invoices": tuple(invoice_names)}, as_dict=True)[0]
        return int(row.discount or 0)

    def get_tax_total(self, invoice_names):
        row = frappe.db.sql("""
            SELECT SUM(tax_amount) AS tax
            FROM `tabSales Taxes and Charges`
            WHERE parent IN %(invoices)s
        """, {"invoices": tuple(invoice_names)}, as_dict=True)[0]
        return int(row.tax or 0)

    def get_items_by_order_type(self, invoice_names):
        return frappe.db.sql("""
            SELECT pi.order_type, pii.item_group,
                   SUM(pii.qty) qty, SUM(pii.amount) amount
            FROM `tabPOS Invoice Item` pii
            JOIN `tabPOS Invoice` pi ON pi.name = pii.parent
            WHERE pi.name IN %(invoices)s
              AND IFNULL(pii.status_kitchen,'') != 'Void Menu'
            GROUP BY pi.order_type, pii.item_group
        """, {"invoices": tuple(invoice_names)}, as_dict=True)

    def get_payments_summary(self, invoice_names):
        return frappe.db.sql("""
            SELECT sip.mode_of_payment, SUM(sip.amount) amount
            FROM `tabSales Invoice Payment` sip
            WHERE sip.parent IN %(invoices)s
            GROUP BY sip.mode_of_payment
        """, {"invoices": tuple(invoice_names)}, as_dict=True)

    def get_taxes_summary(self, invoice_names):
        return frappe.db.sql("""
            SELECT description, SUM(tax_amount) amount
            FROM `tabSales Taxes and Charges`
            WHERE parent IN %(invoices)s
            GROUP BY description
        """, {"invoices": tuple(invoice_names)}, as_dict=True)

    def get_discount_by_order_type(self, invoice_names):
        return frappe.db.sql("""
            SELECT pi.order_type, COUNT(pi.name) AS total_bill,
                   SUM(pi.discount_amount) AS total_discount
            FROM `tabPOS Invoice` pi
            WHERE pi.name IN %(invoices)s
              AND IFNULL(pi.discount_amount, 0) > 0
            GROUP BY pi.order_type
        """, {"invoices": tuple(invoice_names)}, as_dict=True)

    def get_discount_by_bank(self, invoice_names):
        return frappe.db.sql("""
            SELECT pi.discount_for_bank, pi.discount_name,
                   COUNT(pi.name) AS total_bill,
                   SUM(pi.discount_amount) AS total_discount
            FROM `tabPOS Invoice` pi
            WHERE pi.name IN %(invoices)s
              AND IFNULL(pi.discount_for_bank,'') != ''
              AND IFNULL(pi.discount_amount,0) > 0
            GROUP BY pi.discount_for_bank, pi.discount_name
        """, {"invoices": tuple(invoice_names)}, as_dict=True)

    def get_void_items(self, posting_date, outlet_filter):
        outlet_condition = "".join(
            [f" AND pi.{k} = %({k})s" for k in outlet_filter.keys()]
        )
        return frappe.db.sql("""
            SELECT pii.item_name,
                   SUM(pii.void_qty) AS qty,
                   SUM(
                       CASE
                           WHEN IFNULL(pii.void_amount,0) > 0 THEN pii.void_amount
                           ELSE pii.void_rate * pii.void_qty
                       END
                   ) AS amount
            FROM `tabPOS Invoice Item` pii
            JOIN `tabPOS Invoice` pi ON pi.name = pii.parent
            WHERE pi.posting_date = %(posting_date)s
              AND pi.docstatus = 1
              AND pii.status_kitchen = 'Void Menu'
              {outlet_condition}
            GROUP BY pii.item_name
        """.format(outlet_condition=outlet_condition),
            {"posting_date": posting_date, **outlet_filter},
            as_dict=True
        )

    def get_void_bills(self, posting_date, outlet_filter):
        filters = {"posting_date": posting_date, "docstatus": 2}
        filters.update(outlet_filter)
        return frappe.get_all("POS Invoice", filters=filters, fields=["name", "grand_total"])

    # ------------------------------------------------------------------
    # get_end_day_report_v2
    # ------------------------------------------------------------------

    def get_paid_invoices(self, posting_date, outlet_filter):
        filters = {
            "posting_date": posting_date,
            "docstatus": 1,
            "status": ["in", ["Paid", "Consolidated"]]
        }
        filters.update(outlet_filter)
        return frappe.get_all(
            "POS Invoice",
            filters=filters,
            fields=["name", "grand_total", "discount_amount", "order_type"]
        )

    def get_draft_invoices(self, posting_date, outlet_filter):
        filters = {"posting_date": posting_date, "docstatus": 0, "status": "Draft"}
        filters.update(outlet_filter)
        return frappe.get_all(
            "POS Invoice",
            filters=filters,
            fields=["name", "grand_total", "order_type"]
        )

    def get_sub_total_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT SUM(pii.amount)
            FROM `tabPOS Invoice Item` pii
            JOIN `tabPOS Invoice` pi ON pi.name = pii.parent
            WHERE pi.name IN %(inv)s
              AND IFNULL(pii.status_kitchen,'') != 'Void Menu'
        """, {"inv": tuple(invoice_names)})[0][0] or 0

    def get_discount_total_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT SUM(discount_amount)
            FROM `tabPOS Invoice`
            WHERE name IN %(inv)s
        """, {"inv": tuple(invoice_names)})[0][0] or 0

    def get_tax_total_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT SUM(tax_amount)
            FROM `tabSales Taxes and Charges`
            WHERE parent IN %(inv)s
        """, {"inv": tuple(invoice_names)})[0][0] or 0

    def get_pax_total(self, invoice_names):
        return frappe.db.sql("""
            SELECT SUM(pax)
            FROM `tabPOS Invoice`
            WHERE name IN %(inv)s
        """, {"inv": tuple(invoice_names)})[0][0] or 0

    def get_items_by_order_type_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT pi.order_type, pii.item_group,
                   SUM(pii.qty) qty, SUM(pii.amount) amount
            FROM `tabPOS Invoice Item` pii
            JOIN `tabPOS Invoice` pi ON pi.name = pii.parent
            WHERE pi.name IN %(inv)s
              AND IFNULL(pii.status_kitchen,'') != 'Void Menu'
            GROUP BY pi.order_type, pii.item_group
        """, {"inv": tuple(invoice_names)}, as_dict=True)

    def get_payments_summary_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT mode_of_payment, SUM(amount) amount
            FROM `tabSales Invoice Payment`
            WHERE parent IN %(inv)s
            GROUP BY mode_of_payment
        """, {"inv": tuple(invoice_names)}, as_dict=True)

    def get_taxes_summary_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT description, SUM(tax_amount) amount
            FROM `tabSales Taxes and Charges`
            WHERE parent IN %(inv)s
            GROUP BY description
        """, {"inv": tuple(invoice_names)}, as_dict=True)

    def get_discount_by_order_type_v2(self, invoice_names):
        return frappe.db.sql("""
            SELECT pi.discount_for_bank, pi.discount_name,
                   COUNT(DISTINCT pi.name) total_bill,
                   SUM(stc.tax_amount) total_amount
            FROM `tabSales Taxes and Charges` stc
            JOIN `tabPOS Invoice` pi ON pi.name = stc.parent
            WHERE pi.name IN %(inv)s
              AND stc.tax_amount < 0
            GROUP BY pi.discount_for_bank, pi.discount_name
        """, {"inv": tuple(invoice_names)}, as_dict=True)

    def get_void_bills_v2(self, posting_date, outlet_filter):
        filters = {"posting_date": posting_date, "docstatus": 2}
        filters.update(outlet_filter)
        return frappe.get_all("POS Invoice", filters=filters, fields=["name", "rounded_total"])

    def get_void_invoices_with_items(self, posting_date, outlet):
        filters = {
            "docstatus": 1,
            "posting_date": posting_date,
            "status": ["in", ["Paid", "Consolidated"]],
            "branch": outlet
        }
        return frappe.get_all("POS Invoice", filters=filters)

    def get_void_invoice_items(self, parent):
        return frappe.get_all(
            "POS Invoice Item",
            filters={"parent": parent, "is_void_printed": 1},
            fields=["item_name", "void_qty", "void_rate"]
        )

    def get_printer_for_branch(self, branch, field="default_printer_receipt"):
        return frappe.db.get_value("Printer Settings", {"branch": branch}, field)

    # ------------------------------------------------------------------
    # end_shift
    # ------------------------------------------------------------------

    def get_active_opening_for_user(self, user):
        from resto.services.pos_service import POSService
        return POSService().get_active_pos_profile_for_user(user)

    def get_paid_invoices_for_closing(self, pos_profile):
        return frappe.get_all(
            "POS Invoice",
            filters={
                "docstatus": 1,
                "is_pos": 1,
                "status": "Paid",
                "pos_profile": pos_profile
            },
            fields=["name", "posting_date", "posting_time"],
            order_by="posting_date asc, posting_time asc"
        )

    def set_invoice_owner(self, invoice_name, user):
        frappe.db.set_value("POS Invoice", invoice_name, "owner", user)

    def get_invoice_doc(self, name):
        return frappe.get_doc("POS Invoice", name)
