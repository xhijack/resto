import frappe


class KitchenRepository:
    def get_branch_menus(self, branch=None):
        filters = {"enabled": 1}
        if branch:
            filters["branch"] = branch
        return frappe.get_all(
            "Branch Menu",
            filters=filters,
            fields=["name", "menu_item", "rate"],
            limit_page_length=0
        )

    def get_resto_menus_by_names(self, names):
        if not names:
            return {}
        rows = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", names]},
            fields=[
                "name", "title", "menu_category", "sell_item", "use_stock",
                "stock_limit", "stock_used", "is_sold_out", "description"
            ]
        )
        return {r.name: r for r in rows}

    def get_images_for_menus(self, names):
        if not names:
            return {}
        files = frappe.get_all(
            "File",
            filters={"attached_to_doctype": "Resto Menu", "attached_to_name": ["in", names]},
            fields=["attached_to_name", "file_url"]
        )
        return {f.attached_to_name: f.file_url for f in files}

    def get_branch_menu_doc(self, name):
        return frappe.get_doc("Branch Menu", name)

    def get_pos_invoice_branch(self, pos_name):
        return frappe.db.get_value("POS Invoice", pos_name, "branch")

    def get_pos_invoice_items(self, pos_name):
        return frappe.get_all(
            "POS Invoice Item",
            filters={"parent": pos_name},
            fields=["name", "resto_menu", "item_name", "qty", "quick_notes", "add_ons"]
        )

    def get_short_name(self, resto_menu):
        return frappe.db.get_value("Resto Menu", resto_menu, "short_name") or ""

    def get_branch_menu_docs_for_item(self, resto_menu, branch=None):
        filters = {"menu_item": resto_menu}
        if branch:
            filters["branch"] = branch
        bms = frappe.get_all("Branch Menu", filters=filters, fields=["name"])
        return [frappe.get_doc("Branch Menu", bm.name) for bm in bms]

    def get_item_print_status(self, name):
        return int(frappe.db.get_value("POS Invoice Item", name, "is_print_kitchen") or 0)

    def mark_item_printed(self, name):
        frappe.db.set_value("POS Invoice Item", name, "is_print_kitchen", 1)

    def table_exists(self, name):
        return bool(frappe.db.exists("Table", name))
