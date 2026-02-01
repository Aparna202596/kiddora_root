from django.urls import path
from orders.views import admin_order_views
from orders.views import user_order_views

app_name = 'orders'

urlpatterns = [
    #Admin order URLs
    path('admin/orders/', admin_order_views.admin_order_list, name='admin_order_list'),
    path('admin/orders/order_details/<int:order_id>/',admin_order_views.admin_order_detail,name='admin_order_detail'),
    path('admin/orders/update_order_status/<int:order_id>/',admin_order_views.admin_update_order_status,name='admin_update_order_status'),
    path('admin/handle_return',admin_order_views.admin_handle_return,name='admin_handle_return'),

    #User order URLs
    path('user/orders/', user_order_views.user_orders, name='user_orders'),
    path('user/orders/place_orders/', user_order_views.place_order, name='place_order'),
    path('user/orders/details/', user_order_views.order_detail, name='order_detail'),
    path('user/orders/cancel_order/', user_order_views.cancel_order, name='cancel_order'),
    path('user/orders/cancel_order_item/', user_order_views.cancel_order_item_view, name='cancel_order_item'),
    path('user/orders/invoice/', user_order_views.download_invoice, name='download_invoice'),
]