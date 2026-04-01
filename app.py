import os
import io
import uuid
import base64
from datetime import datetime, timedelta, timezone

import qrcode
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_file,
    abort,
    jsonify,
)
from werkzeug.utils import secure_filename

from models import db, Product, Order, OrderItem, DownloadToken

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(
    BASE_DIR, "instance", "database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "instance", "slips")
app.config["FILES_FOLDER"] = os.path.join(BASE_DIR, "files")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# PromptPay phone/tax-ID (set via env or change here)
PROMPTPAY_ID = os.environ.get("PROMPTPAY_ID", "0812345678")

db.init_app(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def build_promptpay_payload(phone_or_tax: str, amount: float) -> str:
    """Build EMVCo PromptPay QR payload string."""

    def crc16(data: str) -> str:
        crc = 0xFFFF
        for ch in data.encode("ascii"):
            crc ^= ch << 8
            for _ in range(8):
                crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        return format(crc & 0xFFFF, "04X")

    def field(tag: str, value: str) -> str:
        return f"{tag}{len(value):02d}{value}"

    # Normalise phone number to 66XXXXXXXXX
    pid = phone_or_tax.strip().lstrip("0")
    if len(pid) == 9:  # local phone stripped of leading 0
        pid = "66" + pid
    # Tax ID stays as-is (13 digits)

    merchant_account = field("00", "A000000677010111") + field("01", "0066" + pid if len(pid) == 11 else pid)
    payload = (
        field("00", "01")
        + field("01", "12")  # static QR – change to "11" for one-time
        + field("29", merchant_account)
        + field("53", "764")  # THB
        + field("54", f"{amount:.2f}")
        + field("58", "TH")
        + "6304"
    )
    return payload + crc16(payload)


def generate_qr_base64(payload: str) -> str:
    """Return base64-encoded PNG of QR code."""
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def get_cart() -> dict:
    return session.get("cart", {})


def save_cart(cart: dict):
    session["cart"] = cart
    session.modified = True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    category = request.args.get("category", "")
    query = Product.query.filter_by(active=True)
    if category:
        query = query.filter_by(category=category)
    products = query.order_by(Product.id).all()
    categories = (
        db.session.query(Product.category).filter_by(active=True).distinct().all()
    )
    categories = [c[0] for c in categories]
    cart = get_cart()
    cart_count = sum(v["qty"] for v in cart.values())
    return render_template(
        "index.html",
        products=products,
        categories=categories,
        selected_category=category,
        cart_count=cart_count,
    )


@app.route("/product/<int:pid>")
def product_detail(pid: int):
    product = Product.query.get_or_404(pid)
    cart_count = sum(v["qty"] for v in get_cart().values())
    return render_template("product.html", product=product, cart_count=cart_count)


# --- Cart ---

@app.route("/cart/add", methods=["POST"])
def cart_add():
    pid = str(request.form.get("product_id", ""))
    product = Product.query.get_or_404(int(pid))
    cart = get_cart()
    if pid in cart:
        cart[pid]["qty"] += 1
    else:
        cart[pid] = {"name": product.name, "price": product.price, "qty": 1}
    save_cart(cart)
    return redirect(url_for("cart_view"))


@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    pid = str(request.form.get("product_id", ""))
    cart = get_cart()
    cart.pop(pid, None)
    save_cart(cart)
    return redirect(url_for("cart_view"))


@app.route("/cart")
def cart_view():
    cart = get_cart()
    total = sum(v["price"] * v["qty"] for v in cart.values())
    cart_count = sum(v["qty"] for v in cart.values())
    return render_template("cart.html", cart=cart, total=total, cart_count=cart_count)


# --- Checkout ---

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = get_cart()
    if not cart:
        return redirect(url_for("index"))

    total = sum(v["price"] * v["qty"] for v in cart.values())
    cart_count = sum(v["qty"] for v in cart.values())

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not email:
            return render_template(
                "checkout.html",
                cart=cart,
                total=total,
                cart_count=cart_count,
                error="กรุณากรอกชื่อและอีเมล",
            )

        order = Order(
            customer_name=name,
            customer_email=email,
            customer_phone=phone,
            total=total,
            status="pending",
        )
        db.session.add(order)
        db.session.flush()  # get order.id

        for pid_str, info in cart.items():
            item = OrderItem(
                order_id=order.id,
                product_id=int(pid_str),
                quantity=info["qty"],
                unit_price=info["price"],
            )
            db.session.add(item)

        db.session.commit()
        save_cart({})
        return redirect(url_for("payment", order_id=order.id))

    return render_template(
        "checkout.html", cart=cart, total=total, cart_count=cart_count, error=None
    )


# --- Payment ---

@app.route("/payment/<int:order_id>")
def payment(order_id: int):
    order = Order.query.get_or_404(order_id)
    if order.status == "paid":
        return redirect(url_for("download_list", order_id=order.id))

    payload = build_promptpay_payload(PROMPTPAY_ID, order.total)
    qr_b64 = generate_qr_base64(payload)
    cart_count = 0
    return render_template(
        "payment.html", order=order, qr_b64=qr_b64, cart_count=cart_count
    )


@app.route("/payment/<int:order_id>/slip", methods=["POST"])
def upload_slip(order_id: int):
    order = Order.query.get_or_404(order_id)
    if order.status == "paid":
        return redirect(url_for("download_list", order_id=order.id))

    slip = request.files.get("slip")
    if slip and allowed_file(slip.filename):
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        filename = secure_filename(f"order{order_id}_{slip.filename}")
        slip.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        order.slip_path = filename

    # Mark as paid and generate download tokens
    order.status = "paid"
    expires = datetime.now(timezone.utc) + timedelta(hours=24)
    for item in order.items:
        for _ in range(item.quantity):
            token = DownloadToken(
                order_id=order.id,
                product_id=item.product_id,
                token=uuid.uuid4().hex,
                expires_at=expires,
            )
            db.session.add(token)

    db.session.commit()
    return redirect(url_for("download_list", order_id=order.id))


# --- Download ---

@app.route("/orders/<int:order_id>/downloads")
def download_list(order_id: int):
    order = Order.query.get_or_404(order_id)
    tokens = DownloadToken.query.filter_by(order_id=order_id, used=False).all()
    cart_count = 0
    return render_template(
        "download.html", order=order, tokens=tokens, cart_count=cart_count
    )


@app.route("/download/<token_str>")
def download_file(token_str: str):
    token = DownloadToken.query.filter_by(token=token_str).first_or_404()
    now = datetime.now(timezone.utc)

    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if token.used or now > expires:
        abort(410)  # Gone

    product = token.product
    file_path = os.path.join(app.config["FILES_FOLDER"], product.file_path)

    if not os.path.exists(file_path):
        # Serve a placeholder CSV if the actual file is missing
        placeholder = f"name,description,price\n{product.name},{product.description},{product.price}\n"
        buf = io.BytesIO(placeholder.encode("utf-8-sig"))
        token.used = True
        db.session.commit()
        return send_file(
            buf,
            as_attachment=True,
            download_name=f"{product.name}.csv",
            mimetype="text/csv",
        )

    token.used = True
    db.session.commit()
    return send_file(file_path, as_attachment=True)


# ---------------------------------------------------------------------------
# Init DB
# ---------------------------------------------------------------------------

def create_tables():
    os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "files"), exist_ok=True)
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    create_tables()
    app.run(debug=True)
