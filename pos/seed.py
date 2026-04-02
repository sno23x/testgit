"""
seed.py – ສ້າງຂໍ້ມູນຕົວຢ່າງ + admin account
ລັນ: python seed.py
"""
import os
from app import create_app
from models import db, Employee, Category, Product, Customer

app = create_app()

with app.app_context():
    os.makedirs("instance", exist_ok=True)
    db.create_all()

    # Admin account
    if not Employee.query.filter_by(username="admin").first():
        admin = Employee(name="ຜູ້ດູແລລະບົບ", username="admin", role="admin")
        admin.set_password("admin123")
        db.session.add(admin)
        print("✓ ສ້າງ admin / admin123")

    # Categories
    cat_names = ["ປູນ / ດິນ", "ຄ້ານ / ທໍ່", "ອິດຖ / ບ ock", "ສີ / ນ້ໍາຢາ", "ເຄື່ອງໄຟຟ້າ", "ປະປາ", "ທົ່ວໄປ"]
    cats = {}
    for name in cat_names:
        c = Category.query.filter_by(name=name).first()
        if not c:
            c = Category(name=name)
            db.session.add(c)
            db.session.flush()
        cats[name] = c

    # Products
    products_data = [
        ("P00001", "ປູນຊີເມັນ ຕາ Elephant 50kg", "ຖົງ", 22000, 25000, 200, "ປູນ / ດິນ"),
        ("P00002", "ທໍ່ PVC ຂະໜາດ 4 ນິ້ວ", "ທ່ອນ", 35000, 42000, 150, "ຄ້ານ / ທໍ່"),
        ("P00003", "ອິດຖ Block 10x20x40cm", "ໜ່ວຍ", 1500, 2000, 5000, "ອິດຖ / ບ ock"),
        ("P00004", "ສີທາ Nippon ຂາວ 5L", "ກະລັ໋ງ", 85000, 110000, 80, "ສີ / ນ້ໍາຢາ"),
        ("P00005", "ສາຍໄຟ 2.5mm THW 100m", "ກ້ວນ", 180000, 220000, 30, "ເຄື່ອງໄຟຟ້າ"),
        ("P00006", "ທໍ່ PP-R ½ ນິ້ວ", "ທ່ອນ", 8000, 12000, 200, "ປະປາ"),
        ("P00007", "ດິນຊາຍ", "ໂຕນ", 150000, 200000, 50, "ປູນ / ດິນ"),
        ("P00008", "ຕຽວເລັກ ຂະໜາດ 3 ຫາ 4 mm", "ກິໂລ", 9000, 13000, 100, "ທົ່ວໄປ"),
        ("P00009", "ໄມ້ອັດ 4x8 ໜາ 4mm", "ແຜ່ນ", 40000, 55000, 60, "ທົ່ວໄປ"),
        ("P00010", "ສະວິດ ປິດ-ເປີດ", "ອັນ", 5000, 8000, 500, "ເຄື່ອງໄຟຟ້າ"),
    ]
    for code, name, unit, cost, sell, stock, cat_name in products_data:
        if not Product.query.filter_by(code=code).first():
            p = Product(code=code, name=name, unit=unit, cost_price=cost,
                        sell_price=sell, stock_qty=stock, category_id=cats[cat_name].id)
            db.session.add(p)

    # Customers
    customers_data = [
        ("ທ້າວ ສົມຈິດ ພົມມະລາດ", "020-5551234", "ບ້ານ ໂຊກໃຫຍ່, ວຽງຈັນ"),
        ("ນາງ ຄໍາຫລ້າ ສີລາວົງ", "020-7779876", "ບ້ານ ຫໍ້ຢ່ານ, ວຽງຈັນ"),
        ("ຮ້ານ ວັດສະດຸ ທຸ່ງທອງ", "021-312456", "ຖ. ລ້ານຊ້າງ"),
    ]
    for name, phone, addr in customers_data:
        if not Customer.query.filter_by(name=name).first():
            db.session.add(Customer(name=name, phone=phone, address=addr))

    db.session.commit()
    print("✓ Seed data ສໍາເລັດ!")
    print("\nເຂົ້າລະບົບ: http://localhost:5000")
    print("Username: admin | Password: admin123")
