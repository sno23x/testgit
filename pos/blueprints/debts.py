from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Sale, Customer, DebtPayment
from datetime import datetime, timezone

debts_bp = Blueprint("debts", __name__)


@debts_bp.route("/")
@login_required
def list_debts():
    debt_sales = Sale.query.filter_by(payment_type="debt").filter(Sale.voided == False).order_by(Sale.created_at.desc()).all()
    unpaid = [s for s in debt_sales if not s.is_fully_paid]
    paid = [s for s in debt_sales if s.is_fully_paid]
    return render_template("debts/list.html", unpaid=unpaid, paid=paid)


@debts_bp.route("/<int:sale_id>/pay", methods=["POST"])
@login_required
def pay_debt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    amount = float(request.form.get("amount", 0) or 0)
    note = request.form.get("note", "").strip()

    if amount <= 0:
        flash("ກະລຸນາໃສ່ຈໍານວນເງິນທີ່ຊໍາລະ", "danger")
        return redirect(url_for("debts.list_debts"))

    amount = min(amount, sale.debt_remaining)

    payment = DebtPayment(
        sale_id=sale.id,
        customer_id=sale.customer_id,
        amount=amount,
        note=note,
        paid_at=datetime.now(timezone.utc),
    )
    db.session.add(payment)

    customer = Customer.query.get(sale.customer_id)
    if customer:
        customer.total_debt = max(0, customer.total_debt - amount)

    db.session.commit()
    flash(f"ບັນທຶກການຊໍາລະ {amount:,.0f} ກີບ ສໍາເລັດ", "success")
    return redirect(url_for("debts.list_debts"))
