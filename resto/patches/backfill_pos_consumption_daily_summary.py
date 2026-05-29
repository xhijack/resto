import frappe


def execute():
	"""Backfill POS Consumption.pos_daily_summary for rows created before
	Phase 6.2 of the Stock Usage refactor.

	Pre-6.2, POS Consumption tracked a single POS Closing Entry on
	`pos_closing`. Phase 6.2 added `pos_daily_summary` so consumption can
	be scoped to the per-branch-per-day aggregate (POS Daily Summary)
	instead of a single shift.

	This patch looks up the Daily Summary that contains each row's PCE
	(via the `POS Closing Entry Report` child table on POS Daily Summary)
	and writes it back to `pos_daily_summary`. Rows whose PCE is not
	listed on any Daily Summary are skipped — those are stragglers from
	before End-Day was enforced; Phase 6.3 tightening will surface them.

	Idempotent: only touches rows where pos_daily_summary is empty.

	Run manually per site, or let `bench migrate` execute it via the
	patches.txt registration.
	"""
	rows = frappe.db.sql(
		"""
		SELECT name, pos_closing
		FROM `tabPOS Consumption`
		WHERE (pos_daily_summary IS NULL OR pos_daily_summary = '')
		  AND pos_closing IS NOT NULL
		  AND pos_closing != ''
		  AND docstatus != 2
		""",
		as_dict=True,
	)

	updated = 0
	missing = 0
	for row in rows:
		eds_name = frappe.db.get_value(
			"POS Closing Entry Report",
			{"pos_closing_entry": row["pos_closing"]},
			"parent",
		)
		if eds_name:
			frappe.db.set_value(
				"POS Consumption", row["name"],
				"pos_daily_summary", eds_name,
				update_modified=False,
			)
			updated += 1
		else:
			missing += 1

	frappe.db.commit()
	print(
		f"POS Consumption backfill: updated {updated}, "
		f"unmapped {missing} (no Daily Summary contains the PCE), "
		f"of {len(rows)} candidates."
	)
