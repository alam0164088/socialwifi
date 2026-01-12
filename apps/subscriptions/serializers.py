from rest_framework import serializers
from .models import Subscription, Plan


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ['id', 'name', 'price', 'currency', 'interval']


class IAPValidateSerializer(serializers.Serializer):
    token = serializers.CharField(required=False, allow_blank=True)
    platform = serializers.ChoiceField(choices=['google', 'apple'], required=True)
    product_id = serializers.CharField(required=True)


class SubscriptionStatusSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = ['status', 'plan', 'trial_start_date', 'trial_end_date', 'renewal_date']
