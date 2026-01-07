from django.urls import path
from . import views

urlpatterns = [
    path('plans/', views.PlansView.as_view(), name='plans'),
]
