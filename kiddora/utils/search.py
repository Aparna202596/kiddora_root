from django.db.models import Q

def apply_search(queryset, search_query, fields):
    if search_query:
        query = Q()
        for field in fields:
            query |= Q(**{f"{field}__icontains": search_query})
        return queryset.filter(query)
    return queryset
#from utils.search import apply_search