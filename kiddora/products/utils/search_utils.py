from django.db.models import Q


def apply_search(queryset, search_term, fields):
    """
    Applies icontains search across multiple fields.

    usage:
    queryset = apply_search(queryset, search, [
        "product_name",
        "brand",
        "sku"
    ])
    """

    if not search_term:
        return queryset

    query = Q()
    for field in fields:
        query |= Q(**{f"{field}__icontains": search_term})

    return queryset.filter(query)
