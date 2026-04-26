import frappe
from frappe.utils import nowdate
from resto.repositories.pos_repository import POSRepository


class POSService:
    def __init__(self, repo=None):
        self.repo = repo or POSRepository()

    def get_active_pos_profile_for_user(self, user):
        pos_profiles = self.repo.get_pos_profiles_for_user(user)
        if not pos_profiles:
            frappe.throw("User tidak punya POS Profile")

        opening = self.repo.find_open_pos_entry(pos_profiles)
        if not opening:
            frappe.throw("POS belum dibuka")

        return opening

    def get_active_pos_opening(self, user):
        pos_profiles = self.repo.get_pos_profiles_for_user(user)
        if not pos_profiles:
            frappe.throw("User tidak memiliki POS Profile")

        opening = self.repo.find_open_pos_opening(pos_profiles)
        if not opening:
            frappe.throw("POS belum dibuka hari ini")

        return opening

    def check_pos_status_for_user(self, user):
        pos_profiles = self.repo.get_pos_profiles_for_user(user)
        if not pos_profiles:
            frappe.throw("User tidak punya POS Profile")

        today = nowdate()
        return {
            "end_day_pending": self.repo.has_pending_end_day(pos_profiles, today),
            "today_opening": self.repo.has_today_opening(pos_profiles, today),
        }
