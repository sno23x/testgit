import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import db, Setting, Product, round_price

QR_UPLOAD_DIR = os.path.join("static", "uploads", "qr")

settings_bp = Blueprint("settings", __name__)

DEFAULT_SETTINGS = {
    "shop_name": "ຮ້ານວັດສະດຸກໍ່ສ້າງ",
    "shop_address": "ທີ່ຢູ່ຮ້ານ",
    "shop_phone": "020-XXXXXXXX",
    "shop_qr": "",
    "thb_qr": "",               # QR ເງິນບາດ (Thai bank PromptPay)
    "thb_bank_name": "",        # ທະນາຄານໄທ
    "thb_bank_account_name": "",
    "thb_bank_account_no": "",
    "bank_name": "",           # ຊື່ທະນາຄານ / ຊື່ Mobile Banking
    "bank_account_name": "",   # ຊື່ບັນຊີ
    "bank_account_no": "",     # ເລກບັນຊີ
    "thb_to_lak": "830",
    "receipt_rows": "15",
    "receipt_auto_print": "1",
    "receipt_footer": "",
    "n8n_webhook_url": "",
    "n8n_api_key": "",
    "callmebot_phone": "",
    "callmebot_apikey": "",
    "cashback_daily_quota": "0",
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
    # Handle QR image uploads (takes priority over text URL)
    os.makedirs(QR_UPLOAD_DIR, exist_ok=True)
    for qr_key, file_field in [("shop_qr", "shop_qr_file"), ("thb_qr", "thb_qr_file")]:
        f = request.files.get(file_field)
        if f and f.filename:
            ext = os.path.splitext(secure_filename(f.filename))[1].lower() or ".jpg"
            save_path = os.path.join(QR_UPLOAD_DIR, f"{qr_key}{ext}")
            f.save(save_path)
            Setting.set(qr_key, "/" + save_path.replace("\\", "/"))

    for key in DEFAULT_SETTINGS:
        if key in request.form:
            # Skip QR keys if a file was uploaded (already handled above)
            if key in ("shop_qr", "thb_qr"):
                file_field = "shop_qr_file" if key == "shop_qr" else "thb_qr_file"
                f = request.files.get(file_field)
                if f and f.filename:
                    continue
            Setting.set(key, request.form.get(key, "").strip())
    # Handle unchecked checkboxes explicitly
    if "receipt_auto_print" not in request.form and "receipt_rows" in request.form:
        Setting.set("receipt_auto_print", "0")
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
            p.sell_price = round_price(p.price_thb * rate)
            updated += 1
    db.session.commit()
    flash(f"ຄຳນວນລາຄາໃໝ່ {updated} ລາຍການ (rate: 1 ບາດ = {rate:,.0f} ກີບ)", "success")
    return redirect(url_for("settings.index"))
