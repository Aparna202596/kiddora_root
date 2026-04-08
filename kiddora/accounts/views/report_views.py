import io
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal

from accounts.decorators import admin_login_required
from accounts.models import CustomUser, UserAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import (Avg, Count, DecimalField, ExpressionWrapper, F,
                              Max, Min, Q, Sum)
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from payments.models import Payment, Wallet, WalletTransaction
from products.models import (AgeGroup, Category, Color, Inventory, Product,
                             ProductImage, ProductVariant, SubCategory)
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (HRFlowable, Image, KeepTogether, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)
from shopcore.models import (Cart, CartItem, Coupon, CouponUsage, Offer, Order,
                             OrderItem, ReferralCode, ReferralUse, Return,
                             Review, Wishlist)

User = get_user_model()


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────


def get_date_range(request, default_days=10):
    today = timezone.now().date()
    start_str = request.GET.get("start_date", "").strip()
    end_str = request.GET.get("end_date", "").strip()
    if start_str and end_str:
        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
            if start_date <= end_date:
                return start_date, end_date
        except ValueError:
            pass
    return today - timedelta(days=default_days - 1), today


def safe_pct(numerator, denominator):
    if denominator:
        return round((numerator / denominator) * 100, 1)
    return 0


def growth_pct(current, previous):
    if previous:
        return round(((current - previous) / previous) * 100, 2)
    return 100 if current else 0


def _register_fonts():
    """Register fonts for PDF generation — falls back gracefully."""
    try:
        font_path = os.path.join(settings.BASE_DIR, "static/fonts/arial.ttf")
        if not os.path.exists(font_path):
            font_path = "C:/Windows/Fonts/arial.ttf"
        if os.path.exists(font_path):
            pdfmetrics.registerFont(TTFont("ReportFont", font_path))
            pdfmetrics.registerFont(TTFont("ReportFont-Bold", font_path))
            return "ReportFont", "ReportFont-Bold"
    except Exception:
        pass
    return "Helvetica", "Helvetica-Bold"


def _logo_path():
    candidates = [
        os.path.join(settings.BASE_DIR, "static/images/kiddora_logo.PNG"),
        os.path.join(settings.BASE_DIR, "static/images/kiddora_logo.png"),
        (
            os.path.join(settings.STATICFILES_DIRS[0], "images/kiddora_logo.PNG")
            if getattr(settings, "STATICFILES_DIRS", [])
            else None
        ),
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return None


def _build_pdf_header(
    elements, font_regular, font_bold, title_text, subtitle_text, start_date, end_date
):
    """Shared header block for both PDF reports."""
    # Logo
    logo = _logo_path()
    if logo:
        img = Image(logo, width=130, height=50)
        img.hAlign = "LEFT"
        elements.append(img)
    elements.append(Spacer(1, 8))

    # Brand name + title row
    now_str = datetime.now().strftime("%d %B %Y, %I:%M %p")
    # header_data = [
    #     [
    #         # Paragraph(f'<font size="18" color="#d98ab2"><b>KIDDORA</b></font>', ParagraphStyle("h", fontName=font_bold)),
    #         Paragraph(f'<font size="9" color="#64748b">Downloaded: {now_str}</font>', ParagraphStyle("dt", fontName=font_regular, alignment=2)),
    #     ]
    # ]
    # ht = Table(header_data, colWidths=[10 * cm, 9 * cm])
    # ht.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    # elements.append(ht)
    # elements.append(Spacer(1, 6))
    # elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#e8a1c6")))
    # elements.append(Spacer(1, 10))

    # Report title
    elements.append(
        Paragraph(
            f'<font size="16" color="#1e293b"><b>{title_text}</b></font>',
            ParagraphStyle("title", fontName=font_bold, spaceAfter=4),
        )
    )
    elements.append(
        Paragraph(
            f'<font size="10" color="#64748b">{subtitle_text}</font>',
            ParagraphStyle("sub", fontName=font_regular, spaceAfter=4),
        )
    )

    # Period banner
    period_data = [
        [
            Paragraph(
                f'<font size="10" color="white"><b>Report Period: {start_date} → {end_date}</b></font>',
                ParagraphStyle("p", fontName=font_bold),
            ),
            Paragraph(
                f'<font size="9" color="white">Downloaded on {now_str}</font>',
                ParagraphStyle("p2", fontName=font_regular, alignment=2),
            ),
        ]
    ]
    pt = Table(period_data, colWidths=[11 * cm, 8 * cm])
    pt.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("ROUNDEDCORNERS", [6]),
            ]
        )
    )
    elements.append(pt)
    elements.append(Spacer(1, 16))


def _section_heading(text, font_bold, color="#1e293b"):
    return Paragraph(
        f'<font size="11" color="{color}"><b>{text}</b></font>',
        ParagraphStyle("sh", fontName=font_bold, spaceBefore=14, spaceAfter=6),
    )


def _kpi_table(rows_data, font_regular, font_bold, col_count=4):
    """Build a coloured KPI grid table from list of (label, value) tuples."""
    BG_COLORS = [
        "#dbeafe",
        "#dcfce7",
        "#fef3c7",
        "#ede9fe",
        "#f0fdf4",
        "#fee2e2",
        "#f3e8ff",
        "#dbeafe",
    ]
    TEXT_COLORS = [
        "#1e40af",
        "#166534",
        "#92400e",
        "#5b21b6",
        "#14532d",
        "#991b1b",
        "#6b21a8",
        "#1e40af",
    ]
    # Pad to full rows
    while len(rows_data) % col_count != 0:
        rows_data.append(("", ""))

    table_rows = []
    for i in range(0, len(rows_data), col_count):
        chunk = rows_data[i : i + col_count]
        label_row = []
        value_row = []
        for j, (label, value) in enumerate(chunk):
            idx = (i + j) % len(BG_COLORS)
            label_row.append(
                Paragraph(
                    f'<font size="8" color="{TEXT_COLORS[idx]}">{label}</font>',
                    ParagraphStyle("kl", fontName=font_regular),
                )
            )
            value_row.append(
                Paragraph(
                    f'<font size="14" color="{TEXT_COLORS[idx]}"><b>{value}</b></font>',
                    ParagraphStyle("kv", fontName=font_bold),
                )
            )

        # Combine into single-row cells (label above value)
        cell_row = []
        for j, (label, value) in enumerate(chunk):
            idx = (i + j) % len(BG_COLORS)
            cell_row.append(
                Paragraph(
                    f'<font size="8" color="{TEXT_COLORS[idx]}">{label}</font><br/>'
                    f'<font size="13" color="{TEXT_COLORS[idx]}"><b>{value}</b></font>',
                    ParagraphStyle(
                        "kc", fontName=font_regular, leading=18, spaceAfter=0
                    ),
                )
            )
        table_rows.append(cell_row)

    col_w = 19 * cm / col_count
    t = Table(table_rows, colWidths=[col_w] * col_count)
    style_cmds = [
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e8ecf0")),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f8fafc")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    # Apply per-cell background
    for row_i, row in enumerate(table_rows):
        for col_i in range(len(row)):
            global_idx = row_i * col_count + col_i
            bg_idx = global_idx % len(BG_COLORS)
            style_cmds.append(
                (
                    "BACKGROUND",
                    (col_i, row_i),
                    (col_i, row_i),
                    colors.HexColor(BG_COLORS[bg_idx]),
                )
            )

    t.setStyle(TableStyle(style_cmds))
    return t


def _data_table(headers, rows, font_regular, font_bold, col_widths=None):
    """Build a striped data table."""
    header_cells = [
        Paragraph(
            f'<font size="9" color="white"><b>{h}</b></font>',
            ParagraphStyle("th", fontName=font_bold, alignment=1),
        )
        for h in headers
    ]
    table_data = [header_cells]
    for row in rows:
        table_data.append(
            [
                Paragraph(
                    f'<font size="8">{str(c)}</font>',
                    ParagraphStyle("td", fontName=font_regular),
                )
                for c in row
            ]
        )

    if not col_widths:
        col_widths = [19 * cm / len(headers)] * len(headers)

    t = Table(table_data, colWidths=col_widths)
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d98ab2")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_regular),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e8ecf0")),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#f8fafc")],
            ),
        ]
    )
    t.setStyle(style)
    return t


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN DASHBOARD VIEW
# ─────────────────────────────────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_dashboard_view(request):
    start_date, end_date = get_date_range(request, default_days=10)
    period_days = (end_date - start_date).days + 1
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date - timedelta(days=1)

    orders_qs = Order.objects.filter(
        order_date__date__gte=start_date, order_date__date__lte=end_date
    )
    paid_orders = orders_qs.filter(payment_status="PAID")
    prev_orders_qs = Order.objects.filter(
        order_date__date__gte=prev_start, order_date__date__lte=prev_end
    )
    prev_paid_orders = prev_orders_qs.filter(payment_status="PAID")
    items_qs = OrderItem.objects.filter(order__in=orders_qs)

    total_orders = orders_qs.count()
    completed_orders = orders_qs.filter(order_status="DELIVERED").count()
    cancelled_orders = orders_qs.filter(order_status="CANCELLED").count()
    pending_orders = orders_qs.filter(order_status="PENDING").count()
    shipped_orders = orders_qs.filter(order_status="SHIPPED").count()
    returned_orders = orders_qs.filter(order_status="RETURNED").count()
    completion_rate = safe_pct(completed_orders, total_orders)
    cancellation_rate = safe_pct(cancelled_orders, total_orders)
    prev_total_orders = prev_orders_qs.count()
    order_growth = growth_pct(total_orders, prev_total_orders)

    total_revenue = paid_orders.aggregate(s=Sum("final_amount"))["s"] or Decimal("0")
    prev_revenue = prev_paid_orders.aggregate(s=Sum("final_amount"))["s"] or Decimal(
        "0"
    )
    revenue_growth = growth_pct(float(total_revenue), float(prev_revenue))
    avg_order_value = paid_orders.aggregate(a=Avg("final_amount"))["a"] or Decimal("0")
    total_discount = orders_qs.aggregate(s=Sum("discount_amount"))["s"] or Decimal("0")
    coupon_discount = orders_qs.aggregate(s=Sum("coupon_discount"))["s"] or Decimal("0")
    shipping_revenue = orders_qs.aggregate(s=Sum("shipping_charge"))["s"] or Decimal(
        "0"
    )

    products_sold = items_qs.aggregate(s=Sum("quantity"))["s"] or 0
    total_products = Product.objects.filter(is_deleted=False).count()
    active_products = Product.objects.filter(is_deleted=False, is_active=True).count()
    inactive_products = total_products - active_products
    total_categories = Category.objects.filter(is_deleted=False).count()
    total_subcategories = SubCategory.objects.filter(is_deleted=False).count()
    total_variants = ProductVariant.objects.filter(is_active=True).count()
    total_stock = Inventory.objects.aggregate(s=Sum("quantity_available"))["s"] or 0
    total_reserved = Inventory.objects.aggregate(s=Sum("quantity_reserved"))["s"] or 0
    total_sold_stock = Inventory.objects.aggregate(s=Sum("quantity_sold"))["s"] or 0
    low_stock_count = Inventory.objects.filter(quantity_available__lte=5).count()
    out_of_stock_count = Inventory.objects.filter(quantity_available=0).count()

    customer_qs = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER, is_deleted=False
    )
    total_customers = customer_qs.count()
    active_customers = customer_qs.filter(is_active=True).count()
    blocked_customers = customer_qs.filter(is_active=False).count()
    new_customers = customer_qs.filter(
        date_joined__date__gte=start_date, date_joined__date__lte=end_date
    ).count()
    prev_customers = customer_qs.filter(
        date_joined__date__gte=prev_start, date_joined__date__lte=prev_end
    ).count()
    customer_growth = growth_pct(new_customers, prev_customers)
    ordering_customers = orders_qs.values("user").distinct().count()
    repeat_customers = (
        orders_qs.values("user").annotate(c=Count("id")).filter(c__gt=1).count()
    )

    payments_qs = Payment.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    )
    paid_payments = payments_qs.filter(payment_status="PAID")
    failed_payments = payments_qs.filter(payment_status="FAILED")
    refunded_amount = payments_qs.filter(
        payment_status__in=["REFUNDED", "PARTIALLY_REFUNDED"]
    ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    paypal_revenue = paid_payments.filter(payment_method="PAYPAL").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    cod_revenue = paid_payments.filter(payment_method="COD").aggregate(s=Sum("amount"))[
        "s"
    ] or Decimal("0")
    wallet_revenue = paid_payments.filter(payment_method="WALLET").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")

    total_wallet_balance = Wallet.objects.aggregate(s=Sum("balance"))["s"] or Decimal(
        "0"
    )
    wallet_txns_qs = WalletTransaction.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    )
    wallet_credits = wallet_txns_qs.filter(txn_type="CREDIT").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    wallet_debits = wallet_txns_qs.filter(txn_type="DEBIT").aggregate(s=Sum("amount"))[
        "s"
    ] or Decimal("0")
    wallet_refunds = wallet_txns_qs.filter(txn_type="REFUND").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")

    total_coupons = Coupon.objects.filter(is_deleted=False).count()
    active_coupons = Coupon.objects.filter(is_deleted=False, is_active=True).count()
    coupon_uses = CouponUsage.objects.aggregate(s=Sum("times_used"))["s"] or 0
    total_offers = Offer.objects.filter(is_deleted=False).count()
    active_offers = Offer.objects.filter(is_deleted=False, is_active=True).count()
    total_referrals = ReferralCode.objects.count()
    referral_uses = ReferralUse.objects.count()

    total_reviews = Review.objects.count()
    approved_reviews = Review.objects.filter(is_approved=True).count()
    avg_rating = Review.objects.aggregate(a=Avg("rating"))["a"] or 0
    total_returns = Return.objects.count()
    approved_returns = Return.objects.filter(status="APPROVED").count()
    pending_returns = Return.objects.filter(status="REQUESTED").count()
    refunded_returns = Return.objects.filter(status="REFUNDED").count()
    total_refund_amount = Return.objects.filter(status="REFUNDED").aggregate(
        s=Sum("refund_amount")
    )["s"] or Decimal("0")

    total_carts = Cart.objects.count()
    cart_items_total = CartItem.objects.aggregate(s=Sum("quantity"))["s"] or 0
    total_wishlists = Wishlist.objects.count()

    top_products = (
        items_qs.values("variant__product__product_name")
        .annotate(total=Sum("quantity"), revenue=Sum("total_price"))
        .order_by("-total")[:10]
    )
    top_categories = (
        items_qs.values("variant__product__subcategory__category__category_name")
        .annotate(total=Sum("quantity"), revenue=Sum("total_price"))
        .order_by("-total")[:10]
    )
    top_brands = (
        items_qs.values("variant__product__brand")
        .annotate(total=Sum("quantity"), revenue=Sum("total_price"))
        .order_by("-total")[:10]
    )
    top_subcategories = (
        items_qs.values("variant__product__subcategory__subcategory_name")
        .annotate(total=Sum("quantity"), revenue=Sum("total_price"))
        .order_by("-total")[:5]
    )
    top_colors = (
        items_qs.values("variant__color__color")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:5]
    )
    top_age_groups = (
        items_qs.values("variant__age_group__age")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:5]
    )

    num_points = min(period_days, 10)
    daily_labels, daily_revenue, products_per_day, orders_per_day = [], [], [], []
    for i in range(num_points - 1, -1, -1):
        d = end_date - timedelta(days=i)
        daily_labels.append(d.strftime("%d %b"))
        day_orders = orders_qs.filter(order_date__date=d)
        daily_revenue.append(
            float(day_orders.aggregate(s=Sum("final_amount"))["s"] or 0)
        )
        products_per_day.append(
            int(
                OrderItem.objects.filter(order__in=day_orders).aggregate(
                    s=Sum("quantity")
                )["s"]
                or 0
            )
        )
        orders_per_day.append(day_orders.count())

    today_date = timezone.now().date()
    monthly_labels, monthly_revenue = [], []
    for m in range(11, -1, -1):
        ref = today_date.replace(day=1) - timedelta(days=m * 30)
        mo_start = ref.replace(day=1)
        mo_end = (
            (ref.replace(month=ref.month + 1, day=1) - timedelta(days=1))
            if ref.month != 12
            else ref.replace(month=12, day=31)
        )
        rev = (
            Order.objects.filter(
                payment_status="PAID",
                order_date__date__gte=mo_start,
                order_date__date__lte=mo_end,
            ).aggregate(s=Sum("final_amount"))["s"]
            or 0
        )
        monthly_labels.append(ref.strftime("%b %Y"))
        monthly_revenue.append(float(rev))

    status_data = dict(
        orders_qs.values("order_status")
        .annotate(count=Count("id"))
        .values_list("order_status", "count")
    )
    payment_method_data = dict(
        paid_orders.values("payment_method")
        .annotate(count=Count("id"))
        .values_list("payment_method", "count")
    )
    gender_data = dict(
        items_qs.values("variant__product__gender")
        .annotate(total=Sum("quantity"))
        .values_list("variant__product__gender", "total")
    )

    recent_orders = orders_qs.select_related("user", "address").order_by("-order_date")[
        :20
    ]
    low_stock_items = (
        Inventory.objects.filter(quantity_available__lte=5)
        .select_related("variant__product", "variant__color", "variant__age_group")
        .order_by("quantity_available")[:10]
    )

    context = {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "total_orders": total_orders,
        "completed_orders": completed_orders,
        "cancelled_orders": cancelled_orders,
        "pending_orders": pending_orders,
        "shipped_orders": shipped_orders,
        "returned_orders": returned_orders,
        "completion_rate": completion_rate,
        "cancellation_rate": cancellation_rate,
        "order_growth": order_growth,
        "total_revenue": total_revenue,
        "prev_revenue": prev_revenue,
        "revenue_growth": revenue_growth,
        "avg_order_value": avg_order_value,
        "total_discount": total_discount,
        "coupon_discount": coupon_discount,
        "shipping_revenue": shipping_revenue,
        "products_sold": products_sold,
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": inactive_products,
        "total_categories": total_categories,
        "total_subcategories": total_subcategories,
        "total_variants": total_variants,
        "total_stock": total_stock,
        "total_reserved": total_reserved,
        "total_sold_stock": total_sold_stock,
        "low_stock_count": low_stock_count,
        "out_of_stock_count": out_of_stock_count,
        "total_customers": total_customers,
        "active_customers": active_customers,
        "blocked_customers": blocked_customers,
        "new_customers": new_customers,
        "customer_growth": customer_growth,
        "customer_growth_10days": customer_growth,
        "customer_growth_30days": customer_growth,
        "ordering_customers": ordering_customers,
        "repeat_customers": repeat_customers,
        "prev_customers": prev_customers,
        "paypal_revenue": paypal_revenue,
        "cod_revenue": cod_revenue,
        "wallet_revenue": wallet_revenue,
        "refunded_amount": refunded_amount,
        "failed_payments": failed_payments.count(),
        "total_wallet_balance": total_wallet_balance,
        "wallet_credits": wallet_credits,
        "wallet_debits": wallet_debits,
        "wallet_refunds": wallet_refunds,
        "total_coupons": total_coupons,
        "active_coupons": active_coupons,
        "coupon_uses": coupon_uses,
        "total_offers": total_offers,
        "active_offers": active_offers,
        "total_referrals": total_referrals,
        "referral_uses": referral_uses,
        "total_reviews": total_reviews,
        "approved_reviews": approved_reviews,
        "avg_rating": round(float(avg_rating), 2),
        "total_returns": total_returns,
        "approved_returns": approved_returns,
        "pending_returns": pending_returns,
        "refunded_returns": refunded_returns,
        "total_refund_amount": total_refund_amount,
        "total_carts": total_carts,
        "cart_items_total": cart_items_total,
        "total_wishlists": total_wishlists,
        "top_products": top_products,
        "top_categories": top_categories,
        "top_brands": top_brands,
        "top_subcategories": top_subcategories,
        "top_colors": top_colors,
        "top_age_groups": top_age_groups,
        "recent_orders": recent_orders,
        "low_stock_items": low_stock_items,
        "order_status_json": json.dumps(status_data),
        "payment_methods_json": json.dumps(payment_method_data),
        "daily_labels_json": json.dumps(daily_labels),
        "daily_revenue_json": json.dumps(daily_revenue),
        "products_per_day_json": json.dumps(products_per_day),
        "orders_per_day_json": json.dumps(orders_per_day),
        "monthly_labels_json": json.dumps(monthly_labels),
        "monthly_revenue_json": json.dumps(monthly_revenue),
        "gender_data_json": json.dumps(gender_data),
        "top_products_labels_json": json.dumps(
            [p["variant__product__product_name"] for p in top_products]
        ),
        "top_products_data_json": json.dumps([p["total"] for p in top_products]),
        "top_categories_labels_json": json.dumps(
            [
                c["variant__product__subcategory__category__category_name"]
                for c in top_categories
            ]
        ),
        "top_categories_data_json": json.dumps([c["total"] for c in top_categories]),
        "top_brands_labels_json": json.dumps(
            [b["variant__product__brand"] for b in top_brands]
        ),
        "top_brands_data_json": json.dumps([b["total"] for b in top_brands]),
        "top_colors_labels_json": json.dumps(
            [c["variant__color__color"] for c in top_colors]
        ),
        "top_colors_data_json": json.dumps([c["total"] for c in top_colors]),
        "top_ages_labels_json": json.dumps(
            [a["variant__age_group__age"] for a in top_age_groups]
        ),
        "top_ages_data_json": json.dumps([a["total"] for a in top_age_groups]),
    }
    return render(request, "accounts/admin/admin_dashboard.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD PDF DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────


@never_cache
@admin_login_required
def download_dashboard_pdf(request):
    start_date, end_date = get_date_range(request, default_days=10)
    period_days = (end_date - start_date).days + 1
    prev_start = start_date - timedelta(days=period_days)
    prev_end = start_date - timedelta(days=1)

    orders_qs = Order.objects.filter(
        order_date__date__gte=start_date, order_date__date__lte=end_date
    )
    paid_orders = orders_qs.filter(payment_status="PAID")
    prev_orders_qs = Order.objects.filter(
        order_date__date__gte=prev_start, order_date__date__lte=prev_end
    )
    prev_paid_orders = prev_orders_qs.filter(payment_status="PAID")
    items_qs = OrderItem.objects.filter(order__in=orders_qs)

    # ── Collect all metrics (same as dashboard view) ──
    total_orders = orders_qs.count()
    completed_orders = orders_qs.filter(order_status="DELIVERED").count()
    cancelled_orders = orders_qs.filter(order_status="CANCELLED").count()
    pending_orders = orders_qs.filter(order_status="PENDING").count()
    shipped_orders = orders_qs.filter(order_status="SHIPPED").count()
    returned_orders = orders_qs.filter(order_status="RETURNED").count()
    completion_rate = safe_pct(completed_orders, total_orders)
    cancellation_rate = safe_pct(cancelled_orders, total_orders)
    order_growth = growth_pct(total_orders, prev_orders_qs.count())

    total_revenue = paid_orders.aggregate(s=Sum("final_amount"))["s"] or Decimal("0")
    prev_revenue = prev_paid_orders.aggregate(s=Sum("final_amount"))["s"] or Decimal(
        "0"
    )
    revenue_growth = growth_pct(float(total_revenue), float(prev_revenue))
    avg_order_value = paid_orders.aggregate(a=Avg("final_amount"))["a"] or Decimal("0")
    total_discount = orders_qs.aggregate(s=Sum("discount_amount"))["s"] or Decimal("0")
    coupon_discount = orders_qs.aggregate(s=Sum("coupon_discount"))["s"] or Decimal("0")
    shipping_revenue = orders_qs.aggregate(s=Sum("shipping_charge"))["s"] or Decimal(
        "0"
    )

    products_sold = items_qs.aggregate(s=Sum("quantity"))["s"] or 0
    total_products = Product.objects.filter(is_deleted=False).count()
    active_products = Product.objects.filter(is_deleted=False, is_active=True).count()
    total_categories = Category.objects.filter(is_deleted=False).count()
    total_stock = Inventory.objects.aggregate(s=Sum("quantity_available"))["s"] or 0
    total_reserved = Inventory.objects.aggregate(s=Sum("quantity_reserved"))["s"] or 0
    low_stock_count = Inventory.objects.filter(quantity_available__lte=5).count()
    out_of_stock_count = Inventory.objects.filter(quantity_available=0).count()

    customer_qs = CustomUser.objects.filter(
        role=CustomUser.ROLE_CUSTOMER, is_deleted=False
    )
    total_customers = customer_qs.count()
    active_customers = customer_qs.filter(is_active=True).count()
    blocked_customers = customer_qs.filter(is_active=False).count()
    new_customers = customer_qs.filter(
        date_joined__date__gte=start_date, date_joined__date__lte=end_date
    ).count()
    prev_customers = customer_qs.filter(
        date_joined__date__gte=prev_start, date_joined__date__lte=prev_end
    ).count()
    customer_growth = growth_pct(new_customers, prev_customers)
    ordering_customers = orders_qs.values("user").distinct().count()
    repeat_customers = (
        orders_qs.values("user").annotate(c=Count("id")).filter(c__gt=1).count()
    )

    payments_qs = Payment.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    )
    paid_payments = payments_qs.filter(payment_status="PAID")
    paypal_revenue = paid_payments.filter(payment_method="PAYPAL").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    cod_revenue = paid_payments.filter(payment_method="COD").aggregate(s=Sum("amount"))[
        "s"
    ] or Decimal("0")
    wallet_revenue = paid_payments.filter(payment_method="WALLET").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    failed_payments_count = payments_qs.filter(payment_status="FAILED").count()
    total_wallet_balance = Wallet.objects.aggregate(s=Sum("balance"))["s"] or Decimal(
        "0"
    )
    wallet_txns_qs = WalletTransaction.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    )
    wallet_credits = wallet_txns_qs.filter(txn_type="CREDIT").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")
    wallet_debits = wallet_txns_qs.filter(txn_type="DEBIT").aggregate(s=Sum("amount"))[
        "s"
    ] or Decimal("0")
    wallet_refunds = wallet_txns_qs.filter(txn_type="REFUND").aggregate(
        s=Sum("amount")
    )["s"] or Decimal("0")

    total_coupons = Coupon.objects.filter(is_deleted=False).count()
    active_coupons = Coupon.objects.filter(is_deleted=False, is_active=True).count()
    coupon_uses = CouponUsage.objects.aggregate(s=Sum("times_used"))["s"] or 0
    total_offers = Offer.objects.filter(is_deleted=False).count()
    active_offers = Offer.objects.filter(is_deleted=False, is_active=True).count()
    total_referrals = ReferralCode.objects.count()
    referral_uses = ReferralUse.objects.count()

    total_reviews = Review.objects.count()
    approved_reviews = Review.objects.filter(is_approved=True).count()
    avg_rating = round(float(Review.objects.aggregate(a=Avg("rating"))["a"] or 0), 2)
    total_returns = Return.objects.count()
    approved_returns = Return.objects.filter(status="APPROVED").count()
    pending_returns = Return.objects.filter(status="REQUESTED").count()
    refunded_returns = Return.objects.filter(status="REFUNDED").count()
    total_refund_amount = Return.objects.filter(status="REFUNDED").aggregate(
        s=Sum("refund_amount")
    )["s"] or Decimal("0")

    top_products = list(
        items_qs.values("variant__product__product_name")
        .annotate(total=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-total")[:10]
    )
    top_categories = list(
        items_qs.values("variant__product__subcategory__category__category_name")
        .annotate(total=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-total")[:10]
    )
    top_brands = list(
        items_qs.values("variant__product__brand")
        .annotate(total=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-total")[:10]
    )
    recent_orders = list(orders_qs.select_related("user").order_by("-order_date")[:15])
    low_stock_items = list(
        Inventory.objects.filter(quantity_available__lte=5)
        .select_related("variant__product", "variant__color", "variant__age_group")
        .order_by("quantity_available")[:10]
    )

    # ── Build PDF ──
    font_regular, font_bold = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    elements = []
    fs = start_date.strftime("%Y-%m-%d")
    fe = end_date.strftime("%Y-%m-%d")

    _build_pdf_header(
        elements,
        font_regular,
        font_bold,
        "Admin Dashboard Report",
        "Complete analytics overview for Kiddora admin",
        fs,
        fe,
    )

    # ── ORDER KPIs ──
    elements.append(_section_heading("Order Analytics", font_bold, "#1e40af"))
    order_kpis = [
        ("Total Orders", str(total_orders)),
        ("Delivered", str(completed_orders)),
        ("Pending", str(pending_orders)),
        ("Shipped", str(shipped_orders)),
        ("Cancelled", str(cancelled_orders)),
        ("Returned", str(returned_orders)),
        ("Completion Rate", f"{completion_rate}%"),
        ("Cancellation Rate", f"{cancellation_rate}%"),
        ("Order Growth", f"{order_growth}%"),
        ("Prev Period Orders", str(prev_orders_qs.count())),
        ("Ordering Customers", str(ordering_customers)),
        ("Repeat Customers", str(repeat_customers)),
    ]
    elements.append(_kpi_table(order_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── REVENUE KPIs ──
    elements.append(_section_heading("Revenue Analytics", font_bold, "#166534"))
    rev_kpis = [
        ("Total Revenue", f"₹{total_revenue:,.0f}"),
        ("Prev Revenue", f"₹{prev_revenue:,.0f}"),
        ("Revenue Growth", f"{revenue_growth}%"),
        ("Avg Order Value", f"₹{avg_order_value:,.0f}"),
        ("Total Discounts", f"₹{total_discount:,.0f}"),
        ("Coupon Savings", f"₹{coupon_discount:,.0f}"),
        ("Shipping Revenue", f"₹{shipping_revenue:,.0f}"),
        ("Refunded Amount", f"₹{total_refund_amount:,.0f}"),
    ]
    elements.append(_kpi_table(rev_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── CUSTOMER KPIs ──
    elements.append(_section_heading("Customer Analytics", font_bold, "#5b21b6"))
    cust_kpis = [
        ("Total Customers", str(total_customers)),
        ("Active Customers", str(active_customers)),
        ("Blocked Customers", str(blocked_customers)),
        ("New (Period)", str(new_customers)),
        ("Customer Growth", f"{customer_growth}%"),
        ("Prev Period New", str(prev_customers)),
        ("Ordering Customers", str(ordering_customers)),
        ("Repeat Customers", str(repeat_customers)),
    ]
    elements.append(_kpi_table(cust_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── PRODUCT & INVENTORY KPIs ──
    elements.append(
        _section_heading("Product & Inventory Analytics", font_bold, "#0f766e")
    )
    prod_kpis = [
        ("Total Products", str(total_products)),
        ("Active Products", str(active_products)),
        ("Total Categories", str(total_categories)),
        ("Total Stock", str(total_stock)),
        ("Reserved Stock", str(total_reserved)),
        ("Items Sold (Period)", str(products_sold)),
        ("Low Stock (≤5)", str(low_stock_count)),
        ("Out of Stock", str(out_of_stock_count)),
    ]
    elements.append(_kpi_table(prod_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── PAYMENT & WALLET KPIs ──
    elements.append(
        _section_heading("Payment & Wallet Analytics", font_bold, "#92400e")
    )
    pay_kpis = [
        ("PayPal Revenue", f"₹{paypal_revenue:,.0f}"),
        ("COD Revenue", f"₹{cod_revenue:,.0f}"),
        ("Wallet Revenue", f"₹{wallet_revenue:,.0f}"),
        ("Wallet Balance", f"₹{total_wallet_balance:,.0f}"),
        ("Wallet Credits", f"₹{wallet_credits:,.0f}"),
        ("Wallet Debits", f"₹{wallet_debits:,.0f}"),
        ("Wallet Refunds", f"₹{wallet_refunds:,.0f}"),
        ("Failed Payments", str(failed_payments_count)),
    ]
    elements.append(_kpi_table(pay_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── COUPON / OFFER / REFERRAL KPIs ──
    elements.append(
        _section_heading("Coupons, Offers & Referrals", font_bold, "#be185d")
    )
    misc_kpis = [
        ("Total Coupons", str(total_coupons)),
        ("Active Coupons", str(active_coupons)),
        ("Coupon Uses", str(coupon_uses)),
        ("Total Offers", str(total_offers)),
        ("Active Offers", str(active_offers)),
        ("Referral Codes", str(total_referrals)),
        ("Referral Uses", str(referral_uses)),
        ("Total Reviews", str(total_reviews)),
        ("Approved Reviews", str(approved_reviews)),
        ("Avg Rating", f"{avg_rating}★"),
        ("Total Returns", str(total_returns)),
        ("Pending Returns", str(pending_returns)),
        ("Approved Returns", str(approved_returns)),
        ("Refunded Returns", str(refunded_returns)),
        ("Refund Amount", f"₹{total_refund_amount:,.0f}"),
        ("", ""),
    ]
    elements.append(_kpi_table(misc_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 14))

    # ── TOP PRODUCTS TABLE ──
    elements.append(_section_heading("Top 10 Products by Quantity Sold", font_bold))
    if top_products:
        elements.append(
            _data_table(
                ["#", "Product Name", "Qty Sold", "Revenue (₹)"],
                [
                    (
                        i + 1,
                        p["variant__product__product_name"],
                        p["total"],
                        f"₹{p['rev']:,.2f}",
                    )
                    for i, p in enumerate(top_products)
                ],
                font_regular,
                font_bold,
                col_widths=[1 * cm, 10 * cm, 3.5 * cm, 4.5 * cm],
            )
        )
    else:
        elements.append(
            Paragraph(
                "No product data for this period.",
                ParagraphStyle("n", fontName=font_regular),
            )
        )
    elements.append(Spacer(1, 10))

    # ── TOP CATEGORIES TABLE ──
    elements.append(_section_heading("Top 10 Categories by Quantity Sold", font_bold))
    if top_categories:
        elements.append(
            _data_table(
                ["#", "Category", "Qty Sold", "Revenue (₹)"],
                [
                    (
                        i + 1,
                        c["variant__product__subcategory__category__category_name"],
                        c["total"],
                        f"₹{c['rev']:,.2f}",
                    )
                    for i, c in enumerate(top_categories)
                ],
                font_regular,
                font_bold,
                col_widths=[1 * cm, 10 * cm, 3.5 * cm, 4.5 * cm],
            )
        )
    else:
        elements.append(
            Paragraph(
                "No category data for this period.",
                ParagraphStyle("n", fontName=font_regular),
            )
        )
    elements.append(Spacer(1, 10))

    # ── TOP BRANDS TABLE ──
    elements.append(_section_heading("Top Brands by Quantity Sold", font_bold))
    if top_brands:
        elements.append(
            _data_table(
                ["#", "Brand", "Qty Sold", "Revenue (₹)"],
                [
                    (
                        i + 1,
                        b["variant__product__brand"],
                        b["total"],
                        f"₹{b['rev']:,.2f}",
                    )
                    for i, b in enumerate(top_brands)
                ],
                font_regular,
                font_bold,
                col_widths=[1 * cm, 10 * cm, 3.5 * cm, 4.5 * cm],
            )
        )
    else:
        elements.append(
            Paragraph(
                "No brand data for this period.",
                ParagraphStyle("n", fontName=font_regular),
            )
        )
    elements.append(Spacer(1, 10))

    # ── RECENT ORDERS TABLE ──
    elements.append(_section_heading("Recent Orders (Last 15)", font_bold))
    if recent_orders:
        elements.append(
            _data_table(
                ["#", "Order ID", "Customer", "Date", "Final (₹)", "Method", "Status"],
                [
                    (
                        i + 1,
                        o.order_id,
                        (o.user.full_name or o.user.email)[:20],
                        o.order_date.strftime("%d %b %Y"),
                        f"₹{o.final_amount:,.2f}",
                        o.payment_method,
                        o.order_status,
                    )
                    for i, o in enumerate(recent_orders)
                ],
                font_regular,
                font_bold,
                col_widths=[
                    0.7 * cm,
                    3.5 * cm,
                    3.8 * cm,
                    2.5 * cm,
                    2.5 * cm,
                    2 * cm,
                    3 * cm,
                ],
            )
        )
    else:
        elements.append(
            Paragraph(
                "No orders in this period.", ParagraphStyle("n", fontName=font_regular)
            )
        )
    elements.append(Spacer(1, 10))

    # ── LOW STOCK TABLE ──
    elements.append(_section_heading("Low Stock Alerts", font_bold, "#991b1b"))
    if low_stock_items:
        elements.append(
            _data_table(
                ["Product", "Color", "Age Group", "Available", "Reserved"],
                [
                    (
                        inv.variant.product.product_name,
                        inv.variant.color.color,
                        inv.variant.age_group.age,
                        inv.quantity_available,
                        inv.quantity_reserved,
                    )
                    for inv in low_stock_items
                ],
                font_regular,
                font_bold,
                col_widths=[6 * cm, 3 * cm, 3.5 * cm, 3 * cm, 3.5 * cm],
            )
        )
    else:
        elements.append(
            Paragraph("No low-stock items.", ParagraphStyle("n", fontName=font_regular))
        )

    # ── Footer ──
    elements.append(Spacer(1, 20))
    elements.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e8ecf0"))
    )
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            f'<font size="8" color="#94a3b8">© {datetime.now().year} Kiddora | Admin Dashboard Report | '
            f'Generated: {datetime.now().strftime("%d %B %Y %I:%M %p")} | '
            f"Period: {fs} to {fe}</font>",
            ParagraphStyle("footer", fontName=font_regular, alignment=1),
        )
    )

    doc.build(elements)
    buffer.seek(0)
    filename = f"kiddora_dashboard_{fs}_{fe}.pdf"
    return HttpResponse(
        buffer,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# SALES REPORT VIEW
# ─────────────────────────────────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_sales_report(request):
    start_date, end_date = get_date_range(request, default_days=10)
    report_type = request.GET.get("report_type", "").strip()

    orders_qs = Order.objects.filter(
        payment_status="PAID",
        order_date__date__gte=start_date,
        order_date__date__lte=end_date,
    ).select_related("user", "coupon", "address")

    if report_type == "daily":
        orders_qs = orders_qs.filter(order_date__date=start_date)
    elif report_type == "weekly":
        week_start = end_date - timedelta(days=6)
        orders_qs = orders_qs.filter(
            order_date__date__gte=week_start, order_date__date__lte=end_date
        )

    items_qs = OrderItem.objects.filter(order__in=orders_qs)

    total_sales = orders_qs.aggregate(s=Sum("final_amount"))["s"] or Decimal("0")
    total_orders_count = orders_qs.count()
    items_sold = items_qs.aggregate(s=Sum("quantity"))["s"] or 0
    total_discount = orders_qs.aggregate(s=Sum("discount_amount"))["s"] or Decimal("0")
    coupon_discount = orders_qs.aggregate(s=Sum("coupon_discount"))["s"] or Decimal("0")
    shipping_collected = orders_qs.aggregate(s=Sum("shipping_charge"))["s"] or Decimal(
        "0"
    )
    avg_order_value = orders_qs.aggregate(a=Avg("final_amount"))["a"] or Decimal("0")
    max_order_value = orders_qs.aggregate(m=Max("final_amount"))["m"] or Decimal("0")
    min_order_value = orders_qs.aggregate(m=Min("final_amount"))["m"] or Decimal("0")
    gross_sales = orders_qs.aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
    net_sales = total_sales
    free_shipping_orders = orders_qs.filter(shipping_charge=0).count()
    paid_shipping_orders = total_orders_count - free_shipping_orders
    coupon_orders = orders_qs.filter(coupon__isnull=False).count()

    refund_qs = Return.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    )
    total_returns = refund_qs.count()
    approved_returns = refund_qs.filter(status="APPROVED").count()
    refunded_returns = refund_qs.filter(status="REFUNDED").count()
    total_refund_amount = refund_qs.filter(status="REFUNDED").aggregate(
        s=Sum("refund_amount")
    )["s"] or Decimal("0")
    return_rate = safe_pct(total_returns, items_sold)

    top_products_sales = (
        items_qs.values("variant__product__product_name")
        .annotate(qty=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-rev")[:10]
    )
    top_categories_sales = (
        items_qs.values("variant__product__subcategory__category__category_name")
        .annotate(qty=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-rev")[:10]
    )
    top_brands_sales = (
        items_qs.values("variant__product__brand")
        .annotate(qty=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-rev")[:10]
    )

    paypal_sales = orders_qs.filter(payment_method="PAYPAL").aggregate(
        s=Sum("final_amount")
    )["s"] or Decimal("0")
    cod_sales = orders_qs.filter(payment_method="COD").aggregate(s=Sum("final_amount"))[
        "s"
    ] or Decimal("0")
    wallet_sales = orders_qs.filter(payment_method="WALLET").aggregate(
        s=Sum("final_amount")
    )["s"] or Decimal("0")
    paypal_count = orders_qs.filter(payment_method="PAYPAL").count()
    cod_count = orders_qs.filter(payment_method="COD").count()
    wallet_count = orders_qs.filter(payment_method="WALLET").count()

    period_days = (end_date - start_date).days + 1
    num_points = min(period_days, 10)
    daily_labels, daily_revenue_list, daily_orders_list, daily_items_list = (
        [],
        [],
        [],
        [],
    )
    for i in range(num_points - 1, -1, -1):
        d = end_date - timedelta(days=i)
        daily_labels.append(d.strftime("%d %b"))
        day_orders = orders_qs.filter(order_date__date=d)
        daily_revenue_list.append(
            float(day_orders.aggregate(s=Sum("final_amount"))["s"] or 0)
        )
        daily_orders_list.append(day_orders.count())
        daily_items_list.append(
            int(
                items_qs.filter(order__in=day_orders).aggregate(s=Sum("quantity"))["s"]
                or 0
            )
        )

    all_orders_in_range = Order.objects.filter(
        order_date__date__gte=start_date, order_date__date__lte=end_date
    )
    status_breakdown = dict(
        all_orders_in_range.values("order_status")
        .annotate(c=Count("id"))
        .values_list("order_status", "c")
    )
    payment_breakdown = dict(
        orders_qs.values("payment_method")
        .annotate(c=Count("id"))
        .values_list("payment_method", "c")
    )

    context = {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "report_type": report_type,
        "total_sales": total_sales,
        "gross_sales": gross_sales,
        "net_sales": net_sales,
        "total_orders": total_orders_count,
        "items_sold": items_sold,
        "total_discount": total_discount,
        "coupon_discount": coupon_discount,
        "shipping_collected": shipping_collected,
        "avg_order_value": avg_order_value,
        "max_order_value": max_order_value,
        "min_order_value": min_order_value,
        "free_shipping_orders": free_shipping_orders,
        "paid_shipping_orders": paid_shipping_orders,
        "coupon_orders": coupon_orders,
        "total_returns": total_returns,
        "approved_returns": approved_returns,
        "refunded_returns": refunded_returns,
        "total_refund_amount": total_refund_amount,
        "return_rate": return_rate,
        "paypal_sales": paypal_sales,
        "cod_sales": cod_sales,
        "wallet_sales": wallet_sales,
        "paypal_count": paypal_count,
        "cod_count": cod_count,
        "wallet_count": wallet_count,
        "top_products_sales": top_products_sales,
        "top_categories_sales": top_categories_sales,
        "top_brands_sales": top_brands_sales,
        "orders": orders_qs.order_by("-order_date"),
        "daily_labels_json": json.dumps(daily_labels),
        "daily_revenue_json": json.dumps(daily_revenue_list),
        "daily_orders_json": json.dumps(daily_orders_list),
        "daily_items_json": json.dumps(daily_items_list),
        "status_breakdown_json": json.dumps(status_breakdown),
        "payment_breakdown_json": json.dumps(payment_breakdown),
        "top_products_labels_json": json.dumps(
            [p["variant__product__product_name"] for p in top_products_sales]
        ),
        "top_products_rev_json": json.dumps(
            [float(p["rev"]) for p in top_products_sales]
        ),
        "top_categories_labels_json": json.dumps(
            [
                c["variant__product__subcategory__category__category_name"]
                for c in top_categories_sales
            ]
        ),
        "top_categories_rev_json": json.dumps(
            [float(c["rev"]) for c in top_categories_sales]
        ),
        "top_brands_labels_json": json.dumps(
            [b["variant__product__brand"] for b in top_brands_sales]
        ),
        "top_brands_rev_json": json.dumps([float(b["rev"]) for b in top_brands_sales]),
    }
    return render(request, "accounts/admin/admin_sales_report.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# SALES REPORT PDF DOWNLOAD
# ─────────────────────────────────────────────────────────────────────────────


@never_cache
@admin_login_required
def download_sales_report_pdf(request):
    start_date, end_date = get_date_range(request, default_days=10)
    report_type = request.GET.get("report_type", "").strip()

    orders_qs = Order.objects.filter(
        payment_status="PAID",
        order_date__date__gte=start_date,
        order_date__date__lte=end_date,
    ).select_related("user", "coupon", "address")

    if report_type == "daily":
        orders_qs = orders_qs.filter(order_date__date=start_date)
    elif report_type == "weekly":
        week_start = end_date - timedelta(days=6)
        orders_qs = orders_qs.filter(
            order_date__date__gte=week_start, order_date__date__lte=end_date
        )

    items_qs = OrderItem.objects.filter(order__in=orders_qs)

    total_sales = orders_qs.aggregate(s=Sum("final_amount"))["s"] or Decimal("0")
    total_orders_count = orders_qs.count()
    items_sold = items_qs.aggregate(s=Sum("quantity"))["s"] or 0
    total_discount = orders_qs.aggregate(s=Sum("discount_amount"))["s"] or Decimal("0")
    coupon_discount = orders_qs.aggregate(s=Sum("coupon_discount"))["s"] or Decimal("0")
    shipping_collected = orders_qs.aggregate(s=Sum("shipping_charge"))["s"] or Decimal(
        "0"
    )
    avg_order_value = orders_qs.aggregate(a=Avg("final_amount"))["a"] or Decimal("0")
    max_order_value = orders_qs.aggregate(m=Max("final_amount"))["m"] or Decimal("0")
    min_order_value = orders_qs.aggregate(m=Min("final_amount"))["m"] or Decimal("0")
    gross_sales = orders_qs.aggregate(s=Sum("total_amount"))["s"] or Decimal("0")
    free_shipping_orders = orders_qs.filter(shipping_charge=0).count()
    paid_shipping_orders = total_orders_count - free_shipping_orders
    coupon_orders = orders_qs.filter(coupon__isnull=False).count()

    refund_qs = Return.objects.filter(
        created_at__date__gte=start_date, created_at__date__lte=end_date
    )
    total_returns = refund_qs.count()
    approved_returns = refund_qs.filter(status="APPROVED").count()
    refunded_returns = refund_qs.filter(status="REFUNDED").count()
    total_refund_amount = refund_qs.filter(status="REFUNDED").aggregate(
        s=Sum("refund_amount")
    )["s"] or Decimal("0")
    return_rate = safe_pct(total_returns, items_sold)

    paypal_sales = orders_qs.filter(payment_method="PAYPAL").aggregate(
        s=Sum("final_amount")
    )["s"] or Decimal("0")
    cod_sales = orders_qs.filter(payment_method="COD").aggregate(s=Sum("final_amount"))[
        "s"
    ] or Decimal("0")
    wallet_sales = orders_qs.filter(payment_method="WALLET").aggregate(
        s=Sum("final_amount")
    )["s"] or Decimal("0")
    paypal_count = orders_qs.filter(payment_method="PAYPAL").count()
    cod_count = orders_qs.filter(payment_method="COD").count()
    wallet_count = orders_qs.filter(payment_method="WALLET").count()

    top_products_sales = list(
        items_qs.values("variant__product__product_name")
        .annotate(qty=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-rev")[:10]
    )
    top_categories_sales = list(
        items_qs.values("variant__product__subcategory__category__category_name")
        .annotate(qty=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-rev")[:10]
    )
    top_brands_sales = list(
        items_qs.values("variant__product__brand")
        .annotate(qty=Sum("quantity"), rev=Sum("total_price"))
        .order_by("-rev")[:10]
    )
    all_orders = list(orders_qs.order_by("-order_date"))

    # ── Build PDF ──
    font_regular, font_bold = _register_fonts()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    elements = []
    fs = start_date.strftime("%Y-%m-%d")
    fe = end_date.strftime("%Y-%m-%d")
    rtype_label = report_type.title() if report_type else "All Range"

    _build_pdf_header(
        elements, font_regular, font_bold, "Sales Report", f" — {rtype_label}", fs, fe
    )

    # ── SUMMARY STRIP TABLE ──
    elements.append(_section_heading("Summary Overview", font_bold, "#166534"))
    summary_kpis = [
        ("Total Orders", str(total_orders_count)),
        ("Items Sold", str(items_sold)),
        ("Gross Sales", f"₹{gross_sales:,.0f}"),
        ("Net Sales", f"₹{total_sales:,.0f}"),
        ("Avg Order Value", f"₹{avg_order_value:,.0f}"),
        ("Max Order", f"₹{max_order_value:,.0f}"),
        ("Min Order", f"₹{min_order_value:,.0f}"),
        ("Return Rate", f"{return_rate}%"),
    ]
    elements.append(_kpi_table(summary_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── DEDUCTIONS KPIs ──
    elements.append(_section_heading("Revenue Deductions", font_bold, "#92400e"))
    deduct_kpis = [
        ("Total Discounts", f"₹{total_discount:,.0f}"),
        ("Coupon Savings", f"₹{coupon_discount:,.0f}"),
        ("Coupon Orders", str(coupon_orders)),
        ("Shipping Collected", f"₹{shipping_collected:,.0f}"),
        ("Free Shipping Orders", str(free_shipping_orders)),
        ("Paid Shipping Orders", str(paid_shipping_orders)),
        ("Refund Amount", f"₹{total_refund_amount:,.0f}"),
        ("Refunded Returns", str(refunded_returns)),
    ]
    elements.append(_kpi_table(deduct_kpis, font_regular, font_bold, col_count=4))
    elements.append(Spacer(1, 8))

    # ── PAYMENT METHOD TABLE ──
    elements.append(_section_heading("Payment Method Breakdown", font_bold, "#1e40af"))
    elements.append(
        _data_table(
            ["Payment Method", "Orders", "Revenue (₹)", "% of Total Revenue"],
            [
                (
                    "PayPal",
                    paypal_count,
                    f"₹{paypal_sales:,.2f}",
                    f"{safe_pct(float(paypal_sales), float(total_sales))}%",
                ),
                (
                    "Cash on Delivery",
                    cod_count,
                    f"₹{cod_sales:,.2f}",
                    f"{safe_pct(float(cod_sales), float(total_sales))}%",
                ),
                (
                    "Wallet",
                    wallet_count,
                    f"₹{wallet_sales:,.2f}",
                    f"{safe_pct(float(wallet_sales), float(total_sales))}%",
                ),
                ("TOTAL", total_orders_count, f"₹{total_sales:,.2f}", "100%"),
            ],
            font_regular,
            font_bold,
            col_widths=[5 * cm, 3 * cm, 5 * cm, 6 * cm],
        )
    )
    elements.append(Spacer(1, 10))

    # ── RETURNS TABLE ──
    elements.append(_section_heading("Returns & Refunds", font_bold, "#991b1b"))
    elements.append(
        _data_table(
            ["Metric", "Value"],
            [
                ("Total Returns", str(total_returns)),
                ("Approved Returns", str(approved_returns)),
                ("Refunded Returns", str(refunded_returns)),
                (
                    "Pending Returns",
                    str(total_returns - approved_returns - refunded_returns),
                ),
                ("Total Refund Amount", f"₹{total_refund_amount:,.2f}"),
                ("Return Rate", f"{return_rate}% of items sold"),
            ],
            font_regular,
            font_bold,
            col_widths=[9 * cm, 10 * cm],
        )
    )
    elements.append(Spacer(1, 10))

    # ── TOP PRODUCTS TABLE ──
    elements.append(_section_heading("Top 10 Products by Revenue", font_bold))
    if top_products_sales:
        elements.append(
            _data_table(
                ["#", "Product", "Qty Sold", "Revenue (₹)"],
                [
                    (
                        i + 1,
                        p["variant__product__product_name"],
                        p["qty"],
                        f"₹{p['rev']:,.2f}",
                    )
                    for i, p in enumerate(top_products_sales)
                ],
                font_regular,
                font_bold,
                col_widths=[1 * cm, 10 * cm, 3.5 * cm, 4.5 * cm],
            )
        )
    else:
        elements.append(
            Paragraph("No product data.", ParagraphStyle("n", fontName=font_regular))
        )
    elements.append(Spacer(1, 10))

    # ── TOP CATEGORIES TABLE ──
    elements.append(_section_heading("Top Categories by Revenue", font_bold))
    if top_categories_sales:
        elements.append(
            _data_table(
                ["#", "Category", "Qty Sold", "Revenue (₹)"],
                [
                    (
                        i + 1,
                        c["variant__product__subcategory__category__category_name"],
                        c["qty"],
                        f"₹{c['rev']:,.2f}",
                    )
                    for i, c in enumerate(top_categories_sales)
                ],
                font_regular,
                font_bold,
                col_widths=[1 * cm, 10 * cm, 3.5 * cm, 4.5 * cm],
            )
        )
    else:
        elements.append(
            Paragraph("No category data.", ParagraphStyle("n", fontName=font_regular))
        )
    elements.append(Spacer(1, 10))

    # ── ALL ORDERS TABLE ──
    elements.append(_section_heading("Order Details", font_bold))
    if all_orders:
        elements.append(
            _data_table(
                [
                    "#",
                    "Order ID",
                    "Customer",
                    "Date",
                    "Gross(₹)",
                    "Disc(₹)",
                    "Ship(₹)",
                    "Final(₹)",
                    "Method",
                    "Status",
                ],
                [
                    (
                        i + 1,
                        o.order_id,
                        (o.user.full_name or o.user.email)[:16],
                        o.order_date.strftime("%d %b %Y"),
                        f"{o.total_amount:,.0f}",
                        f"{o.discount_amount:,.0f}",
                        f"{o.shipping_charge:,.0f}",
                        f"₹{o.final_amount:,.2f}",
                        o.payment_method,
                        o.order_status,
                    )
                    for i, o in enumerate(all_orders)
                ],
                font_regular,
                font_bold,
                col_widths=[
                    0.6 * cm,
                    3.2 * cm,
                    3 * cm,
                    2.3 * cm,
                    1.8 * cm,
                    1.5 * cm,
                    1.5 * cm,
                    2.2 * cm,
                    1.8 * cm,
                    2.1 * cm,
                ],
            )
        )
    else:
        elements.append(
            Paragraph(
                "No orders in this period.", ParagraphStyle("n", fontName=font_regular)
            )
        )

    # ── Footer ──
    elements.append(Spacer(1, 20))
    elements.append(
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e8ecf0"))
    )
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            f'<font size="8" color="#94a3b8">© {datetime.now().year} Kiddora | Sales Report | '
            f'Type: {rtype_label} | Generated: {datetime.now().strftime("%d %B %Y %I:%M %p")} | '
            f"Period: {fs} to {fe}</font>",
            ParagraphStyle("footer", fontName=font_regular, alignment=1),
        )
    )

    doc.build(elements)
    buffer.seek(0)
    filename = f"kiddora_sales_report_{fs}_{fe}.pdf"
    return HttpResponse(
        buffer,
        content_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
