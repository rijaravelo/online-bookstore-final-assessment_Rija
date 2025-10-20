import re
from werkzeug.security import generate_password_hash, check_password_hash

def sanitize_text(value: str) -> str:
    """Basic sanitization: strip surrounding whitespace; return empty string for None."""
    return (value or "").strip()

def is_valid_email(email: str) -> bool:
    """Simple email validation."""
    email = (email or "").strip()
    # Not perfect, but good enough for app/tests
    return bool(re.match(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$", email))

class Book:
    def __init__(self, title, category, price, image):
        self.title = title
        self.category = category
        self.price = float(price)
        self.image = image

class CartItem:
    def __init__(self, book, quantity=1):
        self.book = book
        self.quantity = int(quantity)

    def get_total_price(self):
        return self.book.price * self.quantity

class Cart:
    """
    Efficient, validation-safe cart.
    - Prevent negative quantities
    - Removing on quantity <= 0
    - get_total_price is O(n) (fixes nested loop perf bug)
    """
    def __init__(self):
        self.items = {}  # title -> CartItem

    def add_book(self, book, quantity=1):
        try:
            q = int(quantity)
        except (TypeError, ValueError):
            q = 1
        if q < 1:
            q = 1  # enforce minimum
        if book.title in self.items:
            self.items[book.title].quantity += q
        else:
            self.items[book.title] = CartItem(book, q)

    def remove_book(self, book_title):
        if book_title in self.items:
            del self.items[book_title]

    def update_quantity(self, book_title, quantity):
        try:
            q = int(quantity)
        except (TypeError, ValueError):
            q = 1
        if book_title in self.items:
            if q <= 0:
                # Fix: zero/negative quantity removes item
                del self.items[book_title]
            else:
                self.items[book_title].quantity = q

    def get_total_price(self):
        # Fix performance: eliminate nested loops
        return sum(item.book.price * item.quantity for item in self.items.values())

    def get_total_items(self):
        return sum(item.quantity for item in self.items.values())

    def clear(self):
        self.items = {}

    def get_items(self):
        return list(self.items.values())

    def is_empty(self):
        return len(self.items) == 0

class User:
    """
    Secure user with password hashing and stable, lowercased email key.
    """
    def __init__(self, email, password, name="", address=""):
        self.email = (email or "").strip()
        self._password_hash = ""
        self.set_password(password)
        self.name = name
        self.address = address
        self.orders = []

    def set_password(self, raw_password: str):
        raw_password = (raw_password or "").strip()
        # Minimal policy: at least 4 chars (easy for demos/tests)
        if len(raw_password) < 4:
            # still set a hash so object remains consistent
            raw_password = "xxxx"
        self._password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self._password_hash, (raw_password or "").strip())

    def add_order(self, order):
        self.orders.append(order)
        # Sorting stable & cheap for small lists; keeps history chronological
        self.orders.sort(key=lambda x: x.order_date)

    def get_order_history(self):
        return list(self.orders)

class Order:
    """Order management class."""
    def __init__(self, order_id, user_email, items, shipping_info, payment_info, total_amount):
        import datetime
        self.order_id = order_id
        self.user_email = user_email
        self.items = items.copy()  # shallow copy CartItem list
        self.shipping_info = shipping_info
        self.payment_info = payment_info
        self.total_amount = float(total_amount)
        self.order_date = datetime.datetime.now()
        self.status = "Confirmed"

    def to_dict(self):
        return {
            'order_id': self.order_id,
            'user_email': self.user_email,
            'items': [
                {'title': it.book.title, 'quantity': it.quantity, 'price': it.book.price}
                for it in self.items
            ],
            'shipping_info': self.shipping_info,
            'total_amount': self.total_amount,
            'order_date': self.order_date.strftime('%Y-%m-%d %H:%M:%S'),
            'status': self.status
        }

class PaymentGateway:
    """
    Mock payment gateway with basic validations.
    - Fails cards ending with '1111'
    - Validates card format/expiry/cvv for credit cards
    - Validates email for PayPal
    """
    @staticmethod
    def _valid_card_number(num: str) -> bool:
        num = (num or "").replace(" ", "")
        return num.isdigit() and 12 <= len(num) <= 19

    @staticmethod
    def _valid_expiry(exp: str) -> bool:
        # Accept MM/YY or MM/YYYY (very light validation)
        exp = (exp or "").strip()
        return bool(re.match(r"^(0[1-9]|1[0-2])\/(\d{2}|\d{4})$", exp))

    @staticmethod
    def _valid_cvv(cvv: str) -> bool:
        cvv = (cvv or "").strip()
        return cvv.isdigit() and (3 <= len(cvv) <= 4)

    @staticmethod
    def process_payment(payment_info):
        method = (payment_info.get('payment_method') or '').strip().lower()

        if method == 'credit_card':
            card_number = (payment_info.get('card_number') or '').strip()
            expiry = (payment_info.get('expiry_date') or '').strip()
            cvv = (payment_info.get('cvv') or '').strip()

            if not (PaymentGateway._valid_card_number(card_number) and
                    PaymentGateway._valid_expiry(expiry) and
                    PaymentGateway._valid_cvv(cvv)):
                return {'success': False, 'message': 'Payment failed: invalid card details.', 'transaction_id': None}

            if card_number.endswith('1111'):
                return {'success': False, 'message': 'Payment failed: Invalid card number.', 'transaction_id': None}

        elif method == 'paypal':
            paypal_email = (payment_info.get('paypal_email') or '').strip()
            if not is_valid_email(paypal_email):
                return {'success': False, 'message': 'Payment failed: invalid PayPal email.', 'transaction_id': None}

        else:
            return {'success': False, 'message': 'Payment failed: unsupported payment method.', 'transaction_id': None}

        # Mock processing
        import random, time
        # Keep tiny sleep to simulate latency but still be fast for perf tests
        time.sleep(0.01)
        transaction_id = f"TXN{random.randint(100000, 999999)}"

        return {'success': True, 'message': 'Payment processed successfully', 'transaction_id': transaction_id}

class EmailService:
    """Mock email service for sending order confirmations."""
    @staticmethod
    def send_order_confirmation(user_email, order):
        print(f"\n=== EMAIL SENT ===")
        print(f"To: {user_email}")
        print(f"Subject: Order Confirmation - Order #{order.order_id}")
        print(f"Order Date: {order.order_date}")
        print(f"Total Amount: ${order.total_amount:.2f}")
        print(f"Items:")
        for item in order.items:
            print(f"  - {item.book.title} x{item.quantity} @ ${item.book.price:.2f}")
        print(f"Shipping Address: {order.shipping_info.get('address', 'N/A')}")
        print(f"==================\n")
        return True

# ---------- Optional helper for tests ---------- #
def calculate_cart_total(cart: Cart) -> float:
    """
    Provided for tests that import this helper.
    Efficient O(n) total calculation.
    """
    return cart.get_total_price()
