from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Review
from products.models import Product
from orders.models import OrderItem
from accounts.decorators import admin_login_required, user_login_required

def has_purchased_and_delivered(user, product):
    return OrderItem.objects.filter(
        order__user=user,
        product=product,
        status="DELIVERED"
    ).exists()

@user_login_required
def add_review(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if not has_purchased_and_delivered(request.user, product):
        messages.error(request, "You can review this product only after delivery.")
        return redirect("products:product_detail", product_id=product.id)

    if Review.objects.filter(user=request.user, product=product).exists():
        messages.error(request, "You have already reviewed this product.")
        return redirect("products:product_detail", product_id=product.id)

    if request.method == "POST":
        rating = int(request.POST.get("rating", 0))
        comment = request.POST.get("comment", "").strip()

        if rating < 1 or rating > 5:
            messages.error(request, "Rating must be between 1 and 5.")
            return redirect("reviews:add_review", product_id=product.id)

        Review.objects.create(
            user=request.user,
            product=product,
            rating=rating,
            comment=comment
        )

        messages.success(request, "Review submitted successfully.")
        return redirect("products:product_detail", product_id=product.id)

    return render(request, "reviews/review_form.html", {
        "product": product
    })

@user_login_required
def edit_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)

    if not has_purchased_and_delivered(request.user, review.product):
        messages.error(request, "You are not allowed to edit this review.")
        return redirect("reviews:user_review_list")

    if request.method == "POST":
        rating = int(request.POST.get("rating", 0))
        comment = request.POST.get("comment", "").strip()

        if rating < 1 or rating > 5:
            messages.error(request, "Rating must be between 1 and 5.")
            return redirect("reviews:edit_review", review_id=review.id)

        review.rating = rating
        review.comment = comment
        review.save()

        messages.success(request, "Review updated successfully.")
        return redirect("reviews:user_review_list")

    return render(request, "reviews/review_form.html", {
        "review": review,
        "product": review.product
    })

@user_login_required
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id, user=request.user)
    review.delete()
    messages.success(request, "Review deleted successfully.")
    return redirect("reviews:user_review_list")



@user_login_required
def user_review_list(request):
    reviews = Review.objects.filter(user=request.user).select_related("product")
    return render(request, "reviews/user_review_list.html", {
        "reviews": reviews
    })

@admin_login_required
def user_review(request):
    reviews = Review.objects.select_related("user", "product").order_by("-id")

    rating = request.GET.get("rating")
    if rating:
        reviews = reviews.filter(rating=rating)

    return render(request, "reviews/user_review_list.html", {
        "reviews": reviews,
        "admin_view": True
    })

@admin_login_required
def delete_user_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)
    review.delete()
    messages.success(request, "Review deleted successfully.")
    return redirect("reviews:user_review")
