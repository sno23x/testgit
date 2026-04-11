from datetime import date
from flask import Blueprint, render_template, request, send_file
from flask_login import login_required
from sqlalchemy import extract, func
from models import db, Sale, SaleItem, Product, Customer
import io, openpyxl

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/")
@login_required
def index():
    view = request.args.get("view", "daily")
    today = date.today()

    if view == "daily":
        sel_date = request.args.get("date", today.isoformat())
        try:
            sel_dt = date.fromisoformat(sel_date)
        except Exception:
            sel_dt = today
        sales = Sale.query.filter(db.func.date(Sale.created_at) == sel_dt)\
            .order_by(Sale.created_at.desc()).all()
        total = sum(s.total for s in sales)
        cash_total = sum(s.total for s in sales if s.payment_type == "cash")
        debt_sales_today = [s for s in sales if s.payment_type == "debt"]
        debt_total = sum(s.debt_remaining for s in debt_sales_today)
        overdue_sales = [s for s in debt_sales_today if s.debt_remaining > 0]
        label = f"ລາຍວັນ – {sel_dt.strftime('%d/%m/%Y')}"
        context = dict(view=view, sales=sales, total=total, label=label,
                       sel_date=str(sel_dt),
                       cash_total=cash_total, debt_total=debt_total,
                       bill_count=len(sales), overdue_sales=overdue_sales)

    elif view == "monthly":
        sel_month = request.args.get("month", today.strftime("%Y-%m"))
        try:
            y, m = map(int, sel_month.split("-"))
        except Exception:
            y, m = today.year, today.month
        sales = Sale.query.filter(
            extract("year", Sale.created_at) == y,
            extract("month", Sale.created_at) == m,
        ).order_by(Sale.created_at.desc()).all()
        total = sum(s.total for s in sales)
        label = f"ລາຍເດືອນ – {m:02d}/{y}"
        context = dict(view=view, sales=sales, total=total, label=label, sel_month=sel_month)

    else:  # yearly
        sel_year = int(request.args.get("year", today.year))
        sales = Sale.query.filter(
            extract("year", Sale.created_at) == sel_year,
        ).order_by(Sale.created_at.desc()).all()
        total = sum(s.total for s in sales)
        label = f"ລາຍປີ – {sel_year}"

        # monthly breakdown for chart
        monthly_data = db.session.query(
            extract("month", Sale.created_at).label("m"),
            func.sum(Sale.total).label("t")
        ).filter(extract("year", Sale.created_at) == sel_year)\
         .group_by("m").order_by("m").all()
        chart_labels = [f"ເດືອນ {int(r[0])}" for r in monthly_data]
        chart_data = [float(r[1] or 0) for r in monthly_data]
        context = dict(view=view, sales=sales, total=total, label=label,
                       sel_year=sel_year, chart_labels=chart_labels, chart_data=chart_data)

    # Top 10 products (all time)
    top_products = db.session.query(
        Product.name,
        func.sum(SaleItem.qty).label("qty"),
        func.sum(SaleItem.subtotal).label("revenue")
    ).join(SaleItem, Product.id == SaleItem.product_id)\
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
            "ເງິນສົດ" if s.payment_type == "cash" else "ຕິດໜີ້",
            s.discount,
            s.total,
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
