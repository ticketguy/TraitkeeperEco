"""
admin_secure/forms.py
Forms for encrypted secret management in Django admin.
"""

from django import forms
from .models import EncryptedSecret


class EncryptedSecretForm(forms.ModelForm):
    """
    Custom form for EncryptedSecret that allows inputting plaintext value.
    The plaintext is encrypted before saving.
    """
    plaintext_value = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 4,
            'cols': 80,
            'placeholder': 'Enter the secret value (will be encrypted automatically)',
            'style': 'font-family: monospace;'
        }),
        required=False,
        help_text='Enter the secret value in plaintext. It will be encrypted before saving. '
                  'Leave blank to keep existing encrypted value.'
    )

    class Meta:
        model = EncryptedSecret
        fields = ['name', 'secret_type', 'description', 'is_active', 'expires_at']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'expires_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make plaintext_value required only when creating a new secret
        if not self.instance.pk:
            self.fields['plaintext_value'].required = True
            self.fields['plaintext_value'].help_text = 'Enter the secret value in plaintext. It will be encrypted before saving.'
        else:
            self.fields['plaintext_value'].help_text = 'Leave blank to keep existing encrypted value. Enter new value to re-encrypt.'

    def save(self, commit=True):
        """
        Save the secret, encrypting the plaintext value if provided.
        """
        instance = super().save(commit=False)

        # Get plaintext value from form
        plaintext = self.cleaned_data.get('plaintext_value')

        # If plaintext is provided, encrypt and save it
        if plaintext:
            # Get the user who is saving (should be set by admin)
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Try to get request user from thread-local storage or use a default
            try:
                from threading import current_thread
                request = getattr(current_thread(), 'request', None)
                user = request.user if request and hasattr(request, 'user') else None
            except:
                user = None

            # Encrypt and save
            instance.encrypt_and_save(plaintext, user)
            return instance

        if commit:
            instance.save()

        return instance
