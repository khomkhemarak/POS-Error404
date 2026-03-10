import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Category, Order, OrderItem, Product, Ingredient, Recipe, StockHistory, Customer
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Count
from django.db.models import F
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
    total_revenue = Order.objects.filter(is_completed=True).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    order_count = Order.objects.filter(is_completed=True).count()
    
    # 2. Profit Calculation
    total_profit = Decimal('0.00')
    completed_items = OrderItem.objects.filter(order__is_completed=True).select_related('product')
    for item in completed_items:
        try:
            cost_per_unit = item.product.get_production_cost()
            sale_price = getattr(item, 'price', item.product.base_price) 
            total_profit += (sale_price - cost_per_unit) * item.quantity
        except: continue

    # 3. Popular Items & Charts
    popular_items = OrderItem.objects.filter(order__is_completed=True).values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty')[:5]
    sales_by_hour = Order.objects.filter(is_completed=True).annotate(hour=ExtractHour('created_at')).values('hour').annotate(total=Sum('total_amount')).order_by('hour')
    labels = [f"{item['hour']}:00" for item in sales_by_hour]
    sales_data = [float(item['total']) for item in sales_by_hour]

    # 4. FIXED CAPACITY LOGIC
    # We use lower dividers to represent real coffee usage
    beans = Ingredient.objects.filter(name__icontains="Bean").first()
    milk = Ingredient.objects.filter(name__icontains="Milk").first()
    cups = Ingredient.objects.filter(name__icontains="Cup").aggregate(total=Sum('stock_quantity'))['total'] or 0
    
    capacity_list = []
    if beans:
        capacity_list.append(int(beans.stock_quantity / 30)) # 30g per cup
    if milk:
        # Changed from 250 to 180 to give a more realistic capacity
        capacity_list.append(int(milk.stock_quantity / 190)) 
    if cups > 0:
        capacity_list.append(int(cups))

    total_capacity = min(capacity_list) if capacity_list else 0

    # 5. CONTEXT DATA
    context = {
        'total_revenue': total_revenue,
        'total_profit': total_profit,
        'order_count': order_count,
        'popular_items': popular_items,
        'labels': labels,
        'sales_data': sales_data,
        'all_ingredients': Ingredient.objects.all().order_by('stock_quantity'),
        'products': Product.objects.all(),
        'categories': Category.objects.all(),
        'top_customers': Customer.objects.order_by('-points')[:5],
        'total_capacity': total_capacity,
        # ALERTS: Only alert if under 500g or 1000ml (1 Liter)
        'low_stock_products': Product.objects.filter(stock__lt=10),
        'low_stock_ingredients': Ingredient.objects.filter(stock_quantity__lt=500), 
    }

    return render(request, 'admin_dashboard.html', context)

def add_product(request):
    if request.method == "POST":
        name = request.POST.get('name')
        price = request.POST.get('price')
        image = request.FILES.get('image')
        category_id = request.POST.get('category')

        # Prevent crash if category is missing
        category_obj = get_object_or_404(Category, id=category_id)
        
        # Updated keys to match the HTML "name" attributes exactly
        is_hot = 'can_be_hot' in request.POST
        is_iced = 'can_be_iced' in request.POST
        is_frappe = 'can_be_frappe' in request.POST

        Product.objects.create(
            name=name, 
            base_price=price, 
            image=image,
            can_be_hot=is_hot,
            can_be_iced=is_iced,
            can_be_frappe=is_frappe,
            # Pass the category name string to match your Product model choice field
            category=category_obj.name 
        )
        
        messages.success(request, f'Drink "{name}" added successfully!')
        return redirect('admin_dashboard')
    
def delete_product(request, product_id):
    if request.method == "POST":
        product = get_object_or_404(Product, id=product_id)
        name = product.name
        product.delete()
        messages.warning(request, f'"{name}" has been removed from the menu.')
    return redirect('admin_dashboard')

def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == "POST":
        product.name = request.POST.get('name')
        product.base_price = request.POST.get('price')
        
        # Handle Category
        category_id = request.POST.get('category')
        category_obj = get_object_or_404(Category, id=category_id)
        product.category = category_obj.name 
        
        # --- THE MISSING LOGIC ---
        # These lines check if the key exists in POST. 
        # If unchecked, 'in' returns False, correctly updating your DB.
        product.can_be_hot = 'can_be_hot' in request.POST
        product.can_be_iced = 'can_be_iced' in request.POST
        product.can_be_frappe = 'can_be_frappe' in request.POST
        # -------------------------

        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
            
        product.save()

        messages.info(request, f'Updated "{product.name}" details.')
        return redirect('admin_dashboard')

def pos_screen(request):
    return render(request, 'pos.html', {
        'products': Product.objects.all(),
        'categories': Category.objects.all(), # This line is required!
    })

######## inventory page ########

def inventory_list(request):
    ingredients = Ingredient.objects.all().order_by('name')
    recent_history = StockHistory.objects.order_by('-created_at')[:10]
    
    if request.method == "POST":
        ing_id = request.POST.get('ingredient_id')
        items_to_add = request.POST.get('items_to_add')  # From Modal Textbox 1
        new_unit_size = request.POST.get('unit_size')    # From Modal Textbox 2
        
        if ing_id and items_to_add and new_unit_size:
            ingredient = get_object_or_404(Ingredient, id=ing_id)
            
            # Convert inputs to numerical types
            num_items = Decimal(items_to_add)
            unit_size = Decimal(new_unit_size)
            
            # 1. Update the reference unit size in case it changed (e.g., new bottle size)
            ingredient.initial_stock_per_item = unit_size
            
            # 2. Calculate volume to add (e.g., 2 items * 1500g = 3000g)
            volume_to_add = num_items * unit_size
            
            # 3. Update the raw stock quantity
            ingredient.stock_quantity += volume_to_add

            # 4. Recalculate the Item Count for display
            if ingredient.initial_stock_per_item > 0:
                ingredient.items_count = int(ingredient.stock_quantity // ingredient.initial_stock_per_item)

            ingredient.save()
            
            # 5. Record history (saving the total volume added)
            StockHistory.objects.create(
                ingredient=ingredient, 
                amount_added=volume_to_add
            )
            
            return redirect('inventory_list')

    return render(request, 'inventory.html', {
        'ingredients': ingredients, 
        'recent_history': recent_history
    })

def add_ingredient(request):
    if request.method == "POST":
        name = request.POST.get('name')
        unit = request.POST.get('unit')
        
        # 1. Get values from the form
        # We use .get(..., 0) to prevent errors if a field is empty
        qty_items = int(request.POST.get('quantity_items', 1)) 
        stock_per_item = float(request.POST.get('stock_per_item', 0))
        price_per_item = float(request.POST.get('price_per_item', 0))
        
        # --- NEW: Get Packaging Info ---
        pkg_type = request.POST.get('packaging_type', 'NONE')
        is_pkg = pkg_type != 'NONE'

        # 2. Calculate the total stock quantity
        total_stock = qty_items * stock_per_item
        
        # 3. Calculate UNIT COST (e.g., cost per 1 gram or 1 straw)
        unit_cost = 0
        if stock_per_item > 0:
            unit_cost = price_per_item / stock_per_item
        
        # 4. Save to Database
        Ingredient.objects.create(
            name=name,
            unit=unit,
            items_count=qty_items,
            stock_quantity=total_stock,
            initial_stock_per_item=stock_per_item, # Added this to match your Model
            unit_cost=unit_cost,
            last_purchase_price=price_per_item,
            is_packaging=is_pkg,
            packaging_type=pkg_type
        )
        
        messages.success(request, f'Successfully added {name} to inventory.')
        return redirect('inventory_list')
            
def delete_ingredient(request, pk):
    if request.method == "POST":
        ingredient = get_object_or_404(Ingredient, pk=pk)
        name = ingredient.name
        ingredient.delete()
        messages.success(request, f"'{name}' has been removed from inventory.")
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

@transaction.atomic
def complete_checkout(request):
    if request.method == "POST":
        # 1. Get cart data from the request (JSON or Form)
        cart_data = json.loads(request.POST.get('cart')) 
        
        for item in cart_data:
            # item['type'] = 'Hot', 'Iced', or 'Frappe'
            # item['service'] = 'Dine-in' or 'Takeout'
            
            # --- PACKAGING DEDUCTION LOGIC ---
            
            # A. Deduct the Cup
            cup_type = 'HOT_CUP' if item['type'] == 'Hot' else 'COLD_CUP'
            deduct_stock(cup_type, 1)
            
            # B. Deduct the Straw
            straw_type = 'HOT_STRAW' if item['type'] == 'Hot' else 'COLD_STRAW'
            deduct_stock(straw_type, 1)
            
            # C. Deduct the Carrier (ONLY if Takeout AND not Hot)
            # Most cafes don't put hot drinks in plastic carriers unless requested, 
            # but let's follow your logic for Ice/Frappe takeout:
            if item['service'] == 'Takeout' and item['type'] != 'Hot':
                deduct_stock('CARRIER', 1)

            # D. Deduct regular ingredients (Coffee, Milk, etc.)
            # product = Product.objects.get(id=item['id'])
            # product.reduce_ingredients_stock() 

        return JsonResponse({'status': 'success'})

def deduct_stock(pkg_type, quantity):
    """Helper function to find the right packaging and reduce stock"""
    item = Ingredient.objects.filter(packaging_type=pkg_type).first()
    if item:
        item.stock_quantity -= quantity
        item.save()

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
        size = request.POST.get('size')  # Capture size from the form
        amount = request.POST.get('amount')

        # Ensure all required fields are present to avoid errors
        if product_id and ingredient_id and amount:
            product = get_object_or_404(Product, id=product_id)
            ingredient = get_object_or_404(Ingredient, id=ingredient_id)

            # Create or update the recipe for that specific size
            # Fix: Populate both amount_needed and quantity to satisfy model constraints
            Recipe.objects.update_or_create(
                product=product,
                ingredient=ingredient,
                size=size,
                defaults={
                    'amount_needed': Decimal(amount),
                    'quantity': float(amount)  # Added to resolve NOT NULL constraint failed error
                }
            )
            messages.success(request, f"Recipe for {product.name} ({size}) updated successfully!")
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
    query = request.GET.get('search')
    products = Product.objects.all()
    
    if query:
        products = products.filter(name__icontains=query)
        
    categories = Category.objects.all()
    return render(request, 'pos.html', {'products': products, 'categories': categories})

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
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    try:
        data = json.loads(request.body)
        cart_items = data.get('items', [])
        total_price = data.get('total')
        customer_id = data.get('customer_id') 

        with transaction.atomic():
            new_order = Order.objects.create(total_amount=total_price, is_completed=True)

            if customer_id:
                try:
                    customer = Customer.objects.select_for_update().get(id=customer_id)
                    new_order.customer = customer
                    new_order.save()
                    points_to_add = int(float(total_price))
                    customer.points = F('points') + points_to_add
                    customer.save()
                except (Customer.DoesNotExist, ValueError):
                    pass 

            for item in cart_items:
                product = Product.objects.get(id=item.get('id'))
                target_size = item.get('size', 'Medium')
                qty = int(item.get('qty', 1))
                
                recipe_items = Recipe.objects.filter(product=product, size=target_size)
                if not recipe_items.exists() and target_size != 'Medium':
                    recipe_items = Recipe.objects.filter(product=product, size='Medium')

                if recipe_items.exists():
                    sugar_map = {
                        '0%': Decimal('0.0'), '25%': Decimal('0.25'), '50%': Decimal('0.5'), 
                        '75%': Decimal('0.75'), '100%': Decimal('1.0'), 'Extra': Decimal('1.5')
                    }
                    multiplier = sugar_map.get(item.get('sugar', '100%'), Decimal('1.0'))

                    for recipe in recipe_items:
                        ingredient = Ingredient.objects.select_for_update().get(id=recipe.ingredient.id)
                        
                        usage = Decimal(str(recipe.amount_needed)) * qty
                        if "sugar" in ingredient.name.lower() or "syrup" in ingredient.name.lower():
                            usage = usage * multiplier
                            
                        # Update raw stock (Decimal - Decimal)
                        ingredient.stock_quantity = max(Decimal('0.00'), ingredient.stock_quantity - usage)
                        
                        # LOGIC: Decrease item count if stock falls below the threshold
                        # Example: 2999.00 // 1500.00 = 1 (drops from 2 to 1)
                        if ingredient.initial_stock_per_item > 0:
                            ingredient.items_count = int(ingredient.stock_quantity // ingredient.initial_stock_per_item)                        
                        ingredient.save()

                OrderItem.objects.create(
                    order=new_order, product=product, quantity=qty,
                    size=target_size, sugar=item.get('sugar', '100%'),
                    drink_type=item.get('type', 'Hot') 
                )

        return JsonResponse({'status': 'success', 'order_id': new_order.id})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
def process_order_stock(order_item):
    # order_item contains: product, sugar_multiplier, qty
    recipe_ingredients = Recipe.objects.filter(product=order_item.product)

    for item in recipe_ingredients:
        reduction_amount = item.amount * order_item.qty
        
        # Check if the ingredient is a sugar/sweetener type
        if "sugar" in item.ingredient.name.lower() or "syrup" in item.ingredient.name.lower():
            # Apply the 50% logic here
            reduction_amount = reduction_amount * order_item.sugar_multiplier
            
        # Subtract from inventory
        ingredient = item.ingredient
        ingredient.stock_quantity -= reduction_amount
        ingredient.save()
        
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