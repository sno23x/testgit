from datetime import date
from flask import Blueprint, render_template, request, send_file, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import extract, func
from models import db, Sale, SaleItem, Product, Customer
import io, openpyxl

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def index():
    if not current_user.is_accountant():
        flash("ສິດທິ admin ຫຼື accountant ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("pos.pos_page"))
    view = request.args.get("view", "daily")
    today = date.today()

    show_voided = request.args.get("show_voided", "0") == "1"

    if view == "daily":
        sel_date = request.args.get("date", today.isoformat())
        try:
            sel_dt = date.fromisoformat(sel_date)
        except Exception:
            sel_dt = today
        q = Sale.query.filter(db.func.date(Sale.created_at) == sel_dt)
        if not show_voided:
            q = q.filter(Sale.voided == False)
        sales = q.order_by(Sale.created_at.desc()).all()
        total = sum(s.total for s in sales if not s.voided)
        label = f"ລາຍວັນ – {sel_dt.strftime('%d/%m/%Y')}"
        context = dict(view=view, sales=sales, total=total, label=label,
                       sel_date=str(sel_dt), show_voided=show_voided)

    elif view == "monthly":
        sel_month = request.args.get("month", today.strftime("%Y-%m"))
        try:
            y, m = map(int, sel_month.split("-"))
        except Exception:
            y, m = today.year, today.month
        q = Sale.query.filter(
            extract("year", Sale.created_at) == y,
            extract("month", Sale.created_at) == m,
        )
        if not show_voided:
            q = q.filter(Sale.voided == False)
        sales = q.order_by(Sale.created_at.desc()).all()
        total = sum(s.total for s in sales if not s.voided)
        label = f"ລາຍເດືອນ – {m:02d}/{y}"
        context = dict(view=view, sales=sales, total=total, label=label,
                       sel_month=sel_month, show_voided=show_voided)

    else:  # yearly
        sel_year = int(request.args.get("year", today.year))
        q = Sale.query.filter(extract("year", Sale.created_at) == sel_year)
        if not show_voided:
            q = q.filter(Sale.voided == False)
        sales = q.order_by(Sale.created_at.desc()).all()
        total = sum(s.total for s in sales if not s.voided)
        label = f"ລາຍປີ – {sel_year}"

        monthly_data = db.session.query(
            extract("month", Sale.created_at).label("m"),
            func.sum(Sale.total).label("t")
        ).filter(
            extract("year", Sale.created_at) == sel_year,
            Sale.voided == False
        ).group_by("m").order_by("m").all()
        chart_labels = [f"ເດືອນ {int(r[0])}" for r in monthly_data]
        chart_data = [float(r[1] or 0) for r in monthly_data]
        context = dict(view=view, sales=sales, total=total, label=label,
                       sel_year=sel_year, chart_labels=chart_labels,
                       chart_data=chart_data, show_voided=show_voided)

    # Top 10 products (exclude voided)
    top_products = db.session.query(
        Product.name,
        func.sum(SaleItem.qty).label("qty"),
        func.sum(SaleItem.subtotal).label("revenue")
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(Sale.voided == False)\
     .group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).limit(10).all()

    context["top_products"] = top_products
    return render_template("reports/index.html", **context)


@reports_bp.route("/export")
@login_required
def export_excel():
    view = request.args.get("view", "daily")
    today = date.today()

    if view == "daily":
        sel_date = date.fromisoformat(request.args.get("date", today.isoformat()))
        sales = Sale.query.filter(db.func.date(Sale.created_at) == sel_date).all()
        filename = f"report_daily_{sel_date}.xlsx"
    elif view == "monthly":
        sel_month = request.args.get("month", today.strftime("%Y-%m"))
        y, m = map(int, sel_month.split("-"))
        sales = Sale.query.filter(
            extract("year", Sale.created_at) == y,
            extract("month", Sale.created_at) == m,
        ).all()
        filename = f"report_monthly_{sel_month}.xlsx"
    else:
        sel_year = int(request.args.get("year", today.year))
        sales = Sale.query.filter(extract("year", Sale.created_at) == sel_year).all()
        filename = f"report_yearly_{sel_year}.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ລາຍງານ"
    ws.append(["ເລກບິນ", "ວັນທີ", "ລູກຄ້າ", "ປະເພດຊໍາລະ", "ສ່ວນຫຼຸດ", "ລວມ"])
    for s in sales:
        ws.append([
            s.sale_no,
            s.created_at.strftime("%d/%m/%Y %H:%M"),
            s.customer.name if s.customer else "-",
            "ເງິນສົດ" if s.payment_type == "cash" else ("ໂອນເງິນ" if s.payment_type == "transfer" else "ຄ້າງຊຳລະ"),
            s.discount,
            s.total,
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
