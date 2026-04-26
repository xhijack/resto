import frappe
from unittest.mock import MagicMock, patch
from frappe.tests.utils import FrappeTestCase
from resto.services.pos_service import POSService
from resto.tests.resto_pos_test_base import RestoPOSTestBase


class TestPOSService(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = POSService(repo=self.mock_repo)

    # ------------------------------------------------------------------
    # Unit tests — get_active_pos_profile_for_user
    # ------------------------------------------------------------------

    def test_throws_when_user_has_no_pos_profile(self):
        """Harus throw jika user tidak punya POS Profile"""
        self.mock_repo.get_pos_profiles_for_user.return_value = []
        with self.assertRaises(frappe.ValidationError):
            self.service.get_active_pos_profile_for_user("user@test.com")

    def test_throws_when_no_open_pos_entry(self):
        """Harus throw jika tidak ada POS Opening Entry yang Open"""
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.find_open_pos_entry.return_value = None
        with self.assertRaises(frappe.ValidationError):
            self.service.get_active_pos_profile_for_user("user@test.com")

    def test_returns_opening_entry_when_found(self):
        """Harus return opening entry dari repo jika ada"""
        expected = frappe._dict({"name": "POS-OPEN-001", "pos_profile": "PROF-001", "user": "u@t.com", "branch": "A"})
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.find_open_pos_entry.return_value = expected

        result = self.service.get_active_pos_profile_for_user("user@test.com")
        self.assertEqual(result, expected)

    def test_passes_correct_user_to_repo(self):
        """Harus teruskan user yang benar ke repository"""
        self.mock_repo.get_pos_profiles_for_user.return_value = []
        try:
            self.service.get_active_pos_profile_for_user("specific@user.com")
        except frappe.ValidationError:
            pass
        self.mock_repo.get_pos_profiles_for_user.assert_called_once_with("specific@user.com")

    # ------------------------------------------------------------------
    # Unit tests — get_active_pos_opening
    # ------------------------------------------------------------------

    def test_get_active_pos_opening_throws_when_no_profile(self):
        """Harus throw jika user tidak punya POS Profile"""
        self.mock_repo.get_pos_profiles_for_user.return_value = []
        with self.assertRaises(frappe.ValidationError):
            self.service.get_active_pos_opening("user@test.com")

    def test_get_active_pos_opening_throws_when_not_open(self):
        """Harus throw jika POS belum dibuka"""
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.find_open_pos_opening.return_value = None
        with self.assertRaises(frappe.ValidationError):
            self.service.get_active_pos_opening("user@test.com")

    def test_get_active_pos_opening_returns_opening(self):
        """Harus return opening dari repo jika ada"""
        expected = frappe._dict({
            "name": "POS-OPEN-001", "pos_profile": "PROF-001",
            "branch": "Cabang A", "period_start_date": "2026-04-26 08:00:00"
        })
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.find_open_pos_opening.return_value = expected

        result = self.service.get_active_pos_opening("user@test.com")
        self.assertEqual(result, expected)

    # ------------------------------------------------------------------
    # Unit tests — check_pos_status_for_user
    # ------------------------------------------------------------------

    def test_check_pos_status_throws_when_no_profile(self):
        """Harus throw jika user tidak punya POS Profile"""
        self.mock_repo.get_pos_profiles_for_user.return_value = []
        with self.assertRaises(frappe.ValidationError):
            self.service.check_pos_status_for_user("user@test.com")

    def test_check_pos_status_returns_both_flags(self):
        """Harus return dict dengan end_day_pending dan today_opening"""
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.has_pending_end_day.return_value = False
        self.mock_repo.has_today_opening.return_value = True

        result = self.service.check_pos_status_for_user("user@test.com")

        self.assertIn("end_day_pending", result)
        self.assertIn("today_opening", result)

    def test_check_pos_status_end_day_pending_true(self):
        """end_day_pending harus True jika repo return True"""
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.has_pending_end_day.return_value = True
        self.mock_repo.has_today_opening.return_value = False

        result = self.service.check_pos_status_for_user("user@test.com")
        self.assertTrue(result["end_day_pending"])
        self.assertFalse(result["today_opening"])

    def test_check_pos_status_today_opening_true(self):
        """today_opening harus True jika repo return True"""
        self.mock_repo.get_pos_profiles_for_user.return_value = ["PROF-001"]
        self.mock_repo.has_pending_end_day.return_value = False
        self.mock_repo.has_today_opening.return_value = True

        result = self.service.check_pos_status_for_user("user@test.com")
        self.assertFalse(result["end_day_pending"])
        self.assertTrue(result["today_opening"])

    # ------------------------------------------------------------------
    # Integration test
    # ------------------------------------------------------------------

    def test_get_active_pos_profile_integration(self):
        """Harus return opening entry setelah POS dibuka (pakai DB sungguhan)"""
        self._create_pos_opening_entry()
        real_service = POSService()
        result = real_service.get_active_pos_profile_for_user(frappe.session.user)

        self.assertIsNotNone(result)
        self.assertEqual(result["pos_profile"], self.pos_profile.name)
        self.assertIn("branch", result)
