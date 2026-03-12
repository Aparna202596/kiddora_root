# shopcore/views/referral_views.py
# User : view own referral code + how many people used it
# Admin: list all referral codes + referral uses

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from accounts.decorators import admin_login_required
from shopcore.models import ReferralCode, ReferralUse


# ─────────────────────────────────────────────────────────────
# USER: MY REFERRAL DASHBOARD
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def my_referral(request):
    """
    Shows the user's own referral code and a list of who used it.
    ReferralCode is created at signup via a signal — get_or_create here
    as a safety net.
    """
    referral_code, _ = ReferralCode.objects.get_or_create(user=request.user)
    uses = ReferralUse.objects.filter(
        referral_code=referral_code
    ).select_related("referred_user", "coupon_awarded").order_by("-created_at")

    return render(request, "shopcore/referral/my_referral.html", {
        "referral_code": referral_code,
        "uses":          uses,
        "total_uses":    uses.count(),
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: ALL REFERRAL CODES
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_referral_list(request):
    search = request.GET.get("search", "").strip()

    qs = ReferralCode.objects.select_related("user").annotate(
        use_count=Count("uses")
    ).order_by("-created_at")

    if search:
        qs = qs.filter(
            Q(code__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
        )

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "shopcore/admin/referral/admin_referral_list.html", {
        "page_obj": page_obj,
        "search":   search,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: REFERRAL USES (drill-down for a specific code)
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_referral_uses(request, referral_id):
    from django.shortcuts import get_object_or_404
    referral_code = get_object_or_404(ReferralCode, id=referral_id)
    uses = ReferralUse.objects.filter(
        referral_code=referral_code
    ).select_related("referred_user", "coupon_awarded").order_by("-created_at")

    page_obj = Paginator(uses, 20).get_page(request.GET.get("page"))
    return render(request, "shopcore/admin/referral/admin_referral_uses.html", {
        "referral_code": referral_code,
        "page_obj":      page_obj,
    })