import frappe


class DiscountRepository:
    def get_discounts_with_options(self):
        discounts = frappe.get_all("Discount", fields=["name", "description"])

        result = []
        for d in discounts:
            doc = frappe.get_doc("Discount", d.name)
            result.append({
                "name": doc.name,
                "description": doc.description,
                "discount_options": [
                    {
                        "label": o.label,
                        "discount_type": o.discount_type,
                        "value": o.value,
                        "min_sales_price": o.min_sales_price,
                        "max_discount": o.max_discount,
                        "start_date": o.start_date,
                        "end_date": o.end_date,
                    }
                    for o in doc.discount_options
                ],
                "menu_category": [
                    {"menu_name": m.menu_name}
                    for m in doc.menu_category
                ],
            })

        return result
