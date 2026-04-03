from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, SalaryAdvance, Employee

salary_advance_bp = Blueprint("salary_advance", __name__)


@salary_advance_bp.route("/")
@login_required
def list_advances():
    emp_id = request.args.get("emp", "")
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    query = SalaryAdvance.query
    if emp_id:
        query = query.filter_by(employee_id=int(emp_id))
    advances = query.order_by(SalaryAdvance.advance_date.desc()).all()
    total_unpaid = sum(a.amount for a in advances if not a.repaid)
    return render_template(
        "salary_advance/list.html",
        advances=advances,
        employees=employees,
        emp_filter=emp_id,
        total_unpaid=total_unpaid,
    )


@salary_advance_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_advance():
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    if request.method == "POST":
        emp_id = request.form.get("employee_id")
        amount = float(request.form.get("amount", 0) or 0)
        reason = request.form.get("reason", "").strip()
        advance_date_str = request.form.get("advance_date", "")
        note = request.form.get("note", "").strip()

        if not emp_id or amount <= 0:
            flash("ກະລຸນາລະບຸພະນັກງານ ແລະ ຈຳນວນເງິນ", "danger")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return render_template("salary_advance/form.html", employees=employees, advance=None, today=today)

        try:
            adv_date = datetime.strptime(advance_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            adv_date = datetime.now(timezone.utc).date()

        adv = SalaryAdvance(
            employee_id=int(emp_id),
            amount=amount,
            reason=reason,
            advance_date=adv_date,
            note=note,
        )
        db.session.add(adv)
        db.session.commit()
        flash("ບັນທຶກການເບີກເງິນລ່ວງໜ້າສໍາເລັດ", "success")
        return redirect(url_for("salary_advance.list_advances"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return render_template("salary_advance/form.html", employees=employees, advance=None, today=today)


@salary_advance_bp.route("/<int:adv_id>/edit", methods=["GET", "POST"])
@login_required
def edit_advance(adv_id):
    adv = SalaryAdvance.query.get_or_404(adv_id)
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    if request.method == "POST":
        adv.employee_id = int(request.form.get("employee_id", adv.employee_id))
        adv.amount = float(request.form.get("amount", adv.amount) or adv.amount)
        adv.reason = request.form.get("reason", "").strip()
        adv.note = request.form.get("note", "").strip()
        try:
            adv.advance_date = datetime.strptime(request.form.get("advance_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            pass
        db.session.commit()
        flash("ແກ້ໄຂສໍາເລັດ", "success")
        return redirect(url_for("salary_advance.list_advances"))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return render_template("salary_advance/form.html", employees=employees, advance=adv, today=today)


@salary_advance_bp.route("/<int:adv_id>/repay", methods=["POST"])
@login_required
def mark_repaid(adv_id):
    adv = SalaryAdvance.query.get_or_404(adv_id)
    adv.repaid = True
    adv.repaid_at = datetime.now(timezone.utc)
    db.session.commit()
    flash("ໝາຍວ່າຊຳລະຄືນແລ້ວ", "success")
    return redirect(url_for("salary_advance.list_advances"))


@salary_advance_bp.route("/<int:adv_id>/delete", methods=["POST"])
@login_required
def delete_advance(adv_id):
    adv = SalaryAdvance.query.get_or_404(adv_id)
    db.session.delete(adv)
    db.session.commit()
    flash("ລຶບລາຍການສໍາເລັດ", "success")
    return redirect(url_for("salary_advance.list_advances"))


@salary_advance_bp.route("/employee/<int:emp_id>/summary")
@login_required
def employee_summary(emp_id):
    emp = Employee.query.get_or_404(emp_id)
    advances = SalaryAdvance.query.filter_by(employee_id=emp_id)\
        .order_by(SalaryAdvance.advance_date.desc()).all()
    total_advanced = sum(a.amount for a in advances)
    total_unpaid = sum(a.amount for a in advances if not a.repaid)
    return jsonify({
        "employee": emp.name,
        "total_advanced": total_advanced,
        "total_unpaid": total_unpaid,
        "advances": [
            {
                "id": a.id,
                "date": a.advance_date.strftime("%d/%m/%Y"),
                "amount": a.amount,
                "reason": a.reason,
                "repaid": a.repaid,
            }
            for a in advances
        ],
    })
