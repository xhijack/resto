import json
import frappe
from resto.repositories.kitchen_repository import KitchenRepository

try:
    from resto.printing import kitchen_print_from_payload
except Exception:
    kitchen_print_from_payload = None


class KitchenService:
    def __init__(self, repo=None):
        self.repo = repo or KitchenRepository()

    # ------------------------------------------------------------------
    # get_all_branch_menu_with_children
    # ------------------------------------------------------------------

    def get_all_branch_menu_with_children(self, branch=None):
        branch_menus = self.repo.get_branch_menus(branch=branch)
        if not branch_menus:
            return []

        menu_items = [bm.menu_item for bm in branch_menus if bm.menu_item]
        resto_menus = self.repo.get_resto_menus_by_names(menu_items)
        image_map = self.repo.get_images_for_menus(menu_items)

        result = []
        for bm in branch_menus:
            if bm.menu_item not in resto_menus:
                continue

            branch_doc = self.repo.get_branch_menu_doc(bm.name)
            branch_dict = branch_doc.as_dict()
            branch_dict.update({
                "rate": bm.rate,
                "resto_menu": resto_menus.get(bm.menu_item),
                "image": image_map.get(bm.menu_item)
            })
            result.append(branch_dict)

        return result

    # ------------------------------------------------------------------
    # get_branch_menu_for_kitchen_printing
    # ------------------------------------------------------------------

    def get_branch_menu_for_kitchen_printing(self, pos_name):
        branch = self.repo.get_pos_invoice_branch(pos_name)
        pos_items = self.repo.get_pos_invoice_items(pos_name)

        if not pos_items:
            return []

        station_data = {}
        short_name_cache = {}

        for it in pos_items:
            resto_menu = it.get("resto_menu") if isinstance(it, dict) else getattr(it, "resto_menu", None)
            if not resto_menu:
                continue

            if resto_menu not in short_name_cache:
                short_name_cache[resto_menu] = self.repo.get_short_name(resto_menu)

            bm_docs = self.repo.get_branch_menu_docs_for_item(resto_menu, branch=branch)

            for bm_doc in bm_docs:
                for printer_entry in (bm_doc.printers or []):
                    printer_name = printer_entry.get("printer_name")
                    if not printer_name:
                        continue
                    station = printer_entry.get("kitchen_station")
                    if not station:
                        continue
                    printing_type = printer_entry.get("printing_type") or "Combine"

                    if station not in station_data:
                        station_data[station] = {
                            "printer_name": printer_name,
                            "items": [],
                            "printing_type": printing_type
                        }

                    item_name = it.get("name") if isinstance(it, dict) else getattr(it, "name", None)
                    station_data[station]["items"].append({
                        "resto_menu": resto_menu,
                        "short_name": short_name_cache.get(resto_menu, ""),
                        "item_name": it.get("item_name") if isinstance(it, dict) else getattr(it, "item_name", ""),
                        "qty": it.get("qty") if isinstance(it, dict) else getattr(it, "qty", 0),
                        "quick_notes": it.get("quick_notes") if isinstance(it, dict) else getattr(it, "quick_notes", ""),
                        "add_ons": it.get("add_ons") if isinstance(it, dict) else getattr(it, "add_ons", ""),
                        "name": item_name
                    })

        result = []
        for station, data in station_data.items():
            items = data["items"]
            if not items:
                continue
            printing_type = data["printing_type"]
            printer_name = data["printer_name"]

            if printing_type == "Combine":
                result.append({
                    "kitchen_station": station,
                    "printer_name": printer_name,
                    "pos_invoice": pos_name,
                    "items": items,
                    "printing_type": printing_type
                })
            else:
                for item in items:
                    result.append({
                        "kitchen_station": station,
                        "printer_name": printer_name,
                        "pos_invoice": pos_name,
                        "items": [item],
                        "printing_type": printing_type
                    })

        result.sort(key=lambda x: (x["kitchen_station"] or "", len(x["items"])))
        return result

    # ------------------------------------------------------------------
    # print_to_ks_now
    # ------------------------------------------------------------------

    def print_to_ks_now(self, pos_invoice):
        station_payloads = []
        items_to_lock = set()

        for ticket in self.get_branch_menu_for_kitchen_printing(pos_invoice):
            items_to_send = []
            for it in ticket.get("items", []):
                name = it.get("name")
                if not name:
                    continue
                if self.repo.get_item_print_status(name) == 0:
                    items_to_send.append(it)
                    items_to_lock.add(name)

            if items_to_send:
                station_payloads.append({
                    "kitchen_station": ticket.get("kitchen_station"),
                    "printer_name": ticket.get("printer_name"),
                    "pos_invoice": pos_invoice,
                    "items": items_to_send
                })

        for payload in station_payloads:
            kitchen_print_from_payload(payload)

        for name in items_to_lock:
            self.repo.mark_item_printed(name)

        frappe.db.commit()

    # ------------------------------------------------------------------
    # send_to_kitchen
    # ------------------------------------------------------------------

    def send_to_kitchen(self, payload, table_name=None, status=None, taken_by=None,
                        pax=0, customer=None, type_customer=None, orders=None,
                        checked=None, invoice_service=None, table_service=None):
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                frappe.throw("Payload tidak valid JSON")

        if invoice_service is None:
            from resto.services.invoice_service import InvoiceService
            invoice_service = InvoiceService()

        if table_service is None:
            from resto.services.table_service import TableService
            table_service = TableService()

        result = invoice_service.create_pos_invoice(payload)
        pos_name = result["name"]

        table_update_result = None
        if table_name:
            if self.repo.table_exists(table_name):
                if orders is None:
                    orders = []
                elif isinstance(orders, str):
                    try:
                        orders = json.loads(orders)
                    except Exception:
                        orders = []
                if not isinstance(orders, list):
                    orders = []

                if not any(
                    isinstance(o, dict) and o.get("invoice_name") == pos_name
                    for o in orders
                ):
                    orders.append({"invoice_name": pos_name})

                table_update_result = table_service.update_table_status(
                    name=table_name,
                    status=status or "Terisi",
                    taken_by=taken_by,
                    pax=pax,
                    customer=customer,
                    type_customer=type_customer,
                    orders=orders,
                    checked=checked
                )
            else:
                frappe.log_error(
                    f"Take Away POS Invoice {pos_name} tidak terkait table", "send_to_kitchen"
                )

        printing_status = "Printing queued"
        try:
            self.print_to_ks_now(pos_name)
        except Exception as print_err:
            frappe.log_error(frappe.get_traceback(), f"Printing Error for POS {pos_name}")
            printing_status = f"Printing gagal: {str(print_err)}"

        return {
            "status": "success",
            "pos_invoice": pos_name,
            "table_update": table_update_result,
            "message": f"POS Invoice {pos_name} created. {printing_status}"
        }
