# Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from resto.resto_sopwer.doctype.resto_menu.resto_menu import make_branch_menu

class RestoMenuTool(Document):
	def on_update(self):
		# collect branches that should remain enabled
		enabled_branches = set()
		for bm in self.branch_menu:
			if getattr(bm, "enabled", 0):
				enabled_branches.add(bm.branch)

				# skip if Branch Menu already exists for this branch + menu item
				if frappe.db.exists("Branch Menu", {"menu_item": self.item_menu, "branch": bm.branch}):
					continue

				# try to use make_branch_menu; fall back to positional, then explicit create
				try:
					make_branch_menu(source_name=self.item_menu, branch=bm.branch, price_list=bm.price_list, rate=getattr(bm, "rate", None))
				except TypeError:
					try:
						# positional fallback
						make_branch_menu(self.item_menu, bm.branch, bm.price_list, getattr(bm, "rate", None))
					except Exception:
						try:
							# last-resort: create Branch Menu doc directly
							doc = frappe.get_doc({
								"doctype": "Branch Menu",
								"menu_item": self.item_menu,
								"branch": bm.branch,
								"price_list": bm.price_list,
								"rate": getattr(bm, "rate", None)
							})
							doc.insert(ignore_permissions=True)
						except Exception:
							# ignore creation errors
							pass
				except Exception:
					# ignore other errors from make_branch_menu
					pass

		# remove branch menus that are not enabled (or not present) in this tool
		for bm in frappe.get_all("Branch Menu", filters={"menu_item": self.item_menu}, fields=["name", "branch"]):
			if bm["branch"] not in enabled_branches:
				try:
					frappe.delete_doc("Branch Menu", bm["name"], force=True, ignore_permissions=True)
				except Exception:
					# ignore deletion errors
					pass

@frappe.whitelist(allow_guest=False)
def get_branches_with_menu(item_menu):
	# all branches
	all_branches = frappe.get_all("Branch", fields=["name"])
	# branch menus that reference the item_menu
	branch_menus = frappe.get_all(
		"Branch Menu",
		filters={"menu_item": item_menu},
		fields=["branch", "price_list", "rate"],
	)
	# build a map from branch name to price_list and rate for quick lookup
	branch_menu_map = {
		bm["branch"]: {"price_list": bm.get("price_list"), "rate": bm.get("rate")}
		for bm in branch_menus
		if "branch" in bm
	}

	result = []
	for b in all_branches:
		name = b["name"]
		if name in branch_menu_map:
			pm = branch_menu_map[name]
			result.append({
				"branch": name,
				"enabled": 1,
				"price_list": pm.get("price_list"),
				"rate": pm.get("rate"),
			})
		else:
			result.append({"branch": name, "enabled": 0, "price_list": None, "rate": None})

	return result

