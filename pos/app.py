import os
import sqlalchemy as sa
from flask import Flask, redirect, url_for, request as flask_request
from flask_login import LoginManager, current_user
from flask_socketio import SocketIO, emit
from config import Config
from models import db, Employee
from datetime import datetime, timezone, timedelta

socketio = SocketIO()

_TZ_LAO = timezone(timedelta(hours=7))
# {sid: {'id': int, 'name': str}}
_online_users = {}


def _unique_online():
    seen, result = set(), []
    for u in _online_users.values():
        if u['id'] not in seen:
            seen.add(u['id'])
            result.append(u)
    return result


@socketio.on("cart_update")
def handle_cart_update(data):
    emit("cart_update", data, broadcast=True, include_self=False)


@socketio.on("cart_confirmed")
def handle_cart_confirmed(data):
    emit("cart_confirmed", data, broadcast=True, include_self=False)


@socketio.on("cart_cleared")
def handle_cart_cleared(data):
    emit("cart_cleared", {}, broadcast=True, include_self=False)


@socketio.on("transfer_show")
def handle_transfer_show(data):
    emit("transfer_show", data, broadcast=True, include_self=False)


@socketio.on("delivery_show")
def handle_delivery_show(data):
    emit("delivery_show", data, broadcast=True, include_self=False)


@socketio.on("connect")
def handle_connect():
    if current_user.is_authenticated:
        _online_users[flask_request.sid] = {'id': current_user.id, 'name': current_user.name}
        emit("users_online", _unique_online(), broadcast=True)


@socketio.on("disconnect")
def handle_disconnect():
    _online_users.pop(flask_request.sid, None)
    socketio.emit("users_online", _unique_online())


@socketio.on("chat_join")
def handle_chat_join():
    emit("users_online", _unique_online())


@socketio.on("chat_clear_notify")
def handle_chat_clear_notify():
    if not current_user.is_authenticated or not current_user.is_admin():
        return
    emit("chat_cleared", {}, broadcast=True)


@socketio.on("chat_send")
def handle_chat_send(data):
    if not current_user.is_authenticated:
        return
    from models import ChatMessage
    text = (data.get("message") or "").strip()
    file_path = (data.get("file_path") or "").strip()
    file_name = (data.get("file_name") or "").strip()
    if not text and not file_path:
        return
    if len(text) > 1000:
        return
    msg = ChatMessage(
        employee_id=current_user.id,
        message=text,
        file_path=file_path,
        file_name=file_name,
        created_at=datetime.now(timezone.utc),
    )
    db.session.add(msg)
    db.session.commit()
    now_lao = datetime.now(timezone.utc).astimezone(_TZ_LAO)
    ext = file_path.rsplit(".", 1)[-1].lower() if file_path and "." in file_path else ""
    IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
    emit("chat_receive", {
        "id": msg.id,
        "user_id": current_user.id,
        "name": current_user.name,
        "message": text,
        "file_url": f"/static/uploads/chat/{file_path}" if file_path else "",
        "file_name": file_name,
        "is_image": ext in IMAGE_EXT,
        "time": now_lao.strftime("%H:%M"),
    }, broadcast=True)


from blueprints.auth import auth_bp
from blueprints.pos import pos_bp
from blueprints.products import products_bp
from blueprints.customers import customers_bp
from blueprints.debts import debts_bp
from blueprints.expenses import expenses_bp
from blueprints.employees import employees_bp
from blueprints.reports import reports_bp
from blueprints.settings import settings_bp
from blueprints.import_data import import_bp
from blueprints.payroll import payroll_bp
from blueprints.salary_advance import salary_advance_bp
from blueprints.stock_in import stock_in_bp
from blueprints.quotations import quotations_bp
from blueprints.calculator import calculator_bp
from blueprints.chat import chat_bp

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode="gevent")
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "ກະລຸນາເຂົ້າສູ່ລະບົບກ່ອນ"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return Employee.query.get(int(user_id))

    app.register_blueprint(auth_bp)
    app.register_blueprint(pos_bp, url_prefix="/pos")
    app.register_blueprint(products_bp, url_prefix="/products")
    app.register_blueprint(customers_bp, url_prefix="/customers")
    app.register_blueprint(debts_bp, url_prefix="/debts")
    app.register_blueprint(expenses_bp, url_prefix="/expenses")
    app.register_blueprint(employees_bp, url_prefix="/employees")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(import_bp, url_prefix="/import")
    app.register_blueprint(payroll_bp, url_prefix="/payroll")
    app.register_blueprint(salary_advance_bp, url_prefix="/salary-advance")
    app.register_blueprint(stock_in_bp, url_prefix="/stock-in")
    app.register_blueprint(quotations_bp, url_prefix="/quotations")
    app.register_blueprint(calculator_bp, url_prefix="/calculator")
    app.register_blueprint(chat_bp, url_prefix="/chat")

    # Run DB migrations on every startup (safe with gunicorn too)
    run_migrations(app)

    @app.route("/")
    def index():
        return redirect(url_for("pos.dashboard"))

    return app


def run_migrations(app):
    """ເພີ່ມ column ໃໝ່ທີ່ອາດຍັງບໍ່ມີໃນ DB ເກົ່າ"""
    with app.app_context():
        os.makedirs("instance", exist_ok=True)
        os.makedirs(os.path.join("static", "img"), exist_ok=True)
        os.makedirs(os.path.join("static", "uploads", "products"), exist_ok=True)
        os.makedirs(os.path.join("static", "uploads", "chat"), exist_ok=True)
        db.create_all()
        migrations = [
            "ALTER TABLE products ADD COLUMN price_thb FLOAT",
            "ALTER TABLE products ADD COLUMN image VARCHAR(200) DEFAULT ''",
            "ALTER TABLE employees ADD COLUMN base_salary FLOAT DEFAULT 0",
            "ALTER TABLE employees ADD COLUMN ot_rate FLOAT DEFAULT 0",
            "ALTER TABLE sales ADD COLUMN currency VARCHAR(5) DEFAULT 'LAK'",
            "ALTER TABLE sale_items ADD COLUMN item_discount FLOAT DEFAULT 0",
            "ALTER TABLE customers ADD COLUMN cust_code VARCHAR(50) DEFAULT ''",
            "ALTER TABLE sales ADD COLUMN voided INTEGER DEFAULT 0",
            "ALTER TABLE sales ADD COLUMN voided_at DATETIME",
            "ALTER TABLE sales ADD COLUMN voided_by INTEGER",
            "ALTER TABLE customers ADD COLUMN map_url VARCHAR(500) DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS stock_ins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL REFERENCES products(id),
                qty FLOAT NOT NULL,
                cost_price FLOAT DEFAULT 0,
                supplier VARCHAR(200) DEFAULT '',
                note TEXT DEFAULT '',
                date DATE,
                created_at DATETIME,
                created_by INTEGER REFERENCES employees(id)
            )""",
            """CREATE TABLE IF NOT EXISTS quotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quote_no VARCHAR(30) UNIQUE NOT NULL,
                customer_id INTEGER REFERENCES customers(id),
                customer_name VARCHAR(200) DEFAULT '',
                date DATE,
                valid_days INTEGER DEFAULT 30,
                status VARCHAR(20) DEFAULT 'draft',
                subtotal FLOAT DEFAULT 0,
                discount FLOAT DEFAULT 0,
                total FLOAT DEFAULT 0,
                note TEXT DEFAULT '',
                created_at DATETIME,
                created_by INTEGER REFERENCES employees(id)
            )""",
            """CREATE TABLE IF NOT EXISTS quotation_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quotation_id INTEGER NOT NULL REFERENCES quotations(id),
                product_id INTEGER REFERENCES products(id),
                description VARCHAR(300) DEFAULT '',
                unit VARCHAR(50) DEFAULT '',
                qty FLOAT DEFAULT 1,
                unit_price FLOAT DEFAULT 0,
                subtotal FLOAT DEFAULT 0
            )""",
            "ALTER TABLE quotations ADD COLUMN sale_id INTEGER REFERENCES sales(id)",
            "ALTER TABLE sales ADD COLUMN change_amount FLOAT DEFAULT 0",
            """CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL REFERENCES employees(id),
                message TEXT DEFAULT '',
                file_path VARCHAR(300) DEFAULT '',
                file_name VARCHAR(300) DEFAULT '',
                created_at DATETIME
            )""",
            "ALTER TABLE chat_messages ADD COLUMN file_path VARCHAR(300) DEFAULT ''",
            "ALTER TABLE chat_messages ADD COLUMN file_name VARCHAR(300) DEFAULT ''",
        ]
        with db.engine.connect() as conn:
            for stmt in migrations:
                try:
                    conn.execute(sa.text(stmt))
                    conn.commit()
                except Exception:
                    pass


if __name__ == "__main__":
    app = create_app()
    run_migrations(app)
    # ssl_context='adhoc' ຕ້ອງການ: pip install pyOpenSSL
    # ເຮັດໃຫ້ browser ຍອມໃຊ້ກ້ອງ (camera) ໄດ້ຜ່ານ HTTPS
    try:
        app.run(debug=True, host="0.0.0.0", port=5000, ssl_context="adhoc")
    except Exception:
        # fallback ຖ້າ pyOpenSSL ຍັງບໍ່ໄດ້ຕິດຕັ້ງ
        app.run(debug=True, host="0.0.0.0", port=5000)
