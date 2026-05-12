import frappe


def execute():
	"""Backfill POS Invoice Item.category for split bills created before mobile v1.2.16.

	Pre-v1.2.16, useSplitBillData mapping dropped `category` so split bill items landed
	with empty category in backend. That broke discount validation (validateDiscount
	butuh non-empty category supaya item lulus filter discount bank).

	Patch ini one-shot: lookup Resto Menu.menu_category untuk row yang category-nya
	kosong AND resto_menu-nya ada AND parent docstatus != 2 (skip cancelled).

	Jalankan manual per site yang butuh:
	    bench --site <SITE> execute resto.patches.backfill_split_bill_category.execute
	"""
	rows = frappe.db.sql(
		"""
		SELECT pii.name, pii.resto_menu
		FROM `tabPOS Invoice Item` pii
		JOIN `tabPOS Invoice` pi ON pi.name = pii.parent
		WHERE (pii.category IS NULL OR pii.category = '')
		  AND pii.resto_menu IS NOT NULL
		  AND pii.resto_menu != ''
		  AND pi.docstatus != 2
		""",
		as_dict=True,
	)

	updated = 0
	for row in rows:
		menu_cat = frappe.db.get_value("Resto Menu", row["resto_menu"], "menu_category")
		if menu_cat:
			frappe.db.set_value(
				"POS Invoice Item",
				row["name"],
				"category",
				menu_cat,
				update_modified=False,
			)
			updated += 1
	frappe.db.commit()
	print(
		f"Backfilled category on {updated} POS Invoice Item rows "
		f"(from {len(rows)} candidates)."
	)
