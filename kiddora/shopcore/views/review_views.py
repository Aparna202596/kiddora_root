# shopcore/views/review_views.py
# User : submit, edit, delete their own review on a purchased product
# Admin: list, approve, reject reviews

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from accounts.decorators import admin_login_required
from products.models import Product
from shopcore.models import Order, Review


def _user_bought_product(user, product):
    """True if the user has at least one DELIVERED order containing this product."""
    return Order.objects.filter(
        user=user,
        order_status="DELIVERED",
        order_items__variant__product=product,
    ).exists()


# ─────────────────────────────────────────────────────────────
# USER: SUBMIT / EDIT REVIEW  (combined — same form)
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def submit_review(request, product_id):
    """
    GET  – show the review form (pre-filled if the user already reviewed).
    POST – create or update the review.
    Only allowed for products the user has purchased and received.
    """
    product = get_object_or_404(Product, id=product_id, is_active=True, is_deleted=False)

    if not _user_bought_product(request.user, product):
        messages.error(request, "You can only review products you have purchased and received.")
        return redirect("products:product_detail", product_id=product_id)

    existing = Review.objects.filter(user=request.user, product=product).first()

    if request.method == "POST":
        rating  = request.POST.get("rating", "")
        comment = request.POST.get("comment", "").strip()

        errors = []
        try:
            rating_int = int(rating)
            if rating_int < 1 or rating_int > 5:
                raise ValueError
        except (ValueError, TypeError):
            errors.append("Rating must be between 1 and 5.")
        if not comment:
            errors.append("A comment is required.")

        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "reviews/submit_review.html", {
                "product":  product,
                "existing": existing,
                "form_data": request.POST,
            })

        if existing:
            existing.rating     = rating_int
            existing.comment    = comment
            existing.is_approved = False   # re-approval required after edit
            existing.save(update_fields=["rating", "comment", "is_approved"])
            messages.success(request, "Your review has been updated and is pending approval.")
        else:
            Review.objects.create(
                user       = request.user,
                product    = product,
                rating     = rating_int,
                comment    = comment,
                is_approved = False,
            )
            messages.success(request, "Review submitted! It will appear after approval.")

        return redirect("products:product_detail", product_id=product_id)

    return render(request, "reviews/submit_review.html", {
        "product":  product,
        "existing": existing,
    })


# ─────────────────────────────────────────────────────────────
# USER: DELETE OWN REVIEW
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    product_id = review.product.id
    if request.method == "POST":
        review.delete()
        messages.success(request, "Your review has been deleted.")
    return redirect("products:product_detail", product_id=product_id)


# ─────────────────────────────────────────────────────────────
# USER: MY REVIEWS LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@login_required
def my_reviews(request):
    reviews  = Review.objects.filter(user=request.user).select_related("product").order_by("-created_at")
    page_obj = Paginator(reviews, 10).get_page(request.GET.get("page"))
    return render(request, "reviews/my_reviews.html", {"page_obj": page_obj})


# ─────────────────────────────────────────────────────────────
# ADMIN: LIST
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_review_list(request):
    search    = request.GET.get("search", "").strip()
    status_f  = request.GET.get("status", "")
    rating_f  = request.GET.get("rating", "")

    qs = Review.objects.select_related("user", "product").order_by("-created_at")

    if search:
        qs = qs.filter(
            Q(user__email__icontains=search)
            | Q(product__product_name__icontains=search)
            | Q(comment__icontains=search)
        )
    if status_f == "approved":
        qs = qs.filter(is_approved=True)
    elif status_f == "pending":
        qs = qs.filter(is_approved=False)
    if rating_f:
        qs = qs.filter(rating=int(rating_f))

    page_obj = Paginator(qs, 20).get_page(request.GET.get("page"))
    return render(request, "reviews/admin_review_list.html", {
        "page_obj": page_obj,
        "search":   search,
        "status_f": status_f,
        "rating_f": rating_f,
        "ratings":  [1, 2, 3, 4, 5],
    })


# ─────────────────────────────────────────────────────────────
# ADMIN: APPROVE
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_approve_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    if request.method == "POST":
        review.is_approved = True
        review.save(update_fields=["is_approved"])
        messages.success(request, f"Review by {review.user.email} approved.")
    return redirect("shopcore:admin_review_list")


# ─────────────────────────────────────────────────────────────
# ADMIN: REJECT (delete)
# ─────────────────────────────────────────────────────────────

@never_cache
@admin_login_required
def admin_reject_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    if request.method == "POST":
        review.delete()
        messages.success(request, "Review deleted.")
    return redirect("shopcore:admin_review_list")