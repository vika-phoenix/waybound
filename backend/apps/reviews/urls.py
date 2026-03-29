from django.urls import path
from . import views

urlpatterns = [
    path('',           views.review_list,      name='review-list'),
    path('mine/',      views.my_reviews,        name='review-mine'),
    path('operator/',  views.operator_reviews,  name='review-operator'),
    path('<int:pk>/reply/', views.review_reply, name='review-reply'),
]
