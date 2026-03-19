from __future__ import annotations
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator
from accounts.decorators import user_login_required, admin_login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.conf import settings
from django.db import transaction
from decimal import Decimal

from shopcore.views.coupon_views import compute_coupon_discount
from accounts.models import UserAddress
from shopcore.models import Cart, CartItem, Order, OrderItem, Offer
from products.models import ProductVariant

from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors
import io
import os

# ──────────────────────────────────────────────HELPERS (shared between user & admin)──────────────────────────────────────────────────

def _get_cart(user):
    try:
        return user.cart
    except Cart.DoesNotExist:
        return None

def _variant_is_available(variant: ProductVariant) -> bool:
    try:
        p = variant.product
        sub = p.subcategory
        cat = sub.category
        return (
            variant.is_active
            and p.is_active and not p.is_deleted
            and sub.is_active and not sub.is_deleted
            and cat.is_active and not cat.is_deleted
        )
    except Exception:
        return False

def _stock_for(variant: ProductVariant) -> int:
    try:
        return variant.inventory.quantity_available
    except Exception:
        return 0

def _img_url_for(product):
    img_obj = product.images.filter(is_default=True).first() or product.images.first()
    if img_obj:
        for field in ("image1", "image2", "image3", "image4", "image5"):
            val = getattr(img_obj, field)
            if val:
                return val.url
    return None

def _recalculate_order_amount(order):
    active_items = order.order_items.filter(item_status="ACTIVE")

    subtotal= sum(item.unit_price * item.quantity for item in active_items)

    # Shipping rule
    shipping_charge = Decimal("0")
    if 0 < subtotal < Decimal("499"):
        shipping_charge = Decimal("100")

    order.total_amount = subtotal
    order.shipping_charge = shipping_charge

    # Calculate final amount ensuring it doesn't go negative
    total_deductions = order.discount_amount + order.coupon_discount
    order.final_amount = max(Decimal("0"), subtotal - total_deductions + shipping_charge)

    order.save(update_fields=[
        "total_amount",
        "shipping_charge",
        "final_amount",
    ])
    
def get_max_offer_discount_percent(product):
    """
    Returns the highest applicable offer percentage for this product
    (larger between product-specific and category-specific offer)
    """
    if not product:
        return 0
    
    now = timezone.now()
    # Active offers only
    active_offers = Offer.objects.filter(is_active=True, is_deleted=False, start_date__lte=now)
    # Product-specific
    product_offer = active_offers.filter(offer_type="PRODUCT", product=product).first()
    # Category-specific
    category_offer = None
    try:
        if product.subcategory and product.subcategory.category:
            category_offer = active_offers.filter(
                offer_type="CATEGORY",
                category=product.subcategory.category
            ).first()
    except:
        pass
    
    max_pct = 0
    if product_offer and product_offer.is_valid():
        max_pct = max(max_pct, product_offer.discount_percent)
    if category_offer and category_offer.is_valid():
        max_pct = max(max_pct, category_offer.discount_percent)
    
    return max_pct
#─────────────────────────────────────────────────────────────USER────────────────────────────────────────────────────────────────────────
# USER: CHECKOUT 
@never_cache
@user_login_required
def checkout(request):
    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

    items = cart.items.select_related(
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__color",
        "variant__age_group",
        "variant__inventory",
    ).prefetch_related("variant__product__images").order_by("-added_at")

    checkout_items = []
    subtotal = Decimal("0")               # before any discount
    offer_discount_total = Decimal("0")

    for item in items:
        variant = item.variant
        product = variant.product
        
        available = _variant_is_available(variant)
        stock = _stock_for(variant)
        
        if not available or stock == 0 or item.quantity > stock:
            blocked = True
        
        base_price = product.final_price
        offer_pct = get_max_offer_discount_percent(product)
        discounted_price = base_price * (Decimal('1') - Decimal(offer_pct)/100)
        
        item_base_total    = base_price * item.quantity
        item_offer_discount = (base_price - discounted_price) * item.quantity
        item_final_total   = discounted_price * item.quantity
        
        subtotal += item_base_total
        offer_discount_total += item_offer_discount
        
        checkout_items.append({
            "item": item,
            "variant": variant,
            "product": product,
            "item_total": item_final_total,          # after offer
            "base_item_total": item_base_total,
            "offer_discount": item_offer_discount,
            "offer_pct": offer_pct,
            "available": available,
            "stock": stock,
            "img_url": _img_url_for(product),
        })

    if blocked:
        messages.error(
            request,
            "Some items in your cart are unavailable or out of stock. "
            "Please update your cart before proceeding."
        )
        return redirect("shopcore:cart")

    addresses = UserAddress.objects.filter(user=request.user, is_deleted=False)
    default_address = addresses.filter(is_default=True).first() or addresses.first()
    shipping_charge = Decimal("0")
    coupon_discount = Decimal("0")
    applied_coupon = getattr(cart, "coupon", None)
    if applied_coupon and applied_coupon.is_valid():
        # Use original subtotal (before offer) for coupon – most common behavior
        coupon_discount = compute_coupon_discount(applied_coupon, subtotal)

    shipping_charge = Decimal("0")
    if subtotal < 499:
        shipping_charge = Decimal("100")

    grand_total = subtotal - offer_discount_total - coupon_discount + shipping_charge

    context = {
        "checkout_items": checkout_items,
        "addresses": addresses,
        "default_address": default_address,
        "subtotal": subtotal,
        "offer_discount_total": offer_discount_total,
        "coupon_discount": coupon_discount,
        "applied_coupon": applied_coupon,
        "shipping_charge": shipping_charge,
        "grand_total": grand_total,
    }
    return render(request, "cart/checkout.html", context)

@never_cache
@user_login_required
def edit_address_checkout(request, address_id):
    address = get_object_or_404(
        UserAddress,
        pk=address_id,
        user=request.user,
        is_deleted=False
    )
    
    if request.method == "POST":
        address.full_name = request.POST.get("full_name", address.full_name)
        address.phone = request.POST.get("phone", address.phone)
        address.address_line1 = request.POST.get("address_line1", address.address_line1)
        address.address_line2 = request.POST.get("address_line2", address.address_line2)
        address.city = request.POST.get("city", address.city)
        address.state = request.POST.get("state", address.state)
        address.pincode  = request.POST.get("pincode", address.pincode)
        
        if request.POST.get("set_default"):
            address.is_default = True
            UserAddress.objects.filter(user=request.user, is_deleted=False)\
                                .exclude(pk=address.pk)\
                                .update(is_default=False)
        address.save()
        
        messages.success(request, "Address updated successfully.")
        return redirect("shopcore:checkout")
    
    return render(request, "cart/edit_address.html", {"address": address})

# USER: PLACE ORDER (POST – COD only for now)
@never_cache
@user_login_required
@transaction.atomic
def place_order(request):
    if request.method != "POST":
        return redirect("shopcore:checkout")

    cart = _get_cart(request.user)
    if not cart or not cart.items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("shopcore:cart")

    # Address logic
    address_id = request.POST.get("address_id")
    if address_id:
        address = get_object_or_404(UserAddress, id=address_id, user=request.user, is_deleted=False)
    else:
        address = (UserAddress.objects.filter(user=request.user, is_deleted=False, is_default=True).first()
            or UserAddress.objects.filter(user=request.user, is_deleted=False).first())

    if not address:
        messages.error(request, "Please add a delivery address before placing an order.")
        return redirect("shopcore:checkout")

    # ── Cart validation ─────────────────────────────────────
    items = cart.items.select_related(
        "variant__product",
        "variant__product__subcategory",
        "variant__product__subcategory__category",
        "variant__inventory",
    ).all()

    for item in items:
        if not _variant_is_available(item.variant):
            messages.error(
                request,
                f"'{item.variant.product.product_name}' is no longer available."
            )
            return redirect("shopcore:cart")

        stock = _stock_for(item.variant)
        if stock < item.quantity:
            messages.error(
                request,
                f"Only {stock} unit(s) of '{item.variant.product.product_name}' in stock."
            )
            return redirect("shopcore:cart")

    # ── Calculate totals with offers & coupon ───────────────
    subtotal = Decimal("0")               # before any discount
    offer_discount_total = Decimal("0")

    for item in items:
        base = item.variant.product.final_price * item.quantity
        offer_pct = get_max_offer_discount_percent(item.variant.product)
        item_offer_disc = base * Decimal(offer_pct) / 100

        subtotal += base
        offer_discount_total += item_offer_disc

    coupon_discount = Decimal("0")
    applied_coupon = getattr(cart, "coupon", None)
    if applied_coupon and applied_coupon.is_valid():
        coupon_discount = compute_coupon_discount(applied_coupon, subtotal)
        applied_coupon.used_count += 1
        applied_coupon.used_by.add(request.user)
        applied_coupon.save(update_fields=["used_count"])

    shipping_charge = Decimal("100") if subtotal < 499 else Decimal("0")

    final_amount = subtotal - offer_discount_total - coupon_discount + shipping_charge

    # ── COD restriction ─────────────────────────────────────
    payment_method = request.POST.get("payment_method", "COD")
    if final_amount > Decimal("1000") and payment_method == "COD":
        messages.error(request, "Orders above ₹1000 cannot use Cash on Delivery.")
        return redirect("shopcore:checkout")

    # ── Create Order ────────────────────────────────────────
    order = Order.objects.create(
        user=request.user,
        address=address,
        payment_method=payment_method,
        payment_status="PENDING",
        order_status="PENDING",
        coupon=applied_coupon,
        coupon_discount=coupon_discount,
        total_amount=subtotal,
        discount_amount=offer_discount_total,      # ← offer discount goes here
        shipping_charge=shipping_charge,
        final_amount=final_amount,
    )

    # Address snapshot (if your Order model has these fields)
    snapshot_fields = {
        "snapshot_name": getattr(address, "full_name", ""),
        "snapshot_phone": getattr(address, "phone", ""),
        "snapshot_line1": getattr(address, "address_line1", ""),
        "snapshot_line2": getattr(address, "address_line2", ""),
        "snapshot_city": getattr(address, "city", ""),
        "snapshot_state": getattr(address, "state", ""),
        "snapshot_pincode": getattr(address, "pincode", ""),
    }
    dirty_fields = [f for f, v in snapshot_fields.items() if hasattr(order, f) and v]
    if dirty_fields:
        for field in dirty_fields:
            setattr(order, field, snapshot_fields[field])
        order.save(update_fields=dirty_fields)

    # ── Create OrderItems + update inventory ────────────────
    for item in items:
        variant = item.variant
        base_price = variant.product.final_price
        offer_pct = get_max_offer_discount_percent(variant.product)
        item_discount = (base_price * item.quantity) * Decimal(offer_pct) / 100

        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=item.quantity,
            unit_price=base_price,
            discount_amount=item_discount,          # per-item offer discount
        )

        # Update stock
        inv = variant.inventory
        inv.quantity_available = max(0, inv.quantity_available - item.quantity)
        inv.quantity_sold += item.quantity
        inv.save(update_fields=["quantity_available", "quantity_sold"])

    # ── Clear cart ──────────────────────────────────────────
    cart.items.all().delete()
    if hasattr(cart, "coupon") and cart.coupon:
        cart.coupon = None
        cart.save(update_fields=["coupon"])

    return redirect("shopcore:order_success", order_id=order.order_id)

# USER: ORDER SUCCESS
@never_cache
@user_login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_success.html", {"order": order})

# USER: ORDER LIST
@never_cache
@user_login_required
def user_order_list(request):
    query = request.GET.get("q", "").strip()
    orders = Order.objects.filter(user=request.user).order_by("-order_date")
    if query:
        orders = orders.filter(
            Q(order_id__icontains=query) |
            Q(order_status__icontains=query) |
            Q(order_items__variant__product__product_name__icontains=query)
        ).distinct()
    paginator = Paginator(orders, 10)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "orders/user/user_order_list.html", {
        "page_obj": page_obj,
        "query": query,
    })

# USER: ORDER DETAIL
@never_cache
@user_login_required
def user_order_detail(request, order_id):
    order = get_object_or_404(Order.objects.select_related("address", "coupon").prefetch_related(
            "order_items__variant__product__images",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ),
        order_id=order_id, user=request.user)
    items_with_img = []
    for oi in order.order_items.all():
        product = oi.variant.product
        img_url = _img_url_for(product)
        items_with_img.append({"order_item": oi, "img_url": img_url})
    context = {
        "order": order,
        "items_with_img": items_with_img,
        "can_cancel_order": order.order_status in ("PENDING", "CONFIRMED"),
    }
    return render(request, "orders/user/user_order_detail.html", context)

# USER: CANCEL WHOLE ORDER
@never_cache
@user_login_required
@transaction.atomic
def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.order_status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "This order cannot be cancelled at its current stage.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)
    if request.method != "POST":
        return render(request, "orders/user/confirm_cancel_order.html", {"order": order})
    reason = request.POST.get("cancel_reason", "").strip()
    for oi in order.order_items.filter(item_status="ACTIVE"):
        try:
            inv = oi.variant.inventory
            inv.quantity_available += oi.quantity
            inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
            inv.save()
        except Exception:
            pass
        oi.item_status = "CANCELLED"
        oi.cancel_reason = reason or "Order cancelled by user"
        oi.cancelled_at = timezone.now()
        oi.save()
    order.order_status = "CANCELLED"
    order.cancel_reason = reason or "Cancelled by user"
    order.cancelled_at = timezone.now()
    order.save()
    messages.success(request, f"Order {order.order_id} has been cancelled.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)

# USER: CANCEL SINGLE ITEM
@never_cache
@user_login_required
@transaction.atomic
def cancel_order_item(request, order_id, item_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order, item_status="ACTIVE")
    if order.order_status not in ("PENDING", "CONFIRMED"):
        messages.error(request, "Items in this order can no longer be cancelled.")
        return redirect("shopcore:user_order_detail", order_id=order.order_id)
    if request.method != "POST":
        return render(request, "orders/user/confirm_cancel_item.html", {
            "order": order,
            "order_item": order_item,
        })
    reason = request.POST.get("cancel_reason", "").strip()
    try:
        inv = order_item.variant.inventory
        inv.quantity_available += order_item.quantity
        inv.quantity_sold = max(0, inv.quantity_sold - order_item.quantity)
        inv.save()
    except Exception:
        pass
    order_item.item_status = "CANCELLED"
    order_item.cancel_reason = reason or "Item cancelled by user"
    order_item.cancelled_at = timezone.now()
    order_item.save()

    # Recalculate order totals
    _recalculate_order_amount(order)

    # If all items cancelled -> cancel order
    if not order.order_items.filter(item_status="ACTIVE").exists():
        order.order_status = "CANCELLED"
        order.cancel_reason = "All items cancelled"
        order.cancelled_at = timezone.now()
        order.save(update_fields=["order_status", "cancel_reason", "cancelled_at"])
    messages.success(request, f"Item '{order_item.variant.product.product_name}' cancelled.")
    return redirect("shopcore:user_order_detail", order_id=order.order_id)
# ─────────────────────────────────────────────────────────────ADMIN────────────────────────────────────────────────────────────────────────
# ADMIN: ORDER LIST
@never_cache
@admin_login_required
def admin_order_list(request):
    search = request.GET.get("search", "").strip()
    status_f = request.GET.get("status", "").strip()
    sort = request.GET.get("sort", "order_date")
    dir = request.GET.get("dir", "desc")
    orders = Order.objects.select_related("user", "address").prefetch_related("order_items").order_by("-order_date")
    if search:
        orders = orders.filter(
            Q(order_id__icontains=search) |
            Q(user__email__icontains=search) |
            Q(user__full_name__icontains=search)
        )
    if status_f:
        orders = orders.filter(order_status=status_f)
    if sort in ["order_date", "final_amount", "order_status"]:
        order_field = f"-{sort}" if dir == "desc" else sort
        orders = orders.order_by(order_field)
    page_obj = Paginator(orders, 20).get_page(request.GET.get("page"))
    context = {
        "page_obj": page_obj,
        "search": search,
        "status_f": status_f,
        "sort": sort,
        "dir": dir,
        "status_choices": Order.ORDER_STATUS_CHOICES,
    }
    return render(request, "orders/admin/admin_order_list.html", context)

# ADMIN: ORDER DETAIL
@never_cache
@admin_login_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order.objects.select_related("user", "address", "coupon").prefetch_related(
            "order_items__variant__product__images",
            "order_items__variant__color",
            "order_items__variant__age_group",
        ), order_id=order_id)
    
    items_with_img = []
    for oi in order.order_items.all():
        product = oi.variant.product
        img_url = _img_url_for(product)
        items_with_img.append({"order_item": oi, "img_url": img_url})

    context = {
        "order": order,
        "items_with_img": items_with_img,
        "status_choices": Order.ORDER_STATUS_CHOICES,                
        "item_status_choices": OrderItem.ITEM_STATUS_CHOICES,        
    }
    return render(request, "orders/admin/admin_order_detail.html", context)

# ADMIN: UPDATE ORDER STATUS
@never_cache
@admin_login_required
@transaction.atomic
def admin_update_order_status(request, order_id):
    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)
    order = get_object_or_404(Order, order_id=order_id)
    new_status = request.POST.get("order_status", "").strip()
    valid_transitions = {
        "PENDING": ["CONFIRMED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "CONFIRMED": ["SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "SHIPPED": ["OUT_FOR_DELIVERY", "DELIVERED", "CANCELLED"],
        "OUT_FOR_DELIVERY": ["DELIVERED", "CANCELLED"],
        "DELIVERED": [],
        "CANCELLED": [],
    }
    allowed = valid_transitions.get(order.order_status, [])
    if new_status not in allowed:
        messages.error(
            request,
            f"Cannot change status from '{order.get_order_status_display()}' to '{new_status}'."
        )
        return redirect("shopcore:admin_order_detail", order_id=order.order_id)
    old_status = order.order_status
    order.order_status = new_status

    if new_status == "DELIVERED":
        order.delivered_at = timezone.now()
        order.payment_status = "PAID"
    elif new_status == "CANCELLED":
        order.cancelled_at = timezone.now()
        order.cancel_reason = request.POST.get("cancel_reason", "Cancelled by admin").strip()
        for oi in order.order_items.filter(item_status="ACTIVE"):
            try:
                inv = oi.variant.inventory
                inv.quantity_available += oi.quantity
                inv.quantity_sold = max(0, inv.quantity_sold - oi.quantity)
                inv.save()
            except Exception:
                pass
            oi.item_status = "CANCELLED"
            oi.cancel_reason = order.cancel_reason
            oi.cancelled_at = timezone.now()
            oi.save()
    order.save()
    messages.success(
        request,
        f"Order {order.order_id} status updated: {old_status} → {new_status}"
    )
    return redirect("shopcore:admin_order_detail", order_id=order.order_id)

@never_cache
@admin_login_required
@transaction.atomic
def admin_update_item_status(request, order_id, item_id):

    if request.method != "POST":
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order = get_object_or_404(Order, order_id=order_id)
    order_item = get_object_or_404(OrderItem, id=item_id, order=order)

    new_status = request.POST.get("item_status")

    if new_status not in dict(OrderItem.ITEM_STATUS_CHOICES):
        messages.error(request, "Invalid item status.")
        return redirect("shopcore:admin_order_detail", order_id=order_id)

    order_item.item_status = new_status
    order_item.save()

    if new_status == "CANCELLED":
        _recalculate_order_amount(order)

    messages.success(
        request,
        f"Item '{order_item.variant.product.product_name}' updated to {new_status}"
    )
    return redirect("shopcore:admin_order_detail", order_id=order_id)

@user_login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    font_path = "C:/Windows/Fonts/arial.ttf"
    pdfmetrics.registerFont(TTFont("Arial", font_path))
    styles = getSampleStyleSheet()

    #  CUSTOM SPACING STYLE
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontName="Arial",
        spaceAfter=8,
        leading=14
    )

    heading_style = ParagraphStyle(
        'Heading',
        parent=styles['Heading2'],
        fontName="Arial",
        spaceAfter=12
    )

    elements = []

    # ───── LOGO ─────
    logo_path = os.path.join(settings.BASE_DIR, "static/images/kiddora_logo.PNG")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=120, height=50)
        elements.append(logo)

    elements.append(Spacer(1, 15))

    # ───── TITLE ─────
    elements.append(Paragraph("<b>KIDDORA INVOICE</b>", styles['Title']))
    elements.append(Spacer(1, 20))

    # ───── ORDER INFO ─────
    elements.append(Paragraph(f"<b>Order ID:</b> {order.order_id}", normal_style))
    elements.append(Paragraph(f"<b>Date:</b> {order.order_date.strftime('%d %b %Y')}", normal_style))
    elements.append(Paragraph(f"<b>Status:</b> {order.get_order_status_display()}", normal_style))

    elements.append(Spacer(1, 20))

    # ───── CUSTOMER DETAILS ─────
    address = order.address

    name = getattr(address, 'full_name', None) or getattr(order.user, 'username', '')
    phone = getattr(address, 'phone', None) or getattr(order.user, 'phone', '')

    full_address = f"""
    {getattr(address, 'address_line1', '')}, 
    {getattr(address, 'address_line2', '')}, 
    {getattr(address, 'city', '')}, 
    {getattr(address, 'state', '')} - {getattr(address, 'pincode', '')}
    """

    elements.append(Paragraph("<b>Customer Details</b>", heading_style))
    elements.append(Paragraph(f"<b>Name:</b> {name}", normal_style))
    elements.append(Paragraph(f"<b>Phone:</b> {phone}", normal_style))
    elements.append(Paragraph(f"<b>Address:</b> {full_address}", normal_style))

    elements.append(Spacer(1, 25))

    # ───── TABLE DATA ─────
    data = [["Order ID", "Item", "Qty", "Price (₹)"]]

    for oi in order.order_items.all():
        data.append([
            str(order.order_id),
            oi.variant.product.product_name,
            str(oi.quantity),
            f"₹{oi.unit_price * oi.quantity}"
        ])

    data.append(["", "", "Grand Total", f"₹{order.final_amount}"])

    # ───── TABLE ─────
    table = Table(data, colWidths=[90, 200, 60, 100])

    table.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ff6f91")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "Arial"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),

        # Body
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.whitesmoke, colors.lightgrey]),

        # Alignment
        ("ALIGN", (2, 1), (2, -1), "CENTER"),
        ("ALIGN", (3, 1), (3, -1), "RIGHT"),

        # Padding (✨ better spacing)
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),

        # Grand Total Highlight
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ffd6e0")),
        ("FONTNAME", (0, -1), (-1, -1), "Arial"),
    ]))

    elements.append(table)

    # ───── BUILD PDF ─────
    doc.build(elements)

    buffer.seek(0)

    return HttpResponse(
        buffer,
        content_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice_{order.order_id}.pdf"'
        }
    )