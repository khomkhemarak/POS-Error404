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
        ('Matcha', 'Matcha'),
        ('Other', 'Other'),
    )

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORIES, default='Coffee')
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    
    # Upcharges for specific preparations
    ice_upcharge = models.DecimalField(max_digits=6, decimal_places=2, default=0.50)
    frappe_upcharge = models.DecimalField(max_digits=6, decimal_places=2, default=1.00)

    # Availability toggles
    can_be_hot = models.BooleanField(default=True)
    can_be_iced = models.BooleanField(default=False)
    can_be_frappe = models.BooleanField(default=False)

    # Note: Stock here usually refers to pre-made items. 
    # For made-to-order drinks, we deduct from Ingredient stock instead.
    stock = models.IntegerField(default=0)

    def __str__(self):
        return self.name
    
    # --- CALCULATION METHODS ---

    def get_production_cost(self, size='Medium'):
        """
        Calculates total cost for a specific size based on Recipe 
        (Ingredients + Packaging linked in the Recipe table).
        """
        total_cost = Decimal('0.00')
        
        # Pulls all recipe entries for this product and size
        rules = self.recipes.filter(size=size) 
        
        for rule in rules:
            # Matches your Recipe model field 'quantity' and Ingredient 'unit_cost'
            cost_contribution = rule.quantity * rule.ingredient.unit_cost
            total_cost += cost_contribution
            
        return total_cost

    def get_final_price(self, drink_type='Hot'):
        """Calculates selling price including upcharges"""
        price = self.base_price
        if drink_type == 'Iced':
            price += self.ice_upcharge
        elif drink_type == 'Frappe':
            price += self.frappe_upcharge
        return price

    def get_profit_margin(self, size='Medium', drink_type='Hot'):
        """Profit = Adjusted Price - Production Cost"""
        return self.get_final_price(drink_type) - self.get_production_cost(size)

    def get_profit_percentage(self, size='Medium', drink_type='Hot'):
        """Returns profit % relative to the final selling price"""
        price = self.get_final_price(drink_type)
        if price > 0:
            margin = self.get_profit_margin(size, drink_type)
            return round((margin / price) * 100, 1)
        return 0

    # --- PACKAGING & LOGIC HELPERS ---
    
    def get_total_production_cost(self, size='Medium', drink_type='Hot', is_takeout=False):
        """
        Calculates cost including dynamic recipe ingredients and 
        on-the-fly packaging (like plastic carriers).
        """
        # 1. Start with the recipe-linked cost (beans, milk, cups, straws)
        cost = self.get_production_cost(size) 
        
        # 2. Add Plastic Carrier if it's Takeout (not usually in standard recipes)
        if is_takeout:
            # We reference your Ingredient PACKAGING_CHOICES
            from .models import Ingredient # Local import to avoid circularity
            carrier = Ingredient.objects.filter(packaging_type='CARRIER').first()
            if carrier:
                cost += carrier.unit_cost
                
        return cost

    # --- STOCK LOGIC ---
    
    def reduce_stock(self, quantity):
        """Used for pre-packaged retail items (e.g., bottled water)"""
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
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    size = models.CharField(max_length=20, default='Medium')
    sugar = models.CharField(max_length=20, default='100%')
    drink_type = models.CharField(max_length=20, default='Hot') 

    def __str__(self):
        return f"{self.quantity} x {self.product.name} ({self.drink_type})"



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

    unit_cost = models.DecimalField(max_digits=10, decimal_places=5, default=0.00)
    last_purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    is_packaging = models.BooleanField(default=False)
    packaging_type = models.CharField(max_length=20, choices=PACKAGING_CHOICES, default='NONE')

    def __str__(self):
        return f"{self.name} ({self.stock_quantity}{self.unit})"
    
    @property
    def stock_percent(self):
        """Calculates percentage based on total capacity (items * weight per item)"""
        # Using Decimal for precise calculation
        total_capacity = self.initial_stock_per_item * self.items_count

        if total_capacity <= 0:
            total_capacity = self.max_stock

        if total_capacity > 0:
            percentage = (self.stock_quantity / total_capacity) * 100
            return float(min(percentage, 100))
        return 0

    @property
    def is_low_stock(self):
        """Alert if stock is below 20% of capacity"""
        return self.stock_percent < 20
    
    def add_new_stock(self, new_items_count, price_paid):
        added_quantity = new_items_count * self.initial_stock_per_item
        self.items_count += new_items_count
        self.stock_quantity += added_quantity
        self.last_purchase_price = price_paid
        
        if added_quantity > 0:
            self.unit_cost = price_paid / added_quantity
        self.save()

    @property
    def safe_price(self):
        return self.unit_cost or Decimal('0.00')

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
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name='history')
    amount_added = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at'] # Shows newest updates first

class Customer(models.Model):
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField(null=True, blank=True)
    points = models.IntegerField(default=0)
    discount_rate = models.DecimalField(max_digits=4, decimal_places=2, default=10.00) # 10% discount
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.phone})"