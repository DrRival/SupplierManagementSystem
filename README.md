📦 Supplier Management System

A Flask-based inventory & procurement management application with automated database backup using SQLite triggers.

📘 Overview

The Supplier Management System is a mini full-stack web application built using Flask, SQLite, Bootstrap 5, and Jinja2 templates.
It helps organizations maintain suppliers, products, purchase orders, and automatically maintain a separate backup database through SQL triggers and Python replication logic.

Ideal for MCA mini-projects, DBMS coursework, or a portfolio project.

🚀 Features
1. Supplier Management

Add suppliers

View supplier list

Soft deactivate suppliers

Track contact details, phone, city, state, email

2. Product Management

Add new products

Auto-audit each product insertion using triggers

Track SKU, unit price, activity status

3. Purchase Orders

Create purchase orders

Add multiple items

Auto-calculate totals

View full order summary

4. Automatic Backup Database

This project maintains two databases:

Purpose	File
Main operational DB	supplier_mgmt.db
Permanent backup DB	supplier_backup.db

The workflow is:

Triggers insert audit rows into products_audit and order_items_audit

Python code detects new audit rows

The rows are replicated to backup DB

Even if the main DB item is deleted, backup remains safe

This satisfies academic requirements for:

Triggers

Backup systems

Audit tables

DB consistency

5. Dashboard

A clean dashboard showing:

Total suppliers

Total products

Total orders

6. Demo Data Seeder

One-click:

Insert Demo Data → `/seed_demo`


This populates:

2 suppliers

3 products

1 purchase order

2 order items

Full backup replication

Perfect for viva and presentations.

🗂️ Project Structure
SupplierManagement/
│
├── app.py                     # Main Flask application
│── supplier_mgmt.db          # Main database (auto-created)
│── supplier_backup.db        # Backup DB (auto-created)
│
├── static/
│   └── images/               # Screenshots for README / report
│
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── suppliers.html
    ├── add_supplier.html
    ├── products.html
    ├── add_product.html
    ├── orders.html
    ├── add_order.html
    ├── add_item.html
    ├── order_detail.html
    └── backup.html

🛠️ Installation & Setup
1. Clone the Repository
git clone https://github.com/DrRival/SupplierManagementSystem.git
cd SupplierManagementSystem

2. Create Virtual Environment
python -m venv venv


Activate:

Windows

venv\Scripts\activate

3. Install Requirements
pip install flask


SQLite needs no installation — part of Python.

4. Run the Application
python app.py


Visit:

http://127.0.0.1:5000

🛢️ Database Architecture
Main Tables

suppliers

products

purchase_orders

purchase_order_items

Audit Tables

products_audit

order_items_audit

Backup Tables (separate DB)

products_backup

order_items_backup

Triggers
CREATE TRIGGER trg_products_audit
AFTER INSERT ON products
BEGIN
    INSERT INTO products_audit(product_id, name, sku, unit_price)
    VALUES (NEW.product_id, NEW.name, NEW.sku, NEW.unit_price);
END;

CREATE TRIGGER trg_order_items_audit
AFTER INSERT ON purchase_order_items
BEGIN
    INSERT INTO order_items_audit(item_id, order_id, product_id, description, quantity, unit_price)
    VALUES (NEW.item_id, NEW.order_id, NEW.product_id, NEW.description, NEW.quantity, NEW.unit_price);
END;

🖼️ Screenshots

Place images in:

static/images/


And embed like this (already included in your repo):

![Dashboard](static/images/dashboard_main.png)
![Suppliers](static/images/suppliers_page.png)
![Products](static/images/products_page.png)
![Backup](static/images/backup_db_viewer.png)
![Add Item](static/images/add_item_form.png)

📚 How Backup Works (For Viva)

If a product is added → trigger fires → audit stored → Python copies → permanent backup DB updated.

Even if the main table row is deleted:

SELECT * FROM products_backup;


The backup remains intact.

This proves:

Trigger correctness

Backup replication logic

DB consistency

Perfect viva scoring topic.

🧪 Demo Data Included

Running:

http://127.0.0.1:5000/seed_demo


Creates:

Suppliers

Acme Industrial

TechParts Co.

Products

M3 Screws

Solder Wire

Raspberry Pi 4B

Orders

One PO with 2 items

All automatically backed up.

📄 License

MIT License
