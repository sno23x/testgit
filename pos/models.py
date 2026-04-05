from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def round_price(price):
    """ປັດ 3 ໂຕທ້າຍ: ≥500 ປັດຂຶ້ນ, <500 ປັດລົງ"""
    price = int(price)
    remainder = price % 1000
    if remainder >= 500:
        return price - remainder + 1000
    return price - remainder


class Setting(db.Model):
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


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    products = db.relationship("Product", backref="category", lazy=True)

    def __repr__(self):
        return self.name


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(50), default="ອັນ")
    cost_price = db.Column(db.Float, default=0)
    price_thb = db.Column(db.Float, nullable=True)
    sell_price = db.Column(db.Float, nullable=False)
    stock_qty = db.Column(db.Float, default=0)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    active = db.Column(db.Boolean, default=True)
    image = db.Column(db.String(200), default="")  # filename in uploads/products/

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "sell_price": self.sell_price,
            "price_thb": self.price_thb or 0,
            "stock_qty": self.stock_qty,
            "image": self.image or "",
        }


class Customer(db.Model):
    __tablename__ = "customers"
    id = db.Column(db.Integer, primary_key=True)
    cust_code = db.Column(db.String(50), default="")   # External Cust ID (e.g. CID001)
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
    role = db.Column(db.String(20), default="cashier")
    active = db.Column(db.Boolean, default=True)
    base_salary = db.Column(db.Float, default=0)
    ot_rate = db.Column(db.Float, default=0)   # ຄ່າ OT ຕໍ່ຊົ່ວໂມງ

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
    payment_type = db.Column(db.String(10), default="cash")  # cash / debt / transfer
    currency = db.Column(db.String(5), default="LAK")
    paid_amount = db.Column(db.Float, default=0)
    note = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    voided = db.Column(db.Boolean, default=False)
    voided_at = db.Column(db.DateTime, nullable=True)
    voided_by = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=True)

    items = db.relationship("SaleItem", backref="sale", lazy=True, cascade="all, delete-orphan")
    debt_payments = db.relationship("DebtPayment", backref="sale", lazy=True)
    employee = db.relationship("Employee", foreign_keys=[employee_id])
    voided_by_emp = db.relationship("Employee", foreign_keys=[voided_by])

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
    item_discount = db.Column(db.Float, default=0)   # ສ່ວນຫຼຸດລາຍການ (%)
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


class Attendance(db.Model):
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    # present / absent / late / half_day / holiday
    status = db.Column(db.String(20), default="present")
    ot_hours = db.Column(db.Float, default=0)
    note = db.Column(db.Text, default="")
    employee = db.relationship("Employee")


class SalaryAdvance(db.Model):
    __tablename__ = "salary_advances"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, default="")
    advance_date = db.Column(db.Date, default=lambda: datetime.now(timezone.utc).date())
    repaid = db.Column(db.Boolean, default=False)
    repaid_at = db.Column(db.DateTime, nullable=True)
    note = db.Column(db.Text, default="")
    employee = db.relationship("Employee")


class PayrollRecord(db.Model):
    __tablename__ = "payroll_records"
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    base_salary = db.Column(db.Float, default=0)
    working_days = db.Column(db.Integer, default=26)
    absent_days = db.Column(db.Integer, default=0)
    ot_hours = db.Column(db.Float, default=0)
    ot_rate = db.Column(db.Float, default=0)
    bonus = db.Column(db.Float, default=0)
    other_deductions = db.Column(db.Float, default=0)
    net_salary = db.Column(db.Float, default=0)
    note = db.Column(db.Text, default="")
    paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    employee = db.relationship("Employee")

    def calc_net(self):
        base    = float(self.base_salary or 0)
        days    = max(int(self.working_days or 26), 1)
        absent  = int(self.absent_days or 0)
        ot_h    = float(self.ot_hours or 0)
        ot_r    = float(self.ot_rate or 0)
        bonus   = float(self.bonus or 0)
        deduct  = float(self.other_deductions or 0)
        daily_rate = base / days
        self.net_salary = max(0, base - daily_rate * absent + ot_h * ot_r + bonus - deduct)
        return self.net_salary
