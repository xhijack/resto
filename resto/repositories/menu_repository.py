import frappe


class MenuRepository:
    def get_all_branches(self):
        return frappe.get_all("Branch", fields=["name", "branch"])
