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
