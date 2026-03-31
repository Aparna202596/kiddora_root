from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from accounts.decorators import admin_login_required, user_login_required
from shopcore.models import Coupon, CouponUsage, ReferralCode, ReferralUse, Offer

User = get_user_model()


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def get_or_create_referral_record(user) -> ReferralCode:   # renamed (removed _)
    """
    Ensure the user has a ReferralCode row.
    """
    rc, _ = ReferralCode.objects.get_or_create(
        user=user,
        defaults={"code": ReferralCode.fresh_code()},   # now uses model method
    )
    return rc

def _award_referral_coupon(referrer) -> Coupon | None:
    """
    Find the active REFERRAL offer and return its linked coupon,
    or auto-generate a one-time personal coupon for the referrer.
    """
    now = timezone.now()
    offer = (
        Offer.objects.filter(
            offer_type="REFERRAL",
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
        )
        .exclude(referral_coupon=None)
        .first()
    )

    if offer and offer.referral_coupon and offer.referral_coupon.is_valid():
        return offer.referral_coupon

    # Auto-generate a personal one-time 10% coupon valid 30 days
    code = f"REF-{referrer.referral_record.code[-6:]}-{uuid.uuid4().hex[:4].upper()}"
    coupon = Coupon.objects.create(
        code = f"REF-{uuid.uuid4().hex[:8].upper()}",   # or your existing code generator
        coupon_type = "REFERRAL",                       # ← THIS IS THE ONLY CHANGE YOU NEED
        discount_type = "FLAT",
        discount_value = Decimal("100"),
        min_order_amount = Decimal("0"),
        start_date = timezone.now(),
        expiry_date = timezone.now() + timedelta(days=30),
        usage_limit = 1,
        is_active = True,
    )
    return coupon


def process_referral_on_signup(
    new_user,
    referral_code_str: str = "",
    referral_token: str = "",
) -> bool:
    """
    Call this from the signup view after the new user is saved.
    """
    referral_record = None

    # Try token first
    if referral_token:
        try:
            referral_record = ReferralCode.objects.select_related("user").get(
                token=referral_token
            )
        except ReferralCode.DoesNotExist:
            pass

    # Fall back to typed code
    if not referral_record and referral_code_str:
        try:
            referral_record = ReferralCode.objects.select_related("user").get(
                code=referral_code_str.strip().upper()
            )
        except ReferralCode.DoesNotExist:
            pass

    if not referral_record:
        return False

    referrer = referral_record.user

    if referrer == new_user or ReferralUse.objects.filter(referred_user=new_user).exists():
        return False

    coupon = _award_referral_coupon(referrer)

    ReferralUse.objects.create(
        referral_code=referral_record,
        referred_user=new_user,
        coupon_awarded=coupon,
    )

    # ✅ Removed: new_user.referred_by = referrer  (field no longer exists)

    if coupon:
        CouponUsage.objects.get_or_create(
            coupon=coupon,
            user=referrer,
            defaults={"times_used": 0},
        )

    return True
# ─────────────────────────────────────────────────────────────
# USER: MY REFERRALS
# ─────────────────────────────────────────────────────────────

@never_cache
@user_login_required
def my_referrals(request):
    rc = get_or_create_referral_record(request.user)   # updated call
    uses = rc.uses.select_related("referred_user", "coupon_awarded").order_by("-created_at")

    referral_link = request.build_absolute_uri(f"/accounts/user/signup/?ref={rc.token}")

    return render(request, "referral/my_referrals.html", {
        "referral_code": rc,
        "referral_link": referral_link,
        "uses": uses,
        "total_uses": uses.count(),
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: REFERRAL CODE LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_referral_list(request):
    search = request.GET.get("search", "").strip()
    qs = ReferralCode.objects.select_related("user").order_by("-created_at")
    if search:
        qs = qs.filter(
            Q(code__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__full_name__icontains=search)
        )
    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "referral/admin_referral_list.html", {
        "page_obj": page_obj,
        "search":   search,
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: REFERRAL USES DETAIL
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_referral_uses(request, referral_id):
    referral_code = get_object_or_404(ReferralCode, id=referral_id)
    uses = referral_code.uses.select_related(
        "referred_user", "coupon_awarded"
    ).order_by("-created_at")
    page_obj = Paginator(uses, 20).get_page(request.GET.get("page"))
    return render(request, "referral/admin_referral_uses.html", {
        "referral_code": referral_code,
        "page_obj":      page_obj,
    })