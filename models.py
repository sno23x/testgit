import json
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), default="ทั่วไป")
    preview_rows = db.Column(db.Text, default="[]")  # JSON string
    file_path = db.Column(db.String(300), default="")
    active = db.Column(db.Boolean, default=True)

    @property
    def preview(self):
        try:
            return json.loads(self.preview_rows)
        except Exception:
            return []


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_email = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(50), default="")
    total = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending / paid / cancelled
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    slip_path = db.Column(db.String(300), default="")

    items = db.relationship("OrderItem", backref="order", lazy=True)
    tokens = db.relationship("DownloadToken", backref="order", lazy=True)


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)

    product = db.relationship("Product")


class DownloadToken(db.Model):
    __tablename__ = "download_tokens"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)

    product = db.relationship("Product")
