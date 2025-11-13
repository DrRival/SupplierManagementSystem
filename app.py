# -----------------------------------------------------------
# Supplier Management System (Flask + SQLite + Backup DB)
# - Main DB  = supplier_mgmt.db
# - Backup DB = supplier_backup.db
# - Triggers write audit rows to audit tables
# - Python replicates audit rows to backup DB
# - Beautiful Bootstrap Admin UI
# -----------------------------------------------------------

from flask import Flask, render_template, redirect, request, url_for, flash
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey123"

MAIN_DB = "supplier_mgmt.db"
BACKUP_DB = "supplier_backup.db"

# -----------------------------------------------------------
# --------------------- DB HELPERS --------------------------
# -----------------------------------------------------------

def db_conn():
    conn = sqlite3.connect(MAIN_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def backup_conn():
    conn = sqlite3.connect(BACKUP_DB)
    conn.row_factory = sqlite3.Row
    return conn

# -----------------------------------------------------------
# ----------------- INITIAL DATABASE SETUP ------------------
# -----------------------------------------------------------

SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

-------------------------------------------------------------
-- MAIN TABLES
-------------------------------------------------------------
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id   INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    contact_name  TEXT,
    phone         TEXT,
    email         TEXT UNIQUE,
    address       TEXT,
    city          TEXT,
    state         TEXT,
    country       TEXT DEFAULT 'India',
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (date('now')),
    CHECK (is_active IN (0,1))
);

CREATE TABLE IF NOT EXISTS products (
    product_id    INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    sku           TEXT,
    unit_price    REAL NOT NULL CHECK(unit_price >= 0),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (date('now')),
    CHECK (is_active IN (0,1))
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    order_id      INTEGER PRIMARY KEY,
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(supplier_id) ON DELETE RESTRICT,
    order_date    TEXT NOT NULL DEFAULT (date('now')),
    status        TEXT NOT NULL DEFAULT 'DRAFT',
    notes         TEXT,
    CHECK (status IN ('DRAFT','PLACED','RECEIVED','CANCELLED'))
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    item_id       INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES purchase_orders(order_id) ON DELETE CASCADE,
    product_id    INTEGER REFERENCES products(product_id),
    description   TEXT NOT NULL,
    quantity      REAL NOT NULL CHECK(quantity > 0),
    unit_price    REAL NOT NULL CHECK(unit_price >= 0)
);

-------------------------------------------------------------
-- AUDIT TABLES (main DB)
-------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products_audit (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER,
    name         TEXT,
    sku          TEXT,
    unit_price   REAL,
    audit_time   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items_audit (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER,
    order_id     INTEGER,
    product_id   INTEGER,
    description  TEXT,
    quantity     REAL,
    unit_price   REAL,
    audit_time   TEXT DEFAULT (datetime('now'))
);

-------------------------------------------------------------
-- TRACKING TABLES (main DB, for backup dedupe)
-------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products_backup_ids (
    audit_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS order_items_backup_ids (
    audit_id INTEGER PRIMARY KEY
);

-------------------------------------------------------------
-- VIEW: ORDER TOTALS
-------------------------------------------------------------
CREATE VIEW IF NOT EXISTS v_order_totals AS
SELECT 
    po.order_id,
    SUM(poi.quantity * poi.unit_price) AS order_total
FROM purchase_orders po
LEFT JOIN purchase_order_items poi 
    ON poi.order_id = po.order_id
GROUP BY po.order_id;

-------------------------------------------------------------
-- TRIGGERS
-------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_products_audit
AFTER INSERT ON products
BEGIN
    INSERT INTO products_audit(product_id, name, sku, unit_price)
    VALUES (NEW.product_id, NEW.name, NEW.sku, NEW.unit_price);
END;

CREATE TRIGGER IF NOT EXISTS trg_order_items_audit
AFTER INSERT ON purchase_order_items
BEGIN
    INSERT INTO order_items_audit(item_id, order_id, product_id, description, quantity, unit_price)
    VALUES (NEW.item_id, NEW.order_id, NEW.product_id, NEW.description, NEW.quantity, NEW.unit_price);
END;
"""

# -----------------------------------------------------------
# ------------------- BACKUP DB SCHEMA ----------------------
# -----------------------------------------------------------

BACKUP_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS products_backup (
    backup_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   INTEGER,
    name         TEXT,
    sku          TEXT,
    unit_price   REAL,
    backed_up_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS order_items_backup (
    backup_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id      INTEGER,
    order_id     INTEGER,
    product_id   INTEGER,
    description  TEXT,
    quantity     REAL,
    unit_price   REAL,
    backed_up_at TEXT DEFAULT (datetime('now'))
);
"""

# -----------------------------------------------------------
# ------------------- DB INITIALIZER ------------------------
# -----------------------------------------------------------

@app.before_request
def startup():
    if not hasattr(app, "db_init_done"):
        conn = db_conn()
        conn.executescript(SCHEMA_SQL)
        conn.close()

        bconn = backup_conn()
        bconn.executescript(BACKUP_SCHEMA)
        bconn.close()

        app.db_init_done = True

# -----------------------------------------------------------
# ------------------- BACKUP REPLICATION --------------------
# -----------------------------------------------------------

def replicate_product_to_backup():
    """Copy new product audit rows into backup DB and mark them in main DB."""
    conn = db_conn()
    bconn = backup_conn()

    # all audits not yet backed up (tracked in main DB)
    rows = conn.execute("""
        SELECT * FROM products_audit
        WHERE audit_id NOT IN (SELECT audit_id FROM products_backup_ids)
    """).fetchall()

    for r in rows:
        # write full backup row into backup DB
        bconn.execute("""
            INSERT INTO products_backup(product_id, name, sku, unit_price)
            VALUES (?,?,?,?)
        """, (r["product_id"], r["name"], r["sku"], r["unit_price"]))

        # mark this audit_id as backed up in MAIN DB
        conn.execute(
            "INSERT INTO products_backup_ids(audit_id) VALUES (?)",
            (r["audit_id"],)
        )

    conn.commit()
    bconn.commit()
    conn.close()
    bconn.close()


def replicate_order_item_to_backup():
    """Copy new order item audit rows into backup DB and mark them in main DB."""
    conn = db_conn()
    bconn = backup_conn()

    rows = conn.execute("""
        SELECT * FROM order_items_audit
        WHERE audit_id NOT IN (SELECT audit_id FROM order_items_backup_ids)
    """).fetchall()

    for r in rows:
        bconn.execute("""
            INSERT INTO order_items_backup(item_id, order_id, product_id, description, quantity, unit_price)
            VALUES (?,?,?,?,?,?)
        """, (
            r["item_id"],
            r["order_id"],
            r["product_id"],
            r["description"],
            r["quantity"],
            r["unit_price"],
        ))

        conn.execute(
            "INSERT INTO order_items_backup_ids(audit_id) VALUES (?)",
            (r["audit_id"],)
        )

    conn.commit()
    bconn.commit()
    conn.close()
    bconn.close()

# -----------------------------------------------------------
# ------------------- DEMO DATA SEEDING ---------------------
# -----------------------------------------------------------

def seed_demo():
    """Insert full demo suppliers, products, and one order with items."""
    conn = db_conn()

    # wipe everything so your demo always looks fresh & clean
    conn.execute("DELETE FROM purchase_order_items;")
    conn.execute("DELETE FROM purchase_orders;")
    conn.execute("DELETE FROM products;")
    conn.execute("DELETE FROM suppliers;")
    conn.execute("DELETE FROM products_audit;")
    conn.execute("DELETE FROM order_items_audit;")
    conn.execute("DELETE FROM products_backup_ids;")
    conn.execute("DELETE FROM order_items_backup_ids;")
    conn.commit()

    # -----------------------------------------------------
    # SUPPLIERS (with all the new fields!)
    # -----------------------------------------------------
    suppliers_demo = [
        (
            "Alpha Tech Suppliers", "Kiran Kumar", "9876543210",
            "alpha.tech.suppliers@gmail.com",
            "23 Electronics Street, Industrial Layout",
            "Bengaluru", "KA", "India"
        ),
        (
            "Southern Electronics", "Priya R", "9753186420",
            "contact@southern-electro.in",
            "48 Anna Salai, Opp Metro Pillar 12",
            "Chennai", "TN", "India"
        ),
        (
            "Kerala Industrial Co.", "Anand Pillai", "8899001122",
            "info@kico.co.in",
            "12/88 MG Road, Marine Drive",
            "Kochi", "KL", "India"
        ),
    ]

    conn.executemany("""
        INSERT INTO suppliers(name, contact_name, phone, email, address, city, state, country)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, suppliers_demo)

    # -----------------------------------------------------
    # PRODUCTS
    # -----------------------------------------------------
    products_demo = [
        ("3-Pin Power Cable", "PC-3PIN-IND", 160.0),
        ("Industrial Soldering Iron 40W", "SLD-IRON-40W", 680.0),
        ("Raspberry Pi 4B (4GB RAM)", "RPI4-4GB", 5200.0),
        ("12V SMPS Adapter", "SMPS-12V-2A", 450.0),
        ("CCTV Camera 2MP HD", "CCTV-2MP-HD", 1790.0),
    ]

    conn.executemany("""
        INSERT INTO products(name, sku, unit_price)
        VALUES (?, ?, ?)
    """, products_demo)

    # -----------------------------------------------------
    # ONE PURCHASE ORDER (linked to supplier 1)
    # -----------------------------------------------------
    conn.execute("""
        INSERT INTO purchase_orders(supplier_id, status, notes)
        VALUES (?,?,?)
    """, (1, "PLACED", "Urgent requirement for IoT Lab."))

    order_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # -----------------------------------------------------
    # ORDER ITEMS (realistic)
    # -----------------------------------------------------
    order_items_demo = [
        (order_id, "Raspberry Pi 4B (4GB RAM)", 3, 5200.0),
        (order_id, "CCTV Camera 2MP HD", 5, 1790.0),
        (order_id, "3-Pin Power Cable", 10, 160.0),
    ]

    conn.executemany("""
        INSERT INTO purchase_order_items(order_id, description, quantity, unit_price)
        VALUES (?, ?, ?, ?)
    """, order_items_demo)

    conn.commit()
    conn.close()

    # -----------------------------------------------------
    # REPLICATE TO BACKUP AFTER SEEDING
    # -----------------------------------------------------
    replicate_product_to_backup()
    replicate_order_item_to_backup()



@app.route("/seed_demo")
def seed_demo_route():
    seed_demo()
    flash("Demo data inserted successfully! 🎯", "success")
    return redirect(url_for("dashboard"))

# -----------------------------------------------------------
# ------------------------ ROUTES ---------------------------
# -----------------------------------------------------------

@app.route("/")
def dashboard():
    # keep backup in sync whenever dashboard is hit
    replicate_product_to_backup()
    replicate_order_item_to_backup()

    conn = db_conn()
    total_suppliers = conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
    total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    total_orders = conn.execute("SELECT COUNT(*) FROM purchase_orders").fetchone()[0]
    conn.close()

    return render_template(
        "dashboard.html",
        suppliers=total_suppliers,
        products=total_products,
        orders=total_orders,
    )

# ----------------------- SUPPLIERS -------------------------

@app.route("/suppliers")
def suppliers():
    conn = db_conn()
    rows = conn.execute("SELECT * FROM suppliers ORDER BY supplier_id DESC").fetchall()
    conn.close()
    return render_template("suppliers.html", suppliers=rows)

@app.route("/add_supplier", methods=["GET", "POST"])
def add_supplier():
    if request.method == "POST":
        name = request.form["name"]
        contact = request.form.get("contact")
        phone = request.form.get("phone")
        email = request.form.get("email")
        address = request.form.get("address")
        city = request.form.get("city")
        state = request.form.get("state")
        country = request.form.get("country", "India")

        conn = db_conn()
        conn.execute("""
            INSERT INTO suppliers(name, contact_name, phone, email, address, city, state, country)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, contact, phone, email, address, city, state, country))

        conn.commit()
        conn.close()

        flash("Supplier added successfully!", "success")
        return redirect(url_for("suppliers"))

    return render_template("add_supplier.html")


@app.route("/suppliers_list")
def suppliers_list():
    return redirect(url_for("suppliers"))


@app.route("/supplier/<supplier_id>/deactivate", methods=["POST"])
def supplier_deactivate(supplier_id):
    conn = db_conn()
    conn.execute("UPDATE suppliers SET is_active = 0 WHERE supplier_id=?", (supplier_id,))
    conn.commit()
    conn.close()

    flash("Supplier deactivated!", "warning")
    return redirect(url_for("suppliers"))



# ----------------------- PRODUCTS --------------------------

@app.route("/products")
def products():
    conn = db_conn()
    rows = conn.execute("SELECT * FROM products ORDER BY product_id DESC").fetchall()
    conn.close()
    return render_template("products.html", products=rows)

@app.route("/products_list")
def products_list():
    return redirect(url_for("products"))

@app.route("/add_product", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        name = request.form["name"]
        sku = request.form["sku"]
        price = float(request.form["price"])
        description = request.form.get("description")

        conn = db_conn()
        conn.execute("""
            INSERT INTO products(name, sku, unit_price)
            VALUES (?, ?, ?)
        """, (name, sku, price))

        conn.commit()
        conn.close()

        replicate_product_to_backup()

        flash("Product added successfully!", "success")
        return redirect(url_for("products"))

    return render_template("add_product.html")


# ----------------------- ORDERS ----------------------------

@app.route("/orders")
def orders():
    conn = db_conn()
    rows = conn.execute("""
        SELECT po.order_id,
               po.order_date,
               po.status,
               s.name AS supplier,
               IFNULL(v.order_total, 0) AS total
        FROM purchase_orders po
        JOIN suppliers s ON s.supplier_id = po.supplier_id
        LEFT JOIN v_order_totals v ON v.order_id = po.order_id
        ORDER BY po.order_id DESC
    """).fetchall()
    conn.close()
    return render_template("orders.html", orders=rows)

@app.route("/add_order", methods=["GET", "POST"])
def add_order():
    conn = db_conn()
    if request.method == "POST":
        supplier = request.form["supplier_id"]
        notes = request.form.get("notes")
        conn.execute(
            "INSERT INTO purchase_orders(supplier_id, notes) VALUES (?,?)",
            (supplier, notes),
        )
        conn.commit()
        conn.close()
        flash("Order created!", "success")
        return redirect(url_for("orders"))

    suppliers = conn.execute("SELECT supplier_id, name FROM suppliers").fetchall()
    conn.close()
    return render_template("add_order.html", suppliers=suppliers)

@app.route("/order/<oid>")
def order_detail(oid):
    conn = db_conn()
    order = conn.execute("""
        SELECT po.*,
               s.name AS supplier,
               IFNULL(v.order_total, 0) AS total
        FROM purchase_orders po
        JOIN suppliers s ON s.supplier_id = po.supplier_id
        LEFT JOIN v_order_totals v ON v.order_id = po.order_id
        WHERE po.order_id = ?
    """, (oid,)).fetchone()

    items = conn.execute("""
        SELECT description,
               quantity,
               unit_price,
               (quantity * unit_price) AS total
        FROM purchase_order_items
        WHERE order_id = ?
    """, (oid,)).fetchall()

    conn.close()
    return render_template("order_detail.html", order=order, items=items)

@app.route("/add_item/<oid>", methods=["GET", "POST"])
def add_item(oid):
    conn = db_conn()
    if request.method == "POST":
        desc = request.form["desc"]
        qty = float(request.form["qty"])
        price = float(request.form["price"])
        conn.execute("""
            INSERT INTO purchase_order_items(order_id, description, quantity, unit_price)
            VALUES (?,?,?,?)
        """, (oid, desc, qty, price))
        conn.commit()
        conn.close()

        replicate_order_item_to_backup()

        flash("Item added!", "success")
        return redirect(url_for("order_detail", oid=oid))

    conn.close()
    return render_template("add_item.html", oid=oid)

# ----------------------- BACKUP VIEWER ---------------------

@app.route("/backup")
def backup_viewer():
    bconn = backup_conn()
    products = bconn.execute(
        "SELECT * FROM products_backup ORDER BY backup_id DESC"
    ).fetchall()
    items = bconn.execute(
        "SELECT * FROM order_items_backup ORDER BY backup_id DESC"
    ).fetchall()
    bconn.close()
    return render_template("backup.html", products=products, items=items)

# -----------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
