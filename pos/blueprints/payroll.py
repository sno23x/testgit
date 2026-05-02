import calendar
from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from models import db, Employee, Attendance, PayrollRecord, SalaryAdvance, Expense

payroll_bp = Blueprint("payroll", __name__)


# ──────────────── Attendance ────────────────
@payroll_bp.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    sel_date = request.args.get("date", date.today().isoformat())
    try:
        sel = date.fromisoformat(sel_date)
    except ValueError:
        sel = date.today()

    if request.method == "POST":
        for emp in employees:
            status = request.form.get(f"status_{emp.id}", "present")
            ot_h   = float(request.form.get(f"ot_{emp.id}", 0) or 0)
            note   = request.form.get(f"note_{emp.id}", "")
            a = Attendance.query.filter_by(employee_id=emp.id, date=sel).first()
            if a:
                a.status   = status
                a.ot_hours = ot_h
                a.note     = note
            else:
                db.session.add(Attendance(employee_id=emp.id, date=sel,
                                          status=status, ot_hours=ot_h, note=note))

            # Auto-expense for daily-wage employees
            if emp.pay_type == 'daily' and emp.daily_rate and emp.daily_rate > 0:
                # Remove existing auto-expense for this employee+date (re-save safe)
                Expense.query.filter_by(
                    employee_id=emp.id, date=sel, category="ຄ່າແຮງງານລາຍວັນ"
                ).delete()
                if status == 'present':
                    db.session.add(Expense(
                        category="ຄ່າແຮງງານລາຍວັນ",
                        amount=emp.daily_rate,
                        note=f"ຈ່າຍເງິນລາຍວັນໃຫ້ {emp.name}",
                        date=sel,
                        employee_id=emp.id,
                    ))

        db.session.commit()
        flash("ບັນທຶກການເຂົ້າວຽກສໍາເລັດ", "success")
        return redirect(url_for("payroll.attendance", date=sel_date))

    records = {a.employee_id: a
               for a in Attendance.query.filter_by(date=sel).all()}
    return render_template("payroll/attendance.html",
                           employees=employees, records=records,
                           sel_date=sel_date)


# ──────────────── Payroll list ────────────────
@payroll_bp.route("/")
@login_required
def index():
    year  = int(request.args.get("year",  date.today().year))
    month = int(request.args.get("month", date.today().month))
    records = PayrollRecord.query.filter_by(year=year, month=month)\
        .join(Employee).order_by(Employee.name).all()
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    return render_template("payroll/index.html",
                           records=records, employees=employees,
                           year=year, month=month)


# ──────────────── Generate payroll for month ────────────────
@payroll_bp.route("/generate", methods=["POST"])
@login_required
def generate():
    year  = int(request.form.get("year",  date.today().year))
    month = int(request.form.get("month", date.today().month))

    employees = Employee.query.filter_by(active=True).all()
    for emp in employees:
        existing = PayrollRecord.query.filter_by(
            employee_id=emp.id, year=year, month=month).first()
        if existing:
            continue

        # Count attendance for this month
        att_list = Attendance.query.filter_by(employee_id=emp.id)\
            .filter(db.extract("year",  Attendance.date) == year)\
            .filter(db.extract("month", Attendance.date) == month).all()

        absent_days = sum(1 for a in att_list if a.status in ("absent",))
        ot_hours    = sum(a.ot_hours for a in att_list)

        # Total days in this calendar month (for daily-rate formula)
        days_in_month = calendar.monthrange(year, month)[1]

        # Sum all unrepaid advances for this employee taken up to end of this month
        last_day = date(year, month, days_in_month)
        advance_total = db.session.query(
            db.func.coalesce(db.func.sum(SalaryAdvance.amount), 0)
        ).filter(
            SalaryAdvance.employee_id == emp.id,
            SalaryAdvance.repaid == False,
            SalaryAdvance.advance_date <= last_day,
        ).scalar() or 0

        rec = PayrollRecord(
            employee_id=emp.id, year=year, month=month,
            base_salary=emp.base_salary,
            working_days=days_in_month,
            absent_days=absent_days,
            ot_hours=ot_hours,
            ot_rate=emp.ot_rate,
            advance_deduction=advance_total,
        )
        rec.calc_net()
        db.session.add(rec)

    db.session.commit()
    flash(f"ສ້າງໃບເງິນເດືອນ {month}/{year} ສໍາເລັດ", "success")
    return redirect(url_for("payroll.index", year=year, month=month))


# ──────────────── Edit single payroll record ────────────────
@payroll_bp.route("/<int:rid>/edit", methods=["GET", "POST"])
@login_required
def edit(rid):
    rec = PayrollRecord.query.get_or_404(rid)
    if request.method == "POST":
        rec.base_salary       = float(request.form.get("base_salary", rec.base_salary) or 0)
        rec.working_days      = int(request.form.get("working_days", rec.working_days) or 26)
        rec.absent_days       = int(request.form.get("absent_days", rec.absent_days) or 0)
        rec.ot_hours          = float(request.form.get("ot_hours", rec.ot_hours) or 0)
        rec.ot_rate           = float(request.form.get("ot_rate", rec.ot_rate) or 0)
        rec.bonus             = float(request.form.get("bonus", rec.bonus) or 0)
        rec.other_deductions  = float(request.form.get("other_deductions", rec.other_deductions) or 0)
        rec.advance_deduction = float(request.form.get("advance_deduction", rec.advance_deduction) or 0)
        rec.note              = request.form.get("note", "")
        rec.calc_net()
        db.session.commit()
        flash("ອັບເດດສໍາເລັດ", "success")
        return redirect(url_for("payroll.index", year=rec.year, month=rec.month))
    return render_template("payroll/edit.html", rec=rec)


# ──────────────── Mark paid ────────────────
@payroll_bp.route("/<int:rid>/pay", methods=["POST"])
@login_required
def mark_paid(rid):
    from datetime import datetime, timezone
    rec = PayrollRecord.query.get_or_404(rid)
    rec.paid    = True
    rec.paid_at = datetime.now(timezone.utc)

    # Mark salary advances that were deducted as repaid
    if rec.advance_deduction and rec.advance_deduction > 0:
        last_day = date(rec.year, rec.month, calendar.monthrange(rec.year, rec.month)[1])
        advances = SalaryAdvance.query.filter(
            SalaryAdvance.employee_id == rec.employee_id,
            SalaryAdvance.repaid == False,
            SalaryAdvance.advance_date <= last_day,
        ).all()
        now = datetime.now(timezone.utc)
        for adv in advances:
            adv.repaid    = True
            adv.repaid_at = now

    db.session.commit()
    flash("ບັນທຶກການຈ່າຍເງິນເດືອນສໍາເລັດ", "success")
    return redirect(url_for("payroll.index", year=rec.year, month=rec.month))
