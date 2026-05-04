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


def _get_rate():
    try:
        return float(Setting.get("thb_to_lak", "830"))
    except Exception:
        return 830.0


def _build_sale_message(sale):
    """ສ້າງຂໍ້ຄວາມ Telegram/WhatsApp ສຳລັບບິນ"""
    rate = _get_rate()
    is_thb = (sale.currency or "LAK") == "THB"

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
        f"  • {si.product.name if si.product else '?'} ×{si.qty:g}  "
        + (f"฿{si.subtotal/rate:,.2f}" if is_thb else f"{si.subtotal:,.0f}₭")
        for si in sale.items
    )
    total_display = f"฿{sale.total/rate:,.2f} ບາດ" if is_thb else f"{sale.total:,.0f} ກີບ"
    local_dt = sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO)
    msg = (
        f"🧾 *ບິນໃໝ່ #{sale.sale_no}*\n"
        f"📅 {local_dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"👤 {customer_name}\n\n"
        f"{items_lines}\n\n"
        f"💰 ລວມ: *{total_display}*\n"
        f"{status_label}"
    )
    return msg, pay_label, status_label, is_debt, customer_name


def notify_n8n(sale):
    """ສ້າງ payload ແລ້ວ ສົ່ງໄປ n8n webhook (background thread)"""
    url = Setting.get("n8n_webhook_url", "").strip()
    if not url:
        return
    rate = _get_rate()
    is_thb = (sale.currency or "LAK") == "THB"
    msg, pay_label, status_label, is_debt, customer_name = _build_sale_message(sale)
    cur_sym = "฿" if is_thb else "₭"
    items_summary = " | ".join(
        f"{si.product.name if si.product else '?'} ×{si.qty:g}"
        for si in sale.items
    )
    items_text = "\n".join(
        f"{si.product.name if si.product else '?'} ×{si.qty:g} = "
        + (f"฿{si.subtotal/rate:,.2f}" if is_thb else f"{si.subtotal:,.0f}₭")
        for si in sale.items
    )
    total_display = f"฿{sale.total/rate:,.2f}" if is_thb else f"{sale.total:,.0f}₭"
    actions = []
    if is_debt:
        actions = [
            {"text": "💵 ຮັບເງິນສົດ", "callback_data": f"paid_cash:{sale.sale_no}"},
            {"text": "🏦 ໂອນແລ້ວ",   "callback_data": f"paid_transfer:{sale.sale_no}"},
        ]
    payload = {
        "event": "sale_created",
        "sale_no": sale.sale_no,
        "currency": sale.currency or "LAK",
        "date": sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO).strftime("%d/%m/%Y"),
        "time": sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO).strftime("%H:%M"),
        "customer": customer_name,
        "items": [
            {"name": si.product.name if si.product else "?",
             "unit": si.product.unit if si.product else "",
             "qty": si.qty,
             "unit_price": si.unit_price / rate if is_thb else si.unit_price,
             "subtotal": si.subtotal / rate if is_thb else si.subtotal}
            for si in sale.items
        ],
        "currency_symbol": cur_sym,
        "items_summary": items_summary,
        "items_text": items_text,
        "total_display": total_display,
        "subtotal": sale.subtotal / rate if is_thb else sale.subtotal,
        "discount": sale.discount / rate if is_thb else sale.discount,
        "total": sale.total / rate if is_thb else sale.total,
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

    month_sales = Sale.query.filter(
        extract("year",  Sale.created_at) == today.year,
        extract("month", Sale.created_at) == today.month,
        Sale.voided == False
    ).all()
    cash_month     = sum(s.total for s in month_sales if s.payment_type == "cash")
    transfer_month = sum(s.total for s in month_sales if s.payment_type == "transfer")
    debt_month     = sum(s.total for s in month_sales if s.payment_type == "debt")

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
    shop_qr           = Setting.get("shop_qr", "")
    bank_name         = Setting.get("bank_name", "")
    bank_account_name = Setting.get("bank_account_name", "")
    bank_account_no   = Setting.get("bank_account_no", "")
    thb_qr                = Setting.get("thb_qr", "")
    thb_bank_name         = Setting.get("thb_bank_name", "")
    thb_bank_account_name = Setting.get("thb_bank_account_name", "")
    thb_bank_account_no   = Setting.get("thb_bank_account_no", "")
    return render_template("pos/index.html",
        customers=customers, rate=rate,
        shop_qr=shop_qr, bank_name=bank_name,
        bank_account_name=bank_account_name, bank_account_no=bank_account_no,
        thb_qr=thb_qr, thb_bank_name=thb_bank_name,
        thb_bank_account_name=thb_bank_account_name, thb_bank_account_no=thb_bank_account_no,
    )


# ──────────────── Product search ────────────────
@pos_bp.route("/search")
@login_required
def search_product():
    q = request.args.get("q", "").strip()
    results = Product.query.filter(
        Product.active == True,
        db.or_(Product.name.ilike(f"%{q}%"), Product.code.ilike(f"%{q}%"))
    ).limit(20).all()
    return jsonify([p.to_dict() for p in results])


# ──────────────── Customer lookup ────────────────
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
        sub = db.session.query(SaleItem.product_id, func.max(Sale.created_at).label("last_sold"))\
            .join(Sale).group_by(SaleItem.product_id)\
            .order_by(func.max(Sale.created_at).desc()).limit(12).subquery()
        rows = db.session.query(Product).join(sub, Product.id == sub.c.product_id)\
            .filter(Product.active == True).all()
    else:
        sub = db.session.query(SaleItem.product_id, func.sum(SaleItem.qty).label("total_qty"))\
            .group_by(SaleItem.product_id)\
            .order_by(func.sum(SaleItem.qty).desc()).limit(12).subquery()
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

    payment_type      = data.get("payment_type", "cash")
    currency          = data.get("currency", "LAK")
    customer_id       = data.get("customer_id") or None
    discount          = float(data.get("discount", 0))
    note              = data.get("note", "")
    paid_amount_input = data.get("paid_amount")

    if payment_type == "debt" and not customer_id:
        return jsonify({"error": "ຕ້ອງເລືອກລູກຄ້າສຳລັບການຈັດສົ່ງ (ຄ້າງຊຳລະ)"}), 400

    rate_input = data.get("rate")
    if rate_input:
        try:
            rate = float(rate_input)
            if rate > 0:
                Setting.set("thb_to_lak", str(rate))
        except (ValueError, TypeError):
            rate = _get_rate()
    else:
        rate = _get_rate()

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
        paid_kip   = float(paid_amount_input)
        change_amt = max(0.0, paid_kip - total_kip)
    else:
        paid_kip   = total_kip if payment_type in ("cash", "transfer") else 0
        change_amt = 0.0

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
        deduct = qty * 20 if product.unit == "ໂຕນ" else qty
        product.stock_qty = max(0, product.stock_qty - deduct)

    if payment_type == "debt" and customer_id:
        cust = Customer.query.get(customer_id)
        if cust:
            cust.total_debt = (cust.total_debt or 0) + total_kip
            if currency == "THB":
                cust.total_debt_thb = (cust.total_debt_thb or 0) + total_kip / rate

    db.session.commit()
    notify_n8n(sale)
    return jsonify({"sale_id": sale.id, "sale_no": sale.sale_no, "change_amount": change_amt})


# ──────────────── Receipt ────────────────
@pos_bp.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    rate = _get_rate()
    try:
        receipt_rows = int(Setting.get("receipt_rows", "15"))
    except Exception:
        receipt_rows = 15
    currency = request.args.get("currency", "LAK").upper()
    if currency not in ("LAK", "THB"):
        currency = "LAK"
    return render_template("pos/receipt.html", sale=sale,
        shop_name=Setting.get("shop_name", "ຮ້ານວັດສະດຸກໍ່ສ້າງ"),
        shop_address=Setting.get("shop_address", ""),
        shop_phone=Setting.get("shop_phone", ""),
        shop_qr=Setting.get("shop_qr", ""),
        receipt_footer=Setting.get("receipt_footer", ""),
        receipt_auto_print=Setting.get("receipt_auto_print", "1"),
        receipt_rows=receipt_rows,
        rate=rate,
        currency=currency)


# ──────────────── Void sale ────────────────
@pos_bp.route("/void/<int:sale_id>", methods=["POST"])
@login_required
def void_sale(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if sale.voided:
        flash("ບິນນີ້ຖືກຍົກເລີກໄປແລ້ວ", "warning")
        return redirect(request.referrer or url_for("reports.index"))

    for item in sale.items:
        if item.product:
            restore = item.qty * 20 if item.product.unit == "ໂຕນ" else item.qty
            item.product.stock_qty += restore

    if sale.payment_type == "debt" and sale.customer_id:
        rate = _get_rate()
        cust = Customer.query.get(sale.customer_id)
        if cust:
            cust.total_debt = max(0, (cust.total_debt or 0) - sale.debt_remaining)
            if (sale.currency or "LAK") == "THB":
                cust.total_debt_thb = max(0, (cust.total_debt_thb or 0) - sale.debt_remaining / rate)

    sale.voided    = True
    sale.voided_at = datetime.now(timezone.utc)
    sale.voided_by = current_user.id
    db.session.commit()

    flash(f"ຍົກເລີກບິນ {sale.sale_no} ສໍາເລັດ — ສິນຄ້າກັບຄືນ stock ແລ້ວ", "success")
    return redirect(request.referrer or url_for("reports.index"))


# ──────────────── Customer display ────────────────
@pos_bp.route("/customer-display")
def customer_display():
    shop_name   = Setting.get("shop_name", "ຮ້ານວັດສະດຸກໍ່ສ້າງ")
    ads_enabled = Setting.get("ads_enabled", "0") == "1"
    ads_text    = Setting.get("ads_text", "")
    ads_speed   = Setting.get("ads_speed", "30")
    lines = [l.strip() for l in ads_text.splitlines() if l.strip()]
    ids_str = Setting.get("ads_product_ids", "")
    if ids_str:
        ids = [int(i) for i in ids_str.split(",") if i.strip().isdigit()]
        if ids:
            prods = Product.query.filter(Product.id.in_(ids), Product.active == True).all()
            for p in prods:
                lines.append(f"{p.name} - {int(p.sell_price):,} ₭/{p.unit}")
    return render_template("pos/customer_display.html",
                           shop_name=shop_name,
                           ads_enabled=ads_enabled,
                           ads_text="\n".join(lines),
                           ads_speed=ads_speed)


# ──────────────── Cashback ────────────────
@pos_bp.route("/cashback-set", methods=["POST"])
@login_required
def cashback_set():
    if not current_user.is_accountant():
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
        Sale.voided == False,
    ).scalar() or 0.0
    quota     = float(Setting.get("cashback_daily_quota", "0"))
    remaining = max(0.0, quota - used) if quota > 0 else None
    return jsonify({"used": used, "quota": quota, "remaining": remaining})


# ──────────────── Webhook test ────────────────
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


# ──────────────── Daily Summary API ────────────────
@pos_bp.route("/api/daily-summary")
def api_daily_summary():
    api_key = Setting.get("n8n_api_key", "")
    if api_key and request.args.get("key") != api_key:
        return jsonify({"error": "unauthorized"}), 401

    sel_date = request.args.get("date") or date.today().isoformat()
    try:
        d = date.fromisoformat(sel_date)
    except ValueError:
        d = date.today()

    rate = _get_rate()

    sales = Sale.query.filter(
        func.date(Sale.created_at) == d,
        Sale.voided == False
    ).all()

    total_revenue  = sum(s.total for s in sales)
    cash_total     = sum(s.total for s in sales if s.payment_type == "cash")
    transfer_total = sum(s.total for s in sales if s.payment_type == "transfer")
    debt_total     = sum(s.total for s in sales if s.payment_type == "debt")
    debt_count     = sum(1 for s in sales if s.payment_type == "debt")

    # ລາຍຊື່ລູກຄ້າຄ້າງຊຳລະ
    debt_sales_all = (Sale.query
                     .filter_by(payment_type="debt", voided=False)
                     .filter(Sale.customer_id.isnot(None)).all())
    cust_outstanding = {}
    for s in debt_sales_all:
        rem = s.debt_remaining
        if rem <= 0:
            continue
        cname = s.customer.name if s.customer else "?"
        is_thb = (s.currency or "LAK") == "THB"
        if cname not in cust_outstanding:
            cust_outstanding[cname] = {"lak": 0, "thb": 0}
        if is_thb:
            cust_outstanding[cname]["thb"] += rem / rate
        else:
            cust_outstanding[cname]["lak"] += rem

    if cust_outstanding:
        debt_lines = []
        for name, amounts in sorted(cust_outstanding.items(),
                                    key=lambda x: x[1]["lak"] + x[1]["thb"] * rate,
                                    reverse=True):
            parts = []
            if amounts["lak"] > 0:
                parts.append(f"{amounts['lak']:,.0f} ₭")
            if amounts["thb"] > 0:
                parts.append(f"฿{amounts['thb']:,.2f}")
            debt_lines.append(f"  • {name}: {' + '.join(parts)}")
        debt_section = "\n\n📋 *ລາຍຊື່ຄ້າງຊຳລະ:*\n" + "\n".join(debt_lines)
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
            {"name": n, "lak": v["lak"], "thb": v["thb"]}
            for n, v in cust_outstanding.items()
        ],
        "sales": [
            {"sale_no": s.sale_no, "total": s.total,
             "currency": s.currency or "LAK",
             "payment_type": s.payment_type,
             "customer": s.customer.name if s.customer else ""}
            for s in sales
        ]
    })


# ──────────────── Mark debt as paid (Telegram callback) ────────────────
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
    if not _check_api_key():
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    data   = request.get_json(silent=True) or {}
    method = (data.get("method") or "").strip().lower()
    if method not in ("cash", "transfer"):
        return jsonify({"ok": False, "error": "invalid method"}), 400

    sale = Sale.query.filter_by(sale_no=sale_no).first()
    if not sale:
        return jsonify({"ok": False, "error": "sale not found"}), 404
    if sale.voided:
        return jsonify({"ok": False, "error": "sale voided"}), 400
    if sale.payment_type != "debt":
        return jsonify({"ok": False, "error": "already paid", "status": sale.payment_type}), 400

    rate   = _get_rate()
    is_thb = (sale.currency or "LAK") == "THB"

    remaining = sale.debt_remaining
    if remaining > 0:
        db.session.add(DebtPayment(
            sale_id=sale.id,
            customer_id=sale.customer_id,
            amount=remaining,
            currency=sale.currency or "LAK",
            note=f"ຊຳລະຜ່ານ Telegram ({method})",
        ))
        if sale.customer_id:
            cust = Customer.query.get(sale.customer_id)
            if cust:
                cust.total_debt = max(0, (cust.total_debt or 0) - remaining)
                if is_thb:
                    cust.total_debt_thb = max(0, (cust.total_debt_thb or 0) - remaining / rate)

    sale.payment_type = method
    sale.paid_amount  = sale.total
    db.session.commit()

    method_label  = "ເງິນສົດ" if method == "cash" else "ໂອນເງິນ"
    status_label  = f"✅ ຊຳລະແລ້ວ ({method_label})"
    local_dt      = sale.created_at.replace(tzinfo=timezone.utc).astimezone(_TZ_LAO)
    customer_name = sale.customer.name if sale.customer else "ລູກຄ້າທົ່ວໄປ"
    total_display = f"฿{sale.total/rate:,.2f} ບາດ" if is_thb else f"{sale.total:,.0f} ກີບ"
    items_lines   = "\n".join(
        f"  • {si.product.name if si.product else '?'} ×{si.qty:g}  "
        + (f"฿{si.subtotal/rate:,.2f}" if is_thb else f"{si.subtotal:,.0f}₭")
        for si in sale.items
    )
    updated_msg = (
        f"🧾 *ບິນ #{sale.sale_no}*\n"
        f"📅 {local_dt.strftime('%d/%m/%Y %H:%M')}\n"
        f"👤 {customer_name}\n\n"
        f"{items_lines}\n\n"
        f"💰 ລວມ: *{total_display}*\n"
        f"{status_label}"
    )

    return jsonify({
        "ok": True,
        "sale_no": sale.sale_no,
        "method": method,
        "telegram_msg": updated_msg,
    })
