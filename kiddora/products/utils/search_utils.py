from django.db.models import Q

def apply_search(queryset, search_term, fields):

    if not search_term:
        return queryset

    query = Q()
    for field in fields:
        query |= Q(**{f"{field}__icontains": search_term})

    return queryset.filter(query)
