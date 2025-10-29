# profiles/models.py
from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

# Import your CustomUser model
from wallet.models import CustomUser

class Profile(models.Model):
    """
    Stores user profile information, extending the base CustomUser model.
    """
    # Link to the main user model. One profile per user.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, # Uses AUTH_USER_MODEL setting for flexibility
        on_delete=models.CASCADE,
        related_name='profile' # Access profile via user.profile
    )

    # Core Information
    display_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Public display name (optional, defaults to username)"
    )
    bio = models.TextField(
        max_length=160, # Standard bio length limit
        blank=True,
        help_text="A short description about the user (max 160 chars)"
    )

    # Avatar Options - Users can choose between uploaded image or NFT
    avatar_type = models.CharField(
        max_length=20,
        choices=[
            ('upload', 'Uploaded Image'),
            ('nft', 'NFT Profile Picture'),
            ('url', 'External URL'),
        ],
        default='upload',
        help_text="Type of avatar being used"
    )
    avatar_image = models.ImageField(
        upload_to='avatars/',
        null=True,
        blank=True,
        help_text="Uploaded avatar image"
    )
    avatar_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="External URL for avatar (if not uploading)"
    )
    avatar_nft_mint = models.CharField(
        max_length=44,
        blank=True,
        null=True,
        help_text="NFT mint address to use as profile picture"
    )

    # Social Links (Store only the relevant part, e.g., handle, ID)
    social_x = models.CharField(
        max_length=50, 
        blank=True, 
        help_text="X (Twitter) handle (without @)"
    )
    social_discord = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="Discord username (e.g., username#1234)"
    )
    website_url = models.URLField(
        max_length=255, 
        blank=True,
        help_text="Link to personal website or portfolio"
    )

    # Settings
    is_public = models.BooleanField(
        default=True,
        help_text="Allow others to view this profile?"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        # Use display_name if available, otherwise fallback to user's identifier
        name = self.display_name or getattr(self.user, self.user.USERNAME_FIELD, str(self.user.pk))
        return f"Profile for {name}"

    # Property to easily get the display name (handles fallback)
    @property
    def get_display_name(self):
        return self.display_name or getattr(self.user, self.user.USERNAME_FIELD, f"User {self.user.pk}")

    # Property to get avatar URL based on avatar_type
    @property
    def get_avatar_url(self):
        """Returns avatar URL with proper fallback logic based on avatar type"""
        if self.avatar_type == 'upload' and self.avatar_image:
            return self.avatar_image.url
        elif self.avatar_type == 'nft' and self.avatar_nft_mint:
            # Try to get NFT image from nft_data app
            try:
                from nft_data.models import NFT
                nft = NFT.objects.filter(mint_address=self.avatar_nft_mint).first()
                if nft and nft.image_url:
                    return nft.image_url
            except Exception:
                pass
        elif self.avatar_type == 'url' and self.avatar_url:
            return self.avatar_url

        # Fallback to user's old profile_picture field if exists
        if hasattr(self.user, 'profile_picture') and self.user.profile_picture:
            return self.user.profile_picture

        # Final fallback to default avatar
        return '/static/img/user-avatar-default.jpg'

# --- Signal to create/update Profile when User is created/saved ---

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create or update the user profile when a User object is saved.
    """
    if created:
        Profile.objects.create(user=instance)
    # Ensure the profile is saved even on user update, 
    # in case fields need syncing (though typically not needed here)
    instance.profile.save()


class WatchlistItem(models.Model):
    """
    Allows users to watch/track NFTs or entire Collections.
    """
    class ItemType(models.TextChoices):
        NFT = 'NFT', 'NFT'
        COLLECTION = 'COLLECTION', 'Collection'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='watchlist_items'
    )
    item_type = models.CharField(
        max_length=20,
        choices=ItemType.choices,
        help_text="Type of item being watched"
    )

    # Foreign keys - only one should be set based on item_type
    nft = models.ForeignKey(
        'nft_data.NFT',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='watchers'
    )
    collection = models.ForeignKey(
        'nft_data.NFTCollection',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='watchers'
    )

    # Optional user notes
    notes = models.TextField(
        max_length=500,
        blank=True,
        help_text="Personal notes about why watching this item"
    )

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevent duplicate watchlist entries
        unique_together = [
            ('user', 'nft'),
            ('user', 'collection'),
        ]
        ordering = ['-added_at']
        indexes = [
            models.Index(fields=['user', 'item_type']),
            models.Index(fields=['user', 'added_at']),
        ]

    def clean(self):
        """Ensure exactly one of nft or collection is set"""
        from django.core.exceptions import ValidationError

        if self.item_type == self.ItemType.NFT:
            if not self.nft:
                raise ValidationError("NFT must be specified when item_type is NFT")
            if self.collection:
                raise ValidationError("Collection must be null when item_type is NFT")
        elif self.item_type == self.ItemType.COLLECTION:
            if not self.collection:
                raise ValidationError("Collection must be specified when item_type is COLLECTION")
            if self.nft:
                raise ValidationError("NFT must be null when item_type is COLLECTION")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.item_type == self.ItemType.NFT:
            return f"{self.user.username} watching NFT: {self.nft.name}"
        return f"{self.user.username} watching Collection: {self.collection.name}"

    @property
    def get_item(self):
        """Returns the watched item (NFT or Collection)"""
        return self.nft if self.item_type == self.ItemType.NFT else self.collection


class AchievementCategory(models.Model):
    """
    Categories for organizing achievements (e.g., Trading, Collecting, Social).
    """
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Icon class or emoji for this category"
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order to display categories (lower numbers first)"
    )

    class Meta:
        verbose_name_plural = "Achievement Categories"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class Achievement(models.Model):
    """
    Defines available achievements/badges in the system.
    Enhanced with categories, rarities, and points.
    """
    class Rarity(models.TextChoices):
        COMMON = 'COMMON', 'Common'
        UNCOMMON = 'UNCOMMON', 'Uncommon'
        RARE = 'RARE', 'Rare'
        EPIC = 'EPIC', 'Epic'
        LEGENDARY = 'LEGENDARY', 'Legendary'

    key = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g., 'FIRST_BID', 'TOP_TRADER')"
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    category = models.ForeignKey(
        AchievementCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='achievements'
    )

    rarity = models.CharField(
        max_length=20,
        choices=Rarity.choices,
        default=Rarity.COMMON,
        help_text="Rarity level of this achievement"
    )

    points = models.PositiveIntegerField(
        default=10,
        help_text="Points awarded for earning this achievement"
    )

    icon_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL to the badge icon"
    )
    icon_image = models.ImageField(
        upload_to='achievement_icons/',
        null=True,
        blank=True,
        help_text="Uploaded icon image"
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this achievement can be earned"
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Hidden achievements are not shown until earned"
    )

    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order within category (lower numbers first)"
    )

    # Optional criteria JSON for complex requirements
    criteria = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional: Store criteria data for automatic awarding"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'display_order', 'name']
        indexes = [
            models.Index(fields=['is_active', 'is_hidden']),
            models.Index(fields=['category', 'display_order']),
        ]

    def __str__(self):
        return self.name

    @property
    def get_icon_url(self):
        """Returns icon URL with fallback to uploaded image"""
        if self.icon_url:
            return self.icon_url
        elif self.icon_image:
            return self.icon_image.url
        return f'/static/img/achievements/{self.rarity.lower()}.png'

class UserAchievement(models.Model):
    """
    Links a User to an Achievement they have earned.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='achievements_earned')
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name='earned_by')
    earned_at = models.DateTimeField(auto_now_add=True)
    # data = models.JSONField(default=dict, help_text="Optional: Store specific data about how it was earned")

    class Meta:
        unique_together = ('user', 'achievement') # User can earn each achievement only once
        ordering = ['-earned_at']

    def __str__(self):
        return f"{self.user} earned {self.achievement.name}"