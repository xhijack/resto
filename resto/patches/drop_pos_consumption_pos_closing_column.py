import frappe


def execute():
	"""Drop the legacy pos_closing column from tabPOS Consumption.

	Phase 6.3 step 2-final. After Phase 6.2 introduced pos_daily_summary
	as the canonical scope unit and the backfill patch propagated values
	to existing rows, pos_closing is dead. The doctype JSON no longer
	declares the field, but Frappe doesn't auto-drop columns on schema
	sync — we have to do it explicitly.

	Idempotent: only drops the column when it still exists, so re-runs
	on already-migrated sites are no-ops.

	Run order in patches.txt is important: this patch sits AFTER
	backfill_pos_consumption_daily_summary so any historical pos_closing
	values are read into pos_daily_summary BEFORE the column disappears.
	"""
	columns = frappe.db.sql(
		"""
		SELECT COLUMN_NAME
		FROM INFORMATION_SCHEMA.COLUMNS
		WHERE TABLE_SCHEMA = DATABASE()
		  AND TABLE_NAME = 'tabPOS Consumption'
		  AND COLUMN_NAME = 'pos_closing'
		""",
	)
	if not columns:
		print("drop_pos_consumption_pos_closing_column: column already absent, skipping.")
		return

	frappe.db.sql("ALTER TABLE `tabPOS Consumption` DROP COLUMN `pos_closing`")
	frappe.db.commit()
	print("drop_pos_consumption_pos_closing_column: column dropped.")
