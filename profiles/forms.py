# profiles/forms.py
from django import forms
from django.conf import settings
from.models import Profile
from notifications.models import NotificationPreference # Assuming this is the path

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

