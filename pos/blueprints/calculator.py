from flask import Blueprint, render_template
from flask_login import login_required
from models import Product

calculator_bp = Blueprint("calculator", __name__)


@calculator_bp.route("/")
@login_required
def index():
    products = Product.query.filter_by(active=True).order_by(Product.name).all()
    products_json = [{"id": p.id, "name": p.name, "unit": p.unit,
                      "sell_price": p.sell_price or 0} for p in products]
    return render_template("calculator/index.html", products=products,
                           products_json=products_json)
