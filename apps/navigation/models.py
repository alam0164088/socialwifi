from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class SavedRoute(models.Model):
    """Store user's saved routes and current location."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_routes')
    name = models.CharField(max_length=255)
    latitude = models.FloatField(default=0.0)  # Add default
    longitude = models.FloatField(default=0.0)  # Add default
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('user', 'name')
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.name}"


class OversizedLoadDetail(models.Model):
    """Store oversized load details."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='oversized_loads')
    title = models.CharField(max_length=255, default='Untitled')
    description = models.TextField(blank=True, default='')
    weight = models.FloatField(null=True, blank=True)  # in kg
    dimensions = models.CharField(max_length=255, blank=True, default='')
    latitude = models.FloatField(default=0.0)
    longitude = models.FloatField(default=0.0)
    status = models.CharField(max_length=50, choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.email} - {self.title}"