# right_route_backend/apps/users/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django.conf import settings


class UserManager(BaseUserManager):
    """Custom user manager where email is the unique identifier
    for authentication instead of username.
    """
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.plain_password = password
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    # We won't use username — email is the unique identifier
    username = None
    email = models.EmailField(_('email address'), unique=True)
    plain_password = models.CharField(max_length=255, blank=True, null=True)

    # Additional optional fields
    is_touch_id_enabled = models.BooleanField(default=False)
    terms_agreed = models.BooleanField(default=False)

    # OTP verification fields
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.email


class Subscription(models.Model):
    STATUS_CHOICES = (
        ('trial', 'Trial'),
        ('active', 'Active'),
        ('expired', 'Expired'),
    )

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_subscription')
    plan = models.ForeignKey('subscriptions.Plan', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_subscriptions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='trial')
    trial_start_date = models.DateTimeField(null=True, blank=True)
    trial_end_date = models.DateTimeField(null=True, blank=True)
    renewal_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def activate_trial(self):
        from django.utils import timezone
        from datetime import timedelta
        self.status = 'trial'
        self.trial_start_date = timezone.now()
        self.trial_end_date = timezone.now() + timedelta(days=15)
        self.save()

    def is_active_and_valid(self):
        from django.utils import timezone
        if self.status == 'trial' and self.trial_end_date and self.trial_end_date < timezone.now():
            self.status = 'expired'
            self.save()
        elif self.status == 'active' and self.renewal_date and self.renewal_date < timezone.now():
            self.status = 'expired'
            self.save()
        return self.status in ['trial', 'active']

    def is_trial_active(self):
        from django.utils import timezone
        if self.trial_end_date and self.trial_end_date > timezone.now():
            return True
        return False

    def __str__(self):
        return f"{self.user.email} - {self.status}"