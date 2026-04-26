import frappe


class TableRepository:
    def get_table(self, name):
        return frappe.get_doc("Table", name)

    def save_table(self, doc):
        doc.save(ignore_permissions=True)
        frappe.db.commit()

    def get_all_tables(self):
        return frappe.get_all(
            "Table",
            fields=[
                "name", "table_name", "status", "table_type", "zone",
                "customer", "pax", "type_customer", "floor", "taken_by", "checked",
            ],
            order_by="table_name asc"
        )

    def table_exists(self, name):
        return bool(frappe.db.exists("Table", name))

    def invoice_exists(self, name):
        return bool(frappe.db.exists("POS Invoice", name))
