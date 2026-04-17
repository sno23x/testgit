from datetime import datetime, timezone, date, timedelta

_TZ_LAO = timezone(timedelta(hours=7))
import threading
import requests as _req
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import extract, func
from models import db, Product, Customer, Sale, SaleItem, Employee, Setting, round_price, DebtPayment

pos_bp = Blueprint("pos", __name__)


# ──────────────── n8n Webhook helper ────────────────
def _post_webhook(url, payload):
    try:
        _req.post(url, json=payload, timeout=5)
    except Exception:
        pass


def _build_sale_message(sale):
    """ສ້າງຂໍ້ຄວາມ Telegram/WhatsApp ສຳລັບບິນ"""
    payment_lao = {"cash": "ເງິນສົດ", "debt": "ຄ້າງຊຳລະ", "transfer": "ໂອນເງິນ"}
    pay_label = payment_lao.get(sale.payment_type, sale.payment_type)
    is_debt = sale.payment_type == "debt"
    if is_debt:
        status_label = "🚚 ກຳລັງຈັດສົ່ງ | ⚠️ ຄ້າງຊຳລະ"
    elif sale.payment_type == "cash":
        status_label = "✅ ຊຳລະແລ້ວ (ເງິນສົດ)"
    elif sale.payment_type == "transfer":
        status_label = "✅ ຊຳລະແລ້ວ (ໂອນເງິນ)"
    else:
        status_label = f"✅ ຊຳລະແລ້ວ ({pay_label})"

    customer_name = sale.customer.name if sale.customer else "ລູກຄ້າທົ່ວໄປ"
    items_lines = "\n".join(
        f"  • {si.product.name if si.product else '?'} ×{si.qty:g}  {si.subtotal:,.0f}₭"
        for si in sale.items
    )
    local_dt = sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO)
    msg = (
        f"🧾 *ບິນໃໝ່ #{sale.sale_no}*\n"
        f"📅 {local_dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"👤 {customer_name}\n\n"
        f"{items_lines}\n\n"
        f"💰 ລວມ: *{sale.total:,.0f} ກີບ*\n"
        f"{status_label}"
    )
    return msg, pay_label, status_label, is_debt, customer_name


def notify_n8n(sale):
    """ສ້າງ payload ແລ້ວ ສົ່ງໄປ n8n webhook (background thread)"""
    url = Setting.get("n8n_webhook_url", "").strip()
    if not url:
        return
    msg, pay_label, status_label, is_debt, customer_name = _build_sale_message(sale)
    items_summary = " | ".join(
        f"{si.product.name if si.product else '?'} ×{si.qty:g}"
        for si in sale.items
    )
    # ปุ่ม inline keyboard (ສຳລັບບິນ debt ເທົ່ານັ້ນ)
    actions = []
    if is_debt:
        actions = [
            {"text": "💵 ຮັບເງິນສົດ", "callback_data": f"paid_cash:{sale.sale_no}"},
            {"text": "🏦 ໂອນແລ້ວ",   "callback_data": f"paid_transfer:{sale.sale_no}"},
        ]
    payload = {
        "event": "sale_created",
        "sale_no": sale.sale_no,
        "date": sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO).strftime("%d/%m/%Y"),
        "time": sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO).strftime("%H:%M"),
        "customer": customer_name,
        "items": [
            {"name": si.product.name if si.product else "?",
             "unit": si.product.unit if si.product else "",
             "qty": si.qty,
             "unit_price": si.unit_price,
             "subtotal": si.subtotal}
            for si in sale.items
        ],
        "items_summary": items_summary,
        "subtotal": sale.subtotal,
        "discount": sale.discount,
        "total": sale.total,
        "payment_type": sale.payment_type,
        "payment_label": pay_label,
        "status": "debt" if is_debt else "paid",
        "status_label": status_label,
        "whatsapp_msg": msg,
        "actions": actions,
    }
    threading.Thread(target=_post_webhook, args=(url, payload), daemon=True).start()


def next_sale_no():
    today = date.today().strftime("%Y%m%d")
    last = Sale.query.filter(Sale.sale_no.like(f"S{today}%")).order_by(Sale.id.desc()).first()
    seq = (int(last.sale_no[-4:]) + 1) if last else 1
    return f"S{today}{seq:04d}"


# ──────────────── Dashboard ────────────────
@pos_bp.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    sales_today = Sale.query.filter(
        db.func.date(Sale.created_at) == today,
        Sale.voided == False
    ).all()
    revenue_today = sum(s.total for s in sales_today if s.payment_type in ("cash", "transfer"))
    debt_today    = sum(s.total for s in sales_today if s.payment_type == "debt")
    tx_count      = len(sales_today)

    monthly_rows = db.session.query(
        extract("year",  Sale.created_at).label("y"),
        extract("month", Sale.created_at).label("m"),
        func.sum(Sale.total).label("total")
    ).filter(Sale.voided == False).group_by("y", "m").order_by("y", "m").limit(12).all()
    monthly = [(int(r.y), int(r.m), float(r.total)) for r in monthly_rows]

    debt_sales = Sale.query.filter_by(payment_type="debt", voided=False).all()
    total_debt_outstanding = sum(s.debt_remaining for s in debt_sales)
    low_stock = Product.query.filter(Product.stock_qty <= 5, Product.active == True).all()

    # Payment breakdown this month
    month_sales = Sale.query.filter(
        extract("year",  Sale.created_at) == today.year,
        extract("month", Sale.created_at) == today.month,
        Sale.voided == False
    ).all()
    cash_month     = sum(s.total for s in month_sales if s.payment_type == "cash")
    transfer_month = sum(s.total for s in month_sales if s.payment_type == "transfer")
    debt_month     = sum(s.total for s in month_sales if s.payment_type == "debt")

    # Recent sales (last 10)
    recent_sales = Sale.query.filter_by(voided=False).order_by(Sale.created_at.desc()).limit(10).all()

    return render_template("dashboard.html",
        revenue_today=revenue_today, debt_today=debt_today,
        tx_count=tx_count, total_debt_outstanding=total_debt_outstanding,
        low_stock=low_stock, monthly=monthly,
        cash_month=cash_month, transfer_month=transfer_month, debt_month=debt_month,
        recent_sales=recent_sales)


# ──────────────── POS page ────────────────
@pos_bp.route("/")
@login_required
def pos_page():
    customers = Customer.query.order_by(Customer.name).all()
    rate = Setting.get("thb_to_lak", "830")
    shop_qr          = Setting.get("shop_qr", "")
    bank_name        = Setting.get("bank_name", "")
    bank_account_name = Setting.get("bank_account_name", "")
    bank_account_no  = Setting.get("bank_account_no", "")
    thb_qr               = Setting.get("thb_qr", "")
    thb_bank_name        = Setting.get("thb_bank_name", "")
    thb_bank_account_name = Setting.get("thb_bank_account_name", "")
    thb_bank_account_no  = Setting.get("thb_bank_account_no", "")
    return render_template("pos/index.html",
        customers=customers, rate=rate,
        shop_qr=shop_qr, bank_name=bank_name,
        bank_account_name=bank_account_name, bank_account_no=bank_account_no,
        thb_qr=thb_qr, thb_bank_name=thb_bank_name,
        thb_bank_account_name=thb_bank_account_name, thb_bank_account_no=thb_bank_account_no,
    )


# ──────────────── Product search (text + barcode) ────────────────
@pos_bp.route("/search")
@login_required
def search_product():
    q = request.args.get("q", "").strip()
    results = Product.query.filter(
        Product.active == True,
        db.or_(Product.name.ilike(f"%{q}%"), Product.code.ilike(f"%{q}%"))
    ).limit(20).all()
    return jsonify([p.to_dict() for p in results])


# ──────────────── Customer lookup (phone or name) ────────────────
@pos_bp.route("/customer-lookup")
@login_required
def customer_lookup():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    customers = Customer.query.filter(
        db.or_(Customer.phone.ilike(f"%{q}%"), Customer.name.ilike(f"%{q}%"))
    ).limit(10).all()
    return jsonify([{
        "id": c.id, "name": c.name,
        "phone": c.phone, "debt": c.total_debt,
        "map_url": c.map_url or ""
    } for c in customers])


# ──────────────── Product suggestions ────────────────
@pos_bp.route("/suggestions")
@login_required
def suggestions():
    mode = request.args.get("mode", "bestseller")

    if mode == "recent":
        # ສິນຄ້າທີ່ຫາກໍ່ຂາຍ (10 ລາຍການຫຼ້າສຸດ ທີ່ຕ່າງກັນ)
        sub = db.session.query(SaleItem.product_id, func.max(Sale.created_at).label("last_sold"))\
            .join(Sale)\
            .group_by(SaleItem.product_id)\
            .order_by(func.max(Sale.created_at).desc())\
            .limit(12).subquery()
        rows = db.session.query(Product).join(sub, Product.id == sub.c.product_id)\
            .filter(Product.active == True).all()
    else:
        # ສິນຄ້າຂາຍດີ (by total qty)
        sub = db.session.query(SaleItem.product_id, func.sum(SaleItem.qty).label("total_qty"))\
            .group_by(SaleItem.product_id)\
            .order_by(func.sum(SaleItem.qty).desc())\
            .limit(12).subquery()
        rows = db.session.query(Product).join(sub, Product.id == sub.c.product_id)\
            .filter(Product.active == True).all()

    return jsonify([p.to_dict() for p in rows])


# ──────────────── Create sale ────────────────
@pos_bp.route("/sale", methods=["POST"])
@login_required
def create_sale():
    data = request.get_json()
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "ບໍ່ມີລາຍການ"}), 400

    payment_type = data.get("payment_type", "cash")
    currency     = data.get("currency", "LAK")        # LAK / THB
    customer_id  = data.get("customer_id") or None
    discount     = float(data.get("discount", 0))
    note         = data.get("note", "")
    paid_amount_input = data.get("paid_amount")

    if payment_type == "debt" and not customer_id:
        return jsonify({"error": "ຕ້ອງເລືອກລູກຄ້າສຳລັບການຈັດສົ່ງ (ຄ້າງຊຳລະ)"}), 400

    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except ValueError:
        rate = 830.0

    subtotal = 0
    sale_items = []
    for it in items:
        product = Product.query.get(it["product_id"])
        if not product:
            continue
        qty        = float(it["qty"])
        unit_price = float(it.get("unit_price", product.sell_price))
        sub        = qty * unit_price
        subtotal  += sub
        sale_items.append((product, qty, unit_price, sub))

    total_kip = max(0, subtotal - discount)

    if payment_type == "cash" and paid_amount_input is not None:
        paid_kip = float(paid_amount_input)
        change_amt = max(0.0, paid_kip - total_kip)
    else:
        paid_kip = total_kip if payment_type in ("cash", "transfer") else 0
        change_amt = 0.0

    # ຖ້າຊໍາລະເປັນ THB ຄຳນວນຍອດ LAK ຄືເດີມ, ແຕ່ record currency
    sale = Sale(
        sale_no=next_sale_no(),
        customer_id=customer_id,
        employee_id=current_user.id,
        subtotal=subtotal,
        discount=discount,
        total=total_kip,
        payment_type=payment_type,
        currency=currency,
        paid_amount=paid_kip,
        change_amount=change_amt,
        note=note,
    )
    db.session.add(sale)
    db.session.flush()

    for product, qty, price, sub in sale_items:
        si = SaleItem(sale_id=sale.id, product_id=product.id,
                      qty=qty, unit_price=price, subtotal=sub)
        db.session.add(si)
        # ໂຕນ: 1 ໂຕນ = 20 ສອບ → ລົບ stock ຕາມ ສອບ
        deduct = qty * 20 if product.unit == "ໂຕນ" else qty
        product.stock_qty = max(0, product.stock_qty - deduct)

    if payment_type == "debt" and customer_id:
        cust = Customer.query.get(customer_id)
        if cust:
            cust.total_debt += total_kip

    db.session.commit()
    notify_n8n(sale)
    return jsonify({"sale_id": sale.id, "sale_no": sale.sale_no, "change_amount": change_amt})


# ──────────────── Receipt ────────────────
@pos_bp.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except Exception:
        rate = 830.0
    try:
        receipt_rows = int(Setting.get("receipt_rows", "15"))
    except Exception:
        receipt_rows = 15
    return render_template("pos/receipt.html", sale=sale,
        shop_name=Setting.get("shop_name", "ຮ້ານວັດສະດຸກໍ່ສ້າງ"),
        shop_address=Setting.get("shop_address", ""),
        shop_phone=Setting.get("shop_phone", ""),
        shop_qr=Setting.get("shop_qr", ""),
        receipt_footer=Setting.get("receipt_footer", ""),
        receipt_auto_print=Setting.get("receipt_auto_print", "1"),
        receipt_rows=receipt_rows,
        rate=rate)


# ──────────────── Void sale ────────────────
@pos_bp.route("/void/<int:sale_id>", methods=["POST"])
@login_required
def void_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if sale.voided:
        flash("ບິນນີ້ຖືກຍົກເລີກໄປແລ້ວ", "warning")
        return redirect(request.referrer or url_for("reports.index"))

    # Restore stock (ໂຕນ: ×20 ສອບ)
    for item in sale.items:
        if item.product:
            restore = item.qty * 20 if item.product.unit == "ໂຕນ" else item.qty
            item.product.stock_qty += restore

    # Reverse remaining customer debt (exclude already-paid portion)
    if sale.payment_type == "debt" and sale.customer_id:
        cust = Customer.query.get(sale.customer_id)
        if cust:
            cust.total_debt = max(0, cust.total_debt - sale.debt_remaining)

    sale.voided = True
    sale.voided_at = datetime.now(timezone.utc)
    sale.voided_by = current_user.id
    db.session.commit()

    flash(f"ຍົກເລີກບິນ {sale.sale_no} ສໍາເລັດ — ສິນຄ້າກັບຄືນ stock ແລ້ວ", "success")
    return redirect(request.referrer or url_for("reports.index"))


# ──────────────── Customer display (mirror screen) ────────────────
@pos_bp.route("/customer-display")
def customer_display():
    shop_name = Setting.get("shop_name", "ຮ້ານວັດສະດຸກໍ່ສ້າງ")
    return render_template("pos/customer_display.html", shop_name=shop_name)


# ──────────────── Cashback quota status ────────────────
@pos_bp.route("/cashback-set", methods=["POST"])
@login_required
def cashback_set():
    if not current_user.is_manager():
        return jsonify({"error": "ສິດທິບໍ່ພຽງພໍ"}), 403
    data = request.get_json() or {}
    quota = data.get("quota")
    if quota is not None:
        Setting.set("cashback_daily_quota", str(max(0, float(quota))))
        db.session.commit()
    return jsonify({"ok": True})


@pos_bp.route("/cashback-status")
@login_required
def cashback_status():
    from sqlalchemy import func as sqlfunc
    today = date.today()
    used = db.session.query(sqlfunc.sum(Sale.change_amount)).filter(
        func.date(Sale.created_at) == today,
        Sale.payment_type == "cash",
    ).scalar() or 0.0
    quota = float(Setting.get("cashback_daily_quota", "0"))
    remaining = max(0.0, quota - used) if quota > 0 else None
    return jsonify({"used": used, "quota": quota, "remaining": remaining})


# ──────────────── Webhook test (from settings page) ────────────────
@pos_bp.route("/api/test-webhook", methods=["POST"])
@login_required
def api_test_webhook():
    url = (request.get_json() or {}).get("url", "").strip()
    if not url:
        return jsonify({"ok": False, "error": "ບໍ່ມີ URL"})
    payload = {
        "event": "test",
        "message": "ທົດສອບຈາກ POS ສຳເລັດ! 🎉",
        "shop": Setting.get("shop_name", "ຮ້ານ"),
        "whatsapp_msg": "✅ ທົດສອບ n8n ສຳເລັດ!\nPOS ເຊື່ອມຕໍ່ n8n ໄດ້ແລ້ວ 🎉",
    }
    try:
        r = _req.post(url, json=payload, timeout=8)
        return jsonify({"ok": True, "status": r.status_code})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ──────────────── Daily Summary API (for n8n cron) ────────────────
@pos_bp.route("/api/daily-summary")
def api_daily_summary():
    """n8n ເອີ້ນ endpoint ນີ້ທຸກ 18:30 ເພື່ອດຶງຍອດປະຈຳວັນ"""
    api_key = Setting.get("n8n_api_key", "")
    if api_key and request.args.get("key") != api_key:
        return jsonify({"error": "unauthorized"}), 401

    sel_date = request.args.get("date") or date.today().isoformat()
    try:
        d = date.fromisoformat(sel_date)
    except ValueError:
        d = date.today()

    sales = Sale.query.filter(
        func.date(Sale.created_at) == d,
        Sale.voided == False
    ).all()

    total_revenue = sum(s.total for s in sales)
    cash_total    = sum(s.total for s in sales if s.payment_type == "cash")
    transfer_total = sum(s.total for s in sales if s.payment_type == "transfer")
    debt_total    = sum(s.total for s in sales if s.payment_type == "debt")
    debt_count    = sum(1 for s in sales if s.payment_type == "debt")

    # ລາຍຊື່ລູກຄ້າທີ່ຍັງຄ້າງຊຳລະ (ທຸກໆ debt ທີ່ຍັງຄ້າງ ບໍ່ຈຳກັດສະເພາະວັນນີ້)
    debt_customers = (
        db.session.query(Customer.name, func.sum(Sale.total - Sale.paid_amount).label("outstanding"))
        .join(Sale, Sale.customer_id == Customer.id)
        .filter(Sale.payment_type == "debt", Sale.voided == False)
        .group_by(Customer.id, Customer.name)
        .having(func.sum(Sale.total - Sale.paid_amount) > 0)
        .order_by(func.sum(Sale.total - Sale.paid_amount).desc())
        .all()
    )

    if debt_customers:
        debt_lines = "\n".join(
            f"  • {row.name}: {row.outstanding:,.0f} ₭"
            for row in debt_customers
        )
        debt_section = f"\n\n📋 *ລາຍຊື່ຄ້າງຊຳລະ:*\n{debt_lines}"
    else:
        debt_section = ""

    divider = "─" * 17
    msg = (
        f"📊 *ສະຫຼຸບຍອດ {d.strftime('%d/%m/%Y')}*\n"
        f"{divider}\n"
        f"🧾 ບິນທັງໝົດ:   *{len(sales)} ບິນ*\n"
        f"💰 ລາຍຮັບລວມ: *{total_revenue:,.0f} ₭*\n"
        f"{divider}\n"
        f"  💵 ເງິນສົດ:     {cash_total:,.0f} ₭\n"
        f"  📲 ໂອນເງິນ:    {transfer_total:,.0f} ₭\n"
        f"  ⚠️  ຄ້າງຊຳລະ:  {debt_total:,.0f} ₭  ({debt_count} ບິນ)\n"
        f"{divider}"
        f"{debt_section}" 
    )

    return jsonify({
        "event": "daily_summary",
        "date": d.isoformat(),
        "date_lao": d.strftime("%d/%m/%Y"),
        "total_sales": len(sales),
        "total_revenue": total_revenue,
        "cash_total": cash_total,
        "transfer_total": transfer_total,
        "debt_total": debt_total,
        "debt_count": debt_count,
        "whatsapp_msg": msg,
        "debt_customers": [
            {"name": row.name, "outstanding": float(row.outstanding)}
            for row in debt_customers
        ],
        "sales": [
            {"sale_no": s.sale_no,
             "total": s.total,
             "payment_type": s.payment_type,
             "customer": s.customer.name if s.customer else ""}
            for s in sales
        ]
    })


# ──────────────── Mark debt sale as paid (Telegram bot callback) ────────────────
def _check_api_key():
    api_key = Setting.get("n8n_api_key", "")
    if not api_key:
        return True
    provided = (
        request.headers.get("X-API-Key")
        or request.args.get("key")
        or (request.get_json(silent=True) or {}).get("key")
    )
    return provided == api_key


@pos_bp.route("/api/sales/<sale_no>/mark-paid", methods=["POST"])
def api_mark_paid(sale_no):
    """n8n ເອີ້ນເມື່ອລູກຄ້າກົດປຸ່ມ 'ຮັບເງິນສົດ' ຫຼື 'ໂອນແລ້ວ' ໃນ Telegram"""
    if not _check_api_key():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    method = (data.get("method") or "").strip().lower()
    if method not in ("cash", "transfer"):
        return jsonify({"ok": False, "error": "invalid method"}), 400

    sale = Sale.query.filter_by(sale_no=sale_no).first()
    if not sale:
        return jsonify({"ok": False, "error": "sale not found"}), 404
    if sale.voided:
        return jsonify({"ok": False, "error": "sale voided"}), 400
    if sale.payment_type != "debt":
        return jsonify({
            "ok": False,
            "error": "already paid",
            "status": sale.payment_type,
        }), 400

    remaining = sale.debt_remaining
    if remaining > 0:
        db.session.add(DebtPayment(
            sale_id=sale.id,
            customer_id=sale.customer_id,
            amount=remaining,
            note=f"ຊຳລະຜ່ານ Telegram ({method})",
        ))
        if sale.customer_id:
            cust = Customer.query.get(sale.customer_id)
            if cust:
                cust.total_debt = max(0, (cust.total_debt or 0) - remaining)

    sale.payment_type = method
    sale.paid_amount = sale.total
    db.session.commit()

    method_label = "ເງິນສົດ" if method == "cash" else "ໂອນເງິນ"
    status_label = f"✅ ຊຳລະແລ້ວ ({method_label})"
    local_dt = sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO)
    customer_name = sale.customer.name if sale.customer else "ລູກຄ້າທົ່ວໄປ"
    items_lines = "\n".join(
        f"  • {si.product.name if si.product else '?'} ×{si.qty:g}  {si.subtotal:,.0f}₭"
        for si in sale.items
    )
    updated_msg = (
        f"🧾 *ບິນ #{sale.sale_no}*\n"
        f"📅 {local_dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"👤 {customer_name}\n\n"
        f"{items_lines}\n\n"
        f"💰 ລວມ: *{sale.total:,.0f} ກີບ*\n"
        f"{status_label}"
    )

    return jsonify({
        "ok": True,
        "event": "daily_summary",
        "date_lao": d.strftime("%d/%m/%Y"),
        "total_revenue": total_revenue,
        "telegram_msg": msg, 
        "data": {
            "total_sales": len(sales),
            "cash_total": cash_total,
            "transfer_total": transfer_total,
            "debt_total": debt_total,
            "debt_count": debt_count
        }
    })
