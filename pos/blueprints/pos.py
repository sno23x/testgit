import json
from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Product, Customer, Sale, SaleItem, Employee

pos_bp = Blueprint("pos", __name__)


def next_sale_no():
    today = date.today().strftime("%Y%m%d")
    last = Sale.query.filter(Sale.sale_no.like(f"S{today}%")).order_by(Sale.id.desc()).first()
    if last:
        seq = int(last.sale_no[-4:]) + 1
    else:
        seq = 1
    return f"S{today}{seq:04d}"


@pos_bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    sales_today = Sale.query.filter(
        db.func.date(Sale.created_at) == today
    ).all()
    revenue_today = sum(s.total for s in sales_today if s.payment_type == "cash")
    debt_today = sum(s.total for s in sales_today if s.payment_type == "debt")
    tx_count = len(sales_today)

    # Monthly revenue last 6 months
    from sqlalchemy import extract, func
    monthly = db.session.query(
        extract("year", Sale.created_at).label("y"),
        extract("month", Sale.created_at).label("m"),
        func.sum(Sale.total).label("total")
    ).group_by("y", "m").order_by("y", "m").limit(12).all()

    # Unpaid debts
    debt_sales = Sale.query.filter_by(payment_type="debt").all()
    total_debt_outstanding = sum(s.debt_remaining for s in debt_sales)

    # Low stock
    low_stock = Product.query.filter(Product.stock_qty <= 5, Product.active == True).all()

    return render_template("dashboard.html",
        revenue_today=revenue_today,
        debt_today=debt_today,
        tx_count=tx_count,
        total_debt_outstanding=total_debt_outstanding,
        low_stock=low_stock,
        monthly=monthly,
    )


@pos_bp.route("/")
@login_required
def pos_page():
    customers = Customer.query.order_by(Customer.name).all()
    return render_template("pos/index.html", customers=customers)


@pos_bp.route("/search")
@login_required
def search_product():
    q = request.args.get("q", "").strip()
    results = Product.query.filter(
        Product.active == True,
        db.or_(Product.name.ilike(f"%{q}%"), Product.code.ilike(f"%{q}%"))
    ).limit(20).all()
    return jsonify([p.to_dict() for p in results])


@pos_bp.route("/sale", methods=["POST"])
@login_required
def create_sale():
    data = request.get_json()
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "ບໍ່ມີລາຍການ"}), 400

    payment_type = data.get("payment_type", "cash")
    customer_id = data.get("customer_id") or None
    discount = float(data.get("discount", 0))
    note = data.get("note", "")

    if payment_type == "debt" and not customer_id:
        return jsonify({"error": "ຕ້ອງເລືອກລູກຄ້າເມື່ອຕິດໜີ້"}), 400

    subtotal = 0
    sale_items = []
    for it in items:
        product = Product.query.get(it["product_id"])
        if not product:
            continue
        qty = float(it["qty"])
        price = float(it.get("unit_price", product.sell_price))
        sub = qty * price
        subtotal += sub
        sale_items.append((product, qty, price, sub))

    total = max(0, subtotal - discount)

    sale = Sale(
        sale_no=next_sale_no(),
        customer_id=customer_id,
        employee_id=current_user.id,
        subtotal=subtotal,
        discount=discount,
        total=total,
        payment_type=payment_type,
        paid_amount=total if payment_type == "cash" else 0,
        note=note,
    )
    db.session.add(sale)
    db.session.flush()

    for product, qty, price, sub in sale_items:
        item = SaleItem(sale_id=sale.id, product_id=product.id,
                        qty=qty, unit_price=price, subtotal=sub)
        db.session.add(item)
        product.stock_qty = max(0, product.stock_qty - qty)

    if payment_type == "debt" and customer_id:
        customer = Customer.query.get(customer_id)
        if customer:
            customer.total_debt += total

    db.session.commit()
    return jsonify({"sale_id": sale.id, "sale_no": sale.sale_no})


@pos_bp.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template("pos/receipt.html", sale=sale)
