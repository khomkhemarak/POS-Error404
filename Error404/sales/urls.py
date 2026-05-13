from django.urls import path
from . import views

urlpatterns = [
    # --- Authentication ---
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/confirm/', views.password_reset_confirm, name='password_reset_confirm'),
    
    # --- POS & Customer Management ---
    path('pos/', views.pos_view, name='pos_home'),
    path('check-stock/<int:product_id>/', views.check_stock, name='check_stock'),
    path('api/check-product-stock/', views.check_product_stock, name='check_product_stock'),
    path('api/customer-lookup/', views.customer_lookup, name='customer_lookup'),
    path('api/register-customer/', views.register_customer, name='register_customer'),
    path('api/process-payment/', views.process_payment, name='process_payment'),
    path('api/order-items/', views.api_order_items, name='api_order_items'),
    path('api/drink-requests/', views.api_drink_requests, name='api_drink_requests'),
    path('api/drink-requests/create/', views.create_drink_request, name='create_drink_request'),
    path('api/drink-requests/accept/<int:request_id>/', views.accept_drink_request, name='accept_drink_request'),
    path('api/drink-requests/<int:request_id>/mark-refunded/', views.mark_drink_request_refunded, name='mark_drink_request_refunded'),
    path('api/drink-requests/resolved/', views.api_resolved_drink_requests, name='api_resolved_drink_requests'),
    
    # --- Kitchen Display System (KDS) ---
    path('kitchen/', views.kitchen_view, name='kitchen_view'),
    path('api/kitchen/complete/<int:order_id>/', views.complete_order, name='complete_order'),
    
    # --- Owner & product Management ---
    path('dashboard/', views.owner_view, name='owner'),
    path('add-product/', views.add_product, name='add_product'),
    path('edit-product/<int:product_id>/', views.edit_product, name='edit_product'),
    path('delete-product/<int:product_id>/', views.delete_product, name='delete_product'),
    path('generate-daily-report/', views.generate_daily_report, name='generate_daily_report'),
    path('recipe-builder/', views.recipe_builder, name='recipe_builder'),
    
    # --- Inventory Management ---
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/add/', views.add_ingredient, name='add_ingredient'),
    
    # Unified Stock Update (Points to the API view for silent refreshing)
    path('inventory/update/<int:pk>/', views.api_update_stock, name='update_stock'),
    path('inventory/deduct/<int:pk>/', views.api_deduct_stock, name='deduct_stock'),
    
    path('inventory/rename/<int:pk>/', views.rename_ingredient, name='rename_ingredient'),
    path('inventory/delete/<int:pk>/', views.delete_ingredient, name='delete_ingredient'),

    # --- API Data Endpoints (For Real-Time Sync) ---
    # This endpoint allows the inventory page to fetch fresh numbers without a reload
    path('api/inventory/list/', views.api_inventory_list, name='api_inventory_list'),
    path('api/inventory/logs/', views.api_inventory_logs, name='api_inventory_logs'),
    path('api/dashboard-stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/inventory/raw-materials/', views.api_raw_materials, name='api_raw_materials'),

    # --- Managerial Analytics ---
    path('manager/', views.manager_view, name='manager_display'),
    path('orders/history/', views.order_history_view, name='order_history'),
    path('api/orders/history/', views.api_order_history, name='api_order_history'),

    # --- Invoice & Document Exports ---
    path('invoice/<int:order_id>/', views.generate_invoice, name='generate_invoice'),
    path('export-recipes/', views.export_recipes_pdf, name='export_recipes_pdf'),
]