from datetime import date
from flask import Blueprint, render_template, request, send_file, jsonify
from flask_login import login_required
from sqlalchemy import extract, func
from models import db, Sale, SaleItem, Product, Customer
import io, openpyxl

reports_bp = Blueprint("reports", __name__)


def _aggregate_overdue_by_customer():
    """Return a list of {name, phone, amount, bills} for every customer who
    currently has outstanding debt, sorted by amount (descending).
    Sales without a customer are grouped under "ລູກຄ້າໜ້າຮ້ານ" (walk-in).
    """
    debt_sales = Sale.query.filter_by(payment_type="debt").all()
    groups = {}
    walk_in = {"name": "ລູກຄ້າໜ້າຮ້ານ", "phone": "", "amount": 0, "bills": 0}
    for s in debt_sales:
        rem = s.debt_remaining
        if rem <= 0:
            continue
        if s.customer:
            key = s.customer.id
            if key not in groups:
                groups[key] = {
                    "name": s.customer.name,
                    "phone": s.customer.phone or "",
                    "amount": 0,
                    "bills": 0,
                }
            groups[key]["amount"] += rem
            groups[key]["bills"] += 1
        else:
            walk_in["amount"] += rem
            walk_in["bills"] += 1

    result = sorted(groups.values(), key=lambda c: c["amount"], reverse=True)
    if walk_in["amount"] > 0:
        result.append(walk_in)
    return result


def _build_daily_summary(sel_dt):
    """Compute daily figures + per-customer overdue list for sel_dt."""
    sales = Sale.query.filter(db.func.date(Sale.created_at) == sel_dt)\
        .order_by(Sale.created_at.desc()).all()
    total_revenue = sum(s.total for s in sales)
    cash_total = sum(s.total for s in sales if s.payment_type == "cash")
    debt_sales_today = [s for s in sales if s.payment_type == "debt"]
    debt_total_today = sum(s.total for s in debt_sales_today)
    overdue_customers = _aggregate_overdue_by_customer()
    return dict(
        sales=sales,
        bill_count=len(sales),
        total_revenue=total_revenue,
        cash_total=cash_total,
        debt_total_today=debt_total_today,
        debt_count_today=len(debt_sales_today),
        overdue_customers=overdue_customers,
        overdue_total=sum(c["amount"] for c in overdue_customers),
    )


def _format_telegram_msg(sel_dt, summary):
    """Build the daily summary message for Telegram/WhatsApp."""
    lines = []
    lines.append(f"📊 *ສະຫຼຸບຍອດ {sel_dt.strftime('%d/%m/%Y')}*")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"🧾 ບິນທັງໝົດ:  *{summary['bill_count']} ບິນ*")
    lines.append(f"💰 ລາຍຮັບລວມ: *{summary['total_revenue']:,.0f} ₭*")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append(f"💵 ເງິນສົດ:  {summary['cash_total']:,.0f} ₭")
    lines.append(
        f"⚠️ ຄ້າງຊຳລະວັນນີ້:  {summary['debt_total_today']:,.0f} ₭"
        f"  ({summary['debt_count_today']} ບິນ)"
    )
    overdue = summary["overdue_customers"]
    if overdue:
        lines.append("━━━━━━━━━━━━━━━")
        lines.append(f"👥 *ລາຍຊື່ລູກຄ້າຄ້າງຊຳລະ* ({len(overdue)} ຄົນ)")
        for c in overdue:
            phone = f" ({c['phone']})" if c["phone"] else ""
            lines.append(f"• {c['name']}{phone}: {c['amount']:,.0f} ₭")
        lines.append(f"ລວມຄ້າງທັງໝົດ: *{summary['overdue_total']:,.0f} ₭*")
    return "\n".join(lines)


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
        summary = _build_daily_summary(sel_dt)
        label = f"ລາຍວັນ – {sel_dt.strftime('%d/%m/%Y')}"
        context = dict(
            view=view,
            sales=summary["sales"],
            total=summary["total_revenue"],
            label=label,
            sel_date=str(sel_dt),
            cash_total=summary["cash_total"],
            debt_total=summary["debt_total_today"],
            bill_count=summary["bill_count"],
            overdue_customers=summary["overdue_customers"],
            overdue_total=summary["overdue_total"],
        )

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


@reports_bp.route("/daily-summary.json")
def daily_summary_json():
    """Return the daily summary as JSON for Telegram/webhook integrations.

    Example: /reports/daily-summary.json?date=2026-04-11
    Defaults to today. No auth so an external scheduler (n8n / cron) can
    fetch and post the `whatsapp_msg` field directly to Telegram.
    """
    sel_date = request.args.get("date", date.today().isoformat())
    try:
        sel_dt = date.fromisoformat(sel_date)
    except Exception:
        sel_dt = date.today()

    summary = _build_daily_summary(sel_dt)
    whatsapp_msg = _format_telegram_msg(sel_dt, summary)

    return jsonify({
        "date": sel_dt.isoformat(),
        "total_sales": summary["bill_count"],
        "total_revenue": summary["total_revenue"],
        "cash_total": summary["cash_total"],
        "debt_total_today": summary["debt_total_today"],
        "debt_count_today": summary["debt_count_today"],
        "overdue_total": summary["overdue_total"],
        "overdue_customers": summary["overdue_customers"],
        "whatsapp_msg": whatsapp_msg,
    })


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
