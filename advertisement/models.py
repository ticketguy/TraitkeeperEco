# advertisement/models.py
from django.utils import timezone
from django.db import models


class HeroSlide(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    button_text = models.CharField(max_length=100, blank=True, default="")  # Optional
    button_url = models.CharField(max_length=200, blank=True, default="")  # Optional
    image_url = models.URLField(blank=True, null=True)
    url = models.URLField(blank=True, null=True)  # For clickable slide
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']