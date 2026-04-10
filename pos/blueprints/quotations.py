from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Quotation, QuotationItem, Product, Customer, Sale, SaleItem, Setting
from sqlalchemy import func

quotations_bp = Blueprint("quotations", __name__)


def _next_quote_no():
    today = date.today().strftime("%Y%m%d")
    last = Quotation.query.filter(Quotation.quote_no.like(f"Q{today}%")).order_by(Quotation.id.desc()).first()
    seq = (int(last.quote_no[-4:]) + 1) if last else 1
    return f"Q{today}{seq:04d}"


@quotations_bp.route("/")
@login_required
def list_quotations():
    page = max(1, int(request.args.get("page", 1) or 1))
    status = request.args.get("status", "")
    q = request.args.get("q", "")
    query = Quotation.query
    if status:
        query = query.filter_by(status=status)
    if q:
        query = query.filter(Quotation.quote_no.ilike(f"%{q}%") |
                             Quotation.customer_name.ilike(f"%{q}%"))
    pagination = query.order_by(Quotation.created_at.desc()).paginate(page=page, per_page=30, error_out=False)
    return render_template("quotations/list.html", quotations=pagination.items,
                           pagination=pagination, status=status, q=q)


@quotations_bp.route("/create")
@login_required
def create_form():
    customers = Customer.query.order_by(Customer.name).all()
    rate = Setting.get("thb_to_lak", "830")
    return render_template("quotations/form.html", customers=customers, rate=rate)


@quotations_bp.route("/save", methods=["POST"])
@login_required
def save_quotation():
    data = request.get_json()
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "ບໍ່ມີລາຍການ"}), 400

    customer_id = data.get("customer_id") or None
    customer_name = data.get("customer_name", "").strip()
    if customer_id:
        c = Customer.query.get(customer_id)
        if c:
            customer_name = c.name

    subtotal = sum(float(i["qty"]) * float(i["unit_price"]) for i in items)
    discount = float(data.get("discount", 0))
    total = max(0, subtotal - discount)

    qid = data.get("id")
    if qid:
        qt = Quotation.query.get_or_404(qid)
        for old in qt.items:
            db.session.delete(old)
    else:
        qt = Quotation(quote_no=_next_quote_no(), created_by=current_user.id)
        db.session.add(qt)

    qt.customer_id = customer_id
    qt.customer_name = customer_name
    qt.subtotal = subtotal
    qt.discount = discount
    qt.total = total
    qt.note = data.get("note", "").strip()
    qt.valid_days = int(data.get("valid_days", 30))
    qt.status = data.get("status", "draft")
    db.session.flush()

    for it in items:
        p = Product.query.get(it["product_id"]) if it.get("product_id") else None
        qi = QuotationItem(
            quotation_id=qt.id,
            product_id=it.get("product_id"),
            description=it.get("description", p.name if p else ""),
            unit=it.get("unit", p.unit if p else ""),
            qty=float(it["qty"]),
            unit_price=float(it["unit_price"]),
            subtotal=float(it["qty"]) * float(it["unit_price"]),
        )
        db.session.add(qi)

    db.session.commit()
    return jsonify({"ok": True, "id": qt.id, "quote_no": qt.quote_no})


@quotations_bp.route("/<int:qid>")
@login_required
def view_quotation(qid):
    qt = Quotation.query.get_or_404(qid)
    shop_name = Setting.get("shop_name", "ຮ້ານວັດສະດຸກໍ່ສ້າງ")
    shop_address = Setting.get("shop_address", "")
    shop_phone = Setting.get("shop_phone", "")
    return render_template("quotations/view.html", qt=qt,
                           shop_name=shop_name, shop_address=shop_address, shop_phone=shop_phone)


@quotations_bp.route("/<int:qid>/status", methods=["POST"])
@login_required
def update_status(qid):
    qt = Quotation.query.get_or_404(qid)
    qt.status = request.form.get("status", qt.status)
    db.session.commit()
    flash(f"ອັບເດດສະຖານະເປັນ {qt.status}", "success")
    return redirect(url_for("quotations.view_quotation", qid=qid))


@quotations_bp.route("/<int:qid>/convert", methods=["POST"])
@login_required
def convert_to_sale(qid):
    from blueprints.pos import next_sale_no
    qt = Quotation.query.get_or_404(qid)
    if qt.status not in ("draft", "sent", "accepted"):
        flash("ບໍ່ສາມາດ convert ໄດ້", "danger")
        return redirect(url_for("quotations.view_quotation", qid=qid))

    sale = Sale(
        sale_no=next_sale_no(),
        customer_id=qt.customer_id,
        employee_id=current_user.id,
        subtotal=qt.subtotal,
        discount=qt.discount,
        total=qt.total,
        payment_type="cash",
        currency="LAK",
        paid_amount=qt.total,
        note=f"ຈາກໃບສະເໜີ {qt.quote_no}",
    )
    db.session.add(sale)
    db.session.flush()

    for qi in qt.items:
        if qi.product_id:
            p = Product.query.get(qi.product_id)
            deduct = qi.qty * 20 if (p and p.unit == "ໂຕນ") else qi.qty
            if p:
                p.stock_qty = max(0, p.stock_qty - deduct)
        si = SaleItem(sale_id=sale.id, product_id=qi.product_id,
                      qty=qi.qty, unit_price=qi.unit_price, subtotal=qi.subtotal)
        db.session.add(si)

    qt.status = "accepted"
    db.session.commit()
    flash(f"ສ້າງບິນ {sale.sale_no} ສຳເລັດ", "success")
    return redirect(url_for("pos.receipt", sale_id=sale.id))
