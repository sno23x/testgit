from datetime import datetime, timezone, date
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import extract, func
from models import db, Product, Customer, Sale, SaleItem, Employee, Setting, round_price

pos_bp = Blueprint("pos", __name__)


def next_sale_no():
    today = date.today().strftime("%Y%m%d")
    last = Sale.query.filter(Sale.sale_no.like(f"S{today}%")).order_by(Sale.id.desc()).first()
    seq = (int(last.sale_no[-4:]) + 1) if last else 1
    return f"S{today}{seq:04d}"


# ──────────────── Dashboard ────────────────
@pos_bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    sales_today = Sale.query.filter(db.func.date(Sale.created_at) == today).all()
    revenue_today = sum(s.total for s in sales_today if s.payment_type == "cash")
    debt_today    = sum(s.total for s in sales_today if s.payment_type == "debt")
    tx_count      = len(sales_today)

    monthly_rows = db.session.query(
        extract("year",  Sale.created_at).label("y"),
        extract("month", Sale.created_at).label("m"),
        func.sum(Sale.total).label("total")
    ).group_by("y", "m").order_by("y", "m").limit(12).all()
    monthly = [(int(r.y), int(r.m), float(r.total)) for r in monthly_rows]

    debt_sales = Sale.query.filter_by(payment_type="debt").all()
    total_debt_outstanding = sum(s.debt_remaining for s in debt_sales)
    low_stock = Product.query.filter(Product.stock_qty <= 5, Product.active == True).all()

    return render_template("dashboard.html",
        revenue_today=revenue_today, debt_today=debt_today,
        tx_count=tx_count, total_debt_outstanding=total_debt_outstanding,
        low_stock=low_stock, monthly=monthly)


# ──────────────── POS page ────────────────
@pos_bp.route("/")
@login_required
def pos_page():
    customers = Customer.query.order_by(Customer.name).all()
    rate = Setting.get("thb_to_lak", "830")
    return render_template("pos/index.html", customers=customers, rate=rate)


# ──────────────── Product search (text + barcode) ────────────────
@pos_bp.route("/search")
@login_required
def search_product():
    q = request.args.get("q", "").strip()
    results = Product.query.filter(
        Product.active == True,
        db.or_(Product.name.ilike(f"%{q}%"), Product.code.ilike(f"%{q}%"))
    ).limit(20).all()
    return jsonify([p.to_dict() for p in results])


# ──────────────── Customer lookup (phone or name) ────────────────
@pos_bp.route("/customer-lookup")
@login_required
def customer_lookup():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    customers = Customer.query.filter(
        db.or_(Customer.phone.ilike(f"%{q}%"), Customer.name.ilike(f"%{q}%"))
    ).limit(10).all()
    return jsonify([{
        "id": c.id, "name": c.name,
        "phone": c.phone, "debt": c.total_debt
    } for c in customers])


# ──────────────── Product suggestions ────────────────
@pos_bp.route("/suggestions")
@login_required
def suggestions():
    mode = request.args.get("mode", "bestseller")

    if mode == "recent":
        # ສິນຄ້າທີ່ຫາກໍ່ຂາຍ (10 ລາຍການຫຼ້າສຸດ ທີ່ຕ່າງກັນ)
        sub = db.session.query(SaleItem.product_id, func.max(Sale.created_at).label("last_sold"))\
            .join(Sale)\
            .group_by(SaleItem.product_id)\
            .order_by(func.max(Sale.created_at).desc())\
            .limit(12).subquery()
        rows = db.session.query(Product).join(sub, Product.id == sub.c.product_id)\
            .filter(Product.active == True).all()
    else:
        # ສິນຄ້າຂາຍດີ (by total qty)
        sub = db.session.query(SaleItem.product_id, func.sum(SaleItem.qty).label("total_qty"))\
            .group_by(SaleItem.product_id)\
            .order_by(func.sum(SaleItem.qty).desc())\
            .limit(12).subquery()
        rows = db.session.query(Product).join(sub, Product.id == sub.c.product_id)\
            .filter(Product.active == True).all()

    return jsonify([p.to_dict() for p in rows])


# ──────────────── Create sale ────────────────
@pos_bp.route("/sale", methods=["POST"])
@login_required
def create_sale():
    data = request.get_json()
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "ບໍ່ມີລາຍການ"}), 400

    payment_type = data.get("payment_type", "cash")
    currency     = data.get("currency", "LAK")        # LAK / THB
    customer_id  = data.get("customer_id") or None
    discount     = float(data.get("discount", 0))
    note         = data.get("note", "")

    if payment_type == "debt" and not customer_id:
        return jsonify({"error": "ຕ້ອງເລືອກລູກຄ້າສຳລັບການຈັດສົ່ງ (ຄ້າງຊຳລະ)"}), 400

    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except ValueError:
        rate = 830.0

    subtotal = 0
    sale_items = []
    for it in items:
        product = Product.query.get(it["product_id"])
        if not product:
            continue
        qty        = float(it["qty"])
        unit_price = float(it.get("unit_price", product.sell_price))
        sub        = qty * unit_price
        subtotal  += sub
        sale_items.append((product, qty, unit_price, sub))

    total_kip = max(0, subtotal - discount)

    # ຖ້າຊໍາລະເປັນ THB ຄຳນວນຍອດ LAK ຄືເດີມ, ແຕ່ record currency
    sale = Sale(
        sale_no=next_sale_no(),
        customer_id=customer_id,
        employee_id=current_user.id,
        subtotal=subtotal,
        discount=discount,
        total=total_kip,
        payment_type=payment_type,
        currency=currency,
        paid_amount=total_kip if payment_type in ("cash", "transfer") else 0,
        note=note,
    )
    db.session.add(sale)
    db.session.flush()

    for product, qty, price, sub in sale_items:
        si = SaleItem(sale_id=sale.id, product_id=product.id,
                      qty=qty, unit_price=price, subtotal=sub)
        db.session.add(si)
        product.stock_qty = max(0, product.stock_qty - qty)

    if payment_type == "debt" and customer_id:
        cust = Customer.query.get(customer_id)
        if cust:
            cust.total_debt += total_kip

    db.session.commit()
    return jsonify({"sale_id": sale.id, "sale_no": sale.sale_no})


# ──────────────── Receipt ────────────────
@pos_bp.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except Exception:
        rate = 830.0
    try:
        receipt_rows = int(Setting.get("receipt_rows", "15"))
    except Exception:
        receipt_rows = 15
    return render_template("pos/receipt.html", sale=sale,
        shop_name=Setting.get("shop_name", "ຮ້ານວັດສະດຸກໍ່ສ້າງ"),
        shop_address=Setting.get("shop_address", ""),
        shop_phone=Setting.get("shop_phone", ""),
        shop_qr=Setting.get("shop_qr", ""),
        receipt_footer=Setting.get("receipt_footer", ""),
        receipt_auto_print=Setting.get("receipt_auto_print", "1"),
        receipt_rows=receipt_rows,
        rate=rate)
