from django.db import models
from django.conf import settings


class SavedRoute(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    origin = models.CharField(max_length=255)
    destination = models.CharField(max_length=255)
    waypoints = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.user})"


class OversizedLoadDetail(models.Model):
    route = models.ForeignKey(SavedRoute, on_delete=models.CASCADE, related_name='oversized_details')
    width = models.DecimalField(max_digits=6, decimal_places=2)
    height = models.DecimalField(max_digits=6, decimal_places=2)
    length = models.DecimalField(max_digits=6, decimal_places=2)
    weight = models.DecimalField(max_digits=8, decimal_places=2)
    special_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Oversized for {self.route}"
