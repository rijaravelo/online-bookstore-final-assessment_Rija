"""cProfile analysis for checkout workflow"""
import cProfile
import pstats
from io import StringIO

def profile_cart_operations():
    """Profile cart total price calculation"""
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Perform operations
    cart = Cart()
    book = Book("Test", "Fiction", 10.99, "/test.jpg")
    for _ in range(100):
        cart.add_book(book, 500)
        cart.get_total_price()
    
    profiler.disable()
    
    # Print results
    s = StringIO()
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    ps.print_stats(20)
    print(s.getvalue())

if __name__ == '__main__':
    profile_cart_operations()