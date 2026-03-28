import json
import math
from decimal import Decimal
from datetime import timedelta
import calendar

# Django Core
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib import messages

# Database & Querying
from django.db import transaction
from django.db.models import Sum, Count, F, Avg
from django.db.models.functions import ExtractHour, ExtractDay, ExtractMonth, TruncDay

# Decorators
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from itertools import groupby

# Local App Models
from .models import (
    Category, 
    Order, 
    OrderItem, 
    Product, 
    Ingredient, 
    Recipe, 
    StockHistory, 
    Customer
)

#############################
####### Admin View ##########
#############################

def is_admin(user):
    return user.groups.filter(name='Admin').exists() or user.is_superuser

def owner_view(request):
    # --- 1. TIME WINDOW ---
    now = timezone.now()
    # Default initial view is "Today"
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Define today's completed orders
    orders = Order.objects.filter(is_completed=True, created_at__gte=start_date)

    # --- 2. REVENUE & ORDERS ---
    total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    order_count = orders.count()

    # --- 3. DYNAMIC PROFIT CALCULATION ---
    total_profit = Decimal('0.00')
    items = OrderItem.objects.filter(order__in=orders).select_related('product')

    for item in items:
        try:
            cost_per_unit = item.product.get_production_cost(size=item.size)
            actual_price = item.product.get_final_price(size=item.size, drink_type=item.drink_type)
            net_revenue_per_unit = actual_price / Decimal('1.10')
            total_profit += (net_revenue_per_unit - cost_per_unit) * item.quantity
        except Exception as e:
            continue

    # --- 4. ANALYTICS & CHARTS (Initial: Today) ---
    popular_items = OrderItem.objects.filter(order__in=orders).values('product__name').annotate(
        total_qty=Sum('quantity')
    ).order_by('-total_qty')[:5]

    sales_by_hour = orders.annotate(
        hour=ExtractHour('created_at')
    ).values('hour').annotate(total=Sum('total_amount')).order_by('hour')
    
    labels = [f"{item['hour']}:00" for item in sales_by_hour]
    sales_data = [float(item['total']) for item in sales_by_hour]

    # --- 5. CONTEXT ---
    context = {
        'total_revenue': total_revenue,
        'total_profit': total_profit.quantize(Decimal('0.01')),
        'order_count': order_count,
        'popular_items': popular_items,
        'labels': labels,
        'sales_data': sales_data,
        'all_ingredients': Ingredient.objects.all().order_by('stock_quantity'),
        'products': Product.objects.all(),
        'categories': Category.objects.all(),
        'top_customers': Customer.objects.order_by('-points')[:5],
        'low_stock_products': Product.objects.filter(stock__lt=10),
        'low_stock_ingredients': Ingredient.objects.filter(stock_quantity__lt=500), 
    }
    return render(request, 'owner.html', context)

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
            category=category_obj.name 
        )
        
        messages.success(request, f'Drink "{name}" added successfully!')
        return redirect('owner')
    
def delete_product(request, product_id):
    if request.method == "POST":
        product = get_object_or_404(Product, id=product_id)
        name = product.name
        product.delete()
        messages.warning(request, f'"{name}" has been removed from the menu.')
    return redirect('owner')

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
        return redirect('owner')

def pos_screen(request):
    return render(request, 'pos.html', {
        'products': Product.objects.all(),
        'categories': Category.objects.all(), # This line is required!
    })

################################
######## inventory page ########
################################

def inventory_list(request):
    ingredients = Ingredient.objects.all().order_by('name')
    
    # Fetch logs
    raw_logs = StockHistory.objects.select_related('ingredient').all().order_by('-created_at')

    # Group logs by the 'notes' field (Order Number)
    grouped_logs = []
    # We use groupby on the notes field
    for notes, items in groupby(raw_logs, lambda x: x.notes):
        items_list = list(items)
        # If it's an Order, we group them. If it's a Manual Update, we keep it separate
        if notes and "Order #" in notes:
            grouped_logs.append({
                'is_group': True,
                'notes': notes,
                'created_at': items_list[0].created_at,
                'items': items_list,
                'type': items_list[0].type
            })
        else:
            # Manual updates remain individual cards
            for item in items_list:
                grouped_logs.append({
                    'is_group': False,
                    'log': item
                })

    return render(request, 'inventory.html', {
        'ingredients': ingredients, 
        'grouped_logs': grouped_logs[:20] # Limit to 20 grouped entries
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
        if recipe.ingredient.stock_quantity < recipe.recipe.quantity:
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
    item = Ingredient.objects.filter(packaging_type=pkg_type).first()
    if item:
        item.stock_quantity -= Decimal(str(quantity))
        
        # Update the box count here too!
        if item.initial_stock_per_item > 0:
            import math
            item.items_count = math.ceil(item.stock_quantity / item.initial_stock_per_item)
            
        item.save()

def stock_history_view(request):
    # Fetch all history, including the ingredient name to save database queries
    logs = StockHistory.objects.select_related('ingredient').all().order_by('-created_at')
    
    # Optional: Filter by ingredient if the manager clicks one
    ingredient_id = request.GET.get('ingredient')
    if ingredient_id:
        logs = logs.filter(ingredient_id=ingredient_id)

    ingredients = Ingredient.objects.all()
    
    return render(request, 'stock_history.html', {
        'logs': logs,
        'ingredients': ingredients,
        'selected_ingredient': int(ingredient_id) if ingredient_id else None
    })

##############################
####### Recipe Builder #######
##############################

def recipe_builder(request):
    products = Product.objects.all().order_by('name')
    ingredients = Ingredient.objects.all().order_by('name')
    
    if request.method == "POST":
        # --- 1. HANDLE CLONE/COPY LOGIC ---
        copy_from_product_id = request.POST.get('copy_from_product_id')
        copy_from_size = request.POST.get('copy_from_size')
        target_size = request.POST.get('target_size')

        if copy_from_product_id and copy_from_size and target_size:
            source_recipes = Recipe.objects.filter(product_id=copy_from_product_id, size=copy_from_size)
            if source_recipes.exists():
                for item in source_recipes:
                    Recipe.objects.update_or_create(
                        product=item.product,
                        ingredient=item.ingredient,
                        size=target_size,
                        defaults={'quantity': Decimal(amount)}
                    )
                messages.success(request, f"Successfully cloned {copy_from_size} recipe to {target_size}!")
            else:
                messages.error(request, "No source recipe found to copy.")
            return redirect('recipe_builder')

        # --- 2. HANDLE DELETE LOGIC ---
        delete_id = request.POST.get('delete_recipe_id')
        if delete_id:
            get_object_or_404(Recipe, id=delete_id).delete()
            messages.info(request, "Ingredient removed from recipe.")
            return redirect('recipe_builder')

        # --- 3. HANDLE CREATE/UPDATE LOGIC ---
        product_id = request.POST.get('product')
        ingredient_id = request.POST.get('ingredient')
        size = request.POST.get('size') 
        amount = request.POST.get('amount')

        if product_id and ingredient_id and amount:
            try:
                product = get_object_or_404(Product, id=product_id)
                ingredient = get_object_or_404(Ingredient, id=ingredient_id)
                Recipe.objects.update_or_create(
                    product=product,
                    ingredient=ingredient,
                    size=size,
                    defaults={'quantity': Decimal(amount)}
                )
                messages.success(request, f"Updated {ingredient.name} for {product.name} ({size})")
            except Exception as e:
                messages.error(request, f"Error: {str(e)}")
            return redirect('recipe_builder')

    # --- 4. PREPARE DATA FOR DISPLAY (GET Request) ---
    recipes = Recipe.objects.select_related('product', 'ingredient').all().order_by('product__name', 'size')
    
    # Calculate costs only when we are actually going to render the page
    for r in recipes:
        r.line_cost = (r.ingredient.unit_cost or Decimal('0.00')) * r.quantity

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
        service_type = data.get('service_type', 'Dine-in')

        with transaction.atomic():
            new_order = Order.objects.create(
                total_amount=total_price, 
                is_completed=False,
                service_type=service_type
            )

            # ... (Loyalty logic remains the same) ...

            for item in cart_items:
                product = Product.objects.get(id=item.get('id'))
                target_size = item.get('size', 'Medium') 
                drink_type = item.get('type', 'Hot')     
                qty = int(item.get('qty', 1))
                
                # --- A. DEDUCT BEVERAGE INGREDIENTS ---
                recipe_items = Recipe.objects.filter(product=product, size=target_size)
                if not recipe_items.exists() and target_size != 'Medium':
                    recipe_items = Recipe.objects.filter(product=product, size='Medium')

                if recipe_items.exists():
                    sugar_map = {'0%': Decimal('0.0'), '25%': Decimal('0.25'), '50%': Decimal('0.5'), '75%': Decimal('0.75'), '100%': Decimal('1.0'), 'Extra': Decimal('1.5')}
                    multiplier = sugar_map.get(item.get('sugar', '100%'), Decimal('1.0'))

                    for recipe in recipe_items:
                        ingredient = Ingredient.objects.select_for_update().get(id=recipe.ingredient.id)
                        usage = Decimal(str(recipe.quantity)) * qty
                        if "sugar" in ingredient.name.lower() or "syrup" in ingredient.name.lower():
                            usage = usage * multiplier
                            
                        ingredient.stock_quantity = max(Decimal('0.00'), ingredient.stock_quantity - usage)
                        if ingredient.initial_stock_per_item > 0:
                            ingredient.items_count = math.ceil(ingredient.stock_quantity / ingredient.initial_stock_per_item)
                        ingredient.save()

                        # --- NEW: LOG AUDIT FOR INGREDIENTS ---
                        StockHistory.objects.create(
                            ingredient=ingredient,
                            amount=-usage,  # Negative for deduction
                            type='REDUCTION',
                            notes=f"Order #{new_order.id} ({product.name})"
                        )

                # --- B. SMART PACKAGING DEDUCTION ---
                if drink_type == 'Hot':
                    cup_cat, lid_cat, straw_cat = 'HOT_CUP', 'HOT_LID', 'HOT_STRAW'
                else:
                    cup_cat, lid_cat, straw_cat = 'COLD_CUP', 'COLD_LID', 'COLD_STRAW'

                def deduct_packaging(pkg_type, size_filter=None):
                    query = Ingredient.objects.filter(packaging_type=pkg_type)
                    if size_filter and pkg_type in ['HOT_CUP', 'COLD_CUP']:
                        query = query.filter(name__icontains=size_filter)
                    
                    target_ing = query.first()
                    if target_ing:
                        target_ing = Ingredient.objects.select_for_update().get(id=target_ing.id)
                        target_ing.stock_quantity = max(Decimal('0.00'), target_ing.stock_quantity - qty)
                        if target_ing.initial_stock_per_item > 0:
                            target_ing.items_count = math.ceil(target_ing.stock_quantity / target_ing.initial_stock_per_item)
                        target_ing.save()

                        # --- NEW: LOG AUDIT FOR PACKAGING ---
                        StockHistory.objects.create(
                            ingredient=target_ing,
                            amount=-qty,
                            type='REDUCTION',
                            notes=f"Order #{new_order.id} Packaging"
                        )

                deduct_packaging(cup_cat, target_size)
                deduct_packaging(lid_cat)
                deduct_packaging(straw_cat)

                # --- C. DEDUCT CARRIER ---
                if service_type == 'Takeout':
                    carrier = Ingredient.objects.filter(packaging_type='CARRIER').first()
                    if carrier:
                        carrier = Ingredient.objects.select_for_update().get(id=carrier.id)
                        carrier.stock_quantity = max(Decimal('0.00'), carrier.stock_quantity - qty)
                        if carrier.initial_stock_per_item > 0:
                            carrier.items_count = math.ceil(carrier.stock_quantity / carrier.initial_stock_per_item)
                        carrier.save()

                        # --- NEW: LOG AUDIT FOR CARRIER ---
                        StockHistory.objects.create(
                            ingredient=carrier,
                            amount=-qty,
                            type='REDUCTION',
                            notes=f"Order #{new_order.id} Carrier"
                        )

                OrderItem.objects.create(
                    order=new_order, product=product, quantity=qty,
                    size=target_size, sugar=item.get('sugar', '100%'),
                    drink_type=drink_type 
                )

        return JsonResponse({'status': 'success', 'order_id': new_order.id})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
def process_order_stock(order_item, new_order):
    # order_item contains: product, sugar_multiplier, qty
    recipe_ingredients = Recipe.objects.filter(product=order_item.product)
    
    for item in recipe_ingredients:
        # Calculate base reduction
        reduction_amount = item.quantity * order_item.qty
        
        # Check if the ingredient is a sugar/sweetener type
        if "sugar" in item.ingredient.name.lower() or "syrup" in item.ingredient.name.lower():
            # Apply the sugar multiplier logic
            reduction_amount = reduction_amount * order_item.sugar_multiplier
            
        # Subtract from inventory
        ingredient = item.ingredient
        ingredient.stock_quantity -= reduction_amount
        ingredient.save()
        
        # Record to History
        StockHistory.objects.create(
            ingredient=ingredient,
            # FIX: Use 'reduction_amount' instead of 'usage'
            amount=-reduction_amount, 
            type='REDUCTION',
            # FIX: Use 'new_order.id' and 'order_item.product.name'
            notes=f"Order #{new_order.id} ({order_item.product.name})"
        )
        
def complete_order(request, order_id):
    if request.method == "POST":
        order = get_object_or_404(Order, id=order_id)
        order.is_completed = True
        order.save()

        # Deduct stock based on your Recipe models
        for item in order.items.all():
            # Find the specific recipe for this product and size
            recipe_items = Recipe.objects.filter(product=item.product, size=item.size)
            for recipe in recipe_items:
                recipe.deduct_stock(item.quantity)
        
        messages.success(request, f"Order #{order.id} sent to history.")
    
    return redirect('kitchen_view')

#############################
####### Manager View ########
#############################

def is_manager(user):
    # This checks if the user is an admin OR in the 'Managers' group
    return user.is_staff or user.groups.filter(name='Managers').exists()

def manager_view(request):
    products = Product.objects.all()
    
    # --- 1. Calculate Recipe-Based Stock ---
    for product in products:
        recipes = Recipe.objects.filter(product=product)
        if not recipes.exists():
            product.calculated_stock = 0
            continue
            
        potential_servings = []
        for r in recipes:
            if r.ingredient.stock_quantity > 0:
                servings = int(r.ingredient.stock_quantity / r.quantity)
                potential_servings.append(servings)
            else:
                potential_servings.append(0)
        
        product.calculated_stock = min(potential_servings) if potential_servings else 0

    # --- 2. Summary Cards Logic ---
    total_margin = sum(p.margin_percentage for p in products)
    count = products.count()
    avg_profitability = total_margin / count if count > 0 else 0
    
    # --- 3. REAL Chart Data Logic (Last 30 Days) ---
    today = timezone.now()
    thirty_days_ago = today - timedelta(days=30)
    
    # Fetch all items sold in the last 30 days from completed orders
    # We use select_related to speed up the database query
    recent_sold_items = OrderItem.objects.filter(
        order__created_at__gte=thirty_days_ago,
        order__is_completed=True
    ).select_related('order', 'product')

    # Group the margin percentages by day
    daily_margins = {}
    for item in recent_sold_items:
        # Get the date string (e.g., 'Oct 24')
        date_str = item.order.created_at.strftime('%b %d')
        
        if date_str not in daily_margins:
            daily_margins[date_str] = []
            
        # Add this product's margin to that day's list
        # We multiply by quantity in case they bought 3 of the same drink
        for _ in range(item.quantity):
            daily_margins[date_str].append(item.product.margin_percentage)

    # Build the final lists for Chart.js
    chart_labels = []
    chart_data = []
    
    for i in range(30, -1, -1):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime('%b %d')
        chart_labels.append(date_str)
        
        # If we sold things on this day, calculate the average margin
        if date_str in daily_margins and len(daily_margins[date_str]) > 0:
            day_avg = sum(daily_margins[date_str]) / len(daily_margins[date_str])
            chart_data.append(round(float(day_avg), 1))
        else:
            # If nothing was sold that day, show 0 (or you could put avg_profitability here to keep the line flat)
            chart_data.append(0)

    context = {
        'products': products,
        'avg_profitability': avg_profitability, 
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'all_ingredients': Ingredient.objects.all(),
    }
    return render(request, 'manager.html', context)

def api_dashboard_stats(request):
    range_type = request.GET.get('range', 'today')
    now = timezone.now()
    current_month_name = now.strftime('%b') # Get 'Mar', 'Apr', etc.
    
    # --- 1. SET START DATE & CHART GROUPING ---
    if range_type == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        group_by = ExtractHour('created_at')
        label_fmt = lambda x: f"{x}:00"
        
    elif range_type == 'week':
        # Start from Monday of the current week
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        group_by = ExtractDay('created_at')
        label_fmt = lambda x: f"{current_month_name} {x}"
        
    elif range_type in ['month', '30days']:
        start_date = now.replace(day=1, hour=0, minute=0, second=0) 
        group_by = ExtractDay('created_at')
        label_fmt = lambda x: f"{current_month_name} {x}"
        
    elif range_type == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0)
        group_by = ExtractMonth('created_at')
        label_fmt = lambda x: calendar.month_name[x][:3]
        
    else:
        start_date = now.replace(hour=0, minute=0, second=0)
        group_by = ExtractHour('created_at')
        label_fmt = lambda x: f"{x}:00"

    # --- 2. FILTER & CALCULATE ---
    orders = Order.objects.filter(is_completed=True, created_at__gte=start_date)
    
    total_rev = orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    total_profit = Decimal('0.00')
    items = OrderItem.objects.filter(order__in=orders).select_related('product')
    for item in items:
        try:
            cost = item.product.get_production_cost(size=item.size)
            price = item.product.get_final_price(size=item.size, drink_type=item.drink_type)
            total_profit += ((price / Decimal('1.10')) - cost) * item.quantity
        except: continue

    # --- 3. TREND DATA ---
    sales_trend = orders.annotate(unit=group_by).values('unit').annotate(
        total=Sum('total_amount')
    ).order_by('unit')

    return JsonResponse({
        'revenue': float(total_rev),
        'profit': float(total_profit),
        'orders': orders.count(),
        'labels': [label_fmt(x['unit']) for x in sales_trend],
        'sales_data': [float(x['total']) for x in sales_trend],
    })

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

