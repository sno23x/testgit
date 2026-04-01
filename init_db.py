"""
init_db.py – Import products from data/products.xlsx into SQLite.

Usage:
    python init_db.py
"""

import json
import os

import pandas as pd

from app import app, create_tables
from models import db, Product


DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "products.xlsx")


def import_products():
    df = pd.read_excel(DATA_FILE, dtype=str)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    required = {"name", "price"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Excel ขาดคอลัมน์: {missing}")

    with app.app_context():
        for _, row in df.iterrows():
            name = str(row.get("name", "")).strip()
            if not name:
                continue

            price_raw = row.get("price", "0")
            try:
                price = float(str(price_raw).replace(",", ""))
            except ValueError:
                price = 0.0

            # Collect preview rows if available
            preview_cols = [c for c in df.columns if c.startswith("preview")]
            preview_data = {}
            for col in preview_cols:
                val = row.get(col, "")
                if pd.notna(val) and str(val).strip():
                    preview_data[col.replace("preview_", "")] = str(val).strip()

            product = Product(
                name=name,
                description=str(row.get("description", "")).strip(),
                price=price,
                category=str(row.get("category", "ทั่วไป")).strip(),
                preview_rows=json.dumps(
                    [preview_data] if preview_data else [], ensure_ascii=False
                ),
                file_path=str(row.get("file_path", "")).strip(),
                active=True,
            )
            db.session.add(product)

        db.session.commit()
        count = Product.query.count()
        print(f"นำเข้าสำเร็จ – มีสินค้าทั้งหมด {count} รายการใน database")


if __name__ == "__main__":
    create_tables()
    import_products()
