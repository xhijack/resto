import frappe


class POSRepository:
    def get_pos_profiles_for_user(self, user):
        return frappe.get_all(
            "POS Profile User",
            filters={"user": user},
            pluck="parent"
        )

    def find_open_pos_entry(self, pos_profiles):
        result = frappe.get_all(
            "POS Opening Entry",
            filters={
                "pos_profile": ["in", pos_profiles],
                "status": "Open"
            },
            fields=["name", "pos_profile", "user", "branch"],
            order_by="creation desc",
            limit=1
        )
        return result[0] if result else None

    def find_open_pos_opening(self, pos_profiles):
        result = frappe.get_all(
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
        return result[0] if result else None

    def has_pending_end_day(self, pos_profiles, today):
        return bool(frappe.db.exists("POS Opening Entry", {
            "pos_profile": ["in", pos_profiles],
            "status": "Open",
            "posting_date": ["<", today]
        }))

    def has_today_opening(self, pos_profiles, today):
        return bool(frappe.db.exists("POS Opening Entry", {
            "pos_profile": ["in", pos_profiles],
            "status": "Open",
            "posting_date": today
        }))
