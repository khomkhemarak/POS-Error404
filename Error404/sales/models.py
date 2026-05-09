from django.db import models
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name
class Product(models.Model):
    CATEGORIES = (
        ('Coffee', 'Coffee'),
        ('Tea', 'Tea'),
        ('Soft Drink', 'Soft Drink'),
        ('Other', 'Other'),
    )

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORIES, default='Coffee')
    price_small = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Price for Small (Tax Inclusive)")
    price_medium = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Price for Medium (Tax Inclusive)")
    price_large = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Price for Large (Tax Inclusive)")
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    
    # Pricing increments
    ice_upcharge = models.DecimalField(max_digits=6, decimal_places=2, default=0.25)
    frappe_upcharge = models.DecimalField(max_digits=6, decimal_places=2, default=0.50)

    # --- NEW FIELD ---
    is_available = models.BooleanField(default=True, help_text="Uncheck to hide from customer menu (Snooze)")

    # Availability toggles
    can_be_hot = models.BooleanField(default=True)
    can_be_iced = models.BooleanField(default=False)
    can_be_frappe = models.BooleanField(default=False)

    stock = models.IntegerField(default=0)

    def __str__(self):
        return self.name
    
    # --- DASHBOARD HELPER PROPERTIES ---

    @property
    def price(self):
        return self.price_small

    @property
    def total_cost(self):
        return self.get_product_cost(size='Small')

    @property
    def net_income(self):
        return round(self.price_small / Decimal('1.10'), 2)

    @property
    def profit_percentage(self):
        net_income = self.net_income
        total_cost = self.total_cost 
        if net_income <= 0 or total_cost <= 0:
            return 0
        real_profit = net_income - total_cost
        real_efficiency = (real_profit / total_cost) * 100
        return round(real_efficiency, 1)

    # --- PRICING & TAX LOGIC ---

    def get_final_price(self, size='Small', product_type='Hot'):
        # Force everything to Decimal to prevent "str + int" errors
        # We use Decimal(str()) as a safety net for any data type
        try:
            if size == 'Large':
                price = Decimal(str(self.price_large))
            elif size == 'Medium':
                price = Decimal(str(self.price_medium))
            else:
                price = Decimal(str(self.price_small))
        except (ValueError, TypeError):
            price = Decimal('0.00')

        # 2. Handle Product Type Upcharges
        try:
            if product_type == 'Iced':
                price += Decimal(str(self.ice_upcharge))
            elif product_type == 'Frappe':
                price += Decimal(str(self.frappe_upcharge))
        except (ValueError, TypeError):
            pass # Upcharge is 0 if invalid

        return price

    def get_net_income(self, size='Small', product_type='Hot'):
        total_price = self.get_final_price(size, product_type)
        return total_price / Decimal('1.10')

    def get_profit(self, size='Small', product_type='Hot'):
        net_income = self.get_net_income(size, product_type)
        product_cost = self.get_product_cost(size, product_type)
        return net_income - product_cost

    def get_product_cost(self, size='Small', product_type=None):
        # Determine default type if none provided (useful for dashboard fallbacks)
        if product_type is None:
            if self.can_be_hot: product_type = 'Hot'
            elif self.can_be_iced: product_type = 'Iced'
            elif self.can_be_frappe: product_type = 'Frappe'
            else: product_type = 'Hot'

        total_cost = Decimal('0.00')
        rules = self.recipes.filter(size=size) 
        for rule in rules:
            total_cost += rule.quantity * rule.ingredient.unit_cost
            
        # Add Standard Packaging Costs (Cup, Lid, Straw)
        pkg_cats = []
        if product_type == 'Hot':
            pkg_cats = ['HOT_CUP', 'HOT_LID', 'HOT_STRAW']
        else:
            pkg_cats = ['COLD_CUP', 'COLD_LID', 'COLD_STRAW']

        for cat in pkg_cats:
            query = Ingredient.objects.filter(packaging_type=cat)
            if cat in ['HOT_CUP', 'COLD_CUP']:
                query = query.filter(name__icontains=size)
            
            pkg_item = query.first()
            if pkg_item:
                total_cost += pkg_item.unit_cost
                
        return total_cost

    @property
    def real_profit(self):
        return self.net_income - self.total_cost

    @property
    def cost_medium(self): return self.get_product_cost('Medium')
    @property
    def cost_large(self): return self.get_product_cost('Large')

    @property
    def profit_medium(self): return self.get_profit('Medium')
    @property
    def profit_large(self): return self.get_profit('Large')


    def reduce_stock(self, quantity):
        if self.stock >= quantity:
            self.stock -= quantity
            self.save()
            return True
        return False
        
class ProductVariant(models.Model):
    # This handles things like Size: Large (+ $0.50)
    product = models.ForeignKey(Product, related_name='variants', on_delete=models.CASCADE)
    attribute_name = models.CharField(max_length=50) # e.g., 'Size' or 'Sugar'
    attribute_value = models.CharField(max_length=50) # e.g., 'Large' or '50%'
    price_modifier = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.product.name} - {self.attribute_name}: {self.attribute_value}"

class Order(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_completed = models.BooleanField(default=False)
    service_type = models.CharField(max_length=20, default='Dine-in')
    payment_method = models.CharField(max_length=20, default='Cash')
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0) # 10%
    cash_received = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cash_change = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cashier_name = models.CharField(max_length=100, blank=True, null=True)

    @property
    def tax_amount(self):
        """Calculates tax hidden inside the total price"""
        tax_divisor = 1 + (self.tax_rate / 100)
        subtotal = self.total_amount / tax_divisor
        return self.total_amount - subtotal

    @property
    def subtotal(self):
        """Total minus the tax"""
        return self.total_amount - self.tax_amount

    @property
    def subtotal_amount(self):
        return self.total_amount - self.tax_amount

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    size = models.CharField(max_length=20, default='Medium')
    sugar = models.CharField(max_length=20, default='100%')
    product_type = models.CharField(max_length=20, default='Hot')

    # --- ADD THESE TWO NEW FIELDS ---
    # This freezes the math so future menu changes don't ruin your past reports
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cost_at_sale = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # --------------------------------

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PREPARING', 'Preparing'),
        ('READY', 'Ready'),
        ('COMPLETED', 'Completed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    is_completed = models.BooleanField(default=False)

    @property
    def total_price(self):
        return self.price_at_sale * self.quantity

class Ingredient(models.Model):
    PACKAGING_CHOICES = (
        ('HOT_CUP', 'Hot Cup'),
        ('COLD_CUP', 'Cold Cup'),
        ('HOT_STRAW', 'Hot Straw'),
        ('COLD_STRAW', 'Cold/Frappe Straw'),
        ('CARRIER', 'Plastic Carrier'),
        ('HOT_LID', 'Hot Lid'),
        ('COLD_LID', 'Cold Lid'),
        ('NONE', 'None'),
    )

    name = models.CharField(max_length=100)
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    initial_stock_per_item = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    items_count = models.IntegerField(default=1) 
    max_stock = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    unit = models.CharField(max_length=10) 

    # unit_cost is the "Heart" of your profit summary
    unit_cost = models.DecimalField(max_digits=10, decimal_places=5, default=0.00)
    last_purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_packaging = models.BooleanField(default=False)
    packaging_type = models.CharField(max_length=20, choices=PACKAGING_CHOICES, default='NONE')

    def __str__(self):
        return f"{self.name} ({self.stock_quantity}{self.unit})"
    
    @property
    def stock_percent(self):
        capacity_from_boxes = self.initial_stock_per_item * self.items_count
        total_capacity = capacity_from_boxes if capacity_from_boxes > 0 else self.max_stock

        if total_capacity > 0:
            percentage = (self.stock_quantity / total_capacity) * 100
            return float(min(percentage, 100))
        return 0

    @property
    def is_low_stock(self):
        return self.stock_percent < 20

    @property
    def stock_value(self):
        return self.stock_quantity * self.unit_cost
    
    def add_new_stock(self, new_items_count, price_paid):
        """When you buy more, this automatically lowers/raises your product profits"""
        added_quantity = Decimal(str(new_items_count)) * self.initial_stock_per_item
        
        self.items_count += new_items_count
        self.stock_quantity += added_quantity

        # Store the price per single item (e.g. per box) to maintain consistent calculations
        if new_items_count > 0:
            self.last_purchase_price = Decimal(str(price_paid)) / Decimal(str(new_items_count))
        
        if added_quantity > 0:
            # Updating the cost-per-unit ensures the product profit is always live
            self.unit_cost = Decimal(str(price_paid)) / added_quantity
            
        self.save()

    @property
    def safe_price(self):
        """Ensures the calculation never breaks even if cost is missing"""
        return self.unit_cost if self.unit_cost else Decimal('0.00')

class Recipe(models.Model):
    SIZE_CHOICES = [
        ('Small', 'Small'),
        ('Medium', 'Medium'),
        ('Large', 'Large'),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='recipes')
    ingredient = models.ForeignKey('Ingredient', on_delete=models.CASCADE)
    size = models.CharField(max_length=10, choices=SIZE_CHOICES, default='Medium')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount in g, ml, or pcs")

    class Meta:
        unique_together = ('product', 'ingredient', 'size')

    def __str__(self):
        return f"{self.product.name} ({self.size}) - {self.ingredient.name}"

    def deduct_stock(self, orders_count=1):
        total_to_deduct = self.quantity * Decimal(str(orders_count))
        if self.ingredient.stock_quantity >= total_to_deduct:
            self.ingredient.stock_quantity -= total_to_deduct
            self.ingredient.save()
            return True
        return False
        
class RecipeRequirement(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='requirements')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    quantity_needed = models.DecimalField(max_digits=10, decimal_places=2) # e.g., 36 for beans, 1 for cup

    def __str__(self):
        return f"{self.quantity_needed} of {self.ingredient.name} for {self.recipe.name}"

class StockHistory(models.Model):
    # Define types of stock movements
    STOCK_TYPES = (
        ('RESTOCK', 'Manual Restock'),       # When you buy more beans
        ('REDUCTION', 'Order Deduction'),    # Automatically subtracted by an order
        ('ADJUST', 'Manual Adjustment'),     # Fixing a mistake or waste
    )

    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='history')
    
    # Amount used or added. Use negative numbers for deductions (e.g., -90.00)
    amount = models.DecimalField(max_digits=10, decimal_places=2) 
    
    # Type of movement
    type = models.CharField(max_length=20, choices=STOCK_TYPES, default='RESTOCK')
    
    # Context for the audit (e.g., "Order #51" or "Spilled bag")
    notes = models.CharField(max_length=255, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ingredient.name}: {self.amount} ({self.type})"

class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(null=True, blank=True)
    points = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"