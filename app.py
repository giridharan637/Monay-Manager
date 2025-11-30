import csv
import os
import uuid
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from io import StringIO

app = Flask(__name__)
app.secret_key = "replace_with_a_random_secret_key"

USERS_FILE = "users.csv"
TX_FILE = "transactions.csv"
CATEGORIES = ["Food","Social","Transport","Apparel","Education","Gift","Other"]

# Ensure files exist
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username","password_hash"])

if not os.path.exists(TX_FILE):
    with open(TX_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id","username","type","date","category","amount","description"])

# Utility functions
def user_exists(username):
    with open(USERS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["username"] == username:
                return True
    return False

def create_user(username, password):
    h = generate_password_hash(password)
    with open(USERS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([username, h])

def validate_user(username, password):
    with open(USERS_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r["username"] == username and check_password_hash(r["password_hash"], password):
                return True
    return False

def add_transaction(username, ttype, date, category, amount, description):
    tid = str(uuid.uuid4())
    with open(TX_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([tid, username, ttype, date, category, f"{float(amount):.2f}", description])
    return tid

def read_transactions(username=None):
    rows = []
    with open(TX_FILE, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if username is None or r["username"] == username:
                rows.append(r)
    return rows

def write_all_transactions(rows):
    with open(TX_FILE, "w", newline="") as f:
        fieldnames = ["id","username","type","date","category","amount","description"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

def get_user_summary(username):
    txs = read_transactions(username)
    income = sum(float(t["amount"]) for t in txs if t["type"]=="income")
    expense = sum(float(t["amount"]) for t in txs if t["type"]=="expense")
    return {"income": income, "expense": expense, "balance": income-expense}

def monthly_aggregation(username):
    txs = read_transactions(username)
    months = {}
    for t in txs:
        d = t["date"]
        if not d: continue
        key = d[:7]  # YYYY-MM
        months.setdefault(key, {"income":0.0,"expense":0.0})
        if t["type"]=="income":
            months[key]["income"] += float(t["amount"])
        else:
            months[key]["expense"] += float(t["amount"])
    # sort by month
    items = sorted(months.items())
    labels = [k for k,_ in items]
    inc = [v["income"] for _,v in items]
    exp = [v["expense"] for _,v in items]
    return {"labels": labels, "income": inc, "expense": exp}

def category_breakdown(username):
    txs = read_transactions(username)
    cats = {}
    for t in txs:
        if t["type"]=="expense":
            cats.setdefault(t["category"],0.0)
            cats[t["category"]] += float(t["amount"])
    labels = list(cats.keys())
    values = [cats[k] for k in labels]
    return {"labels": labels, "values": values}

# Routes
@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        u = request.form.get("username").strip()
        p = request.form.get("password").strip()
        if not u or not p:
            flash("Provide username and password","error")
            return redirect(url_for("register"))
        if user_exists(u):
            flash("Username already exists","error")
            return redirect(url_for("register"))
        create_user(u,p)
        flash("Account created. Please login.","success")
        return redirect(url_for("home"))
    return render_template("register.html")

@app.route("/login", methods=["POST"])
def login():
    u = request.form.get("username").strip()
    p = request.form.get("password").strip()
    if validate_user(u,p):
        session["user"] = u
        return redirect(url_for("dashboard"))
    flash("Invalid credentials","error")
    return redirect(url_for("home"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("home"))
    username = session["user"]
    summary = get_user_summary(username)
    recent = sorted(read_transactions(username), key=lambda x: x["date"], reverse=True)[:6]
    return render_template("dashboard.html", username=username, summary=summary, recent=recent)

@app.route("/add", methods=["GET","POST"])
def add():
    if "user" not in session:
        return redirect(url_for("home"))
    if request.method=="POST":
        ttype = request.form.get("type")
        date = request.form.get("date") or datetime.now().strftime("%Y-%m-%d")
        category = request.form.get("category") or "Other"
        amount = request.form.get("amount") or "0"
        description = request.form.get("description") or ""
        try:
            float(amount)
        except:
            flash("Invalid amount", "error")
            return redirect(url_for("add"))
        add_transaction(session["user"], ttype, date, category, amount, description)
        flash("Transaction added", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_transaction.html", categories=CATEGORIES)

@app.route("/transactions")
def transactions():
    if "user" not in session:
        return redirect(url_for("home"))
    rows = sorted(read_transactions(session["user"]), key=lambda x: x["date"], reverse=True)
    return render_template("view_transactions.html", rows=rows)

@app.route("/delete/<tid>", methods=["POST"])
def delete_transaction(tid):
    if "user" not in session:
        return redirect(url_for("home"))
    rows = read_transactions()
    rows = [r for r in rows if r["id"]!=tid or r["username"]!=session["user"]]
    write_all_transactions(rows)
    flash("Deleted", "success")
    return redirect(url_for("transactions"))

@app.route("/edit/<tid>", methods=["GET","POST"])
def edit_transaction(tid):
    if "user" not in session:
        return redirect(url_for("home"))
    rows = read_transactions()
    target = None
    for r in rows:
        if r["id"]==tid and r["username"]==session["user"]:
            target = r
            break
    if not target:
        flash("Not found","error")
        return redirect(url_for("transactions"))
    if request.method=="POST":
        target["date"] = request.form.get("date") or target["date"]
        target["category"] = request.form.get("category") or target["category"]
        target["amount"] = f"{float(request.form.get('amount')):.2f}"
        target["description"] = request.form.get("description") or ""
        write_all_transactions(rows)
        flash("Updated","success")
        return redirect(url_for("transactions"))
    return render_template("add_transaction.html", edit=target, categories=CATEGORIES)

@app.route("/analytics")
def analytics():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("analytics.html")

@app.route("/api/monthly")
def api_monthly():
    if "user" not in session:
        return jsonify({"error":"unauth"}), 401
    data = monthly_aggregation(session["user"])
    return jsonify(data)

@app.route("/api/categories")
def api_categories():
    if "user" not in session:
        return jsonify({"error":"unauth"}), 401
    data = category_breakdown(session["user"])
    return jsonify(data)

@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect(url_for("home"))
    return render_template("profile.html", username=session["user"])

@app.route("/export")
def export_csv():
    if "user" not in session:
        return redirect(url_for("home"))
    rows = read_transactions(session["user"])
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["id","date","type","category","amount","description"])
    for r in rows:
        writer.writerow([r["id"], r["date"], r["type"], r["category"], r["amount"], r["description"]])
    mem = StringIO(si.getvalue())
    mem.seek(0)
    return send_file(
        mem,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"{session['user']}_transactions.csv"
    )

if __name__ == "__main__":
    app.run(debug=True)
