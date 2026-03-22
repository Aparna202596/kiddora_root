# payments/urls.py
from django.urls import path
from payments.views import (
    wallet_views,
    razorpay_views,
    paypal_views,
)

app_name = "payments"

urlpatterns = [

    # ── WALLET ────────────────────────────────────────────────────────────────
    path("pay/wallet/<str:order_id>/",
         wallet_views.pay_with_wallet,
         name="pay_with_wallet"),
    path("pay/wallet/failure/<str:order_id>/",
         wallet_views.wallet_payment_failure,
         name="wallet_payment_failure"),

    # ── RAZORPAY ──────────────────────────────────────────────────────────────
    path("pay/razorpay/<str:order_id>/",
         razorpay_views.initiate_razorpay_payment,
         name="initiate_razorpay_payment"),
    path("pay/razorpay/verify/",
         razorpay_views.verify_razorpay_payment,
         name="verify_razorpay_payment"),
    path("pay/razorpay/failure/<str:order_id>/",
         razorpay_views.payment_failure,               # ← renamed / shared
         name="payment_failure"),
    path("pay/razorpay/retry/<str:order_id>/",
         razorpay_views.retry_payment,
         name="retry_razorpay_payment"),
    path("webhook/razorpay/",
         razorpay_views.razorpay_webhook,
         name="razorpay_webhook"),

    # COD route (if used separately)
    path("cod/confirm/<str:order_id>/",
         razorpay_views.cod_confirmation,             # or move to separate file later
         name="cod_confirmation"),

    # ── PAYPAL ────────────────────────────────────────────────────────────────
    path("pay/paypal/<str:order_id>/",
         paypal_views.initiate_paypal_payment,
         name="initiate_paypal_payment"),
    path("pay/paypal/return/",
         paypal_views.paypal_return,
         name="paypal_return"),
    path("pay/paypal/cancel/",
         paypal_views.paypal_cancel,
         name="paypal_cancel"),
    path("pay/paypal/failure/<str:order_id>/",
         paypal_views.paypal_payment_failure,
         name="paypal_payment_failure"),
    path("webhook/paypal/",
         paypal_views.paypal_webhook,
         name="paypal_webhook"),

    # ── ADMIN ─────────────────────────────────────────────────────────────────
    path("admin/payments/",
         razorpay_views.admin_payment_list,
         name="admin_payment_list"),
    path("admin/payments/<str:txn_id>/",
         razorpay_views.admin_payment_detail,
         name="admin_payment_detail"),
    path("admin/order/<str:order_id>/refund/",
         razorpay_views.admin_manual_refund,
         name="admin_manual_refund"),
]