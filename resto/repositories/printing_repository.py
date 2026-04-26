import frappe


class PrintingRepository:
    def get_bill_printer(self, branch):
        return frappe.db.get_value("Printer Settings", {"branch": branch}, "printer_bill_name")

    def get_receipt_printer(self, branch):
        return frappe.db.get_value("Printer Settings", {"branch": branch}, "printer_receipt_name")

    def get_checker_printer(self, branch):
        return frappe.db.get_value("Printer Settings", {"branch": branch}, "printer_checker_name")

    def get_void_printer(self, branch):
        return (
            frappe.db.get_value("Printer Settings", {"branch": branch}, "default_printer_checker")
            or "Void Printer"
        )

    def get_invoice_branch(self, pos_invoice):
        return frappe.db.get_value("POS Invoice", pos_invoice, "branch")

    def get_void_items_to_print(self, pos_invoice):
        invoice = frappe.get_doc("POS Invoice", pos_invoice)
        result = []
        for item in invoice.items:
            if (
                getattr(item, "status_kitchen", "") == "Void Menu"
                and getattr(item, "is_void_printed", 0) == 0
            ):
                result.append({
                    "name": item.name,
                    "item_code": item.item_code,
                    "item_name": (
                        frappe.db.get_value("Resto Menu", {"sell_item": item.item_code}, "short_name")
                        or item.item_name
                    ),
                    "qty": item.qty,
                    "add_ons": getattr(item, "add_ons", ""),
                    "quick_notes": getattr(item, "quick_notes", ""),
                })
        return result

    def get_branch_menu_printers_for_item(self, item_code, branch):
        bm = frappe.db.get_value(
            "Branch Menu",
            {"branch": branch, "sell_item": item_code},
            "name"
        )
        if not bm:
            return []
        doc = frappe.get_doc("Branch Menu", bm)
        return [p.printer_name for p in doc.printers if p.printer_name]

    def mark_void_printed(self, item_name):
        frappe.db.set_value("POS Invoice Item", item_name, "is_void_printed", 1)
        frappe.db.commit()
