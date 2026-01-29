from django.urls import path
from . import views

app_name = 'wallet'

urlpatterns = [

    path('admin/wallet/transactions/', views.admin_wallet_list, name='admin_wallet_list'),
    path('admin/wallet/transaction/', views.admin_wallet_detail, name='admin_wallet_detail'),
]