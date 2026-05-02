# ລະບົບ POS ຮ້ານວັນນາ

ລະບົບ Point-of-Sale ສຳລັບຮ້ານຂາຍປີກ ພັດທະນາດ້ວຍ Python / Flask.  
ຮອງຮັບ 2 ສະກຸນເງິນ (ກີບ LAK / ບາດ THB), ຈັດການໜີ້, ສິນຄ້າ, ໃບສະເໜີລາຄາ, ເງິນເດືອນ, ແລະ ລາຍງານ.

---

## Tech Stack

| ສ່ວນ | ເທັກໂນໂລຈີ |
|------|------------|
| Backend | Python 3 · Flask 3.0 |
| Database | SQLite (default) · MySQL/PostgreSQL ຜ່ານ `DATABASE_URL` |
| ORM | Flask-SQLAlchemy 3.1 |
| Auth | Flask-Login 0.6 |
| Realtime | Flask-SocketIO 5.3 (WebSocket) |
| Templates | Jinja2 + Bootstrap 5 + Bootstrap Icons |
| Excel Export | openpyxl |

---

## ໂຄງສ້າງໄຟລ໌

```
pos/
├── app.py                  # App factory + ລົງທະບຽນ blueprints + migration runner
├── config.py               # Config class (SECRET_KEY, DATABASE_URL)
├── models.py               # SQLAlchemy models ທັງໝົດ
├── seed.py                 # ຂໍ້ມູນຕົວຢ່າງ (seed)
├── blueprints/
│   ├── auth.py             # Login / Logout
│   ├── pos.py              # ໜ້າຂາຍ POS หลัก + API
│   ├── products.py         # ຈັດການສິນຄ້າ
│   ├── customers.py        # ຈັດການລູກຄ້າ
│   ├── debts.py            # ໜີ້ສິນ
│   ├── expenses.py         # ລາຍຈ່າຍ
│   ├── employees.py        # ຈັດການພະນັກງານ
│   ├── payroll.py          # ເງິນເດືອນ + ບັນທຶກການເຂົ້າວຽກ
│   ├── salary_advance.py   # ເບີກເງິນລ່ວງໜ້າ
│   ├── stock_in.py         # ຮັບສິນຄ້າເຂົ້າ stock
│   ├── quotations.py       # ໃບສະເໜີລາຄາ
│   ├── reports.py          # ລາຍງານ + export Excel
│   ├── chat.py             # ແຊັດກຸ່ມ (SocketIO)
│   ├── dm.py               # ແຊັດສ່ວນຕົວ / ກຸ່ມ DM (SocketIO)
│   ├── settings.py         # ການຕັ້ງຄ່າລະບົບ
│   ├── calculator.py       # ເຄື່ອງຄິດໄລ່
│   └── import_data.py      # ນຳເຂົ້າຂໍ້ມູນ Excel
├── templates/
│   ├── base.html           # Layout ຫຼັກ (sidebar + navbar)
│   ├── dashboard.html
│   ├── pos/                # ໜ້າຂາຍ + ໃບບິນ
│   ├── products/
│   ├── customers/
│   ├── debts/
│   ├── expenses/
│   ├── employees/
│   ├── payroll/            # ໃບເງິນເດືອນ + ການເຂົ້າວຽກ
│   ├── salary_advance/
│   ├── stock_in/
│   ├── quotations/
│   ├── reports/
│   ├── chat/
│   ├── dm/
│   └── settings/
└── static/
    ├── css/style.css
    └── uploads/
        ├── products/       # ຮູບສິນຄ້າ
        ├── chat/           # ໄຟລ໌ chat ກຸ່ມ
        └── dm/             # ໄຟລ໌ DM
```

---

## Database Models

### Setting
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| key | String(100) | unique |
| value | String(500) | |

ໃຊ້ `Setting.get(key, default)` / `Setting.set(key, value)` ທົ່ວລະບົບ.

---

### Category
| Column | Type |
|--------|------|
| id | Integer PK |
| name | String(100) |

---

### Product
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| id | Integer PK | |
| code | String(50) | unique, barcode |
| name | String(200) | |
| unit | String(50) | ໜ່ວຍນັບ |
| cost_price | Float | ລາຄາທຶນ |
| sell_price | Float | ລາຄາຂາຍ (LAK) |
| price_thb | Float | ລາຄາຂາຍ THB (optional) |
| stock_qty | Float | ຈຳນວນ stock |
| category_id | FK → categories | |
| active | Boolean | soft delete |
| image | String(200) | filename ໃນ uploads/products/ |

---

### Customer
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| id | Integer PK | |
| cust_code | String(50) | CID001 ... |
| name | String(200) | |
| phone | String(50) | |
| address | Text | |
| map_url | String(500) | Google Maps link |
| total_debt | Float | ຍອດໜີ້ລວມ |

---

### Employee
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| id | Integer PK | |
| name | String(200) | |
| username | String(100) | unique |
| password_hash | String(256) | |
| role | String(20) | admin / cashier / accountant / driver / porter |
| active | Boolean | soft delete |
| base_salary | Float | ເງິນເດືອນລາຍເດືອນ (LAK) |
| ot_rate | Float | ຄ່າ OT ຕໍ່ຊົ່ວໂມງ (LAK) |
| pay_type | String(10) | `monthly` ຫຼື `daily` |
| daily_rate | Float | ຄ່າແຮງລາຍວັນ (LAK) — ໃຊ້ເມື່ອ pay_type = daily |

**ສິດທິ (roles):**
| Role | ສິດທິ |
|------|-------|
| admin | ທຸກສ່ວນ |
| cashier | POS, ສິນຄ້າ, ລູກຄ້າ, ໜີ້ |
| accountant | ລາຍງານ, ລາຍຈ່າຍ, ເງິນເດືອນ, ເບີກລ່ວງໜ້າ |
| driver / porter | Login ເທົ່ານັ້ນ |

---

### Sale
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| id | Integer PK | |
| sale_no | String(30) | unique, auto-gen |
| customer_id | FK → customers | nullable |
| employee_id | FK → employees | |
| subtotal / discount / total | Float | |
| payment_type | String(10) | cash / debt / transfer |
| currency | String(5) | LAK / THB |
| paid_amount | Float | ຈຳນວນທີ່ຈ່າຍ |
| change_amount | Float | ເງິນທອນ |
| voided | Boolean | ຍົກເລີກ |
| voided_at / voided_by | DateTime / FK | |

**Property:** `debt_remaining`, `is_fully_paid`

---

### SaleItem
| Column | Type |
|--------|------|
| sale_id | FK → sales |
| product_id | FK → products |
| qty | Float |
| unit_price | Float |
| item_discount | Float (%) |
| subtotal | Float |

---

### DebtPayment
ການຊຳລະໜີ້ (ສຳລັບ payment_type = debt).

| Column | Type |
|--------|------|
| sale_id | FK → sales |
| customer_id | FK → customers |
| amount | Float |
| note | Text |
| paid_at | DateTime |

---

### Expense
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| id | Integer PK | |
| category | String(100) | ໝວດລາຍຈ່າຍ |
| amount | Float | |
| note | Text | |
| date | Date | |
| employee_id | Integer | nullable — ສ້າງ auto ສຳລັບ pay_type=daily |

---

### Attendance
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| employee_id | FK → employees | |
| date | Date | |
| status | String(20) | present / absent / late / half_day / holiday |
| ot_hours | Float | |
| note | Text | |

---

### SalaryAdvance
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| employee_id | FK → employees | |
| amount | Float | |
| reason | Text | |
| advance_date | Date | |
| repaid | Boolean | |
| repaid_at | DateTime | auto-set ຕອນ mark_paid payroll |

---

### PayrollRecord
| Column | Type | ໝາຍເຫດ |
|--------|------|---------|
| employee_id | FK → employees | |
| year / month | Integer | |
| base_salary | Float | snapshot ຕອນ generate |
| working_days | Integer | ວັນທັງໝົດໃນເດືອນ (calendar days) |
| absent_days | Integer | ນັບຈາກ Attendance |
| ot_hours | Float | |
| ot_rate | Float | |
| bonus | Float | |
| other_deductions | Float | ຄ່າປັບ / ໜີ້ອື່ນ |
| advance_deduction | Float | ເບີກລ່ວງໜ້າ (auto-sum ຈາກ SalaryAdvance) |
| net_salary | Float | ຄຳນວນໂດຍ `calc_net()` |
| paid | Boolean | |
| paid_at | DateTime | |

**ສູດ `calc_net()`:**
```
daily_rate     = base_salary / working_days
absent_deduct  = daily_rate × absent_days
net_salary     = base_salary - absent_deduct + (ot_hours × ot_rate) + bonus - other_deductions - advance_deduction
net_salary     = max(0, net_salary)
```

---

### StockIn
ປະຫວັດການຮັບສິນຄ້າເຂົ້າ — ເພີ່ມ stock_qty ໃຫ້ Product ໂດຍອັດຕະໂນມັດ.

---

### Quotation / QuotationItem
ໃບສະເໜີລາຄາ — ສາມາດ convert ເປັນ Sale ໄດ້.

---

### ChatMessage / DMRoom / DMRoomMember / DMMessage
ລະບົບ chat ພາຍໃນ — ໃຊ້ Flask-SocketIO.

---

## URL Routes

| Prefix | Blueprint | ໜ້າທີ່ |
|--------|-----------|--------|
| `/login` `/logout` | auth | ເຂົ້າ-ອອກລະບົບ |
| `/pos/` | pos | ໜ້າຂາຍ POS ຫຼັກ |
| `/pos/dashboard` | pos | Dashboard ສະຫຼຸບ |
| `/pos/receipt/<id>` | pos | ໃບບິນ (A5 print) |
| `/pos/void/<id>` | pos | ຍົກເລີກໃບຂາຍ |
| `/products/` | products | ລາຍການສິນຄ້າ + CRUD |
| `/customers/` | customers | ລາຍການລູກຄ້າ + CRUD |
| `/debts/` | debts | ໜີ້ + ການຊຳລະ |
| `/expenses/` | expenses | ລາຍຈ່າຍ |
| `/employees/` | employees | ຈັດການພະນັກງານ |
| `/payroll/` | payroll | ໃບເງິນເດືອນ |
| `/payroll/attendance` | payroll | ບັນທຶກການເຂົ້າວຽກ |
| `/payroll/generate` | payroll | ສ້າງໃບເງິນເດືອນໃຫ້ທຸກຄົນ |
| `/salary-advance/` | salary_advance | ເບີກເງິນລ່ວງໜ້າ |
| `/stock-in/` | stock_in | ຮັບສິນຄ້າເຂົ້າ |
| `/quotations/` | quotations | ໃບສະເໜີລາຄາ |
| `/reports/` | reports | ລາຍງານ + export Excel |
| `/chat/` | chat | ແຊັດກຸ່ມ |
| `/dm/` | dm | ແຊັດສ່ວນຕົວ / ກຸ່ມ |
| `/settings/` | settings | ການຕັ້ງຄ່າ |
| `/calculator/` | calculator | ເຄື່ອງຄິດໄລ່ |

### API Endpoints
| URL | ໝາຍເຫດ |
|-----|---------|
| `GET /pos/search` | ຄົ້ນຫາສິນຄ້າ (JSON) |
| `GET /pos/customer-lookup` | ຄົ້ນຫາລູກຄ້າ (JSON) |
| `GET /pos/cashback-status` | ຍອດ cashback (JSON) |
| `POST /pos/cashback-set` | ຕັ້ງ quota ເງິນທອນ |
| `GET /pos/api/daily-summary` | ສະຫຼຸບຍອດຂາຍປະຈຳວັນ (API key) |
| `POST /pos/api/sales/<no>/mark-paid` | ໝາຍໃບຂາຍວ່າຊຳລະແລ້ວ (API key) |
| `GET /salary-advance/employee/<id>/summary` | ສະຫຼຸບຍອດ advance (JSON) |

---

## ການຕັ້ງຄ່າລະບົບ (Settings)

ຕັ້ງຄ່າທີ່ `/settings/` — ເກັບໃນ `settings` table:

| Key | ໝາຍເຫດ |
|-----|---------|
| `shop_name` | ຊື່ຮ້ານ |
| `shop_address` | ທີ່ຢູ່ |
| `shop_phone` | ເບີໂທ |
| `shop_qr` | ຮູບ QR (upload) |
| `thb_to_lak` | ອັດຕາແລກປ່ຽນ THB→LAK (default 830) |
| `receipt_rows` | ຈຳນວນແຖວໃນໃບບິນ |
| `receipt_footer` | ຂໍ້ຄວາມທ້າຍໃບບິນ |
| `receipt_auto_print` | print ໂດຍອັດຕະໂນມັດ (0/1) |
| `cashback_daily_quota` | ວົງເງິນເງິນທອນປະຈຳວັນ |
| `ads_enabled` | ໂຄສະນາໜ້າ display (0/1) |
| `ads_product_ids` | ID ສິນຄ້າໂຄສະນາ (comma-separated) |

---

## ການທຳງານຫຼັກ

### ໜ້າຂາຍ POS
- ຄົ້ນຫາສິນຄ້າດ້ວຍ keyword ຫຼື barcode scan
- ເພີ່ມ / ລຶບ / ປ່ຽນ qty ລາຍການໃນກະຕ່າ
- ສ່ວນຫຼຸດທັງ cart ຫຼື ລາຍການ (%)
- 3 ຊ່ອງທາງຊຳລະ: **ເງິນສົດ** / **ໂອນ** / **ໜີ້**
- switch currency LAK / THB ໃນ modal ຈ່າຍເງິນ
- ໃບບິນ A5 (Jinja2 → print dialog)
- ຍົກເລີກໃບ (void) — stock ກັບຄືນ, ຕັດຈາກລາຍຮັບ

### ເງິນເດືອນ
1. **ບັນທຶກການເຂົ້າວຽກ** (`/payroll/attendance`) ທຸກວັນ
   - ພະນັກງານ **ລາຍວັນ** (pay_type=daily): ຖ້າ status=present → Expense ສ້າງ auto
2. **ສ້າງໃບເງິນເດືອນ** (`/payroll/generate`) — 1 ຄັ້ງຕໍ່ເດືອນ
   - `working_days` = ວັນທັງໝົດໃນເດືອນ (calendar.monthrange)
   - ນັບ absent_days ຈາກ Attendance
   - ລວມຍອດ SalaryAdvance ທີ່ຍັງບໍ່ຄືນ → `advance_deduction`
3. **ຈ່າຍ** (`/payroll/<id>/pay`) — SalaryAdvance ທີ່ relate mark repaid auto

### ໃບສະເໜີລາຄາ
- ສ້າງ draft → ສົ່ງ → ຮັບ/ປະຕິເສດ
- convert ເປັນ Sale ໄດ້ (stock ຫັກ)

### ລາຍງານ
- ຊ່ວງວັນທີ filter
- ສະຫຼຸບ: ລາຍຮັບ, ກຳໄລ (ລາຄາທຶນ), ລາຍຈ່າຍ
- Export Excel (.xlsx)

---

## ເລີ່ມ Run

```bash
cd pos
pip install -r requirements.txt
python app.py
```

ຄ້ອຍ Default: `http://localhost:5000`

**Environment variables** (`.env` ຫຼື OS):
```
SECRET_KEY=your-secret
DATABASE_URL=sqlite:///pos.db       # ຫຼື mysql+pymysql://...
```

**DB migration** ດຳເນີນການ auto ຕອນ start ຜ່ານ `run_migrations()` ໃນ `app.py` — ໃຊ້ `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pattern.

---

## ໝາຍເຫດ

- ສະກຸນເງິນ THB ໃຊ້ `thb_to_lak` rate ຈາກ Settings ຕລອດ
- `round_price()` ໃນ models.py: ປັດ 3 ໂຕທ້າຍ (≥500 ຂຶ້ນ, <500 ລົງ)
- SocketIO rooms: `chat_global` (group chat), `dm_<room_id>` (DM)
- Webhook N8N: `pos.py/_post_webhook()` — ແຈ້ງເຕືອນຕອນຂາຍສຳເລັດ
- Branch ພັດທະນາ: `claude/create-data-sales-website-hwTvV`
