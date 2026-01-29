from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('product/review/add/', views.add_review, name='add_review'),
    path('product/review/edit/', views.edit_review, name='edit_review'),
    path('product/review/delete/', views.delete_review, name='delete_review'),
    
    path('admin/reviews/', views.user_review_list, name='user_review_list'),
    path('admin/reviews/detail/<int:review_id>/', views.user_review, name='user_review'),
    path('admin/review/delete/<int:review_id>/', views.delete_user_review, name='delete_user_review'),
]