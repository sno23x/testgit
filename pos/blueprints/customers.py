from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Customer, Sale

customers_bp = Blueprint("customers", __name__)


@customers_bp.route("/")
@login_required
def list_customers():
    q = request.args.get("q", "")
    query = Customer.query
    if q:
        query = query.filter(db.or_(Customer.name.ilike(f"%{q}%"), Customer.phone.ilike(f"%{q}%")))
    customers = query.order_by(Customer.name).all()
    return render_template("customers/list.html", customers=customers, q=q)


@customers_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_customer():
    if request.method == "POST":
        c = Customer(
            name=request.form.get("name", "").strip(),
            phone=request.form.get("phone", "").strip(),
            address=request.form.get("address", "").strip(),
        )
        db.session.add(c)
        db.session.commit()
        flash("ເພີ່ມລູກຄ້າສໍາເລັດ", "success")
        return redirect(url_for("customers.list_customers"))
    return render_template("customers/form.html", customer=None)


@customers_bp.route("/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(cid):
    c = Customer.query.get_or_404(cid)
    if request.method == "POST":
        c.name = request.form.get("name", c.name).strip()
        c.phone = request.form.get("phone", c.phone).strip()
        c.address = request.form.get("address", c.address).strip()
        db.session.commit()
        flash("ແກ້ໄຂສໍາເລັດ", "success")
        return redirect(url_for("customers.list_customers"))
    return render_template("customers/form.html", customer=c)


@customers_bp.route("/<int:cid>")
@login_required
def customer_detail(cid):
    c = Customer.query.get_or_404(cid)
    sales = Sale.query.filter_by(customer_id=cid).order_by(Sale.created_at.desc()).all()
    return render_template("customers/detail.html", customer=c, sales=sales)
