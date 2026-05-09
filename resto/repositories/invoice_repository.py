import frappe


class InvoiceRepository:
    def get_default_company(self):
        return frappe.db.get_single_value("Global Defaults", "default_company")

    def get_tax_template_name(self, title):
        return frappe.db.get_value(
            "Sales Taxes and Charges Template",
            {"title": title},
            "name"
        )

    def get_tax_template(self, name):
        return frappe.get_doc("Sales Taxes and Charges Template", name)

    def invoice_exists(self, name):
        return bool(frappe.db.exists("POS Invoice", name))

    def list_paid_invoices_for_table(self, table_name):
        if not table_name:
            return []
        return frappe.db.sql(
            """
            SELECT DISTINCT pi.name, pi.posting_date, pi.posting_time,
                   pi.grand_total, pi.customer, pi.customer_name, pi.pax,
                   pi.status, pi.docstatus
            FROM `tabPOS Invoice` pi
            INNER JOIN `tabTable Order` tor ON tor.invoice_name = pi.name
            WHERE tor.parent = %(table)s
              AND pi.status = 'Paid'
              AND pi.docstatus = 1
            ORDER BY pi.posting_date DESC, pi.posting_time DESC
            """,
            {"table": table_name},
            as_dict=True,
        )

    def list_paid_invoices(self, posting_date=None, branch=None, table_name=None):
        """List Paid POS Invoice — query menggunakan field `table` (custom field)
        sebagai source of truth, bukan JOIN ke `tabTable Order` yang rapuh
        terhadap clear_table. Default filter posting_date = today."""
        filters = ["pi.status = 'Paid'", "pi.docstatus = 1"]
        params = {}
        if posting_date:
            filters.append("pi.posting_date = %(posting_date)s")
            params["posting_date"] = posting_date
        else:
            filters.append("pi.posting_date = CURDATE()")
        if branch:
            filters.append("pi.branch = %(branch)s")
            params["branch"] = branch
        if table_name:
            filters.append("pi.`table` = %(table_name)s")
            params["table_name"] = table_name
        return frappe.db.sql(
            f"""
            SELECT pi.name, pi.posting_date, pi.posting_time, pi.grand_total,
                   pi.customer, pi.customer_name, pi.pax, pi.`table` AS `table`,
                   pi.status, pi.docstatus
            FROM `tabPOS Invoice` pi
            WHERE {' AND '.join(filters)}
            ORDER BY pi.posting_date DESC, pi.posting_time DESC
            """,
            params,
            as_dict=True,
        )

    def get_invoice(self, name):
        return frappe.get_doc("POS Invoice", name)

    def save_invoice(self, doc):
        doc.save()
        frappe.db.commit()

    def get_pos_profile(self, name):
        return frappe.get_doc("POS Profile", name)

    def get_active_profile_for_user(self, user):
        from resto.services.pos_service import POSService
        return POSService().get_active_pos_profile_for_user(user)

    def has_additional_items_field(self):
        return bool(frappe.get_meta("POS Invoice").get_field("additional_items"))

    def find_resto_menu(self, name):
        result = frappe.db.get_value("Resto Menu", {"name": name}, "name")
        if not result:
            result = frappe.db.get_value("Resto Menu", {"title": name}, "name")
        return result

    def get_resto_menu(self, name):
        return frappe.get_doc("Resto Menu", name)

    def get_merged_invoices(self, pos_invoice):
        names = frappe.get_all(
            "POS Invoice",
            filters={"merge_invoice": pos_invoice},
            fields=["name"]
        )
        return [frappe.get_doc("POS Invoice", n.name) for n in names]

    def get_invoice_branch(self, pos_invoice):
        return frappe.db.get_value("POS Invoice", pos_invoice, "branch")
