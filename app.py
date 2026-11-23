import os
import ssl
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, time
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from jinja2 import ChoiceLoader, FileSystemLoader
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, template_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', 'cmdi_canteen_super_secret_key_2026')

app.jinja_loader = ChoiceLoader([
    FileSystemLoader('.'),
    FileSystemLoader('templates')
])

db_url = os.environ.get('DATABASE_URL', 'sqlite:///canteen.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

# Email Settings para kay Admin
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'emmanuelbarbadillo05@gmail.com')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'emmanuelbarbadillo05@gmail.com')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')

def send_admin_email_async(subject, html_content):
    """Nagpapadala ng email sa admin sa background gamit ang SSL at TLS fallback"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[EMAIL SKIP] Walang MAIL_USERNAME o MAIL_PASSWORD na naka-set sa Render Environment.")
        return

    def _send():
        clean_password = MAIL_PASSWORD.replace(' ', '').strip()
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"CMDI Canteen System <{MAIL_USERNAME}>"
        msg['To'] = ADMIN_EMAIL
        msg.attach(MIMEText(html_content, 'html'))

        # Subok 1: SSL Port 465 (Pinakamabilis at hindi madalas ma-block)
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context, timeout=15) as server:
                server.login(MAIL_USERNAME, clean_password)
                server.send_message(msg)
            print(f"[EMAIL SUCCESS] Naipadala ang email kay {ADMIN_EMAIL} (via SSL)")
            return
        except Exception as e_ssl:
            print(f"[EMAIL SSL Retry TLS]: {e_ssl}")

        # Subok 2: TLS Port 587 fallback
        try:
            with smtplib.SMTP('smtp.gmail.com', 587, timeout=15) as server:
                server.starttls()
                server.login(MAIL_USERNAME, clean_password)
                server.send_message(msg)
            print(f"[EMAIL SUCCESS] Naipadala ang email kay {ADMIN_EMAIL} (via TLS)")
        except Exception as e_tls:
            print(f"[EMAIL ERROR] Hindi naipadala ang email: {e_tls}")

    threading.Thread(target=_send, daemon=True).start()

# --- DATABASE MODELS ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')
    name = db.Column(db.String(120), nullable=True)
    wallet_balance = db.Column(db.Float, default=500.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MenuItem(db.Model):
    __tablename__ = 'menu_items'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(255))
    is_available = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(255))

class Reservation(db.Model):
    __tablename__ = 'reservations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    table_number = db.Column(db.Integer, nullable=False)
    reservation_date = db.Column(db.Date, nullable=False)
    reservation_time = db.Column(db.Time, nullable=False)
    guests = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default='confirmed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('reservations', lazy=True))

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    order_type = db.Column(db.String(20), nullable=False)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservations.id'), nullable=True)
    total_amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(20), default='wallet')
    payment_status = db.Column(db.String(20), default='paid')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('orders', lazy=True))
    reservation = db.relationship('Reservation', backref=db.backref('linked_orders', lazy=True))
    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan", lazy=True)

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_items.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)
    menu_item = db.relationship('MenuItem')

def current_user():
    if 'user_id' in session:
        return db.session.get(User, session['user_id'])
    return None

@app.context_processor
def inject_user():
    return dict(current_user=current_user(), now=datetime.utcnow())

# --- DIAGNOSTIC ROUTE PARA SA EMAIL ---
@app.route('/test-email')
def test_email():
    """Diretsong ipapakita sa screen kung bakit hindi nakakapag-email ang Google"""
    clean_password = (MAIL_PASSWORD or '').replace(' ', '').strip()
    
    status_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 650px; margin: 40px auto; padding: 25px; border: 2px solid #0d3b66; border-radius: 10px;">
        <h2 style="color: #0d3b66; margin-top: 0;">CMDI Canteen - Email Diagnostic Test</h2>
        <table style="width: 100%; margin-bottom: 20px;">
            <tr><td><strong>ADMIN_EMAIL:</strong></td><td>{ADMIN_EMAIL}</td></tr>
            <tr><td><strong>MAIL_USERNAME:</strong></td><td>{MAIL_USERNAME or '<span style=\"color:red;\">HINDI NAKA-SET</span>'}</td></tr>
            <tr><td><strong>MAIL_PASSWORD:</strong></td><td>{'Naka-set (' + str(len(clean_password)) + ' characters)' if clean_password else '<span style=\"color:red;\">HINDI NAKA-SET</span>'}</td></tr>
        </table>
    """
    
    if not MAIL_USERNAME or not clean_password:
        status_html += """
        <div style="background-color: #ffebee; color: #c62828; padding: 15px; border-radius: 6px;">
            <strong>ERROR:</strong> Kulang ang Environment Variables sa Render!<br>
            Pumunta sa Render -> Canteen-ordering-systems-6 -> Environment.<br>
            Idagdag ang <code>MAIL_USERNAME</code> at <code>MAIL_PASSWORD</code>.
        </div></div>
        """
        return status_html

    msg = MIMEMultipart('alternative')
    msg['Subject'] = "[TEST] CMDI Canteen System Notification Test"
    msg['From'] = f"CMDI Canteen <{MAIL_USERNAME}>"
    msg['To'] = ADMIN_EMAIL
    msg.attach(MIMEText("<h3>Matagumpay ang Email Test ng CMDI Canteen!</h3><p>Nakatanggap ka ng test notification. Gumagana na ang email para sa mga orders!</p>", 'html'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context, timeout=12) as server:
            server.login(MAIL_USERNAME, clean_password)
            server.send_message(msg)
        status_html += f"""
        <div style="background-color: #e8f5e9; color: #2e7d32; padding: 15px; border-radius: 6px;">
            <strong>SUCCESS!</strong> Matagumpay na naipadala ang test email kay <strong>{ADMIN_EMAIL}</strong>!<br>
            Pakitingnan ang iyong <strong>Inbox</strong> o <strong>Spam</strong> folder sa Gmail.
        </div></div>
        """
        return status_html
    except smtplib.SMTPAuthenticationError as auth_err:
        status_html += f"""
        <div style="background-color: #ffebee; color: #c62828; padding: 15px; border-radius: 6px;">
            <strong>AUTHENTICATION ERROR:</strong> Tinanggihan ni Google ang password!<br><br>
            <em>Dahilan:</em> Baka ang personal mong password sa Gmail ang nailagay mo sa halip na ang <strong>16-letter Google App Password</strong>.<br>
            Kumuha ng App Password sa: <a href="https://myaccount.google.com/apppasswords" target="_blank">myaccount.google.com/apppasswords</a>.<br>
            <small style="color: #666;">Google Error Code: {auth_err}</small>
        </div></div>
        """
        return status_html
    except Exception as e:
        status_html += f"""
        <div style="background-color: #fff3e0; color: #e65100; padding: 15px; border-radius: 6px;">
            <strong>ERROR:</strong> {e}
        </div></div>
        """
        return status_html

# --- ROUTES ---
@app.route('/')
@app.route('/index')
def index():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    if user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('menu'))

@app.route('/home')
def home():
    return index()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            flash(f"Maligayang pagbabalik, {user.name or user.username}!", "success")
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('menu'))
        else:
            flash("Maling username o password. Pakisubukan muli.", "danger")

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        name = request.form.get('name', '').strip()
        
        if not username or not password:
            flash("Pakilagay ang username at password.", "danger")
            return redirect(url_for('register'))
            
        if User.query.filter_by(username=username).first():
            flash("May gumagamit na ng username na ito. Pumili ng iba.", "warning")
            return redirect(url_for('register'))
            
        new_student = User(
            username=username,
            password=generate_password_hash(password),
            role='student',
            name=name or username,
            wallet_balance=100.0
        )
        db.session.add(new_student)
        db.session.commit()
        
        flash("Matagumpay ang pag-rehistro! May libre kang ₱100 balance. Mag-sign in na.", "success")
        return redirect(url_for('login'))
        
    try:
        return render_template('register.html')
    except Exception:
        return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Matagumpay kang naka-logout.", "info")
    return redirect(url_for('login'))

@app.route('/menu')
def menu():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    category = request.args.get('category')
    query = MenuItem.query.filter_by(is_available=True)
    if category and category != 'All':
        query = query.filter_by(category=category)
    items = query.all()
    categories = ['All', 'Meals', 'Snacks', 'Drinks', 'Desserts']
    return render_template('menu.html', items=items, categories=categories, selected_category=category or 'All')

@app.route('/cart')
def cart():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    cart_data = session.get('cart', {})
    cart_items = []
    total = 0.0
    for item_id, qty in cart_data.items():
        item = db.session.get(MenuItem, int(item_id))
        if item:
            subtotal = item.price * qty
            total += subtotal
            cart_items.append({'item': item, 'quantity': qty, 'subtotal': subtotal})
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/cart/add/<int:item_id>', methods=['POST'])
def add_to_cart(item_id):
    cart_data = session.get('cart', {})
    str_id = str(item_id)
    cart_data[str_id] = cart_data.get(str_id, 0) + 1
    session['cart'] = cart_data
    session.modified = True
    flash("Naidagdag ang pagkain sa iyong cart!", "success")
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    cart_data = session.get('cart', {})
    str_id = str(item_id)
    if str_id in cart_data:
        del cart_data[str_id]
        session['cart'] = cart_data
        session.modified = True
        flash("Naalis ang pagkain sa iyong cart.", "info")
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['POST'])
def checkout():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    cart_data = session.get('cart', {})
    if not cart_data:
        flash("Walang laman ang iyong cart.", "warning")
        return redirect(url_for('menu'))

    order_type = request.form.get('order_type', 'takeout')
    payment_method = request.form.get('payment_method', 'wallet')
    reservation_id = request.form.get('reservation_id')

    total_amount = 0.0
    order_items_to_create = []
    for item_id, qty in cart_data.items():
        menu_item = db.session.get(MenuItem, int(item_id))
        if menu_item and menu_item.is_available:
            subtotal = menu_item.price * qty
            total_amount += subtotal
            order_items_to_create.append((menu_item, qty, menu_item.price))

    if payment_method == 'wallet':
        if user.wallet_balance < total_amount:
            flash(f"Kulang ang iyong wallet balance (₱{user.wallet_balance:.2f}). Mag-top up muna o pumili ng Cash on Pickup.", "danger")
            return redirect(url_for('cart'))
        user.wallet_balance -= total_amount
        pay_status = 'paid'
    else:
        pay_status = 'pending_cash'

    new_order = Order(
        user_id=user.id,
        order_type=order_type,
        reservation_id=int(reservation_id) if reservation_id and reservation_id.isdigit() else None,
        total_amount=total_amount,
        payment_method=payment_method,
        payment_status=pay_status,
        status='pending'
    )
    db.session.add(new_order)
    db.session.flush()

    for item, qty, price in order_items_to_create:
        oi = OrderItem(order_id=new_order.id, menu_item_id=item.id, quantity=qty, price=price)
        db.session.add(oi)

    db.session.commit()
    session.pop('cart', None)

    # --- EMAIL NOTIFICATION SA ADMIN ---
    items_rows = "".join([
        f"<tr>"
        f"<td style='padding:10px;border-bottom:1px solid #eee;'>{item.name}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #eee;text-align:center;'>{qty}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #eee;text-align:right;'>₱{price * qty:.2f}</td>"
        f"</tr>"
        for item, qty, price in order_items_to_create
    ])

    email_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #0d3b66; color: white; padding: 20px; text-align: center;">
            <h2 style="margin: 0; color: #ff7200;">CARD-MRI Development Institute, Inc.</h2>
            <h3 style="margin: 6px 0 0 0; font-weight: normal; font-size: 16px;">May Bagong Order sa Canteen!</h3>
        </div>
        <div style="padding: 24px; background-color: #ffffff;">
            <p style="font-size: 15px; color: #333;">Magandang araw Admin,</p>
            <p style="font-size: 14px; color: #555;">May bagong natanggap na order mula sa online canteen system:</p>
            
            <div style="background-color: #f8f9fa; border-left: 4px solid #ff7200; padding: 12px 16px; margin: 15px 0;">
                <p style="margin: 4px 0;"><strong>Order ID:</strong> #{new_order.id}</p>
                <p style="margin: 4px 0;"><strong>Customer:</strong> {user.name or user.username} ({user.role.capitalize()})</p>
                <p style="margin: 4px 0;"><strong>Type:</strong> <span style="color:#ff7200;font-weight:bold;">{order_type.upper()}</span></p>
                <p style="margin: 4px 0;"><strong>Bayad:</strong> {payment_method.replace('_', ' ').capitalize()} ({pay_status})</p>
                <p style="margin: 4px 0;"><strong>Oras:</strong> {new_order.created_at.strftime('%b %d, %Y - %I:%M %p')}</p>
            </div>

            <h4 style="color: #0d3b66; margin-top: 20px; border-bottom: 2px solid #0d3b66; padding-bottom: 6px;">Mga Pagkaing In-order:</h4>
            <table style="width: 100%; border-collapse: collapse;">
                <thead>
                    <tr style="background-color: #f1f5f9; color: #0d3b66; font-size: 13px;">
                        <th style="padding: 8px 10px; text-align: left;">Item</th>
                        <th style="padding: 8px 10px; text-align: center;">Qty</th>
                        <th style="padding: 8px 10px; text-align: right;">Presyo</th>
                    </tr>
                </thead>
                <tbody>
                    {items_rows}
                </tbody>
                <tfoot>
                    <tr style="background-color: #fff8f0;">
                        <td colspan="2" style="padding: 12px 10px; text-align: right; font-weight: bold; font-size: 15px;">Kabuuang Halaga:</td>
                        <td style="padding: 12px 10px; text-align: right; font-weight: bold; font-size: 17px; color: #ff7200;">₱{total_amount:.2f}</td>
                    </tr>
                </tfoot>
            </table>
        </div>
        <div style="background-color: #0d3b66; color: #ffffff; padding: 12px; text-align: center; font-size: 12px;">
            CMDI Online Canteen Ordering & Reservation System
        </div>
    </div>
    """

    send_admin_email_async(
        f"[CMDI Canteen] Bagong Order #{new_order.id} (₱{total_amount:.2f})",
        email_html
    )

    flash(f"Salamat! Matagumpay ang iyong order (#{new_order.id}).", "success")
    return redirect(url_for('orders'))

@app.route('/orders')
def orders():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    user_orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=user_orders)

@app.route('/my_orders')
def my_orders():
    return orders()

@app.route('/reservations', methods=['GET', 'POST'])
def reservations():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    if request.method == 'POST':
        table_num = request.form.get('table_number')
        res_date_str = request.form.get('reservation_date')
        res_time_str = request.form.get('reservation_time')
        guests = request.form.get('guests', 1)

        try:
            r_date = datetime.strptime(res_date_str, '%Y-%m-%d').date()
            r_time = datetime.strptime(res_time_str, '%H:%M').time()
            new_res = Reservation(
                user_id=user.id,
                table_number=int(table_num),
                reservation_date=r_date,
                reservation_time=r_time,
                guests=int(guests),
                status='confirmed'
            )
            db.session.add(new_res)
            db.session.commit()
            flash("Matagumpay ang iyong table reservation!", "success")
            return redirect(url_for('reservations'))
        except Exception as e:
            flash(f"Nagkaroon ng problema sa pag-reserve: {e}", "danger")

    my_res = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.reservation_date.desc()).all()
    return render_template('reservations.html', reservations=my_res)

@app.route('/wallet', methods=['GET', 'POST'])
def wallet():
    user = current_user()
    if not user:
        return redirect(url_for('login'))
    if request.method == 'POST':
        amount = float(request.form.get('amount', 0))
        if amount > 0:
            user.wallet_balance += amount
            db.session.commit()
            flash(f"Matagumpay na nakapag-top up ng ₱{amount:.2f}!", "success")
        else:
            flash("Maglagay ng tamang halaga para sa top up.", "warning")
        return redirect(url_for('wallet'))
    return render_template('wallet.html', user=user)

# --- ADMIN ROUTES ---
@app.route('/admin')
@app.route('/admin/dashboard')
def admin_dashboard():
    user = current_user()
    if not user or user.role != 'admin':
        flash("Para lamang sa Admin ang pahinang ito.", "danger")
        return redirect(url_for('login'))
    total_orders = Order.query.count()
    pending_orders = Order.query.filter_by(status='pending').count()
    total_sales = db.session.query(db.func.sum(Order.total_amount)).filter_by(payment_status='paid').scalar() or 0.0
    total_users = User.query.count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    return render_template('admin_dashboard.html',
                           total_orders=total_orders,
                           pending_orders=pending_orders,
                           total_sales=total_sales,
                           total_users=total_users,
                           recent_orders=recent_orders)

@app.route('/admin/orders')
def admin_orders():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin_orders.html', orders=orders)

@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
def update_order_status(order_id):
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    order = db.session.get(Order, order_id)
    if order:
        new_status = request.form.get('status')
        order.status = new_status
        if new_status == 'completed' and order.payment_method == 'cash_on_pickup':
            order.payment_status = 'paid'
        db.session.commit()
        flash(f"Na-update ang status ng Order #{order.id} sa {new_status}.", "success")
    return redirect(url_for('admin_orders'))

@app.route('/admin/menu', methods=['GET', 'POST'])
def admin_menu():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name')
        category = request.form.get('category')
        price = float(request.form.get('price', 0))
        description = request.form.get('description', '')
        item = MenuItem(name=name, category=category, price=price, description=description)
        db.session.add(item)
        db.session.commit()
        flash("Matagumpay na naidagdag ang bagong pagkain!", "success")
        return redirect(url_for('admin_menu'))
    items = MenuItem.query.all()
    return render_template('admin_menu.html', items=items)

@app.route('/admin/reservations')
def admin_reservations():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    reservations = Reservation.query.order_by(Reservation.reservation_date.desc()).all()
    return render_template('admin_reservations.html', reservations=reservations)

@app.route('/admin/users')
def admin_users():
    user = current_user()
    if not user or user.role != 'admin':
        return redirect(url_for('login'))
    users = User.query.all()
    return render_template('admin_users.html', users=users)

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin',
            name='Canteen Administrator'
        )
        db.session.add(admin)

    if not User.query.filter_by(username='student').first():
        student = User(
            username='student',
            password=generate_password_hash('student123'),
            role='student',
            name='CMDI Student',
            wallet_balance=750.0
        )
        db.session.add(student)

    if MenuItem.query.count() == 0:
        sample_menu = [
            MenuItem(name="Chicken Adobo with Rice", category="Meals", price=65.0, description="Classic Pinoy adobo with steaming hot rice"),
            MenuItem(name="Pork Sinigang with Rice", category="Meals", price=75.0, description="Sour and savory soup with fresh vegetables"),
            MenuItem(name="Beef Caldereta with Rice", category="Meals", price=85.0, description="Rich tomato stew with tender beef chunks"),
            MenuItem(name="Crispy Lumpiang Shanghai (4pcs)", category="Snacks", price=35.0, description="Crunchy spring rolls with sweet chili sauce"),
            MenuItem(name="Pancit Canton Guisado", category="Snacks", price=40.0, description="Stir-fried noodles loaded with veggies and meat"),
            MenuItem(name="Iced Calamansi Juice", category="Drinks", price=20.0, description="Refreshing local citrus drink"),
            MenuItem(name="Bottled Mineral Water (500ml)", category="Drinks", price=15.0, description="Purified drinking water"),
            MenuItem(name="Special Halo-Halo", category="Desserts", price=50.0, description="Shaved ice dessert with sweet beans, jelly, and ube")
        ]
        db.session.bulk_save_objects(sample_menu)

    db.session.commit()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
