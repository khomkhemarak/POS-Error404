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
    
    ice_upcharge = models.DecimalField(max_digits=6, decimal_places=2, default=0.50)
    frappe_upcharge = models.DecimalField(max_digits=6, decimal_places=2, default=1.00)

    can_be_hot = models.BooleanField(default=True)
    can_be_iced = models.BooleanField(default=False)
    can_be_frappe = models.BooleanField(default=False)

    stock = models.IntegerField(default=0)

    def __str__(self):
        return self.name
    
    # --- CALCULATION METHODS ---

    def get_production_cost(self):
        """Calculates total cost based on Recipe Rules and Ingredient Unit Costs"""
        total_cost = Decimal('0.00')
        
        # Use the correct related_name 'recipes' defined in your Recipe model
        rules = self.recipes.all() 
        
        for rule in rules:
            # Calculate: amount_needed (Decimal) * ingredient unit_cost
            # Note: Ensure Ingredient has a unit_cost field
            cost_contribution = Decimal(str(rule.amount_needed)) * Decimal(str(rule.ingredient.unit_cost))
            total_cost += cost_contribution
            
        return total_cost

    def get_profit_margin(self):
        """Profit = Base Price - Production Cost"""
        return self.base_price - self.get_production_cost()

    def get_profit_percentage(self):
        """Returns the profit as a percentage of the base price"""
        cost = self.get_production_cost()
        if self.base_price > 0:
            percentage = (self.get_profit_margin() / self.base_price) * 100
            return round(percentage, 1)
        return 0

    # --- STOCK LOGIC ---
    
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
    name = models.CharField(max_length=100)
    # Total volume/weight (e.g., 3000.00)
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # The "1500" value you set when creating the ingredient
    initial_stock_per_item = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # The integer count (e.g., 2)
    items_count = models.IntegerField(default=1) 
    unit = models.CharField(max_length=10)

    # The cost per 1 unit (e.g., cost per 1 gram)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=5, default=0.00)
    last_purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.name} ({self.stock_quantity}{self.unit})"
    
    def get_stock_percent(self):
        # Assuming 5000 is your "Max/Full" stock for most items
        max_stock = 5000 
        return min((self.stock_quantity / max_stock) * 100, 100)
    
class Recipe(models.Model):
    SIZE_CHOICES = [
        ('Small', 'Small'),
        ('Medium', 'Medium'),
        ('Large', 'Large'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='recipes')
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE)
    size = models.CharField(max_length=10, choices=SIZE_CHOICES, default='Medium') # New Field
    amount_needed = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.FloatField() # e.g. 18.0 (grams or ml needed for 1 unit of product)

    def __str__(self):
        return f"{self.product.name} ({self.size}) - {self.ingredient.name}"
    
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