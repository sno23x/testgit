"""
ນໍາເຂົ້າສິນຄ້າຈາກ Excel
ໂຄງສ້າງ column ທີ່ຮອງຮັບ:
  B/BARCODE, C/ຊື່ສິນຄ້າ, D/ປະເພດ, E/ລາຄາ, F/THB (flag), G/Stock, H/ໜ່ວຍ
"""
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Product, Category, Setting, round_price
import openpyxl

import_bp = Blueprint("import_data", __name__)

UNIT_PRESETS = ["ອັນ","ຖົງ","ກ",("ໂຕນ","ກິໂລ","ລິດ","ກ່ອງ","ທ່ອນ","ດຳ","ແຜ່ນ","ຄູ່","ເຕ","ດ້ານ","ຫ່ໍ","ຈ່ຽງ")][0:1] + \
    ["ຖົງ","ກ","ໂຕນ","ກິໂລ","ລິດ","ກ່ອງ","ທ່ອນ","ດຳ","ແຜ່ນ","ຄູ່","ເຕ","ດ້ານ","ຫ່ໍ","ຈ່ຽງ"]


@import_bp.route("/products", methods=["GET", "POST"])
@login_required
def import_products():
    if request.method == "POST":
        f = request.files.get("excel_file")
        if not f or not f.filename.endswith((".xlsx", ".xls")):
            flash("ກະລຸນາເລືອກໄຟລ໌ Excel (.xlsx)", "danger")
            return redirect(url_for("import_data.import_products"))

        try:
            rate = float(Setting.get("thb_to_lak", "830"))
        except Exception:
            rate = 830.0

        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = wb.active

        rows = list(ws.iter_rows(values_only=True))
        # ຫາ header row (ຊອກ "BARCODE" ຫຼື "barcode")
        header_idx = 0
        for i, row in enumerate(rows):
            cells = [str(c).strip().upper() if c else "" for c in row]
            if "BARCODE" in cells or any("ຊື່ສິນຄ້າ" in str(c) for c in row if c):
                header_idx = i
                break

        headers = [str(c).strip().upper() if c else "" for c in rows[header_idx]]

        def col(name_variants):
            for v in name_variants:
                if v.upper() in headers:
                    return headers.index(v.upper())
            return None

        idx_code  = col(["BARCODE","CODE","ລະຫັດ","B"])
        idx_name  = col(["ຊື່ສິນຄ້າ","ຊື່","NAME","C"])
        idx_type  = col(["ປະເພດ","ໝວດ","TYPE","CATEGORY","D"])
        idx_price = col(["ລາຄາ","PRICE","E"])
        idx_curr  = col(["THB","CURRENCY","F"])
        idx_stock = col(["STOCK","ສ ock","ຈໍານວນ","G"])
        idx_unit  = col(["ໜ່ວຍ","UNIT","H"])

        added = updated = skipped = 0
        for row in rows[header_idx + 1:]:
            if not row or not any(row):
                continue

            def cell(i):
                return str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else ""

            code  = cell(idx_code) if idx_code is not None else ""
            name  = cell(idx_name) if idx_name is not None else ""
            if not name:
                skipped += 1
                continue

            if not code:
                last = Product.query.order_by(Product.id.desc()).first()
                code = f"P{(last.id + 1 if last else 1):05d}"

            # ລາຄາ
            try:
                raw_price = float(str(cell(idx_price)).replace(",", "")) if idx_price is not None else 0
            except Exception:
                raw_price = 0

            is_thb = "THB" in str(cell(idx_curr)).upper() if idx_curr is not None else False
            if is_thb and raw_price > 0:
                price_thb = raw_price
                sell_price = round_price(raw_price * rate)
            else:
                price_thb = None
                sell_price = int(raw_price)

            try:
                stock = float(str(cell(idx_stock)).replace(",","")) if idx_stock is not None else 0
            except Exception:
                stock = 0

            unit = cell(idx_unit) if idx_unit is not None else "ອັນ"
            cat_name = cell(idx_type) if idx_type is not None else ""

            # Category
            cat = None
            if cat_name:
                cat = Category.query.filter_by(name=cat_name).first()
                if not cat:
                    cat = Category(name=cat_name)
                    db.session.add(cat)
                    db.session.flush()

            existing = Product.query.filter_by(code=code).first()
            if existing:
                existing.name       = name
                existing.unit       = unit or existing.unit
                existing.price_thb  = price_thb
                existing.sell_price = sell_price or existing.sell_price
                existing.stock_qty  = stock
                if cat:
                    existing.category_id = cat.id
                updated += 1
            else:
                p = Product(code=code, name=name, unit=unit or "ອັນ",
                            price_thb=price_thb, sell_price=max(sell_price, 1),
                            stock_qty=stock,
                            category_id=cat.id if cat else None)
                db.session.add(p)
                added += 1

        db.session.commit()
        flash(f"ນໍາເຂົ້າສໍາເລັດ: ເພີ່ມ {added} | ອັບເດດ {updated} | ຂ້າມ {skipped}", "success")
        return redirect(url_for("products.list_products"))

    return render_template("products/import.html")
