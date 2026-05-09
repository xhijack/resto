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

    def get_tables_for_invoice(self, pos_invoice_name):
        rows = frappe.get_all(
            "Table Order",
            filters={"invoice_name": pos_invoice_name},
            fields=["parent"],
            distinct=True
        )
        return [r["parent"] for r in rows]

    def get_user_full_names(self, user_emails):
        if not user_emails:
            return {}
        unique_emails = list(set(user_emails))
        rows = frappe.get_all(
            "User",
            filters={"name": ["in", unique_emails]},
            fields=["name", "full_name"],
            ignore_permissions=True,
        )
        result = {r["name"]: (r.get("full_name") or r["name"]) for r in rows}
        # Fallback: untuk email yang tidak ditemukan di tabel User,
        # tetap kembalikan email tsb sebagai display name supaya UI
        # punya sesuatu untuk dirender (caption "oleh <email>").
        for email in unique_emails:
            result.setdefault(email, email)
        return result
