import frappe
from frappe.utils import flt, now_datetime, get_datetime
from resto.repositories.reporting_repository import ReportingRepository


class ReportingService:
    def __init__(self, repo=None):
        self.repo = repo or ReportingRepository()

    # ------------------------------------------------------------------
    # get_end_day_report (v1)
    # ------------------------------------------------------------------

    def get_end_day_report(self, posting_date=None, outlet=None):
        posting_date = posting_date or frappe.form_dict.get("posting_date")
        outlet = outlet or frappe.form_dict.get("outlet")

        if not posting_date or not outlet:
            frappe.throw("posting_date dan outlet wajib diisi")

        outlet_filter = self.repo.detect_outlet_filter(outlet)

        invoices = self.repo.get_submitted_invoices(posting_date, outlet_filter)
        invoice_names = [i.name for i in invoices]

        if not invoice_names:
            return {"message": "No POS Invoice found"}

        sub_total = self.repo.get_sub_total(invoice_names)
        discount = self.repo.get_discount_total(invoice_names)
        tax = self.repo.get_tax_total(invoice_names)
        grand_total = sub_total + tax - discount

        summary = {
            "sub_total": sub_total,
            "discount": discount,
            "tax": tax,
            "grand_total": grand_total
        }

        dine_in, take_away = {}, {}
        for i in self.repo.get_items_by_order_type(invoice_names):
            target = dine_in if i.order_type == "Dine In" else take_away
            target[i.item_group] = {"qty": int(i.qty), "amount": flt(i.amount)}

        payment_summary = {
            p.mode_of_payment: flt(p.amount)
            for p in self.repo.get_payments_summary(invoice_names)
        }

        tax_summary = {
            t.description: flt(t.amount)
            for t in self.repo.get_taxes_summary(invoice_names)
        }

        discount_by_order_type = {}
        for d in self.repo.get_discount_by_order_type(invoice_names):
            discount_by_order_type[d.order_type or "Unknown"] = {
                "total_qty": int(d.total_bill),
                "total_amount": flt(d.total_discount)
            }

        discount_by_bank = {}
        for d in self.repo.get_discount_by_bank(invoice_names):
            key = d.discount_for_bank or "Unknown Bank"
            discount_by_bank.setdefault(key, [])
            discount_by_bank[key].append({
                "discount_name": d.discount_name or "-",
                "total_bill": int(d.total_bill),
                "total_amount": flt(d.total_discount)
            })

        void_items = self.repo.get_void_items(posting_date, outlet_filter)
        void_item_summary = {
            "total_qty": sum(int(v.qty or 0) for v in void_items),
            "total_amount": sum(flt(v.amount or 0) for v in void_items),
            "details": [
                {"item_name": v.item_name, "qty": int(v.qty), "amount": flt(v.amount)}
                for v in void_items
            ]
        }

        void_bills = self.repo.get_void_bills(posting_date, outlet_filter)
        void_bill_summary = {
            "total_bill": len(void_bills),
            "total_amount": sum(flt(v.grand_total) for v in void_bills)
        }

        return {
            "posting_date": posting_date,
            "outlet_filter": outlet_filter,
            "summary": summary,
            "dine_in": dine_in,
            "take_away": take_away,
            "payments": payment_summary,
            "taxes": tax_summary,
            "discount_by_order_type": discount_by_order_type,
            "discount_by_bank": discount_by_bank,
            "void_item": void_item_summary,
            "void_bill": void_bill_summary
        }

    # ------------------------------------------------------------------
    # get_end_day_report_v2
    # ------------------------------------------------------------------

    def get_end_day_report_v2(self, posting_date=None, outlet=None, do_print=False):
        posting_date = posting_date or frappe.form_dict.get("posting_date")
        outlet = outlet or frappe.form_dict.get("outlet")
        do_print = do_print or frappe.form_dict.get("print")

        if not posting_date or not outlet:
            frappe.throw("posting_date dan outlet wajib diisi")

        outlet_filter = self.repo.detect_outlet_filter(outlet)

        paid_invoices = self.repo.get_paid_invoices(posting_date, outlet_filter)
        paid_invoice_names = [i.name for i in paid_invoices]
        draft_invoices = self.repo.get_draft_invoices(posting_date, outlet_filter)

        if not paid_invoice_names:
            return {
                "message": "No PAID POS Invoice found",
                "draft": {
                    "total_bill": len(draft_invoices),
                    "total_amount": sum(flt(d.grand_total) for d in draft_invoices)
                }
            }

        sub_total = self.repo.get_sub_total_v2(paid_invoice_names)
        discount = self.repo.get_discount_total_v2(paid_invoice_names)
        tax = self.repo.get_tax_total_v2(paid_invoice_names)
        total_pax = self.repo.get_pax_total(paid_invoice_names)

        summary = {
            "sub_total": int(sub_total),
            "discount": int(discount),
            "tax": int(tax),
            "grand_total": int(sub_total + tax - discount),
            "total_pax": int(total_pax)
        }

        dine_in, take_away = {}, {}
        for i in self.repo.get_items_by_order_type_v2(paid_invoice_names):
            target = dine_in if i.order_type == "Dine In" else take_away
            target[i.item_group] = {"qty": int(i.qty), "amount": flt(i.amount)}

        payment_summary = {
            p.mode_of_payment: flt(p.amount)
            for p in self.repo.get_payments_summary_v2(paid_invoice_names)
        }

        tax_summary = {
            t.description: flt(t.amount)
            for t in self.repo.get_taxes_summary_v2(paid_invoice_names)
        }

        discount_order_type = {
            f"{d.discount_for_bank or ''} {d.discount_name or 'No Name'}": {
                "total_bill": int(d.total_bill),
                "total_amount": abs(flt(d.total_amount))
            }
            for d in self.repo.get_discount_by_order_type_v2(paid_invoice_names)
        }

        draft_summary = {
            "total_bill": len(draft_invoices),
            "total_amount": sum(flt(d.grand_total) for d in draft_invoices),
            "details": [
                {"invoice": d.name, "order_type": d.order_type, "amount": flt(d.grand_total)}
                for d in draft_invoices
            ]
        }

        void_bills = self.repo.get_void_bills_v2(posting_date, outlet_filter)
        void_bill_summary = {
            "total_bill": len(void_bills),
            "total_amount": sum(flt(v.rounded_total) for v in void_bills),
            "details": [
                {"invoice": v.name, "amount": flt(v.rounded_total)}
                for v in void_bills
            ]
        }

        void_summary = {"total_qty": 0, "total_amount": 0, "items": {}}
        for inv in self.repo.get_void_invoices_with_items(posting_date, outlet):
            for vi in self.repo.get_void_invoice_items(inv.name):
                qty = int(vi.void_qty or 0)
                if qty <= 0:
                    continue
                item_name = vi.item_name or "Unknown"
                amount = flt((vi.void_rate or 0) * qty)
                void_summary["total_qty"] += qty
                void_summary["total_amount"] += amount
                void_summary["items"].setdefault(item_name, {"qty": 0, "amount": 0})
                void_summary["items"][item_name]["qty"] += qty
                void_summary["items"][item_name]["amount"] += amount

        result = {
            "posting_date": posting_date,
            "outlet_filter": outlet_filter,
            "outlet": outlet,
            "summary": summary,
            "dine_in": dine_in,
            "take_away": take_away,
            "payments": payment_summary,
            "taxes": tax_summary,
            "discount_by_order_type": discount_order_type,
            "draft": draft_summary,
            "void_bill": void_bill_summary,
            "void_menu": void_summary
        }

        if do_print:
            try:
                from resto.printing import print_end_day_report_v2
                printer = self.repo.get_printer_for_branch(outlet)
                print_end_day_report_v2(result, printer)
            except Exception as e:
                frappe.log_error(str(e), "End Day Report Print Error")

        return result

    # ------------------------------------------------------------------
    # end_shift
    # ------------------------------------------------------------------

    def end_shift(self, user=None, is_submit=True):
        try:
            from resto.printing import print_shift_report
        except Exception:
            print_shift_report = None

        user = user or frappe.session.user

        opening = self.repo.get_active_opening_for_user(user)
        opening_doc = frappe.get_doc("POS Opening Entry", opening.name)
        opening_dt = get_datetime(opening_doc.period_start_date)

        invoices = self.repo.get_paid_invoices_for_closing(opening_doc.pos_profile)

        if not invoices:
            frappe.throw("Tidak ada POS Invoice")

        for invoice in invoices:
            self.repo.set_invoice_owner(invoice.name, opening_doc.user)
        frappe.db.commit()

        closing = frappe.new_doc("POS Closing Entry")
        closing.pos_opening_entry = opening_doc.name
        closing.company = opening_doc.company
        closing.pos_profile = opening_doc.pos_profile
        closing.user = opening_doc.user
        closing.posting_date = frappe.utils.today()
        closing.posting_time = frappe.utils.nowtime()
        closing.period_start_date = opening_doc.period_start_date
        closing.period_end_date = now_datetime()

        total_qty = 0
        net_total = 0
        tax_total = 0
        grand_total = 0
        payment_map = {}
        tax_map = {}
        discount_map = {}

        for row in invoices:
            inv_dt = get_datetime(f"{row.posting_date} {row.posting_time}")
            if inv_dt < opening_dt:
                continue

            doc = self.repo.get_invoice_doc(row.name)

            closing.append("pos_transactions", {
                "pos_invoice": doc.name,
                "posting_date": doc.posting_date,
                "customer": doc.customer,
                "grand_total": doc.grand_total,
                "is_return": doc.is_return or 0,
                "return_against": doc.return_against
            })

            total_qty += flt(doc.total_qty)
            net_total += flt(doc.net_total)
            tax_total += flt(doc.total_taxes_and_charges)
            grand_total += flt(doc.grand_total)

            discount_added = False
            for t in doc.taxes:
                if not t.tax_amount:
                    continue

                tax_key = (t.account_head, t.charge_type, flt(t.rate))
                if tax_key not in tax_map:
                    tax_map[tax_key] = {
                        "account_head": t.account_head,
                        "charge_type": t.charge_type,
                        "rate": flt(t.rate),
                        "tax_amount": 0,
                        "total": 0
                    }
                tax_map[tax_key]["tax_amount"] += flt(t.tax_amount)
                tax_map[tax_key]["total"] += flt(t.tax_amount)

                if flt(t.tax_amount) >= 0:
                    continue

                discount_key = f"{doc.discount_for_bank or ''} {doc.discount_name or 'No Name'}"
                if discount_key not in discount_map:
                    discount_map[discount_key] = {"total_bill": 0, "total_amount": 0}
                discount_map[discount_key]["total_amount"] += abs(flt(t.tax_amount))
                if not discount_added:
                    discount_map[discount_key]["total_bill"] += 1
                    discount_added = True

            payment_rows = doc.payments or []
            original_payment_total = sum(flt(p.amount) for p in payment_rows) or 1
            scale = flt(doc.grand_total) / original_payment_total
            for p in payment_rows:
                payment_map.setdefault(p.mode_of_payment, 0)
                payment_map[p.mode_of_payment] += flt(p.amount) * scale

        if not closing.pos_transactions:
            frappe.throw("Tidak ada transaksi POS valid setelah opening")

        closing.total_quantity = total_qty
        closing.net_total = net_total
        closing.total_taxes_and_charges = tax_total
        closing.grand_total = grand_total

        for tax in tax_map.values():
            closing.append("taxes", {
                "charge_type": tax["charge_type"],
                "account_head": tax["account_head"],
                "rate": tax["rate"],
                "amount": tax["tax_amount"],
                "total": tax["total"]
            })

        for mop, amount in payment_map.items():
            closing.append("payment_reconciliation", {
                "mode_of_payment": mop,
                "opening_amount": 0,
                "expected_amount": amount,
                "closing_amount": amount,
                "difference": 0
            })

        closing.validate_pos_invoices()
        closing.validate_duplicate_pos_invoices()

        closing.insert()
        frappe.db.commit()

        if is_submit:
            closing1 = frappe.get_doc("POS Closing Entry", closing.name)
            closing1.submit()
            frappe.db.commit()

        if print_shift_report:
            try:
                default_printer_receipt = self.repo.get_printer_for_branch(
                    opening_doc.branch, "default_printer_receipt"
                )
                print_shift_report(closing.name, default_printer_receipt)
            except Exception as e:
                frappe.log_error(f"Error printing shift report: {str(e)}", "Print Error")

        return {
            "closing_entry": closing.name,
            "total_invoice": len(closing.pos_transactions),
            "grand_total": closing.grand_total,
            "total_quantity": closing.total_quantity,
            "tax_total": closing.total_taxes_and_charges,
            "payments": payment_map,
            "discount_detail": discount_map
        }
