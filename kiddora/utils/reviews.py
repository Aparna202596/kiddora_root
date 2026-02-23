from django.db.models import Avg, Count
from shopcore.models import Review

def get_product_review_stats(product):
    data = Review.objects.filter(product=product).aggregate(
        avg_rating=Avg("rating"),
        total_reviews=Count("id")
    )
    return {
        "avg_rating": round(data["avg_rating"] or 0, 1),
        "total_reviews": data["total_reviews"]
    }
