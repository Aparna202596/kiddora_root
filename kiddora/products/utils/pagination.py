from django.core.paginator import Paginator


def paginate_queryset(request, queryset, per_page=10):
    """
    Generic pagination utility for admin listings
    """

    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return page_obj
