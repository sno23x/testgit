from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import db, Product, Category, Setting


def _compute_sell_price(price_thb, sell_price_manual):
    """ຖ້າໃສ່ລາຄາ THB ຈະຄຳນວນ LAK ອັດຕະໂນມັດ, ຖ້າບໍ່ໃຊ້ ລາຄາ LAK ທີ່ກຳນົດ"""
    thb = float(price_thb or 0)
    if thb > 0:
        try:
            rate = float(Setting.get("thb_to_lak", "830"))
        except ValueError:
            rate = 830.0
        return round(thb * rate), thb
    return float(sell_price_manual or 0), None

products_bp = Blueprint("products", __name__)


@products_bp.route("/")
@login_required
def list_products():
    q = request.args.get("q", "")
    cat_id = request.args.get("cat", "")
    query = Product.query.filter_by(active=True)
    if q:
        query = query.filter(db.or_(Product.name.ilike(f"%{q}%"), Product.code.ilike(f"%{q}%")))
    if cat_id:
        query = query.filter_by(category_id=int(cat_id))
    products = query.order_by(Product.name).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template("products/list.html", products=products, categories=categories,
                           q=q, cat_id=cat_id)


@products_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_product():
    categories = Category.query.order_by(Category.name).all()
    rate = Setting.get("thb_to_lak", "830")
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if not code:
            last = Product.query.order_by(Product.id.desc()).first()
            code = f"P{(last.id + 1 if last else 1):05d}"
        sell_price, price_thb = _compute_sell_price(
            request.form.get("price_thb"), request.form.get("sell_price")
        )
        p = Product(
            code=code,
            name=request.form.get("name", "").strip(),
            unit=request.form.get("unit", "ອັນ").strip(),
            cost_price=float(request.form.get("cost_price", 0) or 0),
            price_thb=price_thb,
            sell_price=sell_price,
            stock_qty=float(request.form.get("stock_qty", 0) or 0),
            category_id=int(request.form.get("category_id")) if request.form.get("category_id") else None,
        )
        db.session.add(p)
        db.session.commit()
        flash("ເພີ່ມສິນຄ້າສໍາເລັດ", "success")
        return redirect(url_for("products.list_products"))
    return render_template("products/form.html", product=None, categories=categories, rate=rate)


@products_bp.route("/<int:pid>/edit", methods=["GET", "POST"])
@login_required
def edit_product(pid):
    p = Product.query.get_or_404(pid)
    categories = Category.query.order_by(Category.name).all()
    rate = Setting.get("thb_to_lak", "830")
    if request.method == "POST":
        p.code = request.form.get("code", p.code).strip()
        p.name = request.form.get("name", p.name).strip()
        p.unit = request.form.get("unit", p.unit).strip()
        p.cost_price = float(request.form.get("cost_price", 0) or 0)
        p.stock_qty = float(request.form.get("stock_qty", 0) or 0)
        p.category_id = int(request.form.get("category_id")) if request.form.get("category_id") else None
        sell_price, price_thb = _compute_sell_price(
            request.form.get("price_thb"), request.form.get("sell_price")
        )
        p.price_thb = price_thb
        p.sell_price = sell_price
        db.session.commit()
        flash("ແກ້ໄຂສໍາເລັດ", "success")
        return redirect(url_for("products.list_products"))
    return render_template("products/form.html", product=p, categories=categories, rate=rate)


@products_bp.route("/<int:pid>/delete", methods=["POST"])
@login_required
def delete_product(pid):
    p = Product.query.get_or_404(pid)
    p.active = False
    db.session.commit()
    flash("ລຶບສິນຄ້າສໍາເລັດ", "success")
    return redirect(url_for("products.list_products"))


# --- Categories ---
@products_bp.route("/categories")
@login_required
def list_categories():
    cats = Category.query.order_by(Category.name).all()
    return render_template("products/categories.html", categories=cats)


@products_bp.route("/categories/add", methods=["POST"])
@login_required
def add_category():
    name = request.form.get("name", "").strip()
    if name:
        db.session.add(Category(name=name))
        db.session.commit()
        flash("ເພີ່ມໝວດໝູ່ສໍາເລັດ", "success")
    return redirect(url_for("products.list_categories"))


@products_bp.route("/categories/<int:cid>/delete", methods=["POST"])
@login_required
def delete_category(cid):
    cat = Category.query.get_or_404(cid)
    db.session.delete(cat)
    db.session.commit()
    flash("ລຶບໝວດໝູ່ສໍາເລັດ", "success")
    return redirect(url_for("products.list_categories"))


# --- Bulk operations ---
@products_bp.route("/bulk-delete", methods=["POST"])
@login_required
def bulk_delete():
    data = request.get_json()
    ids = data.get("ids", [])
    if not ids:
        return jsonify({"ok": False, "error": "ບໍ່ມີ ID"})
    Product.query.filter(Product.id.in_(ids)).update({"active": False}, synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True})


@products_bp.route("/bulk-category", methods=["POST"])
@login_required
def bulk_category():
    data = request.get_json()
    ids = data.get("ids", [])
    cat_id = data.get("category_id")
    if not ids or not cat_id:
        return jsonify({"ok": False, "error": "ຂໍ້ມູນບໍ່ຄົບ"})
    Product.query.filter(Product.id.in_(ids)).update({"category_id": cat_id}, synchronize_session=False)
    db.session.commit()
    return jsonify({"ok": True})
