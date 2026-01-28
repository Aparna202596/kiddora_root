from django.urls import path
from .views import payment_views
from .views import wallet_payment_views

app_name = 'payments'

urlpatterns = [
    path('payment/initiate/<int:order_id>/', payment_views.initiate_payment, name='initiate_payment'),
    path('razorpay/success/', payment_views.payment_success, name='payment_success'),
    path('razorpay/failed/<int:payment_id>/', payment_views.payment_failed, name='payment_failed'),
    path('razorpay/retry/<int:payment_id>/', payment_views.retry_payment, name='retry_payment'),

    path('wallet/pay/<int:order_id>/', wallet_payment_views.wallet_payment, name='wallet_payment'),
]