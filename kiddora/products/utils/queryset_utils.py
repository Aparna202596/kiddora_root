def apply_product_filters(queryset, category_id=None, subcategory_id=None):
    """
    Applies category & subcategory filters
    """

    if category_id:
        queryset = queryset.filter(subcategory__category_id=category_id)

    if subcategory_id:
        queryset = queryset.filter(subcategory_id=subcategory_id)

    return queryset


def apply_sorting(queryset, sort_key, sort_map, default="-id"):
    """
    Generic sorting utility
    """

    order_by = sort_map.get(sort_key, default)
    return queryset.order_by(order_by)
