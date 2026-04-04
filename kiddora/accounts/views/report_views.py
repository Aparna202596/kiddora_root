from django.views.decorators.cache import never_cache
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.db.models import (
    Q, Sum, Count, F, Avg, Max, Min,
    DecimalField, ExpressionWrapper
)
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal
import json

from shopcore.models import (
    Order, OrderItem, Coupon, CouponUsage, Offer,
    ReferralCode, ReferralUse, Review, Return, Cart, CartItem, Wishlist
)
from accounts.models import CustomUser, UserAddress
from payments.models import Payment, Wallet, WalletTransaction
from products.models import (
    Product, Category, SubCategory, ProductVariant,
    Inventory, Color, AgeGroup, ProductImage
)
from accounts.decorators import admin_login_required

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# HELPER
# ─────────────────────────────────────────────────────────────────────────────

def get_date_range(request, default_days=10):
    """Parse start/end date from GET params; fall back to last `default_days` days."""
    today = timezone.now().date()
    start_str = request.GET.get('start_date', '').strip()
    end_str   = request.GET.get('end_date',   '').strip()
    if start_str and end_str:
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date   = datetime.strptime(end_str,   '%Y-%m-%d').date()
            if start_date <= end_date:
                return start_date, end_date
        except ValueError:
            pass
    return today - timedelta(days=default_days - 1), today


def safe_pct(numerator, denominator):
    """Return rounded percentage or 0."""
    if denominator:
        return round((numerator / denominator) * 100, 1)
    return 0


def growth_pct(current, previous):
    """Return growth % between two periods."""
    if previous:
        return round(((current - previous) / previous) * 100, 2)
    return 100 if current else 0


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_dashboard_view(request):
    start_date, end_date = get_date_range(request, default_days=10)
    period_days = (end_date - start_date).days + 1
    prev_start  = start_date - timedelta(days=period_days)
    prev_end    = start_date - timedelta(days=1)

    # ── Base querysets ──────────────────────────────────────────────────────
    orders_qs      = Order.objects.filter(
        order_date__date__gte=start_date,
        order_date__date__lte=end_date
    )
    paid_orders     = orders_qs.filter(payment_status='PAID')
    prev_orders_qs  = Order.objects.filter(
        order_date__date__gte=prev_start,
        order_date__date__lte=prev_end
    )
    prev_paid_orders = prev_orders_qs.filter(payment_status='PAID')
    items_qs        = OrderItem.objects.filter(order__in=orders_qs)

    # ── KPI: Orders ─────────────────────────────────────────────────────────
    total_orders      = orders_qs.count()
    completed_orders  = orders_qs.filter(order_status='DELIVERED').count()
    cancelled_orders  = orders_qs.filter(order_status='CANCELLED').count()
    pending_orders    = orders_qs.filter(order_status='PENDING').count()
    shipped_orders    = orders_qs.filter(order_status='SHIPPED').count()
    returned_orders   = orders_qs.filter(order_status='RETURNED').count()
    completion_rate   = safe_pct(completed_orders, total_orders)
    cancellation_rate = safe_pct(cancelled_orders, total_orders)

    prev_total_orders = prev_orders_qs.count()
    order_growth      = growth_pct(total_orders, prev_total_orders)

    # ── KPI: Revenue ────────────────────────────────────────────────────────
    total_revenue  = paid_orders.aggregate(s=Sum('final_amount'))['s'] or Decimal('0')
    prev_revenue   = prev_paid_orders.aggregate(s=Sum('final_amount'))['s'] or Decimal('0')
    revenue_growth = growth_pct(float(total_revenue), float(prev_revenue))

    avg_order_value = (
        paid_orders.aggregate(a=Avg('final_amount'))['a'] or Decimal('0')
    )
    total_discount  = orders_qs.aggregate(s=Sum('discount_amount'))['s'] or Decimal('0')
    coupon_discount = orders_qs.aggregate(s=Sum('coupon_discount'))['s'] or Decimal('0')
    shipping_revenue = orders_qs.aggregate(s=Sum('shipping_charge'))['s'] or Decimal('0')

    # ── KPI: Products / Inventory ───────────────────────────────────────────
    products_sold      = items_qs.aggregate(s=Sum('quantity'))['s'] or 0
    total_products     = Product.objects.filter(is_deleted=False).count()
    active_products    = Product.objects.filter(is_deleted=False, is_active=True).count()
    inactive_products  = total_products - active_products
    total_categories   = Category.objects.filter(is_deleted=False).count()
    total_subcategories = SubCategory.objects.filter(is_deleted=False).count()
    total_variants     = ProductVariant.objects.filter(is_active=True).count()
    total_stock        = Inventory.objects.aggregate(s=Sum('quantity_available'))['s'] or 0
    total_reserved     = Inventory.objects.aggregate(s=Sum('quantity_reserved'))['s'] or 0
    total_sold_stock   = Inventory.objects.aggregate(s=Sum('quantity_sold'))['s'] or 0
    low_stock_count    = Inventory.objects.filter(quantity_available__lte=5).count()
    out_of_stock_count = Inventory.objects.filter(quantity_available=0).count()

    # ── KPI: Customers ──────────────────────────────────────────────────────
    customer_qs   = CustomUser.objects.filter(role=CustomUser.ROLE_CUSTOMER, is_deleted=False)
    total_customers  = customer_qs.count()
    active_customers = customer_qs.filter(is_active=True).count()
    blocked_customers = customer_qs.filter(is_active=False).count()
    new_customers = customer_qs.filter(
        date_joined__date__gte=start_date,
        date_joined__date__lte=end_date
    ).count()
    prev_customers = customer_qs.filter(
        date_joined__date__gte=prev_start,
        date_joined__date__lte=prev_end
    ).count()
    customer_growth = growth_pct(new_customers, prev_customers)

    # Customers who placed an order in the period
    ordering_customers = orders_qs.values('user').distinct().count()
    repeat_customers   = (
        orders_qs.values('user')
        .annotate(c=Count('id'))
        .filter(c__gt=1)
        .count()
    )

    # ── KPI: Payments ───────────────────────────────────────────────────────
    payments_qs    = Payment.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    paid_payments    = payments_qs.filter(payment_status='PAID')
    failed_payments  = payments_qs.filter(payment_status='FAILED')
    refunded_amount  = payments_qs.filter(
        payment_status__in=['REFUNDED', 'PARTIALLY_REFUNDED']
    ).aggregate(s=Sum('amount'))['s'] or Decimal('0')

    paypal_revenue = paid_payments.filter(payment_method='PAYPAL').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    cod_revenue    = paid_payments.filter(payment_method='COD').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    wallet_revenue = paid_payments.filter(payment_method='WALLET').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # ── KPI: Wallets ─────────────────────────────────────────────────────────
    total_wallet_balance = Wallet.objects.aggregate(s=Sum('balance'))['s'] or Decimal('0')
    wallet_txns_qs       = WalletTransaction.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    wallet_credits  = wallet_txns_qs.filter(txn_type='CREDIT').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    wallet_debits   = wallet_txns_qs.filter(txn_type='DEBIT').aggregate(s=Sum('amount'))['s'] or Decimal('0')
    wallet_refunds  = wallet_txns_qs.filter(txn_type='REFUND').aggregate(s=Sum('amount'))['s'] or Decimal('0')

    # ── KPI: Coupons / Offers / Referrals ───────────────────────────────────
    total_coupons    = Coupon.objects.filter(is_deleted=False).count()
    active_coupons   = Coupon.objects.filter(is_deleted=False, is_active=True).count()
    coupon_uses      = CouponUsage.objects.aggregate(s=Sum('times_used'))['s'] or 0
    total_offers     = Offer.objects.filter(is_deleted=False).count()
    active_offers    = Offer.objects.filter(is_deleted=False, is_active=True).count()
    total_referrals  = ReferralCode.objects.count()
    referral_uses    = ReferralUse.objects.count()

    # ── KPI: Reviews / Returns ───────────────────────────────────────────────
    total_reviews    = Review.objects.count()
    approved_reviews = Review.objects.filter(is_approved=True).count()
    avg_rating       = Review.objects.aggregate(a=Avg('rating'))['a'] or 0
    total_returns    = Return.objects.count()
    approved_returns = Return.objects.filter(status='APPROVED').count()
    pending_returns  = Return.objects.filter(status='REQUESTED').count()
    refunded_returns = Return.objects.filter(status='REFUNDED').count()
    total_refund_amount = Return.objects.filter(
        status='REFUNDED'
    ).aggregate(s=Sum('refund_amount'))['s'] or Decimal('0')

    # ── KPI: Cart & Wishlist ─────────────────────────────────────────────────
    total_carts      = Cart.objects.count()
    cart_items_total = CartItem.objects.aggregate(s=Sum('quantity'))['s'] or 0
    total_wishlists  = Wishlist.objects.count()

    # ── Top Performers ──────────────────────────────────────────────────────
    top_products = (
        items_qs
        .values('variant__product__product_name')
        .annotate(total=Sum('quantity'), revenue=Sum('total_price'))
        .order_by('-total')[:10]
    )
    top_categories = (
        items_qs
        .values('variant__product__subcategory__category__category_name')
        .annotate(total=Sum('quantity'), revenue=Sum('total_price'))
        .order_by('-total')[:10]
    )
    top_brands = (
        items_qs
        .values('variant__product__brand')
        .annotate(total=Sum('quantity'), revenue=Sum('total_price'))
        .order_by('-total')[:10]
    )
    top_subcategories = (
        items_qs
        .values('variant__product__subcategory__subcategory_name')
        .annotate(total=Sum('quantity'), revenue=Sum('total_price'))
        .order_by('-total')[:5]
    )
    top_colors = (
        items_qs
        .values('variant__color__color')
        .annotate(total=Sum('quantity'))
        .order_by('-total')[:5]
    )
    top_age_groups = (
        items_qs
        .values('variant__age_group__age')
        .annotate(total=Sum('quantity'))
        .order_by('-total')[:5]
    )

    # ── Daily chart data (over the selected range, capped at 10 points) ──────
    num_points = min(period_days, 10)
    daily_labels   = []
    daily_revenue  = []
    products_per_day = []
    orders_per_day = []
    for i in range(num_points - 1, -1, -1):
        d = end_date - timedelta(days=i)
        daily_labels.append(d.strftime("%d %b"))
        day_orders = orders_qs.filter(order_date__date=d)
        daily_revenue.append(
            float(day_orders.aggregate(s=Sum('final_amount'))['s'] or 0)
        )
        products_per_day.append(
            int(OrderItem.objects.filter(order__in=day_orders).aggregate(s=Sum('quantity'))['s'] or 0)
        )
        orders_per_day.append(day_orders.count())

    # ── Monthly revenue (last 12 months) ─────────────────────────────────────
    today = timezone.now().date()
    monthly_labels  = []
    monthly_revenue = []
    for m in range(11, -1, -1):
        ref      = today.replace(day=1) - timedelta(days=m * 30)
        mo_start = ref.replace(day=1)
        if ref.month == 12:
            mo_end = ref.replace(month=12, day=31)
        else:
            mo_end = (ref.replace(month=ref.month + 1, day=1) - timedelta(days=1))
        rev = (
            Order.objects.filter(
                payment_status='PAID',
                order_date__date__gte=mo_start,
                order_date__date__lte=mo_end
            ).aggregate(s=Sum('final_amount'))['s'] or 0
        )
        monthly_labels.append(ref.strftime("%b %Y"))
        monthly_revenue.append(float(rev))

    # ── Order status & payment breakdown for charts ───────────────────────────
    status_data = dict(
        orders_qs.values('order_status')
        .annotate(count=Count('id'))
        .values_list('order_status', 'count')
    )
    payment_method_data = dict(
        paid_orders.values('payment_method')
        .annotate(count=Count('id'))
        .values_list('payment_method', 'count')
    )

    # ── Gender & fabric breakdown ────────────────────────────────────────────
    gender_data = dict(
        items_qs
        .values('variant__product__gender')
        .annotate(total=Sum('quantity'))
        .values_list('variant__product__gender', 'total')
    )
    fabric_data = (
        items_qs
        .values('variant__product__fabric')
        .annotate(total=Sum('quantity'))
        .order_by('-total')[:8]
    )

    # ── Recent orders for table ───────────────────────────────────────────────
    recent_orders = orders_qs.select_related('user', 'address').order_by('-order_date')[:20]

    # ── Low-stock items ──────────────────────────────────────────────────────
    low_stock_items = (
        Inventory.objects
        .filter(quantity_available__lte=5)
        .select_related('variant__product', 'variant__color', 'variant__age_group')
        .order_by('quantity_available')[:10]
    )

    context = {
        # Date range
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date':   end_date.strftime('%Y-%m-%d'),

        # Orders
        'total_orders':      total_orders,
        'completed_orders':  completed_orders,
        'cancelled_orders':  cancelled_orders,
        'pending_orders':    pending_orders,
        'shipped_orders':    shipped_orders,
        'returned_orders':   returned_orders,
        'completion_rate':   completion_rate,
        'cancellation_rate': cancellation_rate,
        'order_growth':      order_growth,

        # Revenue
        'total_revenue':     total_revenue,
        'prev_revenue':      prev_revenue,
        'revenue_growth':    revenue_growth,
        'avg_order_value':   avg_order_value,
        'total_discount':    total_discount,
        'coupon_discount':   coupon_discount,
        'shipping_revenue':  shipping_revenue,

        # Products / Inventory
        'products_sold':       products_sold,
        'total_products':      total_products,
        'active_products':     active_products,
        'inactive_products':   inactive_products,
        'total_categories':    total_categories,
        'total_subcategories': total_subcategories,
        'total_variants':      total_variants,
        'total_stock':         total_stock,
        'total_reserved':      total_reserved,
        'total_sold_stock':    total_sold_stock,
        'low_stock_count':     low_stock_count,
        'out_of_stock_count':  out_of_stock_count,

        # Customers
        'total_customers':    total_customers,
        'active_customers':   active_customers,
        'blocked_customers':  blocked_customers,
        'new_customers':      new_customers,
        'customer_growth':    customer_growth,
        'customer_growth_10days': customer_growth,
        'customer_growth_30days': customer_growth,
        'ordering_customers': ordering_customers,
        'repeat_customers':   repeat_customers,

        # Payments
        'paypal_revenue':  paypal_revenue,
        'cod_revenue':     cod_revenue,
        'wallet_revenue':  wallet_revenue,
        'refunded_amount': refunded_amount,
        'failed_payments': failed_payments.count(),

        # Wallets
        'total_wallet_balance': total_wallet_balance,
        'wallet_credits':       wallet_credits,
        'wallet_debits':        wallet_debits,
        'wallet_refunds':       wallet_refunds,

        # Coupons / Offers / Referrals
        'total_coupons':   total_coupons,
        'active_coupons':  active_coupons,
        'coupon_uses':     coupon_uses,
        'total_offers':    total_offers,
        'active_offers':   active_offers,
        'total_referrals': total_referrals,
        'referral_uses':   referral_uses,

        # Reviews / Returns
        'total_reviews':      total_reviews,
        'approved_reviews':   approved_reviews,
        'avg_rating':         round(float(avg_rating), 2),
        'total_returns':      total_returns,
        'approved_returns':   approved_returns,
        'pending_returns':    pending_returns,
        'refunded_returns':   refunded_returns,
        'total_refund_amount': total_refund_amount,

        # Cart / Wishlist
        'total_carts':      total_carts,
        'cart_items_total': cart_items_total,
        'total_wishlists':  total_wishlists,

        # Top performers
        'top_products':     top_products,
        'top_categories':   top_categories,
        'top_brands':       top_brands,
        'top_subcategories': top_subcategories,
        'top_colors':       top_colors,
        'top_age_groups':   top_age_groups,

        # Chart data
        'recent_orders':  recent_orders,
        'low_stock_items': low_stock_items,

        # JSON for charts
        'order_status_json':      json.dumps(status_data),
        'payment_methods_json':   json.dumps(payment_method_data),
        'daily_labels_json':      json.dumps(daily_labels),
        'daily_revenue_json':     json.dumps(daily_revenue),
        'products_per_day_json':  json.dumps(products_per_day),
        'orders_per_day_json':    json.dumps(orders_per_day),
        'monthly_labels_json':    json.dumps(monthly_labels),
        'monthly_revenue_json':   json.dumps(monthly_revenue),
        'gender_data_json':       json.dumps(gender_data),
        'top_products_labels_json': json.dumps([p['variant__product__product_name'] for p in top_products]),
        'top_products_data_json':   json.dumps([p['total'] for p in top_products]),
        'top_categories_labels_json': json.dumps([c['variant__product__subcategory__category__category_name'] for c in top_categories]),
        'top_categories_data_json':   json.dumps([c['total'] for c in top_categories]),
        'top_brands_labels_json': json.dumps([b['variant__product__brand'] for b in top_brands]),
        'top_brands_data_json':   json.dumps([b['total'] for b in top_brands]),
        'top_colors_labels_json': json.dumps([c['variant__color__color'] for c in top_colors]),
        'top_colors_data_json':   json.dumps([c['total'] for c in top_colors]),
        'top_ages_labels_json':   json.dumps([a['variant__age_group__age'] for a in top_age_groups]),
        'top_ages_data_json':     json.dumps([a['total'] for a in top_age_groups]),
    }
    return render(request, "accounts/admin/admin_dashboard.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# SALES REPORT
# ─────────────────────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_sales_report(request):
    start_date, end_date = get_date_range(request, default_days=10)
    report_type = request.GET.get('report_type', '').strip()

    # All paid orders in range
    orders_qs = Order.objects.filter(
        payment_status='PAID',
        order_date__date__gte=start_date,
        order_date__date__lte=end_date
    ).select_related('user', 'coupon', 'address')

    if report_type == 'daily':
        orders_qs = orders_qs.filter(order_date__date=start_date)
    elif report_type == 'weekly':
        week_start = end_date - timedelta(days=6)
        orders_qs = orders_qs.filter(
            order_date__date__gte=week_start,
            order_date__date__lte=end_date
        )

    items_qs = OrderItem.objects.filter(order__in=orders_qs)

    # ── Revenue aggregates ───────────────────────────────────────────────────
    total_sales        = orders_qs.aggregate(s=Sum('final_amount'))['s'] or Decimal('0')
    total_orders_count = orders_qs.count()
    items_sold         = items_qs.aggregate(s=Sum('quantity'))['s'] or 0
    total_discount     = orders_qs.aggregate(s=Sum('discount_amount'))['s'] or Decimal('0')
    coupon_discount    = orders_qs.aggregate(s=Sum('coupon_discount'))['s'] or Decimal('0')
    shipping_collected = orders_qs.aggregate(s=Sum('shipping_charge'))['s'] or Decimal('0')
    avg_order_value    = orders_qs.aggregate(a=Avg('final_amount'))['a'] or Decimal('0')
    max_order_value    = orders_qs.aggregate(m=Max('final_amount'))['m'] or Decimal('0')
    min_order_value    = orders_qs.aggregate(m=Min('final_amount'))['m'] or Decimal('0')
    gross_sales        = orders_qs.aggregate(s=Sum('total_amount'))['s'] or Decimal('0')
    net_sales          = total_sales  # after discount + coupon + shipping

    free_shipping_orders = orders_qs.filter(shipping_charge=0).count()
    paid_shipping_orders = total_orders_count - free_shipping_orders
    coupon_orders        = orders_qs.filter(coupon__isnull=False).count()

    # ── Returns / Refunds in range ─────────────────────────────────────────
    refund_qs            = Return.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )
    total_returns        = refund_qs.count()
    approved_returns     = refund_qs.filter(status='APPROVED').count()
    refunded_returns     = refund_qs.filter(status='REFUNDED').count()
    total_refund_amount  = refund_qs.filter(
        status='REFUNDED'
    ).aggregate(s=Sum('refund_amount'))['s'] or Decimal('0')
    return_rate          = safe_pct(total_returns, items_sold)

    # ── Top sellers in range ──────────────────────────────────────────────
    top_products_sales = (
        items_qs
        .values('variant__product__product_name')
        .annotate(qty=Sum('quantity'), rev=Sum('total_price'))
        .order_by('-rev')[:10]
    )
    top_categories_sales = (
        items_qs
        .values('variant__product__subcategory__category__category_name')
        .annotate(qty=Sum('quantity'), rev=Sum('total_price'))
        .order_by('-rev')[:10]
    )
    top_brands_sales = (
        items_qs
        .values('variant__product__brand')
        .annotate(qty=Sum('quantity'), rev=Sum('total_price'))
        .order_by('-rev')[:10]
    )

    # ── Payment breakdown ────────────────────────────────────────────────────
    paypal_sales = orders_qs.filter(payment_method='PAYPAL').aggregate(s=Sum('final_amount'))['s'] or Decimal('0')
    cod_sales    = orders_qs.filter(payment_method='COD').aggregate(s=Sum('final_amount'))['s'] or Decimal('0')
    wallet_sales = orders_qs.filter(payment_method='WALLET').aggregate(s=Sum('final_amount'))['s'] or Decimal('0')
    paypal_count = orders_qs.filter(payment_method='PAYPAL').count()
    cod_count    = orders_qs.filter(payment_method='COD').count()
    wallet_count = orders_qs.filter(payment_method='WALLET').count()

    # ── Daily chart data ─────────────────────────────────────────────────────
    period_days = (end_date - start_date).days + 1
    num_points  = min(period_days, 10)
    daily_labels       = []
    daily_revenue_list = []
    daily_orders_list  = []
    daily_items_list   = []
    for i in range(num_points - 1, -1, -1):
        d = end_date - timedelta(days=i)
        daily_labels.append(d.strftime("%d %b"))
        day_orders = orders_qs.filter(order_date__date=d)
        daily_revenue_list.append(
            float(day_orders.aggregate(s=Sum('final_amount'))['s'] or 0)
        )
        daily_orders_list.append(day_orders.count())
        daily_items_list.append(
            int(items_qs.filter(order__in=day_orders).aggregate(s=Sum('quantity'))['s'] or 0)
        )

    # ── Order status breakdown ───────────────────────────────────────────────
    all_orders_in_range = Order.objects.filter(
        order_date__date__gte=start_date,
        order_date__date__lte=end_date
    )
    status_breakdown = dict(
        all_orders_in_range.values('order_status')
        .annotate(c=Count('id'))
        .values_list('order_status', 'c')
    )
    payment_breakdown = dict(
        orders_qs.values('payment_method')
        .annotate(c=Count('id'))
        .values_list('payment_method', 'c')
    )

    context = {
        # Date / filter
        'start_date':  start_date.strftime('%Y-%m-%d'),
        'end_date':    end_date.strftime('%Y-%m-%d'),
        'report_type': report_type,

        # Revenue KPIs
        'total_sales':        total_sales,
        'gross_sales':        gross_sales,
        'net_sales':          net_sales,
        'total_orders':       total_orders_count,
        'items_sold':         items_sold,
        'total_discount':     total_discount,
        'coupon_discount':    coupon_discount,
        'shipping_collected': shipping_collected,
        'avg_order_value':    avg_order_value,
        'max_order_value':    max_order_value,
        'min_order_value':    min_order_value,
        'free_shipping_orders': free_shipping_orders,
        'paid_shipping_orders': paid_shipping_orders,
        'coupon_orders':      coupon_orders,

        # Returns
        'total_returns':       total_returns,
        'approved_returns':    approved_returns,
        'refunded_returns':    refunded_returns,
        'total_refund_amount': total_refund_amount,
        'return_rate':         return_rate,

        # Payment breakdown
        'paypal_sales':  paypal_sales,
        'cod_sales':     cod_sales,
        'wallet_sales':  wallet_sales,
        'paypal_count':  paypal_count,
        'cod_count':     cod_count,
        'wallet_count':  wallet_count,

        # Top sellers
        'top_products_sales':    top_products_sales,
        'top_categories_sales':  top_categories_sales,
        'top_brands_sales':      top_brands_sales,

        # Orders table
        'orders': orders_qs.order_by('-order_date'),

        # JSON charts
        'daily_labels_json':      json.dumps(daily_labels),
        'daily_revenue_json':     json.dumps(daily_revenue_list),
        'daily_orders_json':      json.dumps(daily_orders_list),
        'daily_items_json':       json.dumps(daily_items_list),
        'status_breakdown_json':  json.dumps(status_breakdown),
        'payment_breakdown_json': json.dumps(payment_breakdown),
        'top_products_labels_json':    json.dumps([p['variant__product__product_name'] for p in top_products_sales]),
        'top_products_rev_json':       json.dumps([float(p['rev']) for p in top_products_sales]),
        'top_categories_labels_json':  json.dumps([c['variant__product__subcategory__category__category_name'] for c in top_categories_sales]),
        'top_categories_rev_json':     json.dumps([float(c['rev']) for c in top_categories_sales]),
        'top_brands_labels_json':      json.dumps([b['variant__product__brand'] for b in top_brands_sales]),
        'top_brands_rev_json':         json.dumps([float(b['rev']) for b in top_brands_sales]),
    }
    return render(request, "accounts/admin/admin_sales_report.html", context)