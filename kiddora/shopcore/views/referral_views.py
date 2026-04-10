from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

from accounts.decorators import admin_login_required, user_login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from shopcore.models import (Coupon, CouponUsage, Offer, ReferralCode,
                            ReferralUse)

User = get_user_model()

# ────────────────────────────────────────────────── HELPER FUNCTIONS ──────────────────────────────────────────────────


def get_or_create_referral_record(user) -> ReferralCode:
    rc, _ = ReferralCode.objects.get_or_create(
        user=user,
        defaults={"code": ReferralCode.fresh_code()},
    )
    return rc


def _make_referral_coupon(
    prefix: str, discount_value: Decimal, usage_limit: int = 1
) -> Coupon:
    """Create a personal one-time referral coupon valid for 30 days."""
    coupon = Coupon.objects.create(
        code=f"{prefix}-{uuid.uuid4().hex[:8].upper()}",
        coupon_type="REFERRAL",
        discount_type="FLAT",
        discount_value=discount_value,
        min_order_amount=Decimal("0"),
        start_date=timezone.now(),
        expiry_date=timezone.now() + timedelta(days=30),
        usage_limit=usage_limit,
        is_active=True,
    )
    return coupon


def _award_referrer_coupon(referrer) -> Coupon | None:

    now = timezone.now()

    # Look for an admin-configured referrer reward on a live REFERRAL offer
    offer = (
        Offer.objects.filter(
            offer_type="REFERRAL",
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
        )
        .exclude(referrer_coupon=None)
        .first()
    )
    if offer and offer.referrer_coupon and offer.referrer_coupon.is_valid():
        return offer.referrer_coupon
# Auto-generate: ₹100 flat, usable once, 30-day validity
    return _make_referral_coupon("REF-REFERRER", Decimal("100"), usage_limit=1)


def _award_new_user_coupon() -> Coupon | None:

    now = timezone.now()

    # Look for an admin-configured new-user welcome reward on a live REFERRAL offer
    offer = (
        Offer.objects.filter(
            offer_type="REFERRAL",
            is_active=True,
            is_deleted=False,
            start_date__lte=now,
        )
        .exclude(new_user_coupon=None)
        .first()
    )
    if offer and offer.new_user_coupon and offer.new_user_coupon.is_valid():
        return offer.new_user_coupon

    # Auto-generate: ₹50 flat welcome coupon, usable once, 30-day validity
    return _make_referral_coupon("REF-NEWUSER", Decimal("50"), usage_limit=1)


def process_referral_on_signup(
    new_user,
    referral_code_str: str = "",
    referral_token: str = "",
) -> bool:

    referral_record = None

    if referral_token:
        try:
            referral_record = ReferralCode.objects.select_related("user").get(
                token=referral_token
            )
        except ReferralCode.DoesNotExist:
            pass

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

    if (
        referrer == new_user
        or ReferralUse.objects.filter(referred_user=new_user).exists()
    ):
        return False

    existing_referrer_use = ReferralUse.objects.filter(
        referral_code=referral_record,
        coupon_awarded__isnull=False,
    ).select_related("coupon_awarded").first()

    if existing_referrer_use and existing_referrer_use.coupon_awarded:
        referrer_coupon = existing_referrer_use.coupon_awarded
        # Each new sign-up earns the referrer one more use of their coupon
        referrer_coupon.usage_limit += 1
        # Extend validity: push expiry 30 days from now if it would expire sooner
        extended = timezone.now() + timedelta(days=30)
        if referrer_coupon.expiry_date < extended:
            referrer_coupon.expiry_date = extended
        referrer_coupon.save(update_fields=["usage_limit", "expiry_date"])
    else:
        referrer_coupon = _award_referrer_coupon(referrer)

    new_user_coupon = _award_new_user_coupon()  # new user always gets a fresh one

    # ── Record the referral use with BOTH coupons ─────────────────────────
    ReferralUse.objects.create(
        referral_code=referral_record,
        referred_user=new_user,
        coupon_awarded=referrer_coupon,
        new_user_coupon=new_user_coupon,
    )

    # ── Pre-create CouponUsage rows so coupons show in checkout immediately ─
    if referrer_coupon:
        CouponUsage.objects.get_or_create(
            coupon=referrer_coupon,
            user=referrer,
            defaults={"times_used": 0},
        )
    if new_user_coupon:
        CouponUsage.objects.get_or_create(
            coupon=new_user_coupon,
            user=new_user,
            defaults={"times_used": 0},
        )
    return True


def award_referral_rewards(referrer, new_user, referral_code_obj):
    # Find active referral offer (if any)
    referral_offer = Offer.objects.filter(
        offer_type="REFERRAL",
        is_active=True,
        is_deleted=False,
        start_date__lte=timezone.now(),
    ).first()

    if not referral_offer:
        return

    coupon_awarded = None  # for referrer
    new_user_coupon = None  # for new user

    if referral_offer.referrer_coupon:
        coupon_awarded = referral_offer.referrer_coupon

    if referral_offer.new_user_coupon:
        new_user_coupon = referral_offer.new_user_coupon

    ReferralUse.objects.create(
        referral_code=referral_code_obj,
        referred_user=new_user,
        coupon_awarded=coupon_awarded,  # to referrer
        new_user_coupon=new_user_coupon,  # to new user
    )

    if coupon_awarded:
        coupon_awarded.used_count += 1
        coupon_awarded.save(update_fields=["used_count"])
    if new_user_coupon:
        new_user_coupon.used_count += 1
        new_user_coupon.save(update_fields=["used_count"])


# ────────────────────────────────────────────────── MY REFERRALS ──────────────────────────────────────────────────


@never_cache
@user_login_required
def my_referrals(request):
    rc = get_or_create_referral_record(request.user)
    uses = rc.uses.select_related(
        "referred_user", "coupon_awarded", "new_user_coupon"
    ).order_by("-created_at")

    referral_link = request.build_absolute_uri(f"/accounts/user/signup/?ref={rc.token}")

    # Show the new-user coupon this user received (if they were referred themselves)
    my_referral_use = (
        ReferralUse.objects.filter(referred_user=request.user)
        .select_related("new_user_coupon", "coupon_awarded")
        .first()
    )

    return render(
        request,
        "referral/my_referrals.html",
        {
            "referral_code": rc,
            "referral_link": referral_link,
            "uses": uses,
            "total_uses": uses.count(),
            "my_new_user_coupon": (
                my_referral_use.new_user_coupon if my_referral_use else None
            ),
            "my_referrer_coupon": (
                my_referral_use.coupon_awarded if my_referral_use else None
            ),
        },
    )


# ────────────────────────────────────────────────── ADMIN: LIST ──────────────────────────────────────────────────


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
    page_obj = Paginator(qs, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "referral/admin_referral_list.html",
        {
            "page_obj": page_obj,
            "search": search,
        },
    )


# ────────────────────────────────────────────────── ADMIN: REFERRAL USES ──────────────────────────────────────────────────


@never_cache
@admin_login_required
def admin_referral_uses(request, referral_id):
    referral_code = get_object_or_404(ReferralCode, id=referral_id)
    uses = referral_code.uses.select_related(
        "referred_user", "coupon_awarded", "new_user_coupon"
    ).order_by("-created_at")
    page_obj = Paginator(uses, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "referral/admin_referral_uses.html",
        {
            "referral_code": referral_code,
            "page_obj": page_obj,
        },
    )
