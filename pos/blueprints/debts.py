from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Sale, Customer, DebtPayment, Setting
from datetime import datetime, timezone, timedelta
import threading
import requests as _req

debts_bp = Blueprint("debts", __name__)

_TZ_LAO = timezone(timedelta(hours=7))


def _notify_debt_paid(sale, payment):
    url = Setting.get("n8n_webhook_url", "").strip()
    if not url:
        return
    customer_name = sale.customer.name if sale.customer else "ລູກຄ້າທົ່ວໄປ"
    now_lao = datetime.now(timezone.utc).astimezone(_TZ_LAO)
    local_dt = sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO)
    items_summary = " | ".join(
        f"{si.product.name if si.product else '?'} ×{si.qty:g}"
        for si in sale.items
    )
    is_fully_paid = sale.is_fully_paid
    remaining = sale.debt_remaining
    status_label = "✅ ຊຳລະຄົບ" if is_fully_paid else f"⚠️ ຍັງຄ້າງ {remaining:,.0f} ₭"
    msg = (
        f"💸 *ຊຳລະໜີ້ #{sale.sale_no}*\n"
        f"📅 {now_lao.strftime('%d/%m/%Y %H:%M')}\n"
        f"👤 {customer_name}\n\n"
        f"💰 ຊຳລະ: *{payment.amount:,.0f} ກີບ*\n"
        f"📦 ຍອດບິນ: {sale.total:,.0f} ກີບ\n"
        f"{status_label}"
    )
    payload = {
        "event": "debt_paid",
        "sale_no": sale.sale_no,
        "sale_date": local_dt.strftime("%d/%m/%Y"),
        "sale_time": local_dt.strftime("%H:%M"),
        "paid_date": now_lao.strftime("%d/%m/%Y"),
        "paid_time": now_lao.strftime("%H:%M"),
        "customer": customer_name,
        "items_summary": items_summary,
        "sale_total": sale.total,
        "paid_amount": payment.amount,
        "is_fully_paid": is_fully_paid,
        "remaining": float(remaining),
        "note": payment.note or "",
        "telegram_msg": msg,
    }
    threading.Thread(
        target=lambda: _req.post(url, json=payload, timeout=5), daemon=True
    ).start()


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
    sale.paid_amount = (sale.paid_amount or 0) + amount

    customer = Customer.query.get(sale.customer_id)
    if customer:
        customer.total_debt = max(0, customer.total_debt - amount)

    db.session.commit()
    _notify_debt_paid(sale, payment)
    flash(f"ບັນທຶກການຊໍາລະ {amount:,.0f} ກີບ ສໍາເລັດ", "success")
    return redirect(url_for("debts.list_debts"))
