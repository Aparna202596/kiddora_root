from django.urls import path
from .views import payment_views
from .views import wallet_payment_views

app_name = 'payments'

urlpatterns = [
    path('user/payment/initiate/', payment_views.initiate_payment, name='initiate_payment'),
    path('user/payment/success/', payment_views.payment_success, name='payment_success'),
    path('user/payment/failed/', payment_views.payment_failed, name='payment_failed'),
    path('user/payment/retry/', payment_views.retry_payment, name='retry_payment'),

    path('user/profile/wallet/pay/', wallet_payment_views.wallet_payment, name='wallet_payment'),
]