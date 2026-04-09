from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Expense, Sale

expenses_bp = Blueprint("expenses", __name__)

EXPENSE_CATS = ["ຄ່າເຊົ່າ", "ຄ່ານໍ້າໄຟ", "ຄ່າຂົນສົ່ງ", "ຄ່າແຮງງານ", "ສິນຄ້າ/ວັດຖຸດິບ", "ທົ່ວໄປ"]


@expenses_bp.route("/")
@login_required
def list_expenses():
    if not current_user.is_accountant():
        flash("ສິດທິ admin ຫຼື accountant ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("pos.pos_page"))
    month = request.args.get("month", date.today().strftime("%Y-%m"))
    try:
        y, m = map(int, month.split("-"))
    except Exception:
        y, m = date.today().year, date.today().month

    expenses = Expense.query.filter(
        db.extract("year", Expense.date) == y,
        db.extract("month", Expense.date) == m,
    ).order_by(Expense.date.desc()).all()

    # Income from sales this month (exclude voided, include cash + transfer)
    from sqlalchemy import extract, func
    income = db.session.query(func.sum(Sale.total)).filter(
        extract("year", Sale.created_at) == y,
        extract("month", Sale.created_at) == m,
        Sale.payment_type.in_(["cash", "transfer"]),
        Sale.voided == False,
    ).scalar() or 0

    total_expense = sum(e.amount for e in expenses)
    profit = income - total_expense

    return render_template("expenses/list.html",
        expenses=expenses, month=month, income=income,
        total_expense=total_expense, profit=profit,
        expense_cats=EXPENSE_CATS)


@expenses_bp.route("/add", methods=["POST"])
@login_required
def add_expense():
    e = Expense(
        category=request.form.get("category", "ທົ່ວໄປ"),
        amount=float(request.form.get("amount", 0) or 0),
        note=request.form.get("note", "").strip(),
        date=date.fromisoformat(request.form.get("date", date.today().isoformat())),
    )
    db.session.add(e)
    db.session.commit()
    flash("ບັນທຶກລາຍຈ່າຍສໍາເລັດ", "success")
    return redirect(url_for("expenses.list_expenses"))


@expenses_bp.route("/<int:eid>/delete", methods=["POST"])
@login_required
def delete_expense(eid):
    e = Expense.query.get_or_404(eid)
    db.session.delete(e)
    db.session.commit()
    flash("ລຶບລາຍຈ່າຍສໍາເລັດ", "success")
    return redirect(url_for("expenses.list_expenses"))
