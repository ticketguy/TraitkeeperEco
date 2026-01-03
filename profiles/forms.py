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

    password = forms.CharField(
        max_length=128,
        required=True,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Enter your current password',
            'autocomplete': 'current-password',
        }),
        help_text='Confirm your identity by entering your current password'
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
        existing_user = User.objects.filter(username=new_username).exclude(pk=self.user.pk).first()
        if existing_user:
            # Check if the existing user is an admin (staff or superuser)
            if existing_user.is_staff or existing_user.is_superuser:
                raise forms.ValidationError("This username is reserved and cannot be used")
            raise forms.ValidationError("This username is already taken")

        # Check if username matches any admin username (case-insensitive)
        admin_users = User.objects.filter(is_staff=True).exclude(pk=self.user.pk) | User.objects.filter(is_superuser=True).exclude(pk=self.user.pk)
        for admin in admin_users.distinct():
            if admin.username.lower() == new_username.lower():
                raise forms.ValidationError("This username is reserved and cannot be used")

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

    def clean_password(self):
        """Verify the password"""
        password = self.cleaned_data.get('password')

        if not password:
            raise forms.ValidationError("Password is required")

        if self.user and not self.user.check_password(password):
            raise forms.ValidationError("Incorrect password. Please try again.")

        return password

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


class SetPasswordForm(forms.Form):
    """
    Form for wallet-only users to set their first password.
    """
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        }),
        help_text='Password must be at least 8 characters long'
    )
    new_password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        }),
        help_text='Enter the same password again for verification'
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_password2(self):
        """Ensure both passwords match"""
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')

        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")

        return password2

    def clean_new_password1(self):
        """Validate password strength"""
        password = self.cleaned_data.get('new_password1')

        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")

        return password

    def clean(self):
        """Check that user doesn't already have a password"""
        cleaned_data = super().clean()

        if self.user and self.user.has_usable_password():
            raise forms.ValidationError("You already have a password set. Use the change password form instead.")

        return cleaned_data


class ChangePasswordForm(forms.Form):
    """
    Form for users to change their existing password.
    """
    old_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Enter current password',
            'autocomplete': 'current-password',
        }),
        help_text='Confirm your identity with your current password'
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password',
        }),
        help_text='Password must be at least 8 characters long'
    )
    new_password2 = forms.CharField(
        label="Confirm new password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full p-2 border rounded bg-background-light dark:bg-gray-700 border-border-light dark:border-border-dark focus:ring-primary focus:border-primary text-sm',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password',
        }),
        help_text='Enter the same password again for verification'
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_old_password(self):
        """Verify the old password is correct"""
        old_password = self.cleaned_data.get('old_password')

        if not old_password:
            raise forms.ValidationError("Current password is required")

        if self.user and not self.user.check_password(old_password):
            raise forms.ValidationError("Your current password is incorrect")

        return old_password

    def clean_new_password2(self):
        """Ensure both new passwords match"""
        password1 = self.cleaned_data.get('new_password1')
        password2 = self.cleaned_data.get('new_password2')

        if password1 and password2:
            if password1 != password2:
                raise forms.ValidationError("The two password fields didn't match.")

        return password2

    def clean_new_password1(self):
        """Validate password strength"""
        password = self.cleaned_data.get('new_password1')

        if len(password) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")

        return password

    def clean(self):
        """Additional validation"""
        cleaned_data = super().clean()

        old_password = cleaned_data.get('old_password')
        new_password1 = cleaned_data.get('new_password1')

        # Check that new password is different from old password
        if old_password and new_password1 and old_password == new_password1:
            raise forms.ValidationError("New password must be different from your current password.")

        return cleaned_data

