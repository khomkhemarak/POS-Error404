from importlib import import_module
import importlib
import json
import math
from decimal import Decimal
from datetime import timedelta
import calendar
from os import name
from urllib import request

# Django Core
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Database & Querying
from django.db import transaction
from django.db.models import Sum, F, Case, When, DecimalField, IntegerField, Value
from django.db.models.functions import ExtractHour, ExtractDay, ExtractMonth, TruncDay

# Decorators
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required, user_passes_test
from django.template.loader import render_to_string
try:
    weasyprint = importlib.import_module('weasyprint')
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    weasyprint = None
    HAS_WEASYPRINT = False
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
    # --- 1. SET TIME WINDOW (Default: Today) ---
    now = timezone.localtime(timezone.now())
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Define today's completed orders
    orders = Order.objects.filter(created_at__gte=start_date)
    order_count = orders.count()

    # --- 2. income (Pulling from Order total_amount - Fixed) ---
    total_income = orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    # --- 3. FROZEN PROFIT CALCULATION ---
    total_profit = Decimal('0.00')
    items = OrderItem.objects.filter(order__in=orders).select_related('product')

    for item in items:
        # Use Snapshot data if it exists (>0), otherwise fallback to current product data
        price = item.price_at_sale if item.price_at_sale > 0 else item.product.price_small
        cost = item.cost_at_sale if item.cost_at_sale > 0 else item.product.get_product_cost(item.size)

        # Performance Math (Net income after 10% tax)
        net_income_per_unit = price / Decimal('1.10')
        total_profit += (net_income_per_unit - cost) * item.quantity

    # --- 4. ANALYTICS & CHARTS ---
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
        'total_income': total_income,
        'total_profit': total_profit.quantize(Decimal('0.01')),
        'order_count': order_count,
        'popular_items': popular_items,
        'labels': labels,
        'sales_data': sales_data,
        'all_ingredients': Ingredient.objects.filter(is_packaging=False).order_by('stock_quantity'),
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
        
        # FIX: Convert string price to Decimal immediately
        # This prevents the "str + int" crash in models.py
        try:
            price = Decimal(request.POST.get('price', '0'))
        except (ValueError, TypeError):
            price = Decimal('0.00')

        image = request.FILES.get('image')
        category_id = request.POST.get('category')

        # Prevent crash if category is missing
        category_obj = get_object_or_404(Category, id=category_id)
        
        is_hot = 'can_be_hot' in request.POST
        is_iced = 'can_be_iced' in request.POST
        is_frappe = 'can_be_frappe' in request.POST

        # Create the product
        product = Product.objects.create(
            name=name,
            price_small=Decimal(request.POST.get('price_small', price)),
            price_medium=Decimal(request.POST.get('price_medium', price)),
            price_large=Decimal(request.POST.get('price_large', price)),
            image=image,
            can_be_hot=is_hot,
            can_be_iced=is_iced,
            can_be_frappe=is_frappe,
            category=category_obj.name
        )

        # Check if this is an AJAX request from owner page
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            # Return JSON for owner page AJAX requests
            try:
                prod_cost = float(product.get_product_cost())
            except:
                prod_cost = 0.0
                
            try:
                prod_profit = float(product.get_profit())
            except:
                prod_profit = float(price) / 1.1

            return JsonResponse({
                'status': 'success',
                'message': f'Product "{name}" added successfully!',
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'price_small': str(product.price_small),
                    'price_medium': str(product.price_medium),
                    'price_large': str(product.price_large),
                    'category_id': category_id,
                    'category': product.category,
                    'cost': prod_cost,
                    'profit': prod_profit,
                    'image_url': product.image.url if product.image else None,
                    'can_be_hot': product.can_be_hot,
                    'can_be_iced': product.can_be_iced,
                    'can_be_frappe': product.can_be_frappe,
                }
            })
        else:
            # Redirect to manager for regular form submissions
            return redirect('manager_display')
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

def delete_product(request, product_id):
    if request.method == "POST":
        product = get_object_or_404(Product, id=product_id)
        prod_id = product.id # Save ID before deleting
        name = product.name
        product.delete()
        
        # Check if this is an AJAX request from owner page
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            # Return JSON for owner page AJAX requests
            return JsonResponse({
                'status': 'success',
                'message': f'"{name}" has been removed.',
                'product_id': prod_id
            })
        else:
            # Redirect to manager for regular form submissions
            return redirect('manager_display')
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == "POST":
        product.name = request.POST.get('name')
        raw_price = request.POST.get('price')
        
        # Update prices (handling both old single-price input and new per-size inputs)
        product.price_small = Decimal(request.POST.get('price_small', raw_price or '0'))
        if request.POST.get('price_medium'): product.price_medium = Decimal(request.POST.get('price_medium'))
        if request.POST.get('price_large'): product.price_large = Decimal(request.POST.get('price_large'))

        
        # Handle Category
        category_id = request.POST.get('category')
        category_obj = get_object_or_404(Category, id=category_id)
        product.category = category_obj.name 
        
        # Checkboxes
        product.can_be_hot = 'can_be_hot' in request.POST
        product.can_be_iced = 'can_be_iced' in request.POST
        product.can_be_frappe = 'can_be_frappe' in request.POST

        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
            
        product.save()

        # Check if this is an AJAX request from owner page
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        
        if is_ajax:
            # Return JSON for owner page AJAX requests
            return JsonResponse({
                'status': 'success',
                'message': f'Updated "{product.name}"',
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'price_small': str(product.price_small),
                    'price_medium': str(product.price_medium),
                    'price_large': str(product.price_large),
                    'category_id': category_id,
                    'category': product.category,
                    'profit': f"{product.get_profit():.2f}" if hasattr(product, 'get_profit') else "0.00",
                    'image_url': product.image.url if product.image else None,
                    'can_be_hot': product.can_be_hot,
                    'can_be_iced': product.can_be_iced,
                    'can_be_frappe': product.can_be_frappe,
                }
            })
        else:
            # Redirect to manager for regular form submissions
            return redirect('manager_display')
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

def pos_screen(request):
    return render(request, 'pos.html', {
        'products': Product.objects.all(),
        'categories': Category.objects.all(), # This line is required!
    })

def generate_daily_report(request):
    if not HAS_WEASYPRINT:
        error_message = "PDF generation library (weasyprint) is not installed or configured correctly."
        detailed_instructions = """
            <p>To enable PDF reports, please ensure you have installed WeasyPrint and its system dependencies:</p>
            <h3>1. Install WeasyPrint via pip:</h3>
            <pre><code>pip install WeasyPrint</code></pre>
            <h3>2. Install System Dependencies:</h3>
            <p><strong>For Debian/Ubuntu:</strong></p>
            <pre><code>sudo apt-get install libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0</code></pre>
            <p><strong>For Windows:</strong> You typically need to install the <a href="https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases" target="_blank">GTK for Windows Runtime</a>. Download and run the latest .exe installer.</p>
            <p><strong>For macOS:</strong> You might need Homebrew: <pre><code>brew install pango cairo gdk-pixbuf</code></pre></p>
            <p>After installing, please restart your Django development server.</p>
        """
        return HttpResponse(f"""
            <!DOCTYPE html>
            <html lang="en">
            <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>PDF Generation Error</title>
            <style>body {{ font-family: sans-serif; margin: 20px; line-height: 1.6; }} h1 {{ color: #dc2626; }} pre {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; overflow-x: auto; }}</style>
            </head>
            <body>
                <h1>PDF Generation Error</h1><p>{error_message}</p>{detailed_instructions}
                <p><a href="javascript:window.close()">Close this tab</a></p>
            </body></html>
        """, content_type="text/html")

    now = timezone.localtime(timezone.now())
    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Re-use logic from owner_view/api_dashboard_stats for 'today'
    orders = Order.objects.filter(created_at__gte=start_date)
    order_count = orders.count()

    total_income = orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    total_profit = Decimal('0.00')
    total_expense = Decimal('0.00')
    total_cups = 0
    total_tax = Decimal('0.00')

    items = OrderItem.objects.filter(order__in=orders).select_related('product')
    for item in items:
        price = item.price_at_sale if item.price_at_sale > 0 else item.product.price_small
        cost = item.cost_at_sale if item.cost_at_sale > 0 else item.product.get_product_cost(item.size)
        
        net_income_per_unit = price / Decimal('1.10')
        total_profit += (net_income_per_unit - cost) * item.quantity
        total_expense += cost * item.quantity
        total_cups += item.quantity

    for order in orders:
        total_tax += order.tax_amount

    income_val = float(total_income)
    if income_val <= 4000:
        annual_rate = 0
    elif income_val <= 6000:
        annual_rate = 0.05
    elif income_val <= 25500:
        annual_rate = 0.10
    elif income_val <= 37500:
        annual_rate = 0.15
    else:
        annual_rate = 0.20
        
    annual_tax_amount = Decimal(str(income_val * annual_rate))
    net_after_annual_tax = total_income - annual_tax_amount

    popular_items = OrderItem.objects.filter(order__in=orders).values('product__name').annotate(
        total_qty=Sum('quantity')
    ).order_by('-total_qty')[:5]

    low_stock_products = Product.objects.filter(stock__lt=10)
    low_stock_ingredients = Ingredient.objects.filter(stock_quantity__lt=500)

    context = {
        'report_date': now.strftime('%Y-%m-%d'),
        'total_income': total_income.quantize(Decimal('0.01')),
        'total_profit': total_profit.quantize(Decimal('0.01')),
        'total_expense': total_expense.quantize(Decimal('0.01')),
        'order_count': order_count,
        'total_cups': total_cups,
        'total_tax': total_tax.quantize(Decimal('0.01')),
        'annual_tax_amount': annual_tax_amount.quantize(Decimal('0.01')),
        'annual_tax_rate': int(annual_rate * 100),
        'net_after_annual_tax': net_after_annual_tax.quantize(Decimal('0.01')),
        'popular_items': popular_items,
        'low_stock_products': low_stock_products,
        'low_stock_ingredients': low_stock_ingredients,
    }

    html_string = render_to_string('daily_report_template.html', context)
    
    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename="daily_report_{now.strftime("%Y%m%d")}.pdf"'
    
    weasyprint.HTML(string=html_string).write_pdf(response)
    return response

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

    paginator = Paginator(grouped_logs, 10)
    page_number = request.GET.get('page', 1)
    if paginator.count == 0:
        page_obj = None
        displayed_logs = []
    else:
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        displayed_logs = page_obj

    low_stock_count = sum(1 for ing in ingredients if ing.is_low_stock)

    return render(request, 'inventory.html', {
        'ingredients': ingredients,
        'grouped_logs': displayed_logs,
        'page_obj': page_obj,
        'low_stock_count': low_stock_count,
    })

def api_inventory_list(request):
    """Returns the current stock levels and percentages for all ingredients as JSON."""
    ingredients = Ingredient.objects.all().order_by('name')
    data = []
    
    for ing in ingredients:
        data.append({
            'id': ing.id,
            'name': ing.name,
            'unit': ing.unit,
            'packaging_type': ing.packaging_type,
            'stock_quantity': float(ing.stock_quantity),
            'stock_percent': float(ing.stock_percent),
            'items_count': ing.items_count,
            'initial_stock_per_item': float(ing.initial_stock_per_item),
            'is_low_stock': ing.is_low_stock,
            'last_purchase_price': float(ing.last_purchase_price),
            'unit_cost': float(ing.unit_cost),
            'stock_value': float(ing.stock_value),
        })
        
    return JsonResponse({'ingredients': data})

def api_raw_materials(request):
    """API specifically for raw materials (excludes packaging)"""
    ingredients = Ingredient.objects.filter(is_packaging=False).order_by('name')
    data = [{
        'id': ing.id,
        'name': ing.name,
        'stock_quantity': float(ing.stock_quantity),
        'unit': ing.unit,
        'stock_percent': float(ing.stock_percent),
        'is_low_stock': ing.is_low_stock,
    } for ing in ingredients]
    return JsonResponse({'ingredients': data})

def api_inventory_logs(request):
    """Returns grouped stock history logs for AJAX refresh."""
    raw_logs = StockHistory.objects.select_related('ingredient').all().order_by('-created_at')[:20]
    data = []
    for notes, items in groupby(raw_logs, lambda x: x.notes):
        items_list = list(items)
        if notes and "Order #" in notes:
            data.append({
                'is_group': True,
                'notes': notes,
                'created_at': timezone.localtime(items_list[0].created_at).strftime("%H:%M %p"),
                'items': [{'name': i.ingredient.name, 'amount': float(i.amount), 'unit': i.ingredient.unit} for i in items_list]
            })
        else:
            for item in items_list:
                data.append({
                    'is_group': False,
                    'name': item.ingredient.name,
                    'amount': float(item.amount),
                    'unit': item.ingredient.unit,
                    'created_at': timezone.localtime(item.created_at).strftime("%H:%M %p"),
                    'notes': item.notes
                })
    return JsonResponse({'logs': data})

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
        ing = Ingredient.objects.create(
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
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'api' in request.path:
            return JsonResponse({
                'status': 'success',
                'message': f'Added {name}',
                'ingredient': {
                    'id': ing.id,
                    'name': ing.name,
                    'unit': ing.unit,
                    'packaging_type': ing.packaging_type,
                    'stock_quantity': float(ing.stock_quantity),
                    'stock_percent': float(ing.stock_percent),
                    'items_count': ing.items_count,
                    'initial_stock_per_item': float(ing.initial_stock_per_item),
                    'is_low_stock': ing.is_low_stock,
                    'last_purchase_price': float(ing.last_purchase_price),
                    'unit_cost': float(ing.unit_cost),
                    'stock_value': float(ing.stock_value),
                }
            })
            
        return redirect('inventory_list')
       
def update_stock(request, pk):
    if request.method == "POST":
        ingredient = get_object_or_404(Ingredient, pk=pk)
        try:
            qty_added = float(request.POST.get('items_to_add') or 0)
            batch_price_input = request.POST.get('batch_price')
            new_unit_size = request.POST.get('unit_size')

            if qty_added > 0:
                if batch_price_input:
                    total_price = float(batch_price_input)
                else:
                    total_price = qty_added * float(ingredient.last_purchase_price)

                if new_unit_size:
                    ingredient.initial_stock_per_item = Decimal(str(new_unit_size))

                ingredient.add_new_stock(qty_added, total_price)

                StockHistory.objects.create(
                    ingredient=ingredient,
                    amount=Decimal(str(qty_added)) * ingredient.initial_stock_per_item,
                    type='RESTOCK',
                    notes=f"Restock: {qty_added} items"
                )
                
                # --- NEW: AJAX Check ---
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'message': 'Stock updated'})
                
                messages.success(request, f"Successfully restocked {ingredient.name}.")
            else:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'message': 'Quantity must be > 0'}, status=400)
                messages.warning(request, "Please enter a quantity greater than 0.")

        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            messages.error(request, f"Error: {str(e)}")
            
    return redirect('inventory_list')
            
def delete_ingredient(request, pk):
    if request.method == "POST":
        ingredient = get_object_or_404(Ingredient, pk=pk)
        name = ingredient.name
        ingredient.delete()
        
        # --- NEW: AJAX Check ---
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'message': f'Deleted {name}'})
            
        messages.success(request, f"'{name}' has been removed from inventory.")
    return redirect('inventory_list')

@csrf_exempt
def rename_ingredient(request, pk):
    if request.method == "POST":
        ingredient = get_object_or_404(Ingredient, pk=pk)
        new_name = request.POST.get('name')
        if new_name:
            ingredient.name = new_name
            ingredient.save()
            return JsonResponse({'status': 'success', 'message': f'Renamed to {new_name}'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)

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
            # Most cafes don't put hot products in plastic carriers unless requested, 
            # but let's follow your logic for Ice/Frappe takeout:
            if item['service'] == 'Takeout' and item['type'] != 'Hot':
                deduct_stock('CARRIER', 1)

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

@csrf_exempt
def api_update_stock(request, pk):
    if request.method == 'POST':
        try:
            ingredient = get_object_or_404(Ingredient, pk=pk)
            items_to_add = float(request.POST.get('items_to_add') or 0)
            # Use the existing unit size if none is provided in the update
            unit_size = request.POST.get('unit_size') or ingredient.initial_stock_per_item
            batch_price = request.POST.get('batch_price')
            
            if items_to_add > 0:
                with transaction.atomic():
                    ingredient.initial_stock_per_item = Decimal(str(unit_size))
                    # Calculate price: user input or previous purchase price[cite: 9]
                    price_paid = Decimal(batch_price) if batch_price else (Decimal(str(items_to_add)) * ingredient.last_purchase_price)
                    
                    ingredient.add_new_stock(new_items_count=items_to_add, price_paid=price_paid)
                    
                    # Create the log entry for the history table[cite: 9]
                    total_quantity_added = Decimal(str(items_to_add)) * ingredient.initial_stock_per_item
                    StockHistory.objects.create(
                        ingredient=ingredient,
                        amount=total_quantity_added,
                        type='RESTOCK',
                        notes=f"Stock Update: {items_to_add} items"
                    )

                return JsonResponse({
                    'status': 'success',
                    'message': f'Updated {ingredient.name}',
                    'new_stock': float(ingredient.stock_quantity)
                })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=405)

@csrf_exempt
def api_deduct_stock(request, pk):
    if request.method == 'POST':
        try:
            ingredient = get_object_or_404(Ingredient, pk=pk)
            items_to_deduct = float(request.POST.get('items_to_deduct') or 0)
            reason = request.POST.get('reason') or "Manual Adjustment"
            
            if items_to_deduct > 0:
                with transaction.atomic():
                    # Calculate the physical quantity to remove (e.g. 1 box * 1000g)
                    total_quantity_deducted = Decimal(str(items_to_deduct)) * ingredient.initial_stock_per_item
                    
                    # Deduct from quantity (preventing negative numbers)
                    ingredient.stock_quantity = max(Decimal('0.00'), ingredient.stock_quantity - total_quantity_deducted)
                    
                    # Recalculate box count based on new quantity
                    if ingredient.initial_stock_per_item > 0:
                        ingredient.items_count = math.ceil(ingredient.stock_quantity / ingredient.initial_stock_per_item)
                    
                    ingredient.save()
                    
                    # Create log entry as ADJUST to distinguish from sales REDUCTION
                    StockHistory.objects.create(
                        ingredient=ingredient,
                        amount=-total_quantity_deducted,
                        type='ADJUST',
                        notes=f"Deduction: {items_to_deduct} items ({reason})"
                    )

                return JsonResponse({
                    'status': 'success',
                    'message': f'Deducted {ingredient.name}',
                    'new_stock': float(ingredient.stock_quantity)
                })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=405)

##############################
####### Recipe Builder #######
##############################

def recipe_builder(request):
    products = Product.objects.all().order_by('name')
    ingredients = Ingredient.objects.filter(is_packaging=False).order_by('name')
    packaging_items = Ingredient.objects.filter(is_packaging=True).annotate(
        packaging_group=Case(
            When(packaging_type__startswith='HOT', then=Value(0)),
            When(packaging_type__startswith='COLD', then=Value(1)),
            default=Value(2),
            output_field=IntegerField(),
        ),
        packaging_order=Case(
            When(packaging_type='HOT_CUP', then=Value(0)),
            When(packaging_type='HOT_LID', then=Value(1)),
            When(packaging_type='HOT_STRAW', then=Value(2)),
            When(packaging_type='COLD_CUP', then=Value(3)),
            When(packaging_type='COLD_LID', then=Value(4)),
            When(packaging_type='COLD_STRAW', then=Value(5)),
            When(packaging_type='CARRIER', then=Value(6)),
            default=Value(7),
            output_field=IntegerField(),
        ),
    ).order_by('packaging_group', 'packaging_order', 'name')
    
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
                        defaults={'quantity': item.quantity}
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
        package_item_id = request.POST.get('package_item')
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

                if package_item_id:
                    try:
                        package_item = get_object_or_404(Ingredient, id=package_item_id)
                        Recipe.objects.update_or_create(
                            product=product,
                            ingredient=package_item,
                            size=size,
                            defaults={'quantity': Decimal('1')}
                        )
                        messages.success(request, f"Updated {ingredient.name} and {package_item.name} for {product.name} ({size})")
                    except Exception as e:
                        messages.warning(request, f"Recipe saved, but package item was not added: {str(e)}")
                else:
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
        'packaging_items': packaging_items,
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
            'points': customer.points
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
        redeem_free_drink = data.get('redeem_free_drink', False)
        payment_method = data.get('payment_method', 'Cash')
        cash_received = data.get('cash_received', 0)
        cash_change = data.get('cash_change', 0)

        with transaction.atomic():
            new_order = Order.objects.create(
                total_amount=total_price, 
                is_completed=False, # Now appears in Kitchen Queue
                service_type=service_type,
                payment_method=payment_method,
                customer_id=customer_id,
                cash_received=Decimal(str(cash_received)),
                cash_change=Decimal(str(cash_change)),
                cashier_name=request.user.get_full_name() or request.user.username if request.user.is_authenticated else "Staff"
            )

            customer = None
            if customer_id:
                customer = Customer.objects.select_for_update().get(id=customer_id)
                if redeem_free_drink:
                    customer.points = max(0, customer.points - 50)
                    customer.save()

            free_drink_applied = False
            total_earned_points = 0
            point_map = {'Small': 3, 'Medium': 5, 'Large': 7}

            for item in cart_items:
                product = Product.objects.get(id=item.get('id'))
                target_size = item.get('size', 'Medium') 
                product_type = item.get('type', 'Hot')     
                qty = int(item.get('qty', 1))
                extra_shots = int(item.get('shots', 0))
                
                # --- A. DEDUCT BEVERAGE INGREDIENTS ---
                recipe_items = Recipe.objects.filter(product=product, size=target_size)
                if not recipe_items.exists() and target_size != 'Medium':
                    recipe_items = Recipe.objects.filter(product=product, size='Medium')

                if recipe_items.exists():
                    sugar_map = {
                        '0%': Decimal('0.0'), '25%': Decimal('0.25'), '50%': Decimal('0.5'), 
                        '75%': Decimal('0.75'), '100%': Decimal('1.0'), 'Extra': Decimal('1.5')
                    }
                    sugar_str = item.get('sugar', '100%')
                    if sugar_str in sugar_map:
                        multiplier = sugar_map[sugar_str]
                    elif sugar_str.endswith('%'):
                        try:
                            # Handle custom percentages like "125%"
                            multiplier = Decimal(sugar_str.replace('%', '')) / Decimal('100')
                        except:
                            multiplier = Decimal('1.0')
                    else:
                        multiplier = Decimal('1.0')

                    for recipe in recipe_items:
                        ingredient = Ingredient.objects.select_for_update().get(id=recipe.ingredient.id)
                        usage = Decimal(str(recipe.quantity)) * qty
                        if "sugar" in ingredient.name.lower() or "syrup" in ingredient.name.lower():
                            usage = usage * multiplier
                            
                        # Extra Shot Stock Deduction (Coffee Bean only)
                        if extra_shots > 0 and "bean" in ingredient.name.lower():
                            usage += Decimal('18') * Decimal(str(extra_shots)) * qty

                        ingredient.stock_quantity = max(Decimal('0.00'), ingredient.stock_quantity - usage)
                        if ingredient.initial_stock_per_item > 0:
                            ingredient.items_count = math.ceil(ingredient.stock_quantity / ingredient.initial_stock_per_item)
                        ingredient.save()

                        # LOG AUDIT FOR INGREDIENTS
                        StockHistory.objects.create(
                            ingredient=ingredient,
                            amount=-usage,
                            type='REDUCTION',
                            notes=f"Order #{new_order.id} ({product.name})"
                        )

                # --- B. SMART PACKAGING DEDUCTION ---
                if product_type == 'Hot':
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

                        # LOG AUDIT FOR PACKAGING
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

                        # LOG AUDIT FOR CARRIER
                        StockHistory.objects.create(
                            ingredient=carrier,
                            amount=-qty,
                            type='REDUCTION',
                            notes=f"Order #{new_order.id} Carrier"
                        )

                # --- D. CREATE ORDER ITEM WITH SNAPSHOTS ---
                price_at_sale = product.get_final_price(target_size, product_type)
                if extra_shots > 0:
                    price_at_sale += Decimal('0.50') * Decimal(str(extra_shots))

                # Loyalty Logic: Apply free drink and calculate points
                if redeem_free_drink and not free_drink_applied and target_size == 'Medium':
                    price_at_sale = Decimal('0.00')
                    free_drink_applied = True
                else:
                    total_earned_points += point_map.get(target_size, 0) * qty

                OrderItem.objects.create(
                    order=new_order, 
                    product=product, 
                    quantity=qty,
                    size=target_size, 
                    sugar=item.get('sugar', '100%'),
                    product_type=product_type,
                    # LOCK THE DATA: This makes your owner_view reports "Fixed"
                    price_at_sale=price_at_sale,
                    cost_at_sale=product.get_product_cost(target_size, product_type)
                )

            if customer:
                customer.points += total_earned_points
                customer.save()

        return JsonResponse({'status': 'success', 'order_id': new_order.id})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
def generate_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    html_string = render_to_string('invoice_pdf.html', {
        'order': order,
        'store_address': 'Street 404, Error City, Phnom Penh',
        'wifi_password': 'Error404_Coffee_Free',
        'now': timezone.localtime(timezone.now()),
    })
    
    # Allow fetching as HTML for the "Soft Invoice" preview in POS
    if request.GET.get('format') == 'html':
        return HttpResponse(html_string)

    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename="invoice_{order.id}.pdf"'
    
    if HAS_WEASYPRINT:
        weasyprint.HTML(string=html_string).write_pdf(response)
        return response
    else:
        return HttpResponse("PDF generation library (weasyprint) is not installed.", status=500)

def export_recipes_pdf(request):
    recipes = Recipe.objects.select_related('product', 'ingredient').all().order_by('product__name', 'size')
    # Calculate costs for display
    for r in recipes:
        r.line_cost = (r.ingredient.unit_cost or Decimal('0.00')) * r.quantity
        
    html_string = render_to_string('recipes_export_template.html', {'recipes': recipes, 'now': timezone.localtime(timezone.now())})
    response = HttpResponse(content_type="application/pdf")
    response['Content-Disposition'] = 'attachment; filename="recipe_export.pdf"'
    
    if HAS_WEASYPRINT:
        weasyprint.HTML(string=html_string).write_pdf(response)
        return response
    return HttpResponse("PDF generation library (weasyprint) is not installed.", status=500)

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

        with transaction.atomic():
            # Deduct stock based on your Recipe models
            for item in order.items.all():
                recipe_items = Recipe.objects.filter(product=item.product, size=item.size)
                for recipe in recipe_items:
                    recipe.deduct_stock(item.quantity)

        return JsonResponse({
            'status': 'success',
            'message': f'Order #{order.id} completed and stock deducted.'
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

#############################
####### Manager View ########
#############################

def is_manager(user):
    # This checks if the user is an admin OR in the 'Managers' group
    return user.is_staff or user.groups.filter(name='Managers').exists()

def manager_view(request):
    products = Product.objects.all()
    
    # --- 1. Recipe-Based Stock & Bottleneck Detection ---
    for product in products:
        recipes = Recipe.objects.filter(product=product).select_related('ingredient')
        if not recipes.exists():
            product.calculated_stock = 0
            product.limiting_ing = None
            continue
            
        servings_data = []
        for r in recipes:
            count = int(r.ingredient.stock_quantity / r.quantity) if r.ingredient.stock_quantity > 0 else 0
            servings_data.append({'count': count, 'ing': r.ingredient})
        
        bottleneck = min(servings_data, key=lambda x: x['count'])
        product.calculated_stock = bottleneck['count']
        product.limiting_ing = bottleneck['ing']

    # --- 2. Summary Stats (Today) ---
    today = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    todays_orders = Order.objects.filter(created_at__gte=today)
    
    total_income = todays_orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    total_profit = Decimal('0.00')
    total_expense = Decimal('0.00')
    total_cups = 0
    total_tax = Decimal('0.00') # This is order-based tax (VAT)
    
    items = OrderItem.objects.filter(order__in=todays_orders).select_related('product')
    for item in items:
        cost = item.cost_at_sale if item.cost_at_sale > 0 else item.product.get_product_cost(item.size)
        price = item.price_at_sale if item.price_at_sale > 0 else item.product.price_small
        
        total_expense += (cost * item.quantity)
        total_profit += ((price / Decimal('1.10')) - cost) * item.quantity
        total_cups += item.quantity

    for order in todays_orders:
        total_tax += order.tax_amount

    total_inventory_value = Ingredient.objects.aggregate(
        total=Sum(F('stock_quantity') * F('unit_cost'), output_field=DecimalField())
    )['total'] or Decimal('0.00')

    total_manual_loss = StockHistory.objects.filter(
        type='ADJUST', 
        amount__lt=0,
        created_at__gte=today
    ).aggregate(total=Sum(F('amount') * F('ingredient__unit_cost'), output_field=DecimalField()))['total'] or Decimal('0.00')

    # --- NEW: Annual Income Tax Calculation ---
    income_val = float(total_income)
    if income_val <= 4000:
        annual_rate = 0
    elif income_val <= 6000:
        annual_rate = 0.05
    elif income_val <= 25500:
        annual_rate = 0.10
    elif income_val <= 37500:
        annual_rate = 0.15
    else:
        annual_rate = 0.20
        
    annual_tax_amount = Decimal(str(income_val * annual_rate))
    net_after_annual_tax = total_income - annual_tax_amount

    avg_profitability = (float(total_profit) / float(total_income) * 100) if total_income > 0 else 0

    # --- 3. Initial Chart Data ---
    sales_by_hour = todays_orders.annotate(hour=ExtractHour('created_at')).values('hour').annotate(total=Sum('total_amount')).order_by('hour')
    chart_labels = [f"{item['hour']}:00" for item in sales_by_hour]
    chart_data = [float(item['total']) for item in sales_by_hour]

    context = {
        'products': products,
        'categories': Category.objects.all(),
        'total_income': total_income,
        'total_drinks_expense': total_expense,
        'total_inventory_value': total_inventory_value,
        'total_deducted_value': abs(total_manual_loss),
        'total_orders' : todays_orders.count(),
        'total_cups': total_cups,
        'total_tax': total_tax,
        'annual_tax_amount': annual_tax_amount, # Pass to manager.html
        'annual_tax_rate': int(annual_rate * 100), # Pass to manager.html
        'net_income_after_tax': net_after_annual_tax, # Pass to manager.html
        'avg_profitability': round(avg_profitability, 1), 
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'all_ingredients': Ingredient.objects.filter(is_packaging=False),
    }
    return render(request, 'manager.html', context)

def order_history_view(request):
    return render(request, 'order_history.html')

def api_order_history(request):
    # Fetch last 50 orders with related items and products to avoid N+1 queries
    orders = Order.objects.prefetch_related('items__product').all().order_by('-created_at')[:50]
    
    order_list = []
    for order in orders:
        items_data = [
            {
                'product_name': item.product.name,
                'quantity': item.quantity
            } for item in order.items.all()
        ]
        
        order_list.append({
            'id': order.id,
            'created_at': timezone.localtime(order.created_at).strftime('%d %b %Y | %H:%M'),
            'total_amount': float(order.total_amount),
            'is_completed': order.is_completed,
            'items': items_data
        })
        
    return JsonResponse({'orders': order_list})

def api_dashboard_stats(request):
    range_type = request.GET.get('range', 'today')
    now = timezone.localtime(timezone.now())
    current_month_name = now.strftime('%b')
    
    # --- 1. SET DATE RANGES & GROUPING ---
    if range_type == 'today':
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_func = ExtractHour
        label_fmt = lambda x: f"{x}:00"
    elif range_type == 'week':
        start_date = now - timedelta(days=now.weekday())
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_func = ExtractDay
        label_fmt = lambda x: f"{current_month_name} {x}"
    elif range_type == 'month':
        start_date = now.replace(day=1, hour=0, minute=0, second=0) 
        date_func = ExtractDay
        label_fmt = lambda x: f"{current_month_name} {x}"
    elif range_type == '30days':
        # Last 30 days: from yesterday back 30 days (e.g., if today is May 8, range is May 7 to Apr 8)
        start_date = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
        date_func = ExtractDay
        label_fmt = lambda x: f"{current_month_name} {x}"
    elif range_type == 'year':
        start_date = now.replace(month=1, day=1, hour=0, minute=0)
        date_func = ExtractMonth
        label_fmt = lambda x: calendar.month_name[x][:3]
    else:
        start_date = now.replace(hour=0, minute=0, second=0)
        date_func = ExtractHour
        label_fmt = lambda x: f"{x}:00"

    # --- 2. FINANCIAL CALCULATIONS ---
    orders = Order.objects.filter(created_at__gte=start_date)
    total_rev = orders.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
    
    # --- NEW: Annual Income Tax Logic for API ---
    income_val = float(total_rev)
    if income_val <= 4000:
        annual_rate = 0
    elif income_val <= 6000:
        annual_rate = 0.05
    elif income_val <= 25500:
        annual_rate = 0.10
    elif income_val <= 37500:
        annual_rate = 0.15
    else:
        annual_rate = 0.20
    
    annual_tax_amount = Decimal(str(income_val * annual_rate))
    net_after_annual_tax = total_rev - annual_tax_amount

    total_profit = Decimal('0.00')
    total_expense = Decimal('0.00')
    total_cups = 0
    total_tax = Decimal('0.00')
    
    items = OrderItem.objects.filter(order__in=orders).select_related('product')
    for item in items:
        price = item.price_at_sale if item.price_at_sale > 0 else item.product.price_small
        cost = item.cost_at_sale if item.cost_at_sale > 0 else item.product.get_product_cost(item.size)
        
        # Net income after 10% tax
        net_income_per_unit = price / Decimal('1.10')
        total_profit += (net_income_per_unit - cost) * item.quantity
        total_expense += cost * item.quantity
        total_cups += item.quantity

    for order in orders:
        total_tax += order.tax_amount

    total_inventory_value = Ingredient.objects.aggregate(
        total=Sum(F('stock_quantity') * F('unit_cost'), output_field=DecimalField())
    )['total'] or Decimal('0.00')

    total_manual_loss = StockHistory.objects.filter(
        type='ADJUST', 
        amount__lt=0,
        created_at__gte=start_date
    ).aggregate(total=Sum(F('amount') * F('ingredient__unit_cost'), output_field=DecimalField()))['total'] or Decimal('0.00')

    # Fixed: Margin ratio must be calculated AFTER the profit loop
    profit_margin_ratio = (float(total_profit) / float(total_rev)) if total_rev > 0 else 0

    # --- 3. EXPENSE TREND DATA ---
    revenue_trend_query = orders.annotate(
        unit=date_func('created_at')
    ).values('unit').annotate(
        total_rev=Sum('total_amount')
    ).order_by('unit')

    expense_trend_query = OrderItem.objects.filter(
        order__is_completed=True, 
        order__created_at__gte=start_date
    ).annotate(
        unit=date_func('order__created_at')
    ).values('unit').annotate(
        total_cost=Sum(
            F('quantity') * Case(
                When(cost_at_sale__gt=0, then=F('cost_at_sale')),
                default=F('product__price_small') * Value(Decimal('0.40')), 
                output_field=DecimalField()
            )
        )
    ).order_by('unit')

    # --- 4. POTENTIAL STOCK & product ANALYTICS ---
    products = Product.objects.all()
    product_stock_data = {}
    for product in products:
        recipes = Recipe.objects.filter(product=product).select_related('ingredient')
        
        # Calculate current live cost and profit
        # (Assuming your product model has these methods as discussed)
        current_cost = product.get_product_cost()
        current_profit = product.get_profit()

        if not recipes.exists():
            product_stock_data[product.id] = {
                'stock': 0, 
                'ing_id': None,
                'cost': float(current_cost),
                'profit': float(current_profit)
            }
            continue
            
        servings_data = []
        for r in recipes:
            count = int(r.ingredient.stock_quantity / r.quantity) if r.ingredient.stock_quantity > 0 else 0
            servings_data.append({'count': count, 'ing': r.ingredient})
        
        limit = min(servings_data, key=lambda x: x['count'])
        
        product_stock_data[product.id] = {
            'stock': limit['count'],
            'ing_id': limit['ing'].id,
            'ing_name': limit['ing'].name,
            'ing_size': float(limit['ing'].initial_stock_per_item),
            'ing_price': float(limit['ing'].last_purchase_price),
            'prices': {
                'S': float(product.price_small),
                'M': float(product.price_medium),
                'L': float(product.price_large)
            },
            'costs': {
                'Small': float(product.get_product_cost('Small')),
                'Medium': float(product.get_product_cost('Medium')),
                'Large': float(product.get_product_cost('Large'))
            },
            'profits': {
                'Small': float(product.get_profit('Small')),
                'Medium': float(product.get_profit('Medium')),
                'Large': float(product.get_profit('Large'))
            }
        }

    return JsonResponse({
        'income': float(total_rev),
        'total_drinks_expense': float(total_expense.quantize(Decimal('0.01'))),
        'inventory_value': float(total_inventory_value.quantize(Decimal('0.01'))),
        'deducted_value': float(abs(total_manual_loss).quantize(Decimal('0.01'))),
        'tax' : float(total_tax.quantize(Decimal('0.01'))),
        'annual_tax': float(annual_tax_amount.quantize(Decimal('0.01'))), # NEW
        'annual_rate': int(annual_rate * 100), # NEW
        'net_after_tax': float(net_after_annual_tax.quantize(Decimal('0.01'))), # NEW
        'profit': float(total_profit.quantize(Decimal('0.01'))),
        'margin_ratio': round(profit_margin_ratio, 2),
        'avg_profit': round((float(total_profit) / float(total_rev) * 100), 1) if total_rev > 0 else 0,
        'orders': orders.count(),
        'total_cups' : total_cups,
        'product_potentials': product_stock_data,
        'labels': [label_fmt(x['unit']) for x in revenue_trend_query],
        'sales_data': [float(x['total_rev']) for x in revenue_trend_query],
        'expense_data': [float(x['total_cost']) for x in expense_trend_query],
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
    recent_time = timezone.localtime(timezone.now()) - timedelta(hours=12)
    completed_orders = Order.objects.filter(
        is_completed=True, 
        created_at__gte=recent_time
    ).order_by('-created_at') # Newest first in history

    return render(request, 'kitchen.html', {
        'pending_orders': pending_orders,
        'completed_orders': completed_orders
    })