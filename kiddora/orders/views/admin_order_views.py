from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.template.loader import get_template
from xhtml2pdf import pisa

from orders.models import Order, OrderItem, OrderReturn
from accounts.models import CustomUser
from products.services.inventory import release_stock
from orders.services.order_life_cycle import cancel_order_item, mark_order_delivered
from accounts.decorators import user_login_required, admin_login_required

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

