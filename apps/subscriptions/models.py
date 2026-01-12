from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Plan(models.Model):
    INTERVAL_CHOICES = [('monthly', 'Monthly'), ('yearly', 'Yearly')]
    
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    interval = models.CharField(max_length=20, choices=INTERVAL_CHOICES, default='monthly')
    
    # ✅ নতুন: একটি মাত্র product_id (Google এবং Apple উভয়ের জন্য)
    product_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def get_next_renewal_date(self):
        if self.interval == 'monthly':
            return timezone.now() + timedelta(days=30)
        elif self.interval == 'yearly':
            return timezone.now() + timedelta(days=365)
        return None

    def __str__(self):
        return f"{self.name} - ${self.price}"


class Subscription(models.Model):
    STATUS_CHOICES = (
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription_plan')
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name='subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    platform = models.CharField(max_length=10, choices=[('google', 'Google'), ('apple', 'Apple')], null=True, blank=True)
    latest_receipt_token = models.TextField(null=True, blank=True)
    trial_start_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    renewal_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def activate_trial(self):
        self.status = 'trial'
        self.trial_start_date = timezone.now()
        self.trial_end_date = timezone.now() + timedelta(days=15)
        self.save()

    def is_active_and_valid(self):
        if self.status == 'trial' and self.trial_end_date and self.trial_end_date < timezone.now():
            self.status = 'expired'
            self.save()
        elif self.status == 'active' and self.renewal_date and self.renewal_date < timezone.now():
            self.status = 'expired'
            self.save()
        return self.status in ['trial', 'active']

    def is_trial_active(self):
        if self.trial_end_date and self.trial_end_date > timezone.now():
            return True
        return False

    def __str__(self):
        return f"{self.user.email} - {self.status}"