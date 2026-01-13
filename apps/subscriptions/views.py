from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta

from .models import Subscription, Plan
from .serializers import IAPValidateSerializer, SubscriptionStatusSerializer


class SubscriptionStatusView(views.APIView):
    """
    API to get current subscription status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        
        if not subscription:
            return Response({
                "status": "no_subscription",
                "message": "No active subscription found."
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = SubscriptionStatusSerializer(subscription)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SubscriptionCheckView(views.APIView):
    """
    API to check if user has active subscription.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = Subscription.objects.filter(user=request.user).first()
        
        if not subscription:
            return Response({
                "has_subscription": False,
                "message": "No subscription found."
            }, status=status.HTTP_200_OK)
        
        is_active = subscription.status == 'active'
        is_trial_active = subscription.is_trial_active()
        
        return Response({
            "has_subscription": True,
            "is_active": is_active,
            "is_trial_active": is_trial_active,
            "status": subscription.status,
            "plan": subscription.plan.name if subscription.plan else None,
            "renewal_date": subscription.renewal_date.isoformat() if subscription.renewal_date else None,
        }, status=status.HTTP_200_OK)


class IAPValidateView(views.APIView):
    """
    API to validate Google Play or Apple App Store purchase.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IAPValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        platform = serializer.validated_data['platform']
        product_id = serializer.validated_data['product_id']
        token = serializer.validated_data.get('token')

        # Search by product_id (works for both platforms)
        plan = Plan.objects.filter(product_id=product_id, is_active=True).first()

        if not plan:
            return Response(
                {"error": f"Invalid product_id '{product_id}' or plan not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get or create subscription
        subscription, created = Subscription.objects.get_or_create(user=request.user)
        
        # Set trial period
        now = timezone.now()
        trial_days = plan.trial_days or 15  # Default 15 days if not set
        trial_end = now + timedelta(days=trial_days)
        
        subscription.plan = plan
        subscription.status = 'trial'
        subscription.platform = platform
        subscription.trial_start_date = now
        subscription.trial_end_date = trial_end
        subscription.latest_receipt_token = token
        
        # Renewal date = trial end + subscription interval
        if plan.interval == 'monthly':
            subscription.renewal_date = trial_end + timedelta(days=30)
        elif plan.interval == 'yearly':
            subscription.renewal_date = trial_end + timedelta(days=365)
        else:
            subscription.renewal_date = trial_end + timedelta(days=30)
        
        subscription.save()

        return Response({
            "success": True,
            "message": "Subscription activated with trial period.",
            "subscription": {
                "status": subscription.status,
                "plan": subscription.plan.name,
                "platform": subscription.platform,
                "trial_start_date": subscription.trial_start_date.isoformat(),
                "trial_end_date": subscription.trial_end_date.isoformat(),
                "renewal_date": subscription.renewal_date.isoformat(),
            }
        }, status=status.HTTP_200_OK)


class PlansView(views.APIView):
    """
    API to list available subscription plans.
    """
    def get(self, request):
        plans = Plan.objects.filter(is_active=True).values(
            'id', 'name', 'price', 'currency', 'interval', 'trial_days', 'product_id'
        )
        return Response({"plans": list(plans)}, status=status.HTTP_200_OK)