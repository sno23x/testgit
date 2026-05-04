from datetime import date
from flask import Blueprint, render_template, request, send_file, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import extract, func
from models import db, Sale, SaleItem, Product, Customer, Category
import io, openpyxl

reports_bp = Blueprint("reports", __name__)


def _aggregate_overdue_by_customer():
    """ລວມໜີ້ຄ້າງຊຳລະທຸກໃບ ຈັດກຸ່ມຕາມລູກຄ້າ."""
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
                groups[key] = {"name": s.customer.name,
                               "phone": s.customer.phone or "",
                               "amount": 0, "bills": 0}
            groups[key]["amount"] += rem
            groups[key]["bills"] += 1
        else:
            walk_in["amount"] += rem
            walk_in["bills"] += 1
    result = sorted(groups.values(), key=lambda c: c["amount"], reverse=True)
    if walk_in["amount"] > 0:
        result.append(walk_in)
    return result


def _format_telegram_msg(sel_dt, summary):
    divider = "━━━━━━━━━━━━━━━"
    lines = [
        f"📊 *ສະຫຼຸບຍອດ {sel_dt.strftime('%d/%m/%Y')}*",
        divider,
        f"🧾 ບິນທັງໝົດ:  *{summary['bill_count']} ບິນ*",
        f"💰 ລາຍຮັບລວມ: *{summary['total_revenue']:,.0f} ₭*",
        divider,
        f"💵 ເງິນສົດ:  {summary['cash_total']:,.0f} ₭",
        f"📲 ໂອນເງິນ:  {summary['transfer_total']:,.0f} ₭",
        f"⚠️ ຄ້າງຊຳລະ:  {summary['debt_total_today']:,.0f} ₭  ({summary['debt_count_today']} ບິນ)",
    ]
    overdue = summary["overdue_customers"]
    if overdue:
        lines.append(divider)
        lines.append(f"👥 *ລາຍຊື່ລູກຄ້າຄ້າງຊຳລະ* ({len(overdue)} ຄົນ)")
        for c in overdue:
            phone = f" ({c['phone']})" if c["phone"] else ""
            lines.append(f"• {c['name']}{phone}:  {c['amount']:,.0f} ₭")
        lines.append(f"ລວມຄ້າງທັງໝົດ: *{summary['overdue_total']:,.0f} ₭*")
    lines.append(divider)
    return "\n".join(lines)


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
        overdue_customers = _aggregate_overdue_by_customer()
        context = dict(
            view=view, sales=sales, total=total, label=label,
            sel_date=str(sel_dt), show_voided=show_voided,
            cash_total=sum(s.total for s in sales if s.payment_type == "cash" and not s.voided),
            transfer_total=sum(s.total for s in sales if s.payment_type == "transfer" and not s.voided),
            debt_total=sum(s.total for s in sales if s.payment_type == "debt" and not s.voided),
            bill_count=sum(1 for s in sales if not s.voided),
            overdue_customers=overdue_customers,
            overdue_total=sum(c["amount"] for c in overdue_customers),
        )

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

    # Profit per sale: (unit_price - cost_price) * qty using current cost_price
    active_sale_ids = [s.id for s in sales if not s.voided]
    profit_map = {}
    if active_sale_ids:
        profit_rows = db.session.query(
            SaleItem.sale_id,
            func.sum((SaleItem.unit_price - func.coalesce(Product.cost_price, 0)) * SaleItem.qty).label("profit")
        ).join(Product, Product.id == SaleItem.product_id)\
         .filter(SaleItem.sale_id.in_(active_sale_ids))\
         .group_by(SaleItem.sale_id).all()
        profit_map = {r[0]: float(r[1] or 0) for r in profit_rows}
    total_profit = sum(profit_map.values())

    context["top_products"] = top_products
    context["profit_map"] = profit_map
    context["total_profit"] = total_profit
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


@reports_bp.route("/daily-summary.json")
def daily_summary_json():
    """JSON endpoint ສຳລັບ n8n / Telegram webhook — ບໍ່ຕ້ອງ auth."""
    sel_date = request.args.get("date", date.today().isoformat())
    try:
        sel_dt = date.fromisoformat(sel_date)
    except Exception:
        sel_dt = date.today()

    sales = Sale.query.filter(
        db.func.date(Sale.created_at) == sel_dt, Sale.voided == False
    ).all()
    cash_total     = sum(s.total for s in sales if s.payment_type == "cash")
    transfer_total = sum(s.total for s in sales if s.payment_type == "transfer")
    debt_sales     = [s for s in sales if s.payment_type == "debt"]
    overdue_customers = _aggregate_overdue_by_customer()
    summary = dict(
        bill_count=len(sales),
        total_revenue=sum(s.total for s in sales),
        cash_total=cash_total,
        transfer_total=transfer_total,
        debt_total_today=sum(s.total for s in debt_sales),
        debt_count_today=len(debt_sales),
        overdue_customers=overdue_customers,
        overdue_total=sum(c["amount"] for c in overdue_customers),
    )
    return jsonify({
        "date": sel_dt.isoformat(),
        "total_sales": summary["bill_count"],
        "total_revenue": summary["total_revenue"],
        "cash_total": summary["cash_total"],
        "transfer_total": summary["transfer_total"],
        "debt_total": summary["debt_total_today"],
        "debt_count": summary["debt_count_today"],
        "overdue_total": summary["overdue_total"],
        "overdue_customers": summary["overdue_customers"],
        "whatsapp_msg": _format_telegram_msg(sel_dt, summary),
    })


@reports_bp.route("/margin")
@login_required
def margin_report():
    if not current_user.is_accountant():
        flash("ສິດທິ admin ຫຼື accountant ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("pos.pos_page"))

    cat_id = request.args.get("cat", "")
    q = request.args.get("q", "")

    # Average sale price per product from actual sales (non-voided)
    avg_prices = db.session.query(
        SaleItem.product_id,
        func.avg(SaleItem.unit_price).label("avg_price"),
        func.sum(SaleItem.qty).label("total_qty"),
        func.sum(SaleItem.subtotal).label("total_revenue"),
    ).join(Sale, Sale.id == SaleItem.sale_id)\
     .filter(Sale.voided == False)\
     .group_by(SaleItem.product_id).all()

    avg_map = {r.product_id: r for r in avg_prices}

    pq = Product.query.filter_by(active=True)
    if cat_id:
        pq = pq.filter_by(category_id=int(cat_id))
    if q:
        pq = pq.filter(Product.name.ilike(f"%{q}%"))
    products = pq.order_by(Product.name).all()
    categories = Category.query.order_by(Category.name).all()

    rows = []
    for p in products:
        rec = avg_map.get(p.id)
        avg_sale = rec.avg_price if rec else None
        total_rev = rec.total_revenue if rec else 0
        total_qty = rec.total_qty if rec else 0
        cost = p.cost_price or 0
        if avg_sale and avg_sale > 0:
            margin_pct = (avg_sale - cost) / avg_sale * 100
            margin_lak = avg_sale - cost
        else:
            margin_pct = None
            margin_lak = None
        rows.append({
            "product": p,
            "cost_price": cost,
            "avg_sale_price": avg_sale,
            "margin_pct": margin_pct,
            "margin_lak": margin_lak,
            "total_qty": total_qty,
            "total_revenue": total_rev,
        })

    # Sort by margin_pct descending (None last)
    rows.sort(key=lambda r: (r["margin_pct"] is None, -(r["margin_pct"] or 0)))

    if request.args.get("export") == "1":
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Margin Report"
        ws.append(["ສິນຄ້າ", "ຫົວໜ່ວຍ", "ຕ້ນທຶນ (ກີບ)", "ລາຄາຂາຍ (ສ.ລ.)", "ກຳໄລ/ຫົວໜ່ວຍ", "Margin %", "ຍອດຂາຍ"])
        for r in rows:
            ws.append([
                r["product"].name,
                r["product"].unit,
                r["cost_price"],
                round(r["avg_sale_price"], 0) if r["avg_sale_price"] else "",
                round(r["margin_lak"], 0) if r["margin_lak"] is not None else "",
                round(r["margin_pct"], 2) if r["margin_pct"] is not None else "",
                round(r["total_revenue"], 0) if r["total_revenue"] else "",
            ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="margin_report.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return render_template("reports/margin.html", rows=rows, categories=categories,
                           cat_id=cat_id, q=q)
