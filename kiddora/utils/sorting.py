def apply_sorting(queryset, sort_key, allowed_sorts):
    if sort_key in allowed_sorts:
        return queryset.order_by(allowed_sorts[sort_key])
    return queryset

SORT_OPTIONS = {
    "price_low": "price",
    "price_high": "-price",
    "az": "name",
    "za": "-name",
    "latest": "-created_at"
}
#from utils.sorting import apply_sorting