from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    url_for
)
from flask import send_file
import csv
import io
from functools import wraps
from services.email_service import send_price_alert
from flask_sqlalchemy import SQLAlchemy
from scraper import get_product_details
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "price_tracker_secret"

def login_required(route_function):

    @wraps(route_function)
    def wrapper(*args, **kwargs):

        if "user_id" not in session:
            return redirect("/login")

        return route_function(*args, **kwargs)

    return wrapper

# =====================
# DATABASE CONFIG
# =====================

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///tracker.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# =====================
# DATABASE MODELS
# =====================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    products = db.relationship(
        "TrackedProduct",
        backref="user",
        lazy=True
    )


class TrackedProduct(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("user.id"),
        nullable=False
    )

    product_name = db.Column(
        db.String(200),
        nullable=False
    )

    url = db.Column(
        db.String(500),
        nullable=False
    )

    target_price = db.Column(
        db.Float,
        nullable=False
    )

    current_price = db.Column(
        db.Float,
        default=0
    )

    status = db.Column(
        db.String(50),
        default="Active"
    )

    alerts = db.relationship(
        "AlertSent",
        back_populates="product",
        cascade="all, delete-orphan"
    )

    image_url = db.Column(db.String(1000))

    price_history = db.relationship(

        "PriceHistory",

        backref="product",

        lazy=True,

        order_by="PriceHistory.scraped_at"

    )


class PriceHistory(db.Model):
    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("tracked_product.id"),
        nullable=False
    )

    price = db.Column(
        db.Float,
        nullable=False
    )

    scraped_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp()
    )


class AlertSent(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("tracked_product.id"),
        nullable=False
    )

    price_at_alert = db.Column(
        db.Float,
        nullable=False
    )

    sent_at = db.Column(
        db.DateTime,
        default=db.func.current_timestamp()
    )

    product = db.relationship(
        "TrackedProduct",
        back_populates="alerts"
    )


def check_prices():

    with app.app_context():

        print("\nChecking product prices...")

        products = TrackedProduct.query.all()

        for product in products:

            if product.status != "Active":
                continue

            # Scrape product details
            product_data = get_product_details(product.url)

            new_price = product_data["price"]
            image_url = product_data["image"]

            if new_price is None:
                continue

            # Update current price
            product.current_price = new_price

            # Update image
            if image_url:
                product.image_url = image_url

            # Save price history if price changed
            last_record = (
                PriceHistory.query
                .filter_by(product_id=product.id)
                .order_by(PriceHistory.scraped_at.desc())
                .first()
            )

            if not last_record or last_record.price != new_price:

                history = PriceHistory(
                    product_id=product.id,
                    price=new_price
                )

                db.session.add(history)

            # Send email only if target price reached
            if new_price <= product.target_price:

                existing_alert = AlertSent.query.filter_by(
                    product_id=product.id
                ).first()

                if existing_alert:
                    continue

                try:

                    send_price_alert(
                        product.user.email,
                        product.product_name,
                        new_price,
                        product.target_price
                    )

                    new_alert = AlertSent(
                        product_id=product.id,
                        price_at_alert=new_price
                    )

                    db.session.add(new_alert)

                except Exception as e:

                    print(f"Email Error for '{product.product_name}': {e}")

        db.session.commit()

        print("Price checking completed.")

# =====================
# HOME PAGE
# =====================

@app.route("/")
def home():
    return redirect(url_for("login"))

# =====================
# TRACK PRODUCT
# =====================


# =====================
# LOGIN
# =====================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        # Email not found
        if not user:

            return render_template(
                "login.html",
                error="No account found with this email. Please register first."
            )

        # Password incorrect
        if not check_password_hash(user.password, password):

            return render_template(
                "login.html",
                error="Incorrect password. Please try again."
            )

        # Login successful
        session["user_id"] = user.id

        return redirect("/dashboard")

    return render_template("login.html")


# =====================
# LOGOUT
# =====================

@app.route("/logout")
@login_required
def logout():

    session.pop("user_id", None)

    return redirect("/login")


# =====================
# REGISTER
# =====================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            return render_template(
                "register.html",
                error="Passwords do not match"
            )

        existing_user = User.query.filter_by(
            email=email
        ).first()

        if existing_user:
            return render_template(
                "register.html",
                error="Email already registered"
            )
        hashed_password = generate_password_hash(password)

        new_user = User(
            name=name,
            email=email,
            password=hashed_password
        )

        db.session.add(new_user)
        db.session.commit()

        return render_template(
            "register.html",
            success="Account created successfully!"
        )

    return render_template("register.html")

# =====================
# DASHBOARD
# =====================

@app.route("/dashboard")
@login_required
def dashboard():

    search = request.args.get("search", "")

    query = TrackedProduct.query.filter_by(
        user_id=session["user_id"]
    )

    if search:

        query = query.filter(
            TrackedProduct.product_name.ilike(f"%{search}%")
        )

    products = query.all()

    # Dashboard Statistics
    total_products = TrackedProduct.query.filter_by(
        user_id=session["user_id"]
    ).count()

    active_products = TrackedProduct.query.filter_by(
        user_id=session["user_id"],
        status="Active"
    ).count()

    paused_products = TrackedProduct.query.filter_by(
        user_id=session["user_id"],
        status="Paused"
    ).count()

    alerts_sent = AlertSent.query.join(TrackedProduct).filter(
        TrackedProduct.user_id == session["user_id"]
    ).count()

    return render_template(
        "dashboard.html",
        products=products,
        search=search,
        total_products=total_products,
        active_products=active_products,
        paused_products=paused_products,
        alerts_sent=alerts_sent
    )
# =====================
# ADD PRODUCT
# =====================

@app.route("/add-product", methods=["GET", "POST"])
@login_required
def add_product():

    if request.method == "POST":

        product_name = request.form.get("product_name")
        product_url = request.form.get("url")
        target_price = request.form.get("target_price")

        # Validate URL
        if not product_url:
            return render_template(
                "add_product.html",
                error="Product URL is required."
            )

        # Get all product details using Playwright
        product_data = get_product_details(product_url)

        # If scraping failed
        if product_data is None:
            return render_template(
                "add_product.html",
                error="Unable to fetch product details."
            )

        # Use Amazon title if user leaves Product Name empty
        if not product_name:
            product_name = product_data["title"]

        current_price = product_data["price"]
        image_url = product_data["image"]

        # If price couldn't be fetched
        if current_price is None:
            current_price = 0

        # Create new product
        new_product = TrackedProduct(
            user_id=session["user_id"],
            product_name=product_name,
            url=product_url,
            target_price=float(target_price),
            current_price=current_price,
            image_url=image_url,
            status="Active"
        )

        db.session.add(new_product)
        db.session.commit()

        # Save initial price history
        history = PriceHistory(
            product_id=new_product.id,
            price=current_price
        )

        db.session.add(history)
        db.session.commit()

        return render_template(
            "add_product.html",
            success="Product added successfully!"
        )

    return render_template("add_product.html")

# =====================
# EDIT PRODUCT
# =====================

@app.route("/edit-product/<int:id>", methods=["GET", "POST"])
@login_required
def edit_product(id):

    product = TrackedProduct.query.get_or_404(id)

    if product.user_id != session["user_id"]:
        return redirect("/dashboard")

    if request.method == "POST":

        product.product_name = request.form.get(
            "product_name"
        )

        product.url = request.form.get(
            "url"
        )

        product.target_price = float(
            request.form.get("target_price")
        )

        db.session.commit()

        return redirect("/dashboard")

    return render_template(
        "edit_product.html",
        product=product
    )

# =====================
# PRODUCT DETAILS
# =====================

@app.route("/product/<int:id>")
@login_required
def product_detail(id):

    product = TrackedProduct.query.get_or_404(id)

    # Prevent users from viewing someone else's product
    if product.user_id != session["user_id"]:
        return redirect("/dashboard")

    # -----------------------------
    # Filter Price History
    # -----------------------------
    filter_type = request.args.get("filter", "30")

    query = PriceHistory.query.filter_by(product_id=id)

    if filter_type == "7":
        cutoff = datetime.utcnow() - timedelta(days=7)
        query = query.filter(PriceHistory.scraped_at >= cutoff)

    elif filter_type == "30":
        cutoff = datetime.utcnow() - timedelta(days=30)
        query = query.filter(PriceHistory.scraped_at >= cutoff)

    elif filter_type == "90":
        cutoff = datetime.utcnow() - timedelta(days=90)
        query = query.filter(PriceHistory.scraped_at >= cutoff)

    history = query.order_by(
        PriceHistory.scraped_at.asc()
    ).all()

    # -----------------------------
    # Price Statistics
    # -----------------------------
    prices = [record.price for record in history]

    if prices:
        current_price = prices[-1]
        lowest_price = min(prices)
        highest_price = max(prices)
        average_price = round(sum(prices) / len(prices), 2)
    else:
        current_price = 0
        lowest_price = 0
        highest_price = 0
        average_price = 0

    # -----------------------------
    # Price Trend
    # -----------------------------
    trend = "same"
    price_difference = 0

    if len(history) >= 2:

        latest_price = history[-1].price
        previous_price = history[-2].price

        price_difference = abs(latest_price - previous_price)

        if latest_price < previous_price:
            trend = "down"

        elif latest_price > previous_price:
            trend = "up"

    # -----------------------------
    # Render Page
    # -----------------------------
    return render_template(
        "product_detail.html",

        product=product,
        history=history,

        current_filter=filter_type,

        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,

        trend=trend,
        price_difference=price_difference
    )


@app.route("/refresh/<int:id>")
@login_required
def refresh(id):

    product = TrackedProduct.query.get_or_404(id)

    if product.user_id != session["user_id"]:
        return redirect("/dashboard")

    product_data = get_product_details(product.url)

    new_price = product_data["price"]

    if new_price is not None:

        product.current_price = new_price

        if product_data["image"]:
            product.image_url = product_data["image"]

        last_record = PriceHistory.query.filter_by(
            product_id=product.id
        ).order_by(
            PriceHistory.scraped_at.desc()
        ).first()

        if not last_record or last_record.price != new_price:

            history = PriceHistory(
                product_id=product.id,
                price=new_price
            )

            db.session.add(history)

        db.session.commit()

    return redirect(f"/product/{id}")


@app.route("/toggle-status/<int:id>")
@login_required
def toggle_status(id):

    product = TrackedProduct.query.get_or_404(id)

    # Security check
    if product.user_id != session["user_id"]:
        return redirect("/dashboard")

    # Toggle status
    if product.status == "Active":
        product.status = "Paused"
    else:
        product.status = "Active"

    db.session.commit()

    return redirect("/dashboard")


# ===
# ==================
# DELETE PRODUCT
# =====================

@app.route("/delete-product/<int:id>")
@login_required
def delete_product(id):

    product = TrackedProduct.query.get_or_404(id)

    if product.user_id != session["user_id"]:
        return redirect("/dashboard")

    # Delete all price history
    PriceHistory.query.filter_by(
        product_id=id
    ).delete()

    # Delete all alerts
    AlertSent.query.filter_by(
        product_id=id
    ).delete()

    # Delete the product
    db.session.delete(product)

    db.session.commit()

    return redirect("/dashboard")


# =====================
# ALERTS PAGE
# =====================

@app.route("/alerts")
@login_required
def alerts():

    alerts = AlertSent.query.join(TrackedProduct).filter(
        TrackedProduct.user_id == session["user_id"]
    ).all()

    print(alerts)

    return render_template(
        "alerts.html",
        alerts=alerts
    )

# =====================
# PRICE HISTORY PAGE
# =====================

@app.route("/history")
@login_required
def history():

    records = PriceHistory.query.all()

    return render_template(
        "history.html",
        records=records
    )

@app.route("/export-history/<int:id>")
@login_required
def export_history(id):

    product = TrackedProduct.query.get_or_404(id)

    if product.user_id != session["user_id"]:
        return redirect("/dashboard")

    history = PriceHistory.query.filter_by(
        product_id=id
    ).order_by(
        PriceHistory.scraped_at.asc()
    ).all()

    output = io.StringIO()

    writer = csv.writer(output)

    writer.writerow([
        "Date",
        "Price"
    ])

    for record in history:

        writer.writerow([
            record.scraped_at.strftime("%d-%m-%Y %H:%M:%S"),
            record.price
        ])

    output.seek(0)

    return send_file(
        io.BytesIO(output.getvalue().encode()),
        mimetype="text/csv",
        as_attachment=True,
        download_name="price_history.csv"
    )

# =====================
# CREATE DATABASE
# =====================

with app.app_context():
    db.create_all()


# =====================
# START SCHEDULER
# =====================

scheduler = BackgroundScheduler()

scheduler.add_job(
    func=check_prices,
    trigger="interval",
    minutes=1
)

scheduler.start()


# =====================
# RUN APP
# =====================

if __name__ == "__main__":
    app.run(debug=True)
