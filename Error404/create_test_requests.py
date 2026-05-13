import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Error404.settings')
import django
django.setup()

from sales.models import DrinkRequest, Order, Product

# Get test data
orders = Order.objects.all()
products = Product.objects.filter(name='Latte')

if orders.exists() and products.exists():
    order = orders.first()
    product = products.first()
    
    # Create fresh RESOLVED requests for testing
    test_requests = [
        {'reason': 'Wrong size', 'note': 'Customer ordered Medium but got Large'},
        {'reason': 'Wrong drink', 'note': 'Wrong espresso shot count'},
        {'reason': 'Cold drink', 'note': 'Arrived cold'},
    ]
    
    for i, req_data in enumerate(test_requests):
        dr = DrinkRequest.objects.create(
            order=order,
            product=product,
            size='Medium',
            quantity=1,
            reason=req_data['reason'],
            note=req_data['note'],
            status='RESOLVED',
            requested_by=order.customer.user if order.customer else None
        )
        print(f"✓ Created DrinkRequest ID: {dr.id}, Status: {dr.status}, Reason: {dr.reason}")
    
    print(f"\nTotal RESOLVED requests: {DrinkRequest.objects.filter(status='RESOLVED').count()}")
else:
    print("No orders or Latte products found.")
