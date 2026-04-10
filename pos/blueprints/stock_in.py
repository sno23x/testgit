from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, StockIn, Product, Category

stock_in_bp = Blueprint("stock_in", __name__)


@stock_in_bp.route("/")
@login_required
def list_stock_ins():
    page = max(1, int(request.args.get("page", 1) or 1))
    q = request.args.get("q", "")
    query = StockIn.query.join(Product)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    pagination = query.order_by(StockIn.created_at.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template("stock_in/list.html", stock_ins=pagination.items, pagination=pagination, q=q)


@stock_in_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_stock_in():
    products = Product.query.filter_by(active=True).order_by(Product.name).all()
    categories = Category.query.order_by(Category.name).all()
    if request.method == "POST":
        data = request.get_json()
        items = data.get("items", [])
        if not items:
            return jsonify({"error": "ບໍ່ມີລາຍການ"}), 400
        for it in items:
            product = Product.query.get(it["product_id"])
            if not product:
                continue
            qty = float(it["qty"])
            cost = float(it.get("cost_price", product.cost_price or 0))
            si = StockIn(
                product_id=product.id,
                qty=qty,
                cost_price=cost,
                supplier=data.get("supplier", "").strip(),
                note=data.get("note", "").strip(),
                created_by=current_user.id,
            )
            db.session.add(si)
            product.stock_qty += qty
            if cost > 0:
                product.cost_price = cost
        db.session.commit()
        return jsonify({"ok": True})
    return render_template("stock_in/form.html", products=products, categories=categories)
