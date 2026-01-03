# profiles/forms.py
from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from .models import Profile, UsernameChangeHistory
from notifications.models import NotificationPreference # Assuming this is the path

User = get_user_model()

class ProfileUpdateForm(forms.ModelForm):
    """
    Form for updating core user profile information.
    Supports multiple avatar options: upload, NFT, or URL.
    """
    class Meta:
        model = Profile
        fields = [
            'display_name',
            'bio',
            'avatar_type',
            'avatar_image',
            'avatar_url',
            'avatar_nft_mint',
            'social_x',
            'social_discord',
            'website_url',
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'placeholder': 'How you want to appear',
                'maxlength': '50',
            }),
            'bio': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'placeholder': 'Tell us a bit about yourself (max 160 chars)',
                'maxlength': '160',
            }),
            'avatar_type': forms.Select(attrs={
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'id': 'avatar-type-select',
            }),
            'avatar_image': forms.ClearableFileInput(attrs={
                'class': 'w-full text-sm text-text-secondary-light dark:text-text-secondary-dark cursor-pointer',
                'accept': 'image/png,image/jpeg,image/jpg,image/gif,image/webp',
            }),
            'avatar_url': forms.URLInput(attrs={
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'placeholder': 'https://example.com/avatar.png',
            }),
            'avatar_nft_mint': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm font-mono',
                'placeholder': 'Enter NFT mint address (e.g., 7xKXt...)',
                'maxlength': '44',
            }),
            'social_x': forms.TextInput(attrs={
                'class': 'w-full p-2 pl-7 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'placeholder': 'YourHandle',
            }),
            'social_discord': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'placeholder': 'username#1234',
            }),
            'website_url': forms.URLInput(attrs={
                'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
                'placeholder': 'https://yourwebsite.com',
            }),
        }
        help_texts = {
            'avatar_type': 'Choose how you want to set your profile picture',
            'avatar_image': 'Upload an image file (PNG, JPG, GIF up to 2MB)',
            'avatar_url': 'Provide a direct URL to an image',
            'avatar_nft_mint': 'Use an NFT you own as your profile picture',
        }


class UsernameChangeForm(forms.Form):
    """
    Form for changing username with validation and rate limiting.
    Users can change username once every 60 days.
    """
    new_username = forms.CharField(
        max_length=150,
        min_length=3,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Enter new username',
            'autocomplete': 'off',
        }),
        help_text='3-150 characters. Letters, digits, and @/./+/-/_ only.'
    )

    reason = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Optional: Why are you changing your username?',
        }),
        help_text='Optional reason for audit trail'
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_username(self):
        """Validate new username"""
        new_username = self.cleaned_data.get('new_username')

        if not new_username:
            raise forms.ValidationError("Username is required")

        # Check if username already exists
        if User.objects.filter(username=new_username).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("This username is already taken")

        # Validate username format (Django's default validator)
        from django.core.validators import validate_slug
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            # Allow alphanumeric and @/./+/-/_
            import re
            if not re.match(r'^[\w.@+-]+$', new_username):
                raise forms.ValidationError(
                    "Username can only contain letters, digits, and @/./+/-/_ characters"
                )
        except DjangoValidationError as e:
            raise forms.ValidationError(str(e))

        # Check if user is trying to use the same username
        if new_username == self.user.username:
            raise forms.ValidationError("This is already your username")

        return new_username

    def clean(self):
        """Check if user can change username (60-day cooldown)"""
        cleaned_data = super().clean()

        if self.user:
            can_change, days_remaining, last_change = UsernameChangeHistory.can_change_username(self.user)

            if not can_change:
                raise forms.ValidationError(
                    f"You can only change your username once every 60 days. "
                    f"Please wait {days_remaining} more day{'s' if days_remaining != 1 else ''} "
                    f"(last changed on {last_change.changed_at.strftime('%B %d, %Y')})"
                )

        return cleaned_data

