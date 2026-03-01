import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Order, OrderItem, Product, Ingredient, Recipe, StockHistory, Customer
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Count
from django.db import transaction
from django.db.models.functions import ExtractHour
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.decorators import login_required
from decimal import Decimal
from django.contrib import messages
from django.utils import timezone
from datetime import timedelta
from django.views.decorators.csrf import csrf_exempt

#############################
####### Admin View ##########
#############################

def is_admin(user):
    return user.groups.filter(name='Admin').exists() or user.is_superuser

def admin_dashboard(request):
    # 1. Sales Analytics
    # Only counting revenue from completed orders
    total_revenue = Order.objects.filter(is_completed=True).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    order_count = Order.objects.count()
    popular_items = OrderItem.objects.values('product__name')\
        .annotate(total_qty=Sum('quantity'))\
        .order_by('-total_qty')[:5]
    
    # 2. Hourly Sales (For the Chart.js graph)
    sales_by_hour = Order.objects.filter(is_completed=True)\
        .annotate(hour=ExtractHour('created_at'))\
        .values('hour')\
        .annotate(total=Sum('total_amount'))\
        .order_by('hour')
    
    labels = [f"{item['hour']}:00" for item in sales_by_hour]
    sales_data = [float(item['total']) for item in sales_by_hour]

    # 3. Capacity Logic (Bottleneck analysis)
    beans = Ingredient.objects.filter(name__icontains="Beans").first()
    milk = Ingredient.objects.filter(name__icontains="Milk").first()
    total_capacity = 0
    
    if beans:
        total_capacity = int(beans.stock_quantity / 20) # 20g per cup
        if milk:
            total_capacity = min(total_capacity, int(milk.stock_quantity / 250)) # 250ml per cup

    # 4. Loyalty Leaderboard
    # Fetching top 5 customers by points
    top_customers = Customer.objects.order_by('-points')[:5]

    # 5. Context Assembly
    context = {
        'total_revenue': total_revenue,
        'order_count': order_count,
        'popular_items': popular_items,
        'labels': labels,
        'sales_data': sales_data,
        'all_ingredients': Ingredient.objects.all(),
        'products': Product.objects.all(),
        'top_customers': top_customers, # Added for the leaderboard
        'total_capacity': total_capacity,
        'low_stock_products': [], # Kept empty to avoid FieldErrors
        'low_stock_ingredients': Ingredient.objects.filter(stock_quantity__lt=500),
    }
    return render(request, 'admin_dashboard.html', context)

def add_product(request):
    if request.method == "POST":
        name = request.POST.get('name')
        price = request.POST.get('price')
        image = request.FILES.get('image')
        
        # Catch the checkboxes (True if checked, False if not)
        is_hot = 'type_hot' in request.POST
        is_iced = 'type_iced' in request.POST
        is_frappe = 'type_frappe' in request.POST

        Product.objects.create(
            name=name, 
            base_price=price, 
            image=image,
            can_be_hot=is_hot,
            can_be_iced=is_iced,
            can_be_frappe=is_frappe
        )
        return redirect('admin_dashboard')

######## inventory page ########

def inventory_list(request):
    ingredients = Ingredient.objects.all().order_by('name')
    # Get the last 10 stock updates to show on the page
    recent_history = StockHistory.objects.all()[:10]
    
    if request.method == "POST":
        ing_id = request.POST.get('ingredient_id')
        add_amount = request.POST.get('amount')
        
        if ing_id and add_amount:
            ingredient = get_object_or_404(Ingredient, id=ing_id)
            amount_decimal = Decimal(add_amount)
            
            # 1. Update the stock
            ingredient.stock_quantity += amount_decimal
            ingredient.save()
            
            # 2. Record the history entry
            StockHistory.objects.create(
                ingredient=ingredient,
                amount_added=amount_decimal
            )
            
        return redirect('inventory_list')

    return render(request, 'inventory.html', {
        'ingredients': ingredients,
        'recent_history': recent_history
    })

def add_ingredient(request):
    if request.method == "POST":
        name = request.POST.get('name')
        stock = request.POST.get('stock')
        unit = request.POST.get('unit')
        
        Ingredient.objects.create(
            name=name,
            stock_quantity=stock,
            unit=unit
        )
    return redirect('inventory_list')

def delete_ingredient(request, ing_id):
    ingredient = get_object_or_404(Ingredient, id=ing_id)
    ingredient.delete()
    return redirect('inventory_list')

def check_stock(request, product_id):
    product = Product.objects.get(id=product_id)
    recipes = Recipe.objects.filter(product=product)
    
    for recipe in recipes:
        if recipe.ingredient.stock_quantity < recipe.amount_needed:
            return JsonResponse({
                'available': False, 
                'message': f"Not enough {recipe.ingredient.name}!"
            })
            
    return JsonResponse({'available': True})

#############################
####### Recipe Builder #######
#############################


def recipe_builder(request):
    products = Product.objects.all()
    ingredients = Ingredient.objects.all()
    recipes = Recipe.objects.all().order_by('product__name', 'size')

    if request.method == "POST":
        product_id = request.POST.get('product')
        ingredient_id = request.POST.get('ingredient')
        size = request.POST.get('size') # Capture size
        amount = request.POST.get('amount')

        product = get_object_or_404(Product, id=product_id)
        ingredient = get_object_or_404(Ingredient, id=ingredient_id)

        # Create or update the recipe for that specific size
        Recipe.objects.update_or_create(
            product=product,
            ingredient=ingredient,
            size=size,
            defaults={'amount_needed': amount}
        )
        return redirect('recipe_builder')

    return render(request, 'recipe_builder.html', {
        'products': products,
        'ingredients': ingredients,
        'recipes': recipes
    })

#############################
####### Barista view ########
#############################

def pos_view(request):
    # This fetches EVERY product currently in your database
    products = Product.objects.all() 
    
    # You can also order them by name or category
    # products = Product.objects.all().order_by('category__name', 'name')
    
    context = {
        'products': products
    }
    return render(request, 'pos.html', context)

def customer_lookup(request):
    phone = request.GET.get('phone')
    try:
        # We use .get() because phone numbers are unique
        customer = Customer.objects.get(phone=phone)
        return JsonResponse({
            'status': 'success',
            'id': customer.id,
            'name': customer.name,
            'points': customer.points,
            'discount': float(customer.discount_rate)
        })
    except Customer.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Customer not found'}, status=404)

@csrf_exempt    
def register_customer(request):
    if request.method == "POST":
        import json
        data = json.loads(request.body)
        try:
            new_cust = Customer.objects.create(
                name=data.get('name'),
                phone=data.get('phone'),
                email=data.get('email', '')
            )
            return JsonResponse({
                'status': 'success', 
                'id': new_cust.id, 
                'name': new_cust.name
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

###########################
##### Process Payment #####
###########################

@csrf_exempt
def process_payment(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            cart_items = data.get('items', [])
            total_price = data.get('total')
            customer_id = data.get('customer_id') 

            with transaction.atomic():
                # 1. Create the Main Order (is_completed=True means it's paid)
                new_order = Order.objects.create(
                    total_amount=total_price,
                    is_completed=True 
                )

                # 2. Link Customer & Add Loyalty Points
                if customer_id:
                    try:
                        customer = Customer.objects.get(id=customer_id)
                        new_order.customer = customer
                        new_order.save()
                        
                        # Add 1 point per $1 spent (rounded down)
                        customer.points += int(float(total_price))
                        customer.save()
                    except (Customer.DoesNotExist, ValueError):
                        pass # Continue as guest if ID is invalid

                # 3. Process each item in the cart
                for item in cart_items:
                    product = Product.objects.get(id=item['id'])
                    target_size = item.get('size', 'Medium')
                    # Get the new Drink Type (Hot/Iced/Frappe)
                    target_type = item.get('type', 'Hot')
                    
                    # --- INVENTORY DEDUCTION LOGIC ---
                    recipe_items = Recipe.objects.filter(product=product, size=target_size)
                    
                    # FALLBACK: If specific size recipe doesn't exist, try Medium
                    if not recipe_items.exists() and target_size != 'Medium':
                        recipe_items = Recipe.objects.filter(product=product, size='Medium')
                    
                    # If a recipe exists, subtract ingredients
                    if recipe_items.exists():
                        for recipe in recipe_items:
                            usage = recipe.amount_needed * item['qty']
                            ingredient = recipe.ingredient
                            ingredient.stock_quantity -= usage
                            ingredient.save()
                    else:
                        # Log warning but don't crash the POS (optional)
                        print(f"Warning: No recipe for {product.name}. Inventory not deducted.")

                    # 4. Create the OrderItem record
                    # We store the Size, Sugar, and Type for the Kitchen View
                    OrderItem.objects.create(
                        order=new_order,
                        product=product,
                        quantity=item['qty'],
                        size=target_size,
                        sugar=item.get('sugar', '100%'),
                        drink_type=target_type # Saving the Hot/Iced/Frappe choice
                    )

            return JsonResponse({
                'status': 'success', 
                'order_id': new_order.id,
                'message': 'Order processed and inventory updated'
            })

        except Exception as e:
            print(f"CRITICAL Payment Error: {str(e)}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        
def complete_order(request, order_id):
    if request.method == 'POST':
        # Find the specific order
        order = get_object_or_404(Order, id=order_id)
        
        # Switch status to True (Hidden from kitchen)
        order.is_completed = True
        order.save()
        
    # Redirect back to the kitchen screen
    return redirect('kitchen_view')

#############################
####### Kitchen View ########
#############################


def kitchen_view(request):
    # 1. Orders that still need to be made (Live Queue)
    # Sorted by 'created_at' so oldest orders stay at the top (FIFO)
    pending_orders = Order.objects.filter(is_completed=False).order_by('created_at')
    
    # 2. Orders completed in the last 12 hours (History)
    # This prevents the history tab from getting cluttered with days-old data
    recent_time = timezone.now() - timedelta(hours=12)
    completed_orders = Order.objects.filter(
        is_completed=True, 
        created_at__gte=recent_time
    ).order_by('-created_at') # Newest first in history

    return render(request, 'kitchen.html', {
        'pending_orders': pending_orders,
        'completed_orders': completed_orders
    })