from rest_framework import views, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Subscription, Plan
from .serializers import IAPValidateSerializer, SubscriptionStatusSerializer


class IAPValidateView(views.APIView):
    """
    API to validate Google Play or Apple App Store purchase.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IAPValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        platform = serializer.validated_data['platform']
        product_id = serializer.validated_data['product_id']  # ✅ product_id ব্যবহার করছি
        token = serializer.validated_data.get('token')

        # ✅ product_id দিয়ে Plan খুঁজছি (google_product_id নয়)
        plan = Plan.objects.filter(product_id=product_id, is_active=True).first()

        if not plan:
            return Response(
                {"error": f"Invalid product_id '{product_id}' or plan not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get or create subscription for the user
        subscription, created = Subscription.objects.get_or_create(user=request.user)
        subscription.plan = plan
        subscription.status = 'active'
        subscription.platform = platform
        subscription.latest_receipt_token = token
        subscription.renewal_date = plan.get_next_renewal_date()
        subscription.save()

        return Response({
            "success": True,
            "message": "Subscription activated successfully.",
            "subscription": {
                "status": subscription.status,
                "plan": subscription.plan.name,
                "platform": subscription.platform,
                "renewal_date": subscription.renewal_date.isoformat() if subscription.renewal_date else None,
            }
        }, status=status.HTTP_200_OK)


class SubscriptionCheckView(views.APIView):
    """
    API to check if user has an active subscription.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subscription = Subscription.objects.get(user=request.user)
            
            # Check if subscription is still valid
            is_valid = subscription.is_active_and_valid()
            
            return Response({
                "active": is_valid,
                "need_subscription": not is_valid,
                "status": subscription.status,
                "plan": subscription.plan.name if subscription.plan else None,
                "renewal_date": subscription.renewal_date.isoformat() if subscription.renewal_date else None,
                "message": "Your subscription is active." if is_valid else "Your subscription has expired. Please renew to continue."
            }, status=status.HTTP_200_OK)
        
        except Subscription.DoesNotExist:
            return Response({
                "active": False,
                "need_subscription": True,
                "message": "You need a subscription to continue using the service."
            }, status=status.HTTP_404_NOT_FOUND)


class SubscriptionStatusView(views.APIView):
    """
    API to get subscription status and details.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            subscription = Subscription.objects.get(user=request.user)
            serializer = SubscriptionStatusSerializer(subscription)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        except Subscription.DoesNotExist:
            return Response(
                {"error": "No subscription found for the user."},
                status=status.HTTP_404_NOT_FOUND
            )


class PlansView(views.APIView):
    """
    API to list available subscription plans.
    """
    def get(self, request):
        plans = Plan.objects.filter(is_active=True).values(
            'id', 'name', 'price', 'currency', 'interval', 'product_id'
        )
        return Response({"plans": list(plans)}, status=status.HTTP_200_OK)