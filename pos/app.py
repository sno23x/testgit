import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from config import Config
from models import db, Employee
from blueprints.auth import auth_bp
from blueprints.pos import pos_bp
from blueprints.products import products_bp
from blueprints.customers import customers_bp
from blueprints.debts import debts_bp
from blueprints.expenses import expenses_bp
from blueprints.employees import employees_bp
from blueprints.reports import reports_bp

login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
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

    @app.route("/")
    def index():
        return redirect(url_for("pos.dashboard"))

    return app


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        os.makedirs("instance", exist_ok=True)
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)
