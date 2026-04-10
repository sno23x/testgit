from flask import Blueprint, render_template
from flask_login import login_required
from models import Product

calculator_bp = Blueprint("calculator", __name__)


@calculator_bp.route("/")
@login_required
def index():
    # Load products for price lookup (keywords: ຊີມັງ, ຊາຍ, ຫີນ, ດິນຈີ່, ດິນບັອກ)
    products = Product.query.filter_by(active=True).order_by(Product.name).all()
    return render_template("calculator/index.html", products=products)
