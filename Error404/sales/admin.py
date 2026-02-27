from django.contrib import admin
from .models import Category, Product, Order, OrderItem

# This makes the models visible in the /admin dashboard
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Order)
admin.site.register(OrderItem)