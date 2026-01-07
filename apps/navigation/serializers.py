from rest_framework import serializers
from .models import SavedRoute, OversizedLoadDetail


class OversizedLoadDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OversizedLoadDetail
        fields = '__all__'


class SavedRouteSerializer(serializers.ModelSerializer):
    oversized_details = OversizedLoadDetailSerializer(many=True, read_only=True)

    class Meta:
        model = SavedRoute
        fields = ['id', 'user', 'name', 'origin', 'destination', 'waypoints', 'created_at', 'oversized_details']
