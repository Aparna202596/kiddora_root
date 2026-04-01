from django.urls import path
from payments.views import paypal_views, wallet_views

app_name = "payments"

urlpatterns = [

#    ────────────────────── PAYPAL ──────────────────────
    # Step 1: Buyer clicks "Pay with PayPal" and we redirect them to PayPal
    path("paypal/initiate/<str:order_id>/", paypal_views.initiate_paypal_payment, name="initiate_paypal_payment"),
    
    # Step 2: PayPal redirects back to our site after payment approval
    path("paypal/callback/", paypal_views.paypal_callback, name="paypal_callback"),
    
    # Step 3: PayPal redirects back to our site if the buyer cancels the payment
    path("paypal/cancel/", paypal_views.paypal_cancel, name="paypal_cancel"),
    
    # Step 4: PayPal sends webhook notifications for payment events (e.g., completed, failed)
    path("paypal/webhook/", paypal_views.paypal_webhook, name="paypal_webhook"),
    
    # Step 5: Display success or failure pages based on the payment outcome
    path("paypal/success/<str:order_id>/",paypal_views.paypal_success, name="paypal_success"),
    
    # Step 6: Handle payment failure (e.g., show error message, allow retry)
    path("paypal/failure/<str:order_id>/", paypal_views.paypal_failure, name="paypal_failure", ),
    
    # Step 7: Allow users to retry payment if it failed
    path("paypal/retry/<str:order_id>/", paypal_views.retry_payment, name="retry_payment"),

# ────────────────────── WALLET ──────────────────────
    path("wallet/pay/<str:order_id>/", wallet_views.pay_with_wallet, name="pay_with_wallet"),
    path("wallet/failure/<str:order_id>/", wallet_views.wallet_payment_failure, name="wallet_payment_failure"),
    path("wallet/balance/", wallet_views.wallet_balance, name="wallet_balance"),

    path("admin/payments/",wallet_views.admin_payment_list, name="admin_payment_list"),

    path("admin/wallet/", wallet_views.admin_wallet_list, name="admin_wallet_list"),
    path("admin/wallet/<uuid:txn_id>/", wallet_views.admin_wallet_detail, name="admin_wallet_detail"),
]