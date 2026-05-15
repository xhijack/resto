import frappe

def after_migrate():
    def add_custom_field():
        if not frappe.db.exists("DocType", "POS Invoice Item"):
            frappe.logger().warning("POS Invoice Item DocType not found. Skipping custom fields creation.")
            return

        if not frappe.db.exists("Custom Field", {'fieldname': "resto_menu", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "resto_menu",
                "label": "Resto Menu",
                "fieldtype": "Link",
                "options": "Resto Menu",
                "insert_after": "item_name",
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "category", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "category",
                "label": "Category",
                "fieldtype": "Data",
                "insert_after": "resto_menu",
                "fetch_from": "resto_menu.menu_category",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "quick_notes", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "quick_notes",
                "label": "Quick Notes",
                "fieldtype": "Small Text",
                "insert_after": "resto_menu",
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "add_ons", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "add_ons",
                "label": "Add Ons",
                "fieldtype": "Small Text",
                "insert_after": "quick_notes",
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "is_checked", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "is_checked",
                "label": "Is Checked (Printed)",
                "fieldtype": "Check",
                "insert_after":"add_ons",
                "default": 0,
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {'fieldname': "is_print_kitchen", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "is_print_kitchen",
                "label": "Is Print Kitchen",
                "fieldtype": "Check",
                "insert_after":"add_ons",
                "default": 0,
            }).insert(ignore_permissions=True)

        # if not frappe.db.exists("Custom Field", {"fieldname": "pin_code", "dt": "User"}):
        #     frappe.get_doc({
        #         "doctype": "Custom Field",
        #         "dt": "User",
        #         "fieldname": "pin_code",
        #         "label": "PIN Code",
        #         "fieldtype": "Data",
        #         "unique": 1,
        #         "length": 6,
        #         "insert_after": "username",
        #         "description": "Masukkan 6 digit PIN unik untuk login"
        #     }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {"fieldname": "pincode", "dt": "User"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "User",
                "fieldname": "pincode",
                "label": "PIN Code",
                "fieldtype": "Data",
                "unique": 1,
                "length": 6,
                "insert_after": "username",
                "description": "Masukkan 6 digit PIN unik untuk login"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "status_kitchen", "dt": "POS Invoice Item"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "status_kitchen",
                "label": "Status Kitchen",
                "fieldtype": "Select",
                "insert_after": "item_code",
                "options": "\nNot Send\nAlready Send To Kitchen\nVoid Menu",
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': 'void_qty', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "void_qty",
                "label": "Void QTY",
                "fieldtype": "Float",
                "insert_after": "stock_uom",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': 'is_void_printed', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "is_void_printed",
                "label": "Is Void Printed",
                "fieldtype": "Check",
                "insert_after": "void_qty",
                "default": 0,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': 'void_rate', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "void_rate",
                "label": "Void Rate",
                "fieldtype": "Currency",
                "insert_after": "item_tax_template",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': 'void_amount', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "void_amount",
                "label": "Void Amount",
                "fieldtype": "Currency",
                "insert_after": "void_rate",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
            }).insert(ignore_permissions=True)

        # v1.2.18 Issue #3: kasir wajib pilih alasan void (dropdown) + boleh
        # tambah catatan freetext. Reason muncul di void item receipt.
        if not frappe.db.exists("Custom Field", {'fieldname': 'void_reason', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "void_reason",
                "label": "Void Reason",
                "fieldtype": "Data",
                "insert_after": "void_amount",
                "allow_on_submit": 1,
                "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': 'void_reason_note', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "void_reason_note",
                "label": "Void Reason Note",
                "fieldtype": "Small Text",
                "insert_after": "void_reason",
                "allow_on_submit": 1,
                "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': 'kitchen_stock_consumed', 'dt': 'POS Invoice Item'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "kitchen_stock_consumed",
                "label": "Kitchen Stock Consumed",
                "fieldtype": "Check",
                "insert_after": "stock_uom",
                "read_only": 1,
                "hidden": 1,
                "default": 0
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': 'queue', 'dt': 'POS Invoice'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "queue",
                "label": "Queue",
                "fieldtype": "Data",
                "insert_after": "status_kitchen"
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': 'is_merged', 'dt': 'POS Invoice'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "is_merged",
                "label": "Is Merged",
                "fieldtype": "Check",
                "insert_after": "queue",
                "default": 0,
                "read_only": 1,
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': 'merge_invoice', 'dt': 'POS Invoice'}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "merge_invoice",
                "label": "Merge Invoice",
                "fieldtype": "Data",
                "insert_after": "is_merged",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "branch", "dt": "POS Invoice"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "branch",
                "label": "Branch",
                "fieldtype": "Link",
                "options": "Branch",
                "insert_after": "due_date",
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': "additional_items", "dt": "POS Invoice"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "additional_items",
                "label": "Additional Items",
                "fieldtype": "Table",
                "options": "Additional Items",  
                "insert_after": "items",
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': "order_type", "dt": "POS Invoice"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "order_type",
                "label": "Order Type",
                "fieldtype": "Select",
                "options": "Dine In\nTake Away",
                "insert_after": "branch",
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "ordered_by", "dt": "POS Invoice"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "ordered_by",
                "label": "Ordered By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "order_type",
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "address", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "address",
                "label": "Address",
                "fieldtype": "Link",
                "options": "Address",
                "insert_after": "branch",
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "address_line1", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "address_line1",
                "label": "Adress Line 1",
                "fieldtype": "Data",
                "insert_after": "address",
                "fetch_from": "address.address_line1",
                "read_only": 1,
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {'fieldname': "address_line2", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "address_line2",
                "label": "Adress Line 2",
                "fieldtype": "Data",
                "insert_after": "address_line1",
                "fetch_from": "address.address_line2",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "city", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "city",
                "label": "City",
                "fieldtype": "Data",
                "insert_after": "address_line2",
                "fetch_from": "address.city",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "state", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "state",
                "label": "State/Province",
                "fieldtype": "Data",
                "insert_after": "city",
                "fetch_from": "address.state",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "pincode", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "pincode",
                "label": "Postal Code",
                "fieldtype": "Data",
                "insert_after": "state",
                "fetch_from": "address.pincode",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {'fieldname': "phone", "dt": "Branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Branch",
                "fieldname": "phone",
                "label": "Phone",
                "fieldtype": "Data",
                "insert_after": "pincode",
                "fetch_from": "address.phone",
                "read_only": 1,
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {"dt": "Company", "fieldname": "custom_company_logo"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Company",
                "fieldname": "custom_company_logo",
                "label": "Company Logo",
                "fieldtype": "Attach Image",
                "insert_after": "company_name"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "discount_for_bank"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "discount_for_bank",
                "label": "Discount For Bank",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "base_discount_amount"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "discount_name"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "discount_name",
                "label": "Discount Name",
                "fieldtype": "Data",
                "read_only": 1,
                "insert_after": "base_discount_amount"
            }).insert(ignore_permissions=True)

        if not frappe.db.exists("Custom Field", {"dt": "POS Closing Entry", "fieldname": "end_day_processed"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Closing Entry",
                "fieldname": "end_day_processed",
                "label": "End Day Processed",
                "fieldtype": "Check",
                "default": 0,
                "read_only": 1,
                "allow_on_submit": 1,
                "insert_after": "period_end_date"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {"dt": "POS Opening Entry", "fieldname": "branch"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Opening Entry",
                "fieldname": "branch",
                "label": "Branch",
                "fieldtype": "Link",
                "options": "Branch",
                "reqd": 1,
                "insert_after": "user"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice Item", "fieldname": "waiter"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "waiter",
                "label": "Waiter",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "status_kitchen"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "paid_by"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "paid_by",
                "label": "Paid By",
                "fieldtype": "Link",
                "options": "User",
                "insert_after": "is_return"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {"dt": "Mode of Payment", "fieldname": "parent1"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Mode of Payment",
                "fieldname": "parent1",
                "label": "Parent",
                "fieldtype": "Link",
                "options": "Mode of Payment",
                "insert_after": "mode_of_payment"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {"dt": "POS Profile", "fieldname": "takeaway_tax_and_charges"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Profile",
                "fieldname": "takeaway_tax_and_charges",
                "label": "Takeaway Tax and Charges",
                "fieldtype": "Link",
                "options": "Sales Taxes and Charges Template",
                "insert_after": "taxes_and_charges"
            }).insert(ignore_permissions=True)
            
        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "pax"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "pax",
                "label": "Pax",
                "fieldtype": "Int",
                "insert_after": "paid_by"
            }).insert(ignore_permissions=True)
        
        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "type_customer"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "type_customer",
                "label": "Type Customer",
                "fieldtype": "Select",
                "options": "\nPersonal\nFamily\nCorporate",
                "insert_after": "pax"
            }).insert(ignore_permissions=True)

        # Field `table` di POS Invoice — single source of truth relasi invoice→meja.
        # Dipakai oleh Bill Function query (list Paid by tanggal) dan menggantikan
        # JOIN ke `tabTable Order` yang rapuh terhadap clear_table.
        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "table"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice",
                "fieldname": "table",
                "label": "Table",
                "fieldtype": "Link",
                "options": "Table",
                "insert_after": "type_customer",
                "read_only": 1,
                "no_copy": 1,
                "search_index": 1,
            }).insert(ignore_permissions=True)
        else:
            # Backfill: kalau field sudah ada tapi tanpa search_index → set + add DB index.
            cf_name = frappe.db.get_value(
                "Custom Field",
                {"dt": "POS Invoice", "fieldname": "table"},
                "name",
            )
            cf = frappe.get_doc("Custom Field", cf_name)
            if not cf.search_index:
                cf.search_index = 1
                cf.save(ignore_permissions=True)
                try:
                    frappe.db.add_index("POS Invoice", ["table"])
                except Exception:
                    pass

    add_custom_field()
    seed_pilot_print_format()


PILOT_KITCHEN_TEMPLATE = """{{ esc_init() }}{{ esc_font_a() }}
{{ esc_align_center() }}{{ esc_char_size_dotmatrix(2, 2) }}{{ esc_bold(1) }}{{ payload.kitchen_station }}
{{ esc_char_size_dotmatrix(1, 1) }}{{ esc_bold(0) }}{{ esc_align_left() }}
Tanggal : {{ header.date }}
Meja    : {{ header.table_name }}
{% if header.pax %}Pax     : {{ header.pax }}
{% endif %}Petugas : {{ header.operator_name }}
{{ line_separator() }}
{% for it in unprinted_items %}{{ esc_char_size_dotmatrix(2, 2) }}{{ esc_bold(1) }}{{ it.qty }}x {{ it.short_name or it.item_name }}
{{ esc_char_size_dotmatrix(1, 1) }}{{ esc_bold(0) }}{% if it.add_ons %}  + {{ it.add_ons }}
{% endif %}{% if it.quick_notes %}  ! {{ it.quick_notes }}
{% endif %}
{% endfor %}{{ line_separator() }}
{% if invoice.order_type == 'take away' and invoice.queue %}{{ esc_align_center() }}{{ esc_bold(1) }}QUEUE: {{ invoice.queue }}{{ esc_bold(0) }}{{ esc_align_left() }}
{% endif %}{{ esc_feed(5) }}{{ esc_cut_full() }}"""


def seed_pilot_print_format():
    """Idempotent seed: pilot kitchen receipt PF + matching Resto Print Rule.

    Rule is created disabled — admin must enable explicitly to switch from
    legacy hardcoded builder. Skips insert if either already exists.
    """
    pf_name = "Kitchen Receipt (Default)"
    rule_name = "Kitchen Receipt - Default"

    if not frappe.db.exists("DocType", "Print Format"):
        return

    if not frappe.db.exists("Print Format", pf_name):
        try:
            frappe.get_doc({
                "doctype": "Print Format",
                "name": pf_name,
                "doc_type": "POS Invoice",
                "print_format_type": "Jinja",
                "raw_printing": 1,
                "html": PILOT_KITCHEN_TEMPLATE,
                "module": "Resto Sopwer",
                "standard": "No",
            }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.logger().warning(f"seed_pilot_print_format: PF insert failed: {e}")
            return

    if not frappe.db.exists("DocType", "Resto Print Rule"):
        return

    if not frappe.db.exists("Resto Print Rule", rule_name):
        try:
            frappe.get_doc({
                "doctype": "Resto Print Rule",
                "rule_name": rule_name,
                "action_key": "kitchen_receipt",
                "print_format": pf_name,
                "printer_resolver": "From Payload",
                "enabled": 0,
                "priority": 0,
                "description": (
                    "Default kitchen receipt template. Enable to switch from "
                    "legacy hardcoded builder to this Print Format."
                ),
            }).insert(ignore_permissions=True)
        except Exception as e:
            frappe.logger().warning(f"seed_pilot_print_format: Rule insert failed: {e}")