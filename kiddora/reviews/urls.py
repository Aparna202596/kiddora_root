from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('review/add/<int:product_id>/', views.add_review, name='add_review'),
    path('review/edit/<int:review_id>/', views.edit_review, name='edit_review'),
    path('review/delete/<int:review_id>/', views.delete_review, name='delete_review'),
    
    path('admin/reviews/', views.user_review_list, name='user_review_list'),
    path('admin/reviews/detail/<int:review_id>/', views.user_review, name='user_review'),
    path('admin/review/delete/<int:review_id>/', views.delete_user_review, name='delete_user_review'),
]