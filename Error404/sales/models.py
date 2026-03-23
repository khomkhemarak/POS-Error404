from django.db import models
from decimal import Decimal

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

from django.db import models
from decimal import Decimal

class Product(models.Model):
    CATEGORIES = (
        ('Coffee', 'Coffee'),
        ('Tea', 'Tea'),
        ('Matcha', 'Matcha'),
        ('Other', 'Other'),
    )

    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORIES, default='Coffee')
    base_price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Base Price for SMALL HOT (Tax Inclusive)")
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
        return self.base_price

    @property
    def total_cost(self):
        return self.get_production_cost(size='Small')

    @property
    def net_revenue(self):
        return round(self.base_price / Decimal('1.10'), 2)

    @property
    def margin_percentage(self):
        net_revenue = self.net_revenue
        total_cost = self.total_cost 
        if net_revenue <= 0 or total_cost <= 0:
            return 0
        real_profit = net_revenue - total_cost
        real_efficiency = (real_profit / total_cost) * 100
        return round(real_efficiency, 1)

    # --- PRICING & TAX LOGIC ---

    def get_final_price(self, size='Small', drink_type='Hot'):
        variant = getattr(self, 'variants', None)
        if variant:
            v_obj = variant.filter(attribute_value=size).first()
            price = self.base_price + (v_obj.price_modifier if v_obj else 0)
        else:
            price = self.base_price

        if drink_type == 'Iced':
            price += self.ice_upcharge
        elif drink_type == 'Frappe':
            price += self.frappe_upcharge
        return price

    def get_net_revenue(self, size='Small', drink_type='Hot'):
        total_price = self.get_final_price(size, drink_type)
        return total_price / Decimal('1.10')

    def get_profit_margin(self, size='Small', drink_type='Hot'):
        net_revenue = self.get_net_revenue(size, drink_type)
        production_cost = self.get_production_cost(size)
        return net_revenue - production_cost

    def get_production_cost(self, size='Small'):
        total_cost = Decimal('0.00')
        rules = self.recipes.filter(size=size) 
        for rule in rules:
            total_cost += rule.quantity * rule.ingredient.unit_cost
        return total_cost

    @property
    def real_profit(self):
        return self.net_revenue - self.total_cost

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
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10.0) # 10%

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

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    size = models.CharField(max_length=20, default='Medium')
    sugar = models.CharField(max_length=20, default='100%')
    drink_type = models.CharField(max_length=20, default='Hot')

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PREPARING', 'Preparing'),
        ('READY', 'Ready'),
        ('COMPLETED', 'Completed'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    is_completed = models.BooleanField(default=False)

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
    
    def add_new_stock(self, new_items_count, price_paid):
        """When you buy more, this automatically lowers/raises your product margins"""
        added_quantity = Decimal(str(new_items_count)) * self.initial_stock_per_item
        
        self.items_count += new_items_count
        self.stock_quantity += added_quantity
        self.last_purchase_price = price_paid
        
        if added_quantity > 0:
            # Updating the cost-per-unit ensures the Product margin is always live
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