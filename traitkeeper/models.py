from django.db import models
from django.utils import timezone
from admin_panel.models import AdminUser
import uuid

class Token(models.Model):
    """
    Custom Token model for external users, with email and expiry fields.
    """
    key = models.CharField(max_length=40, primary_key=True, default=uuid.uuid4().hex)
    email = models.EmailField(
        help_text="Email address of the external user associated with this token."
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="The date and time when the token expires. Leave blank for no expiry."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        AdminUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_tokens',
        help_text="The admin user who created this token."
    )

    class Meta:
        verbose_name = "Token"
        verbose_name_plural = "Tokens"

    def __str__(self):
        return f"Token for {self.email} (Created by {self.created_by})"

    def is_expired(self):
        """
        Check if the token has expired.
        """
        if self.expires_at is None:
            return False
        return self.expires_at < timezone.now()