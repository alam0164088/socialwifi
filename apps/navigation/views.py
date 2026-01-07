"""
apps/navigation/views.py

এই ফাইলটি কোর ম্যাপ এবং রুট সম্পর্কিত API-এর স্ট্রাকচার ধারণ করে।
- SavedRouteViewSet: রুট সংরক্ষণ/লিস্ট/রিট্রিভ/আপডেট/ডিলিট
- OversizedLoadViewSet: অতিরিক্ত লোড ডিটেইল সংরক্ষণ ও পরিচালনা

TODOs / Next steps:
- Permissions (IsAuthenticated), pagination, filtering এবং query optimization যোগ করুন
- Tests লিখুন (happy path + validations)
- Map-routing logic (e.g., integrating with external routing APIs) যোগ করুন

"""
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from .models import SavedRoute, OversizedLoadDetail
from .serializers import SavedRouteSerializer, OversizedLoadDetailSerializer


class SavedRouteViewSet(viewsets.ModelViewSet):
    """ViewSet for SavedRoute

    Supports: list, retrieve, create, update, destroy

    Note: user-based filtering, permissions and ownership checks should be enforced in production.
    """
    queryset = SavedRoute.objects.all()
    serializer_class = SavedRouteSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # Basic pattern: if authenticated, return user's routes; otherwise public ones (if any)
        user = getattr(self.request, 'user', None)
        if user and user.is_authenticated:
            return SavedRoute.objects.filter(user=user)
        return SavedRoute.objects.none()

    def perform_create(self, serializer):
        # Attach the currently authenticated user as owner
        user = getattr(self.request, 'user', None)
        serializer.save(user=user)


class OversizedLoadViewSet(viewsets.ModelViewSet):
    """ViewSet for OversizedLoadDetail

    This manages size/weight metadata associated with a SavedRoute.
    """
    queryset = OversizedLoadDetail.objects.all()
    serializer_class = OversizedLoadDetailSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        user = getattr(self.request, 'user', None)
        if user and user.is_authenticated:
            # Only return oversized details for routes that belong to this user
            return OversizedLoadDetail.objects.filter(route__user=user)
        return OversizedLoadDetail.objects.none()

    def create(self, request, *args, **kwargs):
        # Example: validate that the route belongs to the requesting user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        route = serializer.validated_data.get('route')
        if route.user != request.user:
            return Response({'detail': 'Cannot add oversized details to a route you do not own.'}, status=status.HTTP_403_FORBIDDEN)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
