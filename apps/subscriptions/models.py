from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Plan(models.Model):
    PLAN_TYPES = [
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('team', 'Team'),
    ]
    
    INTERVAL_CHOICES = [
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    name = models.CharField(max_length=100)
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    interval = models.CharField(max_length=10, choices=INTERVAL_CHOICES, default='monthly')
    product_id = models.CharField(max_length=255, unique=True)
    max_drivers = models.IntegerField(default=1, help_text="Maximum number of drivers for team plans")
    trial_days = models.IntegerField(default=7, help_text="Trial period in days")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['plan_type', 'price']
        verbose_name = 'Plan'
        verbose_name_plural = 'Plans'
    
    def __str__(self):
        return f"{self.name} - ${self.price}/{self.interval}"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ]
    
    PLATFORM_CHOICES = [
        ('google', 'Google Play'),
        ('apple', 'Apple App Store'),
    ]
    
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES, blank=True, null=True)
    
    trial_start_date = models.DateTimeField(blank=True, null=True)
    trial_end_date = models.DateTimeField(blank=True, null=True)
    renewal_date = models.DateTimeField(blank=True, null=True)
    
    latest_receipt_token = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Subscription'
        verbose_name_plural = 'Subscriptions'
    
    def __str__(self):
        return f"{self.user.email} - {self.plan.name if self.plan else 'No Plan'}"
    
    def is_trial_active(self):
        """Check if trial period is still active"""
        if self.trial_end_date is None:
            return False
        return timezone.now() < self.trial_end_date
    
    def is_subscription_active(self):
        """Check if subscription is active (not expired)"""
        if self.renewal_date is None:
            return self.status == 'active'
        return self.status == 'active' and timezone.now() < self.renewal_date

    def activate_trial(self, plan=None):
        """
        Activate a trial for this subscription.
        If plan not provided, try to pick a 'basic' monthly Plan.
        """
        if plan is None:
            try:
                plan = Plan.objects.filter(plan_type='basic', interval='monthly', is_active=True).first()
            except Exception:
                plan = None

        now = timezone.now()
        self.plan = plan
        self.status = 'trial'
        self.trial_start_date = now
        self.trial_end_date = now + timedelta(days=(plan.trial_days if plan else 7))
        # set renewal_date optionally after trial ends (example: trial_end + 30 days)
        self.renewal_date = self.trial_end_date + timedelta(days=30)
        self.save(update_fields=['plan', 'status', 'trial_start_date', 'trial_end_date', 'renewal_date'])
        return self

    def is_active_and_valid(self):
        """Helper used in views to check if subscription is active and not expired."""
        if self.status == 'active':
            return self.is_subscription_active()
        if self.status == 'trial':
            return self.is_trial_active()
        return False