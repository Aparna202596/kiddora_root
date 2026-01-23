from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

def paginate_queryset(queryset, page_number, per_page=10):
    paginator = Paginator(queryset, per_page)

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    return page_obj
