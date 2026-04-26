import frappe


class MenuRepository:
    def get_all_branches(self):
        return frappe.get_all("Branch", fields=["name", "branch"])

    def get_company_name(self):
        return frappe.get_all(
            "Company",
            fields=["company_name"],
            limit_page_length=1,
            order_by="creation asc"
        )
