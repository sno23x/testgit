from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, Setting, Product

settings_bp = Blueprint("settings", __name__)

DEFAULT_SETTINGS = {
    "shop_name": "ຮ້ານວັດສະດຸກໍ່ສ້າງ",
    "shop_address": "ທີ່ຢູ່ຮ້ານ",
    "shop_phone": "020-XXXXXXXX",
    "shop_qr": "",        # URL ຫຼື path ຮູບ QR ຮ້ານ
    "thb_to_lak": "830",  # 1 ບາດ = 830 ກີບ (ຄ່າເລີ່ມຕົ້ນ)
}


@settings_bp.route("/")
@login_required
def index():
    if not current_user.is_admin():
        flash("ສິດທິ admin ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("pos.dashboard"))
    vals = {k: Setting.get(k, v) for k, v in DEFAULT_SETTINGS.items()}
    return render_template("settings/index.html", s=vals)


@settings_bp.route("/save", methods=["POST"])
@login_required
def save():
    if not current_user.is_admin():
        flash("ສິດທິ admin ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("pos.dashboard"))
    for key in DEFAULT_SETTINGS:
        val = request.form.get(key, "").strip()
        Setting.set(key, val)
    db.session.commit()
    flash("ບັນທຶກການຕັ້ງຄ່າສໍາເລັດ", "success")
    return redirect(url_for("settings.index"))


@settings_bp.route("/recalculate", methods=["POST"])
@login_required
def recalculate():
    """ຄຳນວນລາຄາ LAK ໃໝ່ທັງໝົດ ໂດຍໃຊ້ exchange rate ປັດຈຸບັນ"""
    if not current_user.is_admin():
        flash("ສິດທິ admin ເທົ່ານັ້ນ", "danger")
        return redirect(url_for("settings.index"))
    try:
        rate = float(Setting.get("thb_to_lak", "830"))
    except ValueError:
        flash("Exchange rate ບໍ່ຖືກຕ້ອງ", "danger")
        return redirect(url_for("settings.index"))

    updated = 0
    for p in Product.query.filter(Product.price_thb.isnot(None), Product.active == True).all():
        if p.price_thb and p.price_thb > 0:
            p.sell_price = round(p.price_thb * rate)
            updated += 1
    db.session.commit()
    flash(f"ຄຳນວນລາຄາໃໝ່ {updated} ລາຍການ (rate: 1 ບາດ = {rate:,.0f} ກີບ)", "success")
    return redirect(url_for("settings.index"))
