from django.urls import path
from . import views

app_name = 'returns'

urlpatterns = [
    path("return/request/<int:order_item_id>",views.request_return,name="request_return"),
    path("return/status/", views.return_status_view, name="return_status_view"),
    path("return/detail/<int:return_id>/", views.return_detail_view, name="return_detail_view"),
    path("admin/return_list/", views.admin_return_list, name="admin_return_list"),
    path("admin/return/verify/<int:return_id>/", views.admin_verify_return, name="admin_verify_return"),
    path("admin/return/analytics/", views.return_analytics_dashboard, name="return_analytics_dashboard"),

]