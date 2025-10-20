from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from models import (
    Book, Cart, User, Order, PaymentGateway, EmailService,
    is_valid_email, sanitize_text  # new helpers
)
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # In production, load from env

# Global storage for users and orders (demo only; use DB in prod)
# Store users by LOWERCASED email to prevent duplicate-case issues
users = {}   # email(lower) -> User
orders = {}  # order_id -> Order

# Demo user
demo_user = User("demo@bookstore.com", "demo123", "Demo User", "123 Demo Street, Demo City, DC 12345")
users[demo_user.email.lower()] = demo_user

# Single Cart instance (demo)
cart = Cart()

# Catalog
BOOKS = [
    Book("The Great Gatsby", "Fiction", 10.99, "/images/books/the_great_gatsby.jpg"),
    Book("1984", "Dystopia", 8.99, "/images/books/1984.jpg"),
    Book("I Ching", "Traditional", 18.99, "/images/books/I-Ching.jpg"),
    Book("Moby Dick", "Adventure", 12.49, "/images/books/moby_dick.jpg"),
]

def get_book_by_title(title: str):
    title = (title or "").strip()
    return next((b for b in BOOKS if b.title == title), None)

def get_current_user():
    if 'user_email' in session:
        return users.get(session['user_email'].lower())
    return None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_email' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

@app.route('/')
def index():
    return render_template('index.html', books=BOOKS, cart=cart, current_user=get_current_user())

@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    title = sanitize_text(request.form.get('title'))
    raw_qty = request.form.get('quantity', '1')

    # Robust quantity parsing & validation
    try:
        quantity = int(raw_qty)
    except ValueError:
        quantity = 1
    if quantity < 1:
        flash('Quantity must be at least 1.', 'error')
        return redirect(url_for('index'))
    if quantity > 999:
        quantity = 999  # simple upper bound to avoid abuse

    book = get_book_by_title(title)
    if not book:
        flash('Book not found!', 'error')
        return redirect(url_for('index'))

    cart.add_book(book, quantity)
    flash(f'Added {quantity} "{book.title}" to cart!', 'success')
    return redirect(url_for('index'))

@app.route('/remove-from-cart', methods=['POST'])
def remove_from_cart():
    title = sanitize_text(request.form.get('title'))
    cart.remove_book(title)
    flash(f'Removed "{title}" from cart!', 'success')
    return redirect(url_for('view_cart'))

@app.route('/update-cart', methods=['POST'])
def update_cart():
    title = sanitize_text(request.form.get('title'))
    raw_qty = request.form.get('quantity', '1')

    try:
        quantity = int(raw_qty)
    except ValueError:
        quantity = 1

    # If the quantity is <= 0, remove the item (fixes “zero not removed” bug)
    cart.update_quantity(title, quantity)
    if quantity <= 0:
        flash(f'Removed "{title}" from cart!', 'success')
    else:
        flash(f'Updated "{title}" quantity to {quantity}!', 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    return render_template('cart.html', cart=cart, current_user=get_current_user())

@app.route('/clear-cart', methods=['POST'])
def clear_cart():
    cart.clear()
    flash('Cart cleared!', 'success')
    return redirect(url_for('view_cart'))

@app.route('/checkout')
def checkout():
    if cart.is_empty():
        flash('Your cart is empty!', 'error')
        return redirect(url_for('index'))
    return render_template('checkout.html', cart=cart, total_price=cart.get_total_price(), current_user=get_current_user())

@app.route('/process-checkout', methods=['POST'])
def process_checkout():
    if cart.is_empty():
        flash('Your cart is empty!', 'error')
        return redirect(url_for('index'))

    # Shipping info
    shipping_info = {
        'name': sanitize_text(request.form.get('name')),
        'email': sanitize_text(request.form.get('email')),
        'address': sanitize_text(request.form.get('address')),
        'city': sanitize_text(request.form.get('city')),
        'zip_code': sanitize_text(request.form.get('zip_code')),
    }

    # Required shipping fields + email format
    required = ['name', 'email', 'address', 'city', 'zip_code']
    for f in required:
        if not shipping_info.get(f):
            flash(f'Please fill in the {f.replace("_", " ")} field.', 'error')
            return redirect(url_for('checkout'))
    if not is_valid_email(shipping_info['email']):
        flash('Please enter a valid email address.', 'error')
        return redirect(url_for('checkout'))

    # Payment info
    payment_method = request.form.get('payment_method', '').strip().lower()
    payment_info = {
        'payment_method': payment_method,
        'card_number': sanitize_text(request.form.get('card_number')),
        'expiry_date': sanitize_text(request.form.get('expiry_date')),
        'cvv': sanitize_text(request.form.get('cvv')),
        'paypal_email': sanitize_text(request.form.get('paypal_email')),  # for PayPal validation
    }

    # Discounts: case-insensitive & trimmed (fix case-sensitive bug)
    discount_code = (request.form.get('discount_code', '') or '').strip().upper()
    total_amount = cart.get_total_price()
    discount_applied = 0.0

    DISCOUNTS = {
        'SAVE10': 0.10,
        'WELCOME20': 0.20,
    }
    if discount_code:
        if discount_code in DISCOUNTS:
            rate = DISCOUNTS[discount_code]
            discount_applied = total_amount * rate
            total_amount -= discount_applied
            flash(f'Discount applied! You saved ${discount_applied:.2f}', 'success')
        else:
            # non-blocking error message
            flash('Invalid discount code.', 'error')

    # Validate required payment fields (fix missing PayPal validation)
    if payment_method == 'credit_card':
        if not (payment_info['card_number'] and payment_info['expiry_date'] and payment_info['cvv']):
            flash('Please fill in all credit card details.', 'error')
            return redirect(url_for('checkout'))
    elif payment_method == 'paypal':
        if not payment_info['paypal_email'] or not is_valid_email(payment_info['paypal_email']):
            flash('Please provide a valid PayPal email.', 'error')
            return redirect(url_for('checkout'))
    else:
        flash('Please select a valid payment method.', 'error')
        return redirect(url_for('checkout'))

    # Process payment (mock)
    payment_result = PaymentGateway.process_payment(payment_info)
    if not payment_result['success']:
        flash(payment_result['message'], 'error')
        return redirect(url_for('checkout'))

    # Create order
    order_id = str(uuid.uuid4())[:8].upper()
    order = Order(
        order_id=order_id,
        user_email=shipping_info['email'],
        items=cart.get_items(),
        shipping_info=shipping_info,
        payment_info={'method': payment_method, 'transaction_id': payment_result['transaction_id']},
        total_amount=total_amount
    )
    orders[order_id] = order

    # Attach order to logged-in user
    current_user = get_current_user()
    if current_user:
        current_user.add_order(order)

    # Confirmation email (mock)
    EmailService.send_order_confirmation(shipping_info['email'], order)

    # Clear cart for next purchase
    cart.clear()

    # Show confirmation
    session['last_order_id'] = order_id
    flash('Payment successful! Your order has been confirmed.', 'success')
    return redirect(url_for('order_confirmation', order_id=order_id))

@app.route('/order-confirmation/<order_id>')
def order_confirmation(order_id):
    order = orders.get(order_id)
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('index'))
    return render_template('order_confirmation.html', order=order, current_user=get_current_user())

# -------- User Account Management -------- #

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = sanitize_text(request.form.get('email'))
        password = request.form.get('password') or ''
        name = sanitize_text(request.form.get('name'))
        address = sanitize_text(request.form.get('address', ''))

        if not email or not password or not name:
            flash('Please fill in all required fields.', 'error')
            return render_template('register.html')

        if not is_valid_email(email):
            flash('Please enter a valid email address.', 'error')
            return render_template('register.html')

        key = email.lower()
        if key in users:
            flash('An account with this email already exists.', 'error')
            return render_template('register.html')

        # Create user with hashed password (fix plain-text storage)
        user = User(email, password, name, address)
        users[key] = user

        session['user_email'] = email
        flash('Account created successfully! You are now logged in.', 'success')
        return redirect(url_for('index'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = sanitize_text(request.form.get('email'))
        password = request.form.get('password') or ''
        user = users.get((email or '').lower())

        if user and user.check_password(password):
            session['user_email'] = user.email  # original case preserved on object
            flash('Logged in successfully!', 'success')
            return redirect(url_for('index'))

        flash('Invalid email or password.', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_email', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/account')
@login_required
def account():
    return render_template('account.html', current_user=get_current_user())

@app.route('/update-profile', methods=['POST'])
@login_required
def update_profile():
    current_user = get_current_user()
    current_user.name = sanitize_text(request.form.get('name', current_user.name))
    current_user.address = sanitize_text(request.form.get('address', current_user.address))

    new_password = request.form.get('new_password')
    if new_password:
        current_user.set_password(new_password)
        flash('Password updated successfully!', 'success')
    else:
        flash('Profile updated successfully!', 'success')

    return redirect(url_for('account'))


if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
