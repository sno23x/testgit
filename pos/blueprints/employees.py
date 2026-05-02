from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Employee

employees_bp = Blueprint("employees", __name__)


@employees_bp.route("/")
@login_required
def list_employees():
    employees = Employee.query.filter_by(active=True).order_by(Employee.name).all()
    return render_template("employees/list.html", employees=employees)


@employees_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_employee():
    if not current_user.is_admin():
        flash("ສິດທິ admin ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("employees.list_employees"))
    if request.method == "POST":
        emp = Employee(
            name=request.form.get("name", "").strip(),
            username=request.form.get("username", "").strip(),
            role=request.form.get("role", "cashier"),
            base_salary=float(request.form.get("base_salary", 0) or 0),
            ot_rate=float(request.form.get("ot_rate", 0) or 0),
            pay_type=request.form.get("pay_type", "monthly"),
            daily_rate=float(request.form.get("daily_rate", 0) or 0),
        )
        emp.set_password(request.form.get("password", ""))
        db.session.add(emp)
        db.session.commit()
        flash("ເພີ່ມພະນັກງານສໍາເລັດ", "success")
        return redirect(url_for("employees.list_employees"))
    return render_template("employees/form.html", employee=None)


@employees_bp.route("/<int:eid>/edit", methods=["GET", "POST"])
@login_required
def edit_employee(eid):
    if not current_user.is_admin():
        flash("ສິດທິ admin ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("employees.list_employees"))
    emp = Employee.query.get_or_404(eid)
    if request.method == "POST":
        emp.name = request.form.get("name", emp.name).strip()
        emp.username = request.form.get("username", emp.username).strip()
        emp.role = request.form.get("role", emp.role)
        emp.base_salary = float(request.form.get("base_salary", emp.base_salary) or 0)
        emp.ot_rate = float(request.form.get("ot_rate", emp.ot_rate) or 0)
        emp.pay_type = request.form.get("pay_type", emp.pay_type or "monthly")
        emp.daily_rate = float(request.form.get("daily_rate", emp.daily_rate) or 0)
        pw = request.form.get("password", "").strip()
        if pw:
            emp.set_password(pw)
        db.session.commit()
        flash("ແກ້ໄຂສໍາເລັດ", "success")
        return redirect(url_for("employees.list_employees"))
    return render_template("employees/form.html", employee=emp)


@employees_bp.route("/<int:eid>/delete", methods=["POST"])
@login_required
def delete_employee(eid):
    if not current_user.is_admin():
        flash("ສິດທິ admin ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("employees.list_employees"))
    emp = Employee.query.get_or_404(eid)
    emp.active = False
    db.session.commit()
    flash("ລຶບພະນັກງານສໍາເລັດ", "success")
    return redirect(url_for("employees.list_employees"))
