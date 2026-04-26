import frappe


class POSRepository:
    def get_active_pos_profile_for_user(self, user):
        pos_profiles = frappe.get_all(
            "POS Profile User",
            filters={"user": user},
            pluck="parent"
        )

        if not pos_profiles:
            frappe.throw("User tidak punya POS Profile")

        opening = frappe.get_all(
            "POS Opening Entry",
            filters={
                "pos_profile": ["in", pos_profiles],
                "status": "Open"
            },
            fields=["name", "pos_profile", "user", "branch"],
            order_by="creation desc",
            limit=1
        )

        if not opening:
            frappe.throw("POS belum dibuka")

        return opening[0]

    def get_active_pos_opening(self, user):
        pos_profiles = frappe.get_all(
            "POS Profile User",
            filters={"user": user},
            pluck="parent"
        )

        if not pos_profiles:
            frappe.throw("User tidak memiliki POS Profile")

        opening = frappe.get_all(
            "POS Opening Entry",
            filters={
                "pos_profile": ["in", pos_profiles],
                "docstatus": 1,
                "status": "Open"
            },
            fields=["name", "pos_profile", "branch", "period_start_date"],
            order_by="period_start_date desc",
            limit=1
        )

        if not opening:
            frappe.throw("POS belum dibuka hari ini")

        return opening[0]
