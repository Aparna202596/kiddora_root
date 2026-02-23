from shopcore.services.order_life_cycle import *
from products.services.inventory import *
from django.shortcuts import render, get_object_or_404, redirect
from accounts.decorators import user_login_required, admin_login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from accounts.models import *
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.contrib import messages
from shopcore.models import *
from products.models import *

from django.db import transaction

@admin_login_required
def admin_order_list(request):
    orders = Order.objects.all().order_by("-order_date")
    search = request.GET.get("search")
    status = request.GET.get("status")
    if search:
        orders = orders.filter(
            Q(order_id__icontains=search) |
            Q(user__email__icontains=search))
    if status:
        orders = orders.filter(order_status=status)
    paginator = Paginator(orders, 15)
    page = request.GET.get("page")
    orders = paginator.get_page(page)
    return render(request, "orders/admin/admin_order_list.html", {
        "orders": orders,
        "search": search,
        "status": status,
    })

@admin_login_required
def admin_order_detail(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    return render(request, "orders/admin/admin_order_detail.html", {"order": order})

@admin_login_required
def admin_update_order_status(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    if request.method == "POST":
        status = request.POST.get("status")
        if status == "DELIVERED":
            mark_order_delivered(order)
        else:
            order.order_status = status
            order.save()
    return redirect("orders:admin_order_detail", order_id=order.order_id)

@admin_login_required
def admin_handle_return(request, return_id):
    order_return = get_object_or_404(OrderReturn, id=return_id)
    if request.method == "POST":
        action = request.POST.get("action")
        remark = request.POST.get("remark")
        if action == "approve":
            order_return.status = "RETURN_APPROVED"
            order_return.refunded_at = timezone.now()
            # Inventory restore
            for item in order_return.order.items.all():
                release_stock(item.variant, item.quantity)
            # Logical wallet refund (no model change)
            order_return.order.payment_status = "REFUNDED"
            order_return.order.save()
        elif action == "reject":
            order_return.status = "RETURN_REJECTED"
        order_return.admin_remark = remark
        order_return.save()
    return redirect("orders:admin_order_detail", order_id=order_return.order.order_id)

#USER


@user_login_required
@transaction.atomic
def place_order(request):
    if request.method != "POST":
        return redirect("cart:checkout")

    address_id = request.POST.get("address_id")
    payment_method = request.POST.get("payment_method")

    address = get_object_or_404(UserAddress, id=address_id, user=request.user)
    cart = get_object_or_404(Cart, user=request.user)

    subtotal = 0
    for item in cart.items.select_related("variant", "variant__product"):
        subtotal += item.variant.product.final_price * item.quantity

    discount = 0
    coupon_id = request.session.get("coupon_id")
    if coupon_id:
        coupon = Coupon.objects.filter(id=coupon_id).first()
        if coupon:
            discount = min(
                coupon.discount_value if coupon.discount_type == "FLAT"
                else (coupon.discount_value / 100) * subtotal,
                coupon.max_discount or discount
            )

    delivery_charge = 0 if subtotal >= 500 else 50
    final_total = subtotal - discount + delivery_charge

    # COD restriction
    if payment_method == "COD" and final_total > 1000:
        messages.error(request, "Cash on Delivery not allowed above ₹1000.")
        return redirect("cart:checkout")

    # Create order
    order = Order.objects.create(
        user=request.user,
        address=address,
        total_amount=subtotal,
        discount_amount=discount,
        final_amount=final_total,
        payment_method=payment_method,
        payment_status="PENDING"
    )

    for item in cart.items.all():
        OrderItem.objects.create(
            order=order,
            product=item.variant.product,
            quantity=item.quantity,
            price=item.variant.product.final_price
        )

        inventory = item.variant.inventory
        inventory.quantity_available -= item.quantity
        inventory.quantity_sold += item.quantity
        inventory.save()

    cart.items.all().delete()
    request.session.pop("coupon_id", None)

    return redirect("payments:initiate_payment", order_id=order.id)

@user_login_required
def user_orders(request):
    orders = Order.objects.filter(user=request.user).order_by("-order_date")
    search = request.GET.get("search")
    if search:
        orders = orders.filter(order_id__icontains=search)
    paginator = Paginator(orders, 15)
    page = request.GET.get("page")
    orders = paginator.get_page(page)
    return render(request, "orders/user/order_list.html", {"orders": orders})

def order_detail(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/user/order_detail.html", {"order": order})

def cancel_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if request.method == "POST":
        for item in order.items.all():
            cancel_order_item(item)
        order.order_status = "CANCELLED"
        order.cancelled_at = timezone.now()
        order.save()
        messages.success(request, "Order cancelled successfully")
        return redirect("orders:user_orders")
    return render(request, "orders/user/order_cancel_confirm.html", {"order": order})

@user_login_required
def cancel_order_item_view(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    if request.method == "POST":
        cancel_order_item(item)
    return redirect("orders:order_detail", order_id=item.order.order_id)

@user_login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    template = get_template("orders/user/invoice.html")
    html = template.render({"order": order})
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="invoice_{order.order_id}.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response
# @user_login_required
# def download_invoice(request, order_id):
#     order = get_object_or_404(Order, id=order_id, user=request.user)
#     buffer = generate_invoice_pdf(order)

#     response = HttpResponse(buffer, content_type="application/pdf")
#     response["Content-Disposition"] = f'attachment; filename="invoice_{order.id}.pdf"'
#     return response

