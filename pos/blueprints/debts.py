from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Sale, Customer, DebtPayment, Setting
from datetime import datetime, timezone

debts_bp = Blueprint("debts", __name__)


@debts_bp.route("/")
@login_required
def list_debts():
    debt_sales = (Sale.query
                  .filter_by(payment_type="debt")
                  .filter(Sale.voided == False)
                  .order_by(Sale.created_at.desc()).all())
    unpaid = [s for s in debt_sales if not s.is_fully_paid]
    paid   = [s for s in debt_sales if s.is_fully_paid]
    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except Exception:
        rate = 830.0
    return render_template("debts/list.html", unpaid=unpaid, paid=paid, rate=rate)


@debts_bp.route("/<int:sale_id>/pay", methods=["POST"])
@login_required
def pay_debt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    currency = sale.currency or "LAK"
    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except Exception:
        rate = 830.0

    amount_input = float(request.form.get("amount", 0) or 0)
    note = request.form.get("note", "").strip()

    if amount_input <= 0:
        flash("ກະລຸນາໃສ່ຈໍານວນເງິນທີ່ຊໍາລະ", "danger")
        return redirect(url_for("debts.list_debts"))

    # ຮັບ input ເປັນ THB → ແປງເປັນ LAK ກ່ອນບັນທຶກ (sale.total ເກັບ LAK ສະເໝີ)
    amount_lak = amount_input * rate if currency == "THB" else amount_input
    amount_lak = min(amount_lak, sale.debt_remaining)

    payment = DebtPayment(
        sale_id=sale.id,
        customer_id=sale.customer_id,
        amount=amount_lak,
        currency=currency,
        note=note,
        paid_at=datetime.now(timezone.utc),
    )
    db.session.add(payment)

    customer = Customer.query.get(sale.customer_id)
    if customer:
        customer.total_debt = max(0, (customer.total_debt or 0) - amount_lak)

    db.session.commit()

    currency_label = "ບາດ" if currency == "THB" else "ກີບ"
    flash(f"ບັນທຶກການຊໍາລະ {amount_input:,.2f} {currency_label} ສໍາເລັດ", "success")
    return redirect(url_for("debts.list_debts"))
