from django.urls import path
from .views import (
    IAPValidateView,
    SubscriptionCheckView,
    SubscriptionStatusView,
    PlansView
)

urlpatterns = [
    path('validate-iap/', IAPValidateView.as_view(), name='validate_iap'),
    path('check-subscription/', SubscriptionCheckView.as_view(), name='check_subscription'),
    path('status/', SubscriptionStatusView.as_view(), name='subscription_status'),
    path('plans/', PlansView.as_view(), name='plans'),
]