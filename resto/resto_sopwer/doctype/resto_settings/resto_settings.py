# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RestoSettings(Document):
	def validate(self):
		seen = set()

		for row in self.permissions:
			key = (row.role, row.permission)

			if key in seen:
				frappe.throw(
					f"Duplicate entry found for Role '{row.role}' and Permission '{row.permission}'"
				)

			seen.add(key)

