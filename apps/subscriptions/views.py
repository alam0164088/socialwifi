from rest_framework.views import APIView
from rest_framework.response import Response
from .models import SubscriptionPlan
from .serializers import SubscriptionPlanSerializer


class PlansView(APIView):
    def get(self, request):
        plans = SubscriptionPlan.objects.all()
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)
