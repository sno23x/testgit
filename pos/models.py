from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    products = db.relationship("Product", backref="category", lazy=True)

    def __repr__(self):
        return self.name


class Setting(db.Model):
    """ຕັ້ງຄ່າລະບົບ (key-value)"""
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(500), default="")

    @staticmethod
    def get(key, default=""):
        s = Setting.query.filter_by(key=key).first()
        return s.value if s else default

    @staticmethod
    def set(key, value):
        s = Setting.query.filter_by(key=key).first()
        if s:
            s.value = str(value)
        else:
            db.session.add(Setting(key=key, value=str(value)))


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(50), default="ອັນ")
    cost_price = db.Column(db.Float, default=0)
    price_thb = db.Column(db.Float, nullable=True)   # ລາຄາໃນເງິນບາດ (ໄທ)
    sell_price = db.Column(db.Float, nullable=False)  # ລາຄາໃນກີບ (ຄຳນວນອັດຕະໂນມັດ ຫຼື ກຳນົດເອງ)
    stock_qty = db.Column(db.Float, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "sell_price": self.sell_price,
            "price_thb": self.price_thb or 0,
            "stock_qty": self.stock_qty,
        }


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(50), default="")
    address = db.Column(db.Text, default="")
    total_debt = db.Column(db.Float, default=0)
    sales = db.relationship("Sale", backref="customer", lazy=True)


class Employee(db.Model, UserMixin):
    __tablename__ = "employees"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="cashier")  # admin / cashier
    active = db.Column(db.Boolean, default=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def is_admin(self):
        return self.role == "admin"


class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    sale_no = db.Column(db.String(30), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)
    subtotal = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    payment_type = db.Column(db.String(10), default="cash")  # cash / debt
    paid_amount = db.Column(db.Float, default=0)
    note = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    items = db.relationship("SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan")
    debt_payments = db.relationship("DebtPayment", backref="sale", lazy=True)
    employee = db.relationship("Employee", foreign_keys=[employee_id])

    @property
    def debt_remaining(self):
        paid = sum(p.amount for p in self.debt_payments)
        return max(0, self.total - paid)

    @property
    def is_fully_paid(self):
        return self.debt_remaining <= 0


class SaleItem(db.Model):
    __tablename__ = "sale_items"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    product = db.relationship("Product")


class DebtPayment(db.Model):
    __tablename__ = "debt_payments"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.Text, default="")
    paid_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    customer = db.relationship("Customer")


class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), default="ທົ່ວໄປ")
    amount = db.Column(db.Float, nullable=False)
    note = db.Column(db.Text, default="")
    date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
