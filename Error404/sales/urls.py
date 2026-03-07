from django.urls import path
from . import views

urlpatterns = [
    # The main Barista/Cashier Dashboard
    path('pos/', views.pos_view, name='pos_home'),
    path('check-stock/<int:product_id>/', views.check_stock, name='check_stock'),
    path('api/customer-lookup/', views.customer_lookup, name='customer_lookup'),
    path('api/register-customer/', views.register_customer, name='register_customer'),

    # API endpoints for the Frontend to talk to the Backend
    path('api/process-payment/', views.process_payment, name='process_payment'),
    
    # Kitchen Display System (KDS) - to see active tickets
    path('kitchen/', views.kitchen_view, name='kitchen_view'),
    path('kitchen/complete/<int:order_id>/', views.complete_order, name='complete_order'),

    # Admin Dashboard for managing products, categories, and orders
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('add-product/', views.add_product, name='add_product'),
    path('edit-product/<int:product_id>/', views.edit_product, name='edit_product'),
    path('delete-product/<int:product_id>/', views.delete_product, name='delete_product'),
    path('recipe-builder/', views.recipe_builder, name='recipe_builder'),
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/add/', views.add_ingredient, name='add_ingredient'),
    path('inventory/delete/<int:pk>/', views.delete_ingredient, name='delete_ingredient'),
]