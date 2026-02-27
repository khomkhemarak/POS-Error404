from django.db import models

class Category(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=100)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    category = models.CharField(max_length=50, default="Coffee") # Optional: Coffee, Tea, etc.

    def __str__(self):
        return self.name
    
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
    price = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True, null=True)

class Ingredient(models.Model):
    name = models.CharField(max_length=100) # e.g., "Whole Milk", "Espresso Beans"
    stock_quantity = models.DecimalField(max_digits=10, decimal_places=2) 
    unit = models.CharField(max_length=10, choices=[('g', 'Grams'), ('ml', 'Milliliters')])

    def __str__(self):
        return f"{self.name} ({self.stock_quantity}{self.unit})"

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