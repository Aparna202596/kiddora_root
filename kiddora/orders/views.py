from django.shortcuts import render
from django.shortcuts import render, redirect
from django.contrib import messages
from accounts.decorators import user_login_required
from django.views.decorators.cache import never_cache
from orders.models import Order,OrderItem,OrderReturn
from django.shortcuts import render, redirect, get_object_or_404
from accounts.decorators import user_login_required
from django.contrib import messages
from django.views.decorators.cache import never_cache
from django.contrib.auth import login, logout, authenticate, get_user_model

User = get_user_model()

# checkout_view
# place_order_view
# order_list_view
# order_detail_view
@user_login_required
def user_orders(request):
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "orders/user_orders.html", {"orders": orders})

@user_login_required
def request_order_return(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user,
        order_status='DELIVERED'
    )

    if hasattr(order, 'orderreturn'):
        messages.warning(request, "Return already requested.")
        return redirect('orders:user_orders')

    if request.method == "POST":
        reason = request.POST.get("reason")

        OrderReturn.objects.create(
            order=order,
            reason=reason
        )

        order.order_status = 'RETURN_REQUESTED'
        order.save()

        messages.success(request, "Return request submitted successfully.")
        return redirect('orders:user_orders')

    return render(request, "orders/request_return.html", {"order": order})

@never_cache
@user_login_required
def cancel_order(request, order_id):
    order = get_object_or_404(Order,id=order_id,user=request.user,order_status__in=["PLACED", "CONFIRMED"])

    if request.method == "POST":
        order.order_status = "CANCELLED"
        order.save()
        messages.success(request, "Order cancelled successfully")
        return redirect("accounts:user_profile")

    return render(
        request,
        "orders/order_cancel_confirm.html",
        {"order": order}
    )
