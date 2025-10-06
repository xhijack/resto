# Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc


class RestoMenu(Document):
	pass

@frappe.whitelist()
def make_branch_menu(source_name, branch=None, price_list=None):
    """
    Duplikasi Resto Menu -> Branch Menu (termasuk child).
    Set juga field branch & price_list jika diisi dari dialog.
    """
    def _postprocess(source, target):
        if branch:
            # sesuaikan dengan nama field sebenarnya di Branch Menu
            target.branch = branch
        if price_list:
            # sesuaikan dengan nama field sebenarnya di Branch Menu
            target.price_list = price_list

    mapping = {
        "Resto Menu": {
            "doctype": "Branch Menu",
            # "field_map": {"field_di_resto": "field_di_branch"},  # jika perlu
        },
        "Menu Add Ons": {
            "doctype": "Menu Add Ons",  # ganti jika child doctype di Branch Menu berbeda
            # "field_map": {"item": "item", "price": "price"},
        },
    }

    doc = get_mapped_doc(
        "Resto Menu",
        source_name,
        mapping,
        target_doc=None,
        postprocess=_postprocess,
        ignore_permissions=False,   # set True jika memang mau bypass
    )

    doc.insert()
    frappe.db.commit()
    return doc.name

