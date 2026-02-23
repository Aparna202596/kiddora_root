from django.shortcuts import render, get_object_or_404
from django.db.models import Sum
from django.utils.timezone import now
from datetime import timedelta, datetime
from accounts.decorators import admin_login_required
from shopcore.models import *

# Admin Wallet Transaction List
# -----------------------
@admin_login_required
def admin_wallet_list(request):
    transactions = WalletTransaction.objects.select_related("wallet__user").order_by("-created_at")

    # ----- FILTER BY DATE RANGE -----
    start_date = request.GET.get("start_date")  # "YYYY-MM-DD"
    end_date = request.GET.get("end_date")
    if start_date and end_date:
        transactions = transactions.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )

    # ----- FILTER BY USER -----
    user_id = request.GET.get("user_id")
    if user_id:
        transactions = transactions.filter(wallet__user__id=user_id)

    # ----- FILTER BY TRANSACTION TYPE -----
    txn_type = request.GET.get("txn_type")
    if txn_type:
        transactions = transactions.filter(txn_type=txn_type)

    # Pagination (optional)
    from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
    paginator = Paginator(transactions, 25)
    page = request.GET.get("page")
    try:
        transactions = paginator.page(page)
    except PageNotAnInteger:
        transactions = paginator.page(1)
    except EmptyPage:
        transactions = paginator.page(paginator.num_pages)

    return render(request, "wallet/admin_wallet_list.html", {
        "transactions": transactions,
        "start_date": start_date,
        "end_date": end_date,
        "user_id": user_id,
        "txn_type": txn_type,
    })


# -----------------------
# Admin Wallet Transaction Detail
# -----------------------
@admin_login_required
def admin_wallet_detail(request, txn_id):
    txn = get_object_or_404(WalletTransaction, id=txn_id)

    # If reference_type is ORDER or RETURN, fetch related object
    reference_obj = None
    if txn.reference_type == "ORDER":
        reference_obj = Order.objects.filter(order_id=txn.reference_id).first()
    elif txn.reference_type == "RETURN":
        reference_obj = Return.objects.filter(id=txn.reference_id).first()

    return render(request, "wallet/admin_wallet_detail.html", {
        "txn": txn,
        "reference_obj": reference_obj,
    })

