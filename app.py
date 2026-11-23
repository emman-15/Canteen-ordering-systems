import os
import re
from datetime import datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'canteen-super-secret-key-change-in-production')

# ---------------------------------------------------------------------------
# DATABASE CONFIGURATION: NEON POSTGRESQL + LOCAL SQLITE FALLBACK
# ---------------------------------------------------------------------------
raw_db_url = os.environ.get('DATABASE_URL', '').strip()

if raw_db_url:
    # Render and Heroku often provide postgres:// which SQLAlchemy 2.0+ requires as postgresql://
    if raw_db_url.startswith('postgres://'):
        raw_db_url = raw_db_url.replace('postgres://', 'postgresql://', 1)

    # For Neon and hosted PostgreSQL, ensure SSL mode is required
    if raw_db_url.startswith('postgresql://') and 'sslmode=' not in raw_db_url:
        separator = '&' if '?' in raw_db_url else '?'
        raw_db_url = f"{raw_db_url}{separator}sslmode=require"

    app.config['SQLALCHEMY_DATABASE_URI'] = raw_db_url
    app.config['DB_TYPE'] = 'Neon PostgreSQL'
else:
    # Fallback to local SQLite for seamless offline/local development
    db_path = os.path.join(BASE_DIR, 'canteen.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"
    app.config['DB_TYPE'] = 'Local SQLite'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,   # Automatically test connections; reconnects smoothly if Neon auto-suspends
    'pool_recycle': 300,      # Recycle connections every 5 minutes
}

db = SQLAlchemy(app)

# ---------------------------------------------------------------------------
# DATABASE MODELS
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'admin' or 'user'
    wallet_balance = db.Column(db.Float, nullable=False, default=0.0)
    phone = db.Column(db.String(50), nullable=True, default='')
    created_at = db.Column(db.String(50), nullable=False, default=lambda: datetime.utcnow().isoformat())

    orders = db.relationship('Order', backref='user', lazy=True, cascade='all, delete-orphan')
    reservations = db.relationship('Reservation', backref='user', lazy=True, cascade='all, delete-orphan')


class MenuItem(db.Model):
    __tablename__ = 'menu_item'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), default='General')
    available = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(255), default='')
    prep_time = db.Column(db.String(30), default='15 mins')


class Reservation(db.Model):
    __tablename__ = 'reservation'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_phone = db.Column(db.String(50), nullable=False)
    customer_email = db.Column(db.String(120), nullable=False)
    reservation_date = db.Column(db.String(30), nullable=False)  # YYYY-MM-DD
    reservation_time = db.Column(db.String(30), nullable=False)  # e.g. 12:30 PM
    party_size = db.Column(db.Integer, nullable=False, default=2)
    table_preference = db.Column(db.String(60), default='Main Dining Hall')
    special_notes = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='pending')  # pending, confirmed, seated, completed, cancelled
    created_at = db.Column(db.String(50), default=lambda: datetime.utcnow().isoformat())

    orders = db.relationship('Order', backref='reservation', lazy=True)


class Order(db.Model):
    __tablename__ = 'order'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reservation_id = db.Column(db.Integer, db.ForeignKey('reservation.id'), nullable=True)
    order_type = db.Column(db.String(30), default='pickup')  # pickup, dine_in
    total = db.Column(db.Float, nullable=False, default=0.0)
    payment_method = db.Column(db.String(30), default='wallet')  # wallet, gcash, maya, cash
    payment_status = db.Column(db.String(30), default='paid')    # paid, pending, refunded
    status = db.Column(db.String(30), default='pending')        # pending, preparing, ready, completed, cancelled
    pickup_time = db.Column(db.String(60), default='ASAP')
    special_instructions = db.Column(db.Text, default='')
    created_at = db.Column(db.String(50), default=lambda: datetime.utcnow().isoformat())

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')


class OrderItem(db.Model):
    __tablename__ = 'order_item'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=True)
    item_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Float, nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)


# ---------------------------------------------------------------------------
# DATABASE INITIALIZATION, SEEDING & MIGRATION
# ---------------------------------------------------------------------------

def ensure_sqlite_columns():
    """Ensure any new columns exist in local SQLite if migrating from previous schema."""
    if not str(db.engine.url).startswith('sqlite'):
        return

    with db.engine.connect() as conn:
        # Check user table
        try:
            user_cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(user)")).fetchall()]
            if 'phone' not in user_cols:
                conn.execute(db.text("ALTER TABLE user ADD COLUMN phone TEXT DEFAULT ''"))
                conn.commit()
        except Exception:
            pass

        # Check order table
        try:
            order_cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(\"order\")")).fetchall()]
            if 'reservation_id' not in order_cols:
                conn.execute(db.text("ALTER TABLE \"order\" ADD COLUMN reservation_id INTEGER"))
            if 'order_type' not in order_cols:
                conn.execute(db.text("ALTER TABLE \"order\" ADD COLUMN order_type TEXT DEFAULT 'pickup'"))
            if 'payment_method' not in order_cols:
                conn.execute(db.text("ALTER TABLE \"order\" ADD COLUMN payment_method TEXT DEFAULT 'wallet'"))
            if 'payment_status' not in order_cols:
                conn.execute(db.text("ALTER TABLE \"order\" ADD COLUMN payment_status TEXT DEFAULT 'paid'"))
            if 'special_instructions' not in order_cols:
                conn.execute(db.text("ALTER TABLE \"order\" ADD COLUMN special_instructions TEXT DEFAULT ''"))
            conn.commit()
        except Exception:
            pass

        # Check menu_item table
        try:
            menu_cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(menu_item)")).fetchall()]
            if 'image_url' not in menu_cols:
                conn.execute(db.text("ALTER TABLE menu_item ADD COLUMN image_url TEXT DEFAULT ''"))
            if 'prep_time' not in menu_cols:
                conn.execute(db.text("ALTER TABLE menu_item ADD COLUMN prep_time TEXT DEFAULT '15 mins'"))
            conn.commit()
        except Exception:
            pass


def init_db():
    """Creates tables and seeds default demo data for Neon / SQLite."""
    db.create_all()
    ensure_sqlite_columns()

    # Seed Admin account
    admin = User.query.filter_by(email='admin@canteen.com').first()
    if not admin:
        admin = User(
            name='Canteen Admin',
            email='admin@canteen.com',
            password_hash=generate_password_hash('admin123'),
            role='admin',
            wallet_balance=0.0,
            phone='0917-111-2222',
            created_at=datetime.utcnow().isoformat()
        )
        db.session.add(admin)

    # Seed Demo Student account
    student = User.query.filter_by(email='student@canteen.com').first()
    if not student:
        student = User(
            name='Demo Student',
            email='student@canteen.com',
            password_hash=generate_password_hash('student123'),
            role='user',
            wallet_balance=500.0,
            phone='0928-333-4444',
            created_at=datetime.utcnow().isoformat()
        )
        db.session.add(student)

    # Seed Menu Items if empty
    if MenuItem.query.count() == 0:
        sample_items = [
            # Meals
            ('Chicken Adobo Rice Bowl', 'Savory tender chicken braised in garlic, soy sauce, vinegar, with hot steamed rice.', 65.0, 'Meals', '🍗', '15 mins'),
            ('Sizzling Pork Sisig with Rice', 'Crispy, seasoned minced pork with onions, calamansi, egg, and steamed rice.', 75.0, 'Meals', '🍳', '15 mins'),
            ('Beef Caldereta Rice Bowl', 'Hearty beef stew in rich tomato gravy with bell peppers and potatoes.', 85.0, 'Meals', '🍲', '20 mins'),
            ('Crispy Lechon Kawali', 'Golden deep-fried pork belly with signature spiced liver dipping sauce and rice.', 90.0, 'Meals', '🥓', '15 mins'),
            ('Sinigang na Baboy Soup', 'Pork ribs in sour tamarind broth with kangkong, radish, and tomato.', 80.0, 'Meals', '🥣', '20 mins'),

            # Snacks
            ('Crispy Veggie Lumpia (5pcs)', 'Golden-fried vegetable spring rolls served with homemade sweet chili dip.', 40.0, 'Snacks', '🥟', '10 mins'),
            ('Filipino Sweet Spaghetti', 'Classic sweet tomato sauce with savory hotdog slices and grated melted cheese.', 45.0, 'Snacks', '🍝', '10 mins'),
            ('Cheesy Burger with Fries', 'Juicy beef patty with melted cheddar, lettuce, and crispy golden potato fries.', 60.0, 'Snacks', '🍔', '12 mins'),
            ('Clubhouse Sandwich', 'Triple-decker sandwich with ham, egg, cheese, and crunchy vegetable slaw.', 50.0, 'Snacks', '🥪', '10 mins'),

            # Drinks
            ('Signature House Iced Tea (16oz)', 'Refreshing freshly brewed black tea with calamansi and honey.', 20.0, 'Drinks', '🍹', '5 mins'),
            ('Fresh Calamansi Juice (16oz)', 'Natural vitamin C packed citrus cooler served chilled.', 25.0, 'Drinks', '🍋', '5 mins'),
            ('Iced Caramel Macchiato', 'Cold espresso layered with fresh milk and sweet caramel drizzle.', 45.0, 'Drinks', '☕', '5 mins'),
            ('Bottled Spring Water (500ml)', 'Purified and chilled drinking water.', 15.0, 'Drinks', '💧', '2 mins'),

            # Desserts
            ('Special Halo-Halo Supreme', 'Shaved ice with ube halaya, leche flan, nata de coco, pinipig, and evaporated milk.', 55.0, 'Desserts', '🍨', '8 mins'),
            ('Creamy Leche Flan Slice', 'Silky smooth baked caramel custard dessert slice.', 35.0, 'Desserts', '🍮', '5 mins'),
            ('Crispy Banana Turon (3pcs)', 'Sweet banana and jackfruit wrapped and glazed in melted brown sugar.', 25.0, 'Desserts', '🍌', '5 mins'),
        ]

        for name, desc, price, cat, icon, prep in sample_items:
            db.session.add(MenuItem(
                name=name,
                description=desc,
                price=price,
                category=cat,
                available=True,
                image_url=icon,
                prep_time=prep
            ))

    db.session.commit()


# ---------------------------------------------------------------------------
# AUTHENTICATION & ACCESS DECORATORS
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Administrator access required.', 'danger')
            return redirect(url_for('menu'))
        return f(*args, **kwargs)
    return wrapper


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return User.query.get(uid)


def get_cart():
    return session.get('cart', {})  # {menu_item_id(str): qty(int)}


def save_cart(cart):
    session['cart'] = cart
    session.modified = True


@app.context_processor
def inject_globals():
    cart = get_cart()
    cart_count = sum(cart.values()) if cart else 0
    return dict(
        current_user=current_user(),
        cart_count=cart_count,
        db_type=app.config.get('DB_TYPE', 'Database'),
        now_year=datetime.utcnow().year,
    )


# ---------------------------------------------------------------------------
# CORE & AUTH ROUTES
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard') if session.get('role') == 'admin' else url_for('menu'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        phone = request.form.get('phone', '').strip()

        if not name or not email or not password:
            flash('Name, email, and password are required.', 'danger')
            return redirect(url_for('register'))

        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('An account with that email already exists.', 'danger')
            return redirect(url_for('register'))

        new_user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role='user',
            wallet_balance=100.0,  # Bonus ₱100 welcome balance
            phone=phone,
            created_at=datetime.utcnow().isoformat()
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Account created with ₱100 welcome balance! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['name'] = user.name
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('admin_dashboard') if user.role == 'admin' else url_for('menu'))

        flash('Invalid email or password. Please try again.', 'danger')
        return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# CUSTOMER: ONLINE ORDERING & MENU ROUTES
# ---------------------------------------------------------------------------

@app.route('/menu')
@login_required
def menu():
    category_filter = request.args.get('category', '').strip()
    search_query = request.args.get('q', '').strip()

    query = MenuItem.query.filter_by(available=True)

    if category_filter and category_filter != 'All':
        query = query.filter_by(category=category_filter)

    if search_query:
        query = query.filter(MenuItem.name.ilike(f'%{search_query}%'))

    items = query.order_by(MenuItem.category, MenuItem.name).all()

    # Get all distinct categories
    all_categories = [c[0] for c in db.session.query(MenuItem.category).distinct().order_by(MenuItem.category).all()]

    return render_template(
        'menu.html',
        items=items,
        categories=all_categories,
        active_category=category_filter or 'All',
        search_query=search_query
    )


@app.route('/cart/add/<int:item_id>', methods=['POST'])
@login_required
def add_to_cart(item_id):
    item = MenuItem.query.get(item_id)
    if not item or not item.available:
        flash('That item is currently unavailable.', 'warning')
        return redirect(url_for('menu'))

    qty = int(request.form.get('qty', 1))
    cart = get_cart()
    key = str(item_id)
    cart[key] = cart.get(key, 0) + max(1, qty)
    save_cart(cart)
    flash(f'Added {qty}× "{item.name}" to your cart.', 'success')
    return redirect(request.referrer or url_for('menu'))


@app.route('/cart')
@login_required
def cart():
    user = current_user()
    cart_data = get_cart()
    line_items = []
    total = 0.0

    for item_id_str, qty in list(cart_data.items()):
        item = MenuItem.query.get(int(item_id_str))
        if not item or not item.available:
            continue
        subtotal = item.price * qty
        total += subtotal
        line_items.append({'item': item, 'qty': qty, 'subtotal': subtotal})

    # Get user's active/confirmed reservations to allow linking dine-in pre-orders
    active_reservations = Reservation.query.filter(
        Reservation.user_id == user.id,
        Reservation.status.in_(['pending', 'confirmed'])
    ).order_by(Reservation.reservation_date.desc(), Reservation.reservation_time.desc()).all()

    return render_template(
        'cart.html',
        line_items=line_items,
        total=total,
        active_reservations=active_reservations
    )


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    try:
        qty = int(request.form.get('qty', 1))
    except ValueError:
        qty = 1

    cart = get_cart()
    key = str(item_id)
    if qty <= 0:
        cart.pop(key, None)
    else:
        cart[key] = qty
    save_cart(cart)
    return redirect(url_for('cart'))


@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_from_cart(item_id):
    cart = get_cart()
    cart.pop(str(item_id), None)
    save_cart(cart)
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))


@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    user = current_user()
    cart_data = get_cart()

    if not cart_data:
        flash('Your cart is empty. Please choose some delicious items from our menu.', 'warning')
        return redirect(url_for('menu'))

    order_type = request.form.get('order_type', 'pickup')  # pickup or dine_in
    pickup_time = request.form.get('pickup_time', 'ASAP').strip() or 'ASAP'
    payment_method = request.form.get('payment_method', 'wallet')  # wallet, gcash, maya, cash
    special_instructions = request.form.get('special_instructions', '').strip()
    reservation_id_raw = request.form.get('reservation_id')

    reservation_id = int(reservation_id_raw) if reservation_id_raw and reservation_id_raw.isdigit() else None

    # Calculate order total
    total = 0.0
    order_items_to_create = []

    for item_id_str, qty in cart_data.items():
        item = MenuItem.query.get(int(item_id_str))
        if not item or not item.available:
            continue
        subtotal = item.price * qty
        total += subtotal
        order_items_to_create.append((item.id, item.name, item.price, qty))

    if not order_items_to_create:
        flash('Selected items are no longer available.', 'danger')
        save_cart({})
        return redirect(url_for('menu'))

    # Payment processing
    payment_status = 'paid'
    if payment_method == 'wallet':
        if user.wallet_balance < total:
            shortage = total - user.wallet_balance
            flash(f'Insufficient wallet balance! Total is ₱{total:.2f}, you have ₱{user.wallet_balance:.2f}. Need ₱{shortage:.2f} more. Please top up or pick another payment method.', 'danger')
            return redirect(url_for('wallet'))
        user.wallet_balance -= total
    elif payment_method in ('gcash', 'maya'):
        # Simulated e-wallet instant payment
        payment_status = 'paid'
    elif payment_method == 'cash':
        payment_status = 'pending'

    # Create Order
    new_order = Order(
        user_id=user.id,
        reservation_id=reservation_id,
        order_type=order_type,
        total=total,
        payment_method=payment_method,
        payment_status=payment_status,
        status='pending',
        pickup_time=pickup_time,
        special_instructions=special_instructions,
        created_at=datetime.utcnow().isoformat()
    )
    db.session.add(new_order)
    db.session.flush()  # Populates new_order.id

    for m_id, name, price, qty in order_items_to_create:
        db.session.add(OrderItem(
            order_id=new_order.id,
            menu_item_id=m_id,
            item_name=name,
            price=price,
            qty=qty
        ))

    db.session.commit()
    save_cart({})

    pay_label = {
        'wallet': f'₱{total:.2f} deducted from in-app wallet',
        'gcash': f'₱{total:.2f} paid via GCash',
        'maya': f'₱{total:.2f} paid via Maya',
        'cash': f'₱{total:.2f} to pay upon pickup/seating'
    }.get(payment_method, f'₱{total:.2f}')

    flash(f'🎉 Order #{new_order.id} placed successfully! ({pay_label})', 'success')
    return redirect(url_for('orders'))


@app.route('/orders')
@login_required
def orders():
    user = current_user()
    user_orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=user_orders)


@app.route('/orders/cancel/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    user = current_user()
    order = Order.query.filter_by(id=order_id, user_id=user.id).first()

    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('orders'))

    if order.status != 'pending':
        flash('Only pending orders can be cancelled. Your food is already being prepared!', 'warning')
        return redirect(url_for('orders'))

    # Refund wallet if paid via wallet
    if order.payment_method == 'wallet' and order.payment_status == 'paid':
        user.wallet_balance += order.total
        order.payment_status = 'refunded'
        flash(f'Order #{order.id} cancelled. ₱{order.total:.2f} has been refunded to your wallet.', 'success')
    else:
        flash(f'Order #{order.id} has been cancelled.', 'info')

    order.status = 'cancelled'
    db.session.commit()
    return redirect(url_for('orders'))


# ---------------------------------------------------------------------------
# CUSTOMER: TABLE RESERVATION ROUTES
# ---------------------------------------------------------------------------

@app.route('/reservations', methods=['GET', 'POST'])
@login_required
def reservations():
    user = current_user()

    if request.method == 'POST':
        customer_name = request.form.get('customer_name', '').strip() or user.name
        customer_phone = request.form.get('customer_phone', '').strip() or user.phone or 'N/A'
        customer_email = request.form.get('customer_email', '').strip() or user.email
        reservation_date = request.form.get('reservation_date', '').strip()
        reservation_time = request.form.get('reservation_time', '').strip()
        party_size = int(request.form.get('party_size', 2))
        table_preference = request.form.get('table_preference', 'Main Dining Hall')
        special_notes = request.form.get('special_notes', '').strip()
        preorder_food = request.form.get('preorder_food') == 'yes'

        if not reservation_date or not reservation_time:
            flash('Please select both a reservation date and time.', 'danger')
            return redirect(url_for('reservations'))

        new_res = Reservation(
            user_id=user.id,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_email=customer_email,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            party_size=party_size,
            table_preference=table_preference,
            special_notes=special_notes,
            status='pending',
            created_at=datetime.utcnow().isoformat()
        )
        db.session.add(new_res)
        db.session.commit()

        if preorder_food:
            flash(f'Reservation #{new_res.id} requested for {reservation_date} at {reservation_time}! Now choose dishes to pre-order.', 'success')
            return redirect(url_for('menu'))

        flash(f'Reservation #{new_res.id} successfully placed! We look forward to hosting you on {reservation_date} at {reservation_time}.', 'success')
        return redirect(url_for('reservations'))

    user_reservations = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.created_at.desc()).all()
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    return render_template('reservations.html', reservations=user_reservations, today_str=today_str)


@app.route('/reservations/cancel/<int:reservation_id>', methods=['POST'])
@login_required
def cancel_reservation(reservation_id):
    user = current_user()
    reservation = Reservation.query.filter_by(id=reservation_id, user_id=user.id).first()

    if not reservation:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('reservations'))

    if reservation.status in ('completed', 'cancelled'):
        flash('This reservation cannot be cancelled.', 'warning')
        return redirect(url_for('reservations'))

    reservation.status = 'cancelled'
    db.session.commit()
    flash(f'Reservation #{reservation.id} has been cancelled.', 'info')
    return redirect(url_for('reservations'))


# ---------------------------------------------------------------------------
# CUSTOMER: CASHLESS WALLET ROUTES
# ---------------------------------------------------------------------------

@app.route('/wallet', methods=['GET', 'POST'])
@login_required
def wallet():
    user = current_user()

    if request.method == 'POST':
        try:
            amount = float(request.form.get('amount', 0))
        except ValueError:
            amount = 0.0

        payment_provider = request.form.get('provider', 'GCash')

        if amount <= 0:
            flash('Please enter a valid top-up amount greater than ₱0.', 'danger')
        else:
            user.wallet_balance += amount
            db.session.commit()
            flash(f'✅ Successfully loaded ₱{amount:.2f} into your wallet via {payment_provider}!', 'success')
        return redirect(url_for('wallet'))

    return render_template('wallet.html')


# ---------------------------------------------------------------------------
# ADMIN ROUTES: DASHBOARD, ORDERS, RESERVATIONS, MENU, USERS
# ---------------------------------------------------------------------------

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.filter_by(role='user').count()
    total_items = MenuItem.query.count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter(Order.status.in_(['pending', 'preparing'])).count()
    total_reservations = Reservation.query.count()
    pending_reservations = Reservation.query.filter(Reservation.status.in_(['pending', 'confirmed'])).count()

    # Revenue from completed / active orders
    revenue_res = db.session.query(db.func.coalesce(db.func.sum(Order.total), 0.0))\
        .filter(Order.status != 'cancelled').scalar()
    revenue = float(revenue_res or 0.0)

    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    upcoming_reservations = Reservation.query.order_by(Reservation.reservation_date.desc(), Reservation.reservation_time.desc()).limit(6).all()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_items=total_items,
        total_orders=total_orders,
        pending_orders=pending_orders,
        total_reservations=total_reservations,
        pending_reservations=pending_reservations,
        revenue=revenue,
        recent_orders=recent_orders,
        upcoming_reservations=upcoming_reservations
    )


@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    status_filter = request.args.get('status', 'all')
    type_filter = request.args.get('type', 'all')

    query = Order.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if type_filter != 'all':
        query = query.filter_by(order_type=type_filter)

    all_orders = query.order_by(Order.created_at.desc()).all()

    return render_template(
        'admin_orders.html',
        orders=all_orders,
        active_status=status_filter,
        active_type=type_filter
    )


@app.route('/admin/orders/status/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def admin_order_status(order_id):
    order = Order.query.get(order_id)
    new_status = request.form.get('status')

    valid_statuses = ('pending', 'preparing', 'ready', 'completed', 'cancelled')
    if order and new_status in valid_statuses:
        # If cancelled, auto-refund wallet if wallet payment was used
        if new_status == 'cancelled' and order.status != 'cancelled':
            if order.payment_method == 'wallet' and order.payment_status == 'paid':
                order.user.wallet_balance += order.total
                order.payment_status = 'refunded'
                flash(f'Order #{order.id} cancelled. ₱{order.total:.2f} refunded to {order.user.name}.', 'info')

        order.status = new_status
        db.session.commit()
        flash(f'Order #{order_id} marked as {new_status.upper()}.', 'success')

    return redirect(request.referrer or url_for('admin_orders'))


@app.route('/admin/reservations')
@login_required
@admin_required
def admin_reservations():
    status_filter = request.args.get('status', 'all')
    date_filter = request.args.get('date', '').strip()

    query = Reservation.query

    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if date_filter:
        query = query.filter_by(reservation_date=date_filter)

    reservations_list = query.order_by(Reservation.reservation_date.desc(), Reservation.reservation_time.desc()).all()

    return render_template(
        'admin_reservations.html',
        reservations=reservations_list,
        active_status=status_filter,
        active_date=date_filter
    )


@app.route('/admin/reservations/status/<int:reservation_id>', methods=['POST'])
@login_required
@admin_required
def admin_reservation_status(reservation_id):
    res = Reservation.query.get(reservation_id)
    new_status = request.form.get('status')

    valid_statuses = ('pending', 'confirmed', 'seated', 'completed', 'cancelled')
    if res and new_status in valid_statuses:
        res.status = new_status
        db.session.commit()
        flash(f'Reservation #{res.id} ({res.customer_name}) marked as {new_status.upper()}.', 'success')

    return redirect(request.referrer or url_for('admin_reservations'))


@app.route('/admin/menu')
@login_required
@admin_required
def admin_menu():
    items = MenuItem.query.order_by(MenuItem.category, MenuItem.name).all()
    categories = [c[0] for c in db.session.query(MenuItem.category).distinct().all()]
    return render_template('admin_menu.html', items=items, categories=categories)


@app.route('/admin/menu/add', methods=['POST'])
@login_required
@admin_required
def admin_menu_add():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    category = request.form.get('category', 'General').strip() or 'General'
    image_url = request.form.get('image_url', '').strip()
    prep_time = request.form.get('prep_time', '15 mins').strip() or '15 mins'

    try:
        price = float(request.form.get('price', 0))
    except ValueError:
        price = 0.0

    if not name or price <= 0:
        flash('Item name and a valid price (> 0) are required.', 'danger')
        return redirect(url_for('admin_menu'))

    new_item = MenuItem(
        name=name,
        description=description,
        price=price,
        category=category,
        available=True,
        image_url=image_url or '🍽️',
        prep_time=prep_time
    )
    db.session.add(new_item)
    db.session.commit()
    flash(f'Successfully added "{name}" to the menu.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/toggle/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_menu_toggle(item_id):
    item = MenuItem.query.get(item_id)
    if item:
        item.available = not item.available
        db.session.commit()
        status_text = 'Available' if item.available else 'Hidden'
        flash(f'"{item.name}" is now marked as {status_text}.', 'info')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/delete/<int:item_id>', methods=['POST'])
@login_required
@admin_required
def admin_menu_delete(item_id):
    item = MenuItem.query.get(item_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash(f'Deleted "{item.name}" from the menu.', 'info')
    return redirect(url_for('admin_menu'))


@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.filter_by(role='user').order_by(User.name).all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/topup/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_user_topup(user_id):
    user = User.query.get(user_id)
    try:
        amount = float(request.form.get('amount', 0))
    except ValueError:
        amount = 0.0

    if user and amount > 0:
        user.wallet_balance += amount
        db.session.commit()
        flash(f'Added ₱{amount:.2f} credit to {user.name}\'s wallet.', 'success')
    else:
        flash('Invalid top-up amount.', 'danger')

    return redirect(url_for('admin_users'))


# ---------------------------------------------------------------------------
# APPLICATION ENTRYPOINT & DATABASE AUTO-INITIALIZE
# ---------------------------------------------------------------------------

with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"Warning during DB init: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
