# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestRestoSettings(FrappeTestCase):

    def create_resto_settings(self, permissions):
        doc = frappe.get_doc({
            "doctype": "Resto Settings",
            "permissions": permissions
        })
        return doc

    def test_no_duplicate_permissions(self):
        """Should pass when no duplicate role + permission"""
        doc = self.create_resto_settings([
            {
                "doctype": "Resto Event Permissions",
                "role": "Accounts User",
                "permission": "Allow Move Item"
            },
            {
                "doctype": "Resto Event Permissions",
                "role": "Academics User",
                "permission": "Allow Apply Discount"
            }
        ])

        # Should NOT raise error
        doc.insert(ignore_permissions=True)

    def test_duplicate_permissions_should_fail(self):
        """Should throw error when duplicate role + permission exists"""
        doc = self.create_resto_settings([
            {
                "doctype": "Resto Event Permissions",
                "role": "Accounts User",
                "permission": "Allow Move Item"
            },
            {
                "doctype": "Resto Event Permissions",
                "role": "Accounts User",
                "permission": "Allow Move Item"
            }
        ])

        # Expect error
        self.assertRaises(frappe.ValidationError, doc.insert, ignore_permissions=True)