# Profile System - Next Phase Enhancements

## 📋 Requirements Summary

Based on your feedback, here are the enhancements to implement:

1. ✅ **Marketplace Integration** - Fetch listings/bids in profile
   - Direct sells
   - Auctions
   - Sell intents
   - Your bids placed
   - Bids received on your NFTs

2. ✅ **Watchlist System** - Track favorite NFTs/collections

3. ✅ **Achievement System** - Badge system with admin management

4. ✅ **NFT Pagination & Grouping** - Organized by collections, art/list view

5. ✅ **Profile Sharing** - Shareable profiles without sensitive data

6. ✅ **Notification System** - NFT-related notifications for users

7. ⚠️ **Collection Approval** - Remove from notification types (not needed)

---

## 1. Marketplace Integration

### Models Needed

#### A. Listing Models (Direct Sell & Sell Intent)
```python
# marketplace/models.py

class ListingType(models.TextChoices):
    DIRECT_SELL = 'DIRECT_SELL', 'Direct Sell'
    SELL_INTENT = 'SELL_INTENT', 'Sell Intent'

class NFTListing(models.Model):
    """
    Tracks NFTs listed for sale (direct or intent to sell)
    """
    listing_id = models.CharField(max_length=88, primary_key=True)
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name='listings')
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='listings')

    seller = models.CharField(max_length=44, db_index=True)
    listing_type = models.CharField(max_length=20, choices=ListingType.choices)

    # Pricing
    price = models.DecimalField(max_digits=20, decimal_places=9, help_text="Listing price in SOL")

    # Status
    is_active = models.BooleanField(default=True, db_index=True)

    # Timestamps
    listed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-listed_at']
        indexes = [
            models.Index(fields=['seller', 'is_active']),
            models.Index(fields=['nft', 'is_active']),
            models.Index(fields=['collection', 'is_active']),
        ]

    def __str__(self):
        return f"{self.get_listing_type_display()} - {self.nft.name}"
```

#### B. Bid Model
```python
class BidStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    ACCEPTED = 'ACCEPTED', 'Accepted'
    REJECTED = 'REJECTED', 'Rejected'
    EXPIRED = 'EXPIRED', 'Expired'
    CANCELLED = 'CANCELLED', 'Cancelled'

class Bid(models.Model):
    """
    Tracks bids placed on NFTs (both auction bids and offers)
    """
    bid_id = models.CharField(max_length=88, primary_key=True)
    nft = models.ForeignKey(NFT, on_delete=models.CASCADE, related_name='bids')
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='bids')

    # Bidder info
    bidder = models.CharField(max_length=44, db_index=True)

    # Related to auction (if it's an auction bid)
    auction = models.ForeignKey(
        'AuctionEvent',
        on_delete=models.CASCADE,
        related_name='bids',
        null=True,
        blank=True
    )

    # Bid details
    amount = models.DecimalField(max_digits=20, decimal_places=9, help_text="Bid amount in SOL")
    status = models.CharField(max_length=20, choices=BidStatus.choices, default=BidStatus.ACTIVE, db_index=True)

    # Timestamps
    placed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-placed_at']
        indexes = [
            models.Index(fields=['bidder', 'status']),
            models.Index(fields=['nft', 'status']),
            models.Index(fields=['auction', 'status']),
        ]

    def __str__(self):
        return f"Bid of {self.amount} SOL on {self.nft.name}"

    @property
    def is_auction_bid(self):
        return self.auction is not None
```

### Views Update for Profile

```python
# profiles/views.py

def profile_view(request, username):
    # ... existing code ...

    # Get user's wallets
    user_wallets = profile_user.wallets.all() if hasattr(profile_user, 'wallets') else []
    wallet_addresses = list(user_wallets.values_list('public_key', flat=True))

    # Fetch NFTs from all wallets
    user_nfts = []
    if wallet_addresses:
        user_nfts = NFT.objects.filter(
            owner__in=wallet_addresses
        ).select_related('collection').prefetch_related('auctions', 'listings', 'bids')

    # Marketplace Data - Active Listings (seller)
    active_listings = NFTListing.objects.filter(
        seller__in=wallet_addresses,
        is_active=True
    ).select_related('nft', 'collection').order_by('-listed_at')

    # Marketplace Data - Active Auctions (seller)
    active_auctions = AuctionEvent.objects.filter(
        creator__in=wallet_addresses,
        status=AuctionEvent.Status.ACTIVE
    ).select_related('nft', 'collection').order_by('-end_time')

    # Combine listings and auctions
    active_sells = {
        'direct_sells': active_listings.filter(listing_type=ListingType.DIRECT_SELL),
        'sell_intents': active_listings.filter(listing_type=ListingType.SELL_INTENT),
        'auctions': active_auctions,
    }

    # Marketplace Data - Your Bids (placed by you)
    your_active_bids = Bid.objects.filter(
        bidder__in=wallet_addresses,
        status=BidStatus.ACTIVE
    ).select_related('nft', 'collection', 'auction').order_by('-placed_at')

    # Marketplace Data - Bids Received (on your NFTs)
    nft_ids = [nft.mint_address for nft in user_nfts]
    bids_received = Bid.objects.filter(
        nft__mint_address__in=nft_ids,
        status=BidStatus.ACTIVE
    ).exclude(
        bidder__in=wallet_addresses  # Exclude your own bids
    ).select_related('nft', 'collection', 'auction').order_by('-placed_at')

    # Group NFTs by collection for better organization
    from collections import defaultdict
    nfts_by_collection = defaultdict(list)
    for nft in user_nfts:
        nfts_by_collection[nft.collection].append(nft)

    # Pagination for NFTs
    from django.core.paginator import Paginator
    paginator = Paginator(user_nfts, 24)  # 24 NFTs per page
    page_number = request.GET.get('page')
    nfts_page = paginator.get_page(page_number)

    context = {
        'profile_user': profile_user,
        'is_owner': is_owner,
        'user_wallets': user_wallets,
        'primary_wallet': primary_wallet,
        'user_nfts': user_nfts,
        'nfts_by_collection': dict(nfts_by_collection),
        'nfts_page': nfts_page,
        'active_sells': active_sells,
        'your_active_bids': your_active_bids,
        'bids_received': bids_received,
        'watchlist_items': watchlist_items,
        'activity_history': activity_history,
        'pnl_data': pnl_data,
    }
    return render(request, 'profiles/user_profile.html', context)
```

---

## 2. Watchlist System

### Model
```python
# profiles/models.py

class WatchlistItem(models.Model):
    """
    Allows users to track NFTs or collections they're interested in
    """
    class ItemType(models.TextChoices):
        NFT = 'NFT', 'NFT'
        COLLECTION = 'COLLECTION', 'Collection'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='watchlist'
    )
    item_type = models.CharField(max_length=20, choices=ItemType.choices)

    # Either nft OR collection will be set, not both
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

    # Optional notes
    notes = models.TextField(blank=True, help_text="Personal notes about why you're watching this")

    # Timestamps
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [
            ('user', 'nft'),
            ('user', 'collection'),
        ]
        ordering = ['-added_at']
        indexes = [
            models.Index(fields=['user', 'item_type']),
        ]

    def __str__(self):
        if self.item_type == self.ItemType.NFT:
            return f"{self.user.username} watching {self.nft.name}"
        return f"{self.user.username} watching {self.collection.name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        # Ensure exactly one of nft or collection is set
        if self.item_type == self.ItemType.NFT and not self.nft:
            raise ValidationError("NFT must be set for NFT watchlist items")
        if self.item_type == self.ItemType.COLLECTION and not self.collection:
            raise ValidationError("Collection must be set for collection watchlist items")
        if self.nft and self.collection:
            raise ValidationError("Cannot watch both NFT and collection simultaneously")
```

### Views
```python
# profiles/views.py

@login_required
def add_to_watchlist(request):
    """API endpoint to add item to watchlist"""
    if request.method == 'POST':
        item_type = request.POST.get('item_type')
        item_id = request.POST.get('item_id')
        notes = request.POST.get('notes', '')

        try:
            if item_type == 'NFT':
                nft = NFT.objects.get(mint_address=item_id)
                WatchlistItem.objects.get_or_create(
                    user=request.user,
                    item_type=WatchlistItem.ItemType.NFT,
                    nft=nft,
                    defaults={'notes': notes}
                )
                messages.success(request, f'Added {nft.name} to your watchlist')
            elif item_type == 'COLLECTION':
                collection = NFTCollection.objects.get(address=item_id)
                WatchlistItem.objects.get_or_create(
                    user=request.user,
                    item_type=WatchlistItem.ItemType.COLLECTION,
                    collection=collection,
                    defaults={'notes': notes}
                )
                messages.success(request, f'Added {collection.name} to your watchlist')

            return redirect(request.META.get('HTTP_REFERER', 'profiles:profile'))
        except Exception as e:
            messages.error(request, f'Error adding to watchlist: {e}')
            return redirect(request.META.get('HTTP_REFERER', 'profiles:profile'))

    return redirect('profiles:profile', username=request.user.username)

@login_required
def remove_from_watchlist(request, item_id):
    """Remove item from watchlist"""
    if request.method == 'POST':
        try:
            watchlist_item = WatchlistItem.objects.get(id=item_id, user=request.user)
            watchlist_item.delete()
            messages.success(request, 'Removed from watchlist')
        except WatchlistItem.DoesNotExist:
            messages.error(request, 'Watchlist item not found')

    return redirect(request.META.get('HTTP_REFERER', 'profiles:profile'))
```

### URLs
```python
# profiles/urls.py
urlpatterns += [
    path('watchlist/add/', views.add_to_watchlist, name='add_to_watchlist'),
    path('watchlist/remove/<int:item_id>/', views.remove_from_watchlist, name='remove_from_watchlist'),
]
```

---

## 3. Achievement System with Admin Management

### Models
```python
# profiles/models.py

class AchievementCategory(models.Model):
    """Categories for organizing achievements"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    order = models.IntegerField(default=0, help_text="Display order")

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Achievement Category'
        verbose_name_plural = 'Achievement Categories'

    def __str__(self):
        return self.name

class Achievement(models.Model):
    """
    Defines available achievements/badges users can earn.
    Admin can easily create and manage these.
    """
    # Unique identifier
    key = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique key for this achievement (e.g., 'FIRST_BID', 'TRADER_100')"
    )

    # Display information
    name = models.CharField(max_length=100)
    description = models.TextField()
    category = models.ForeignKey(
        AchievementCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='achievements'
    )

    # Visual
    icon_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="URL to achievement badge image"
    )
    icon_class = models.CharField(
        max_length=100,
        blank=True,
        help_text="Font Awesome icon class (e.g., 'fas fa-trophy')"
    )
    color = models.CharField(
        max_length=7,
        default='#800080',
        help_text="Hex color for the badge"
    )

    # Rarity/Value
    rarity = models.CharField(
        max_length=20,
        choices=[
            ('COMMON', 'Common'),
            ('UNCOMMON', 'Uncommon'),
            ('RARE', 'Rare'),
            ('EPIC', 'Epic'),
            ('LEGENDARY', 'Legendary'),
        ],
        default='COMMON'
    )
    points = models.IntegerField(
        default=10,
        help_text="Points awarded for earning this achievement"
    )

    # Requirements (for reference/documentation)
    requirements = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON describing how to earn this achievement"
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this achievement can currently be earned"
    )
    is_hidden = models.BooleanField(
        default=False,
        help_text="Whether to hide this achievement until earned"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category__order', 'rarity', 'name']
        verbose_name = 'Achievement'
        verbose_name_plural = 'Achievements'

    def __str__(self):
        return f"{self.name} ({self.rarity})"

    @property
    def earned_count(self):
        """How many users have earned this achievement"""
        return self.user_achievements.count()

class UserAchievement(models.Model):
    """
    Tracks which achievements a user has earned
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='achievements'
    )
    achievement = models.ForeignKey(
        Achievement,
        on_delete=models.CASCADE,
        related_name='user_achievements'
    )
    earned_at = models.DateTimeField(auto_now_add=True)

    # Optional context about how it was earned
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional data about when/how this was earned"
    )

    class Meta:
        unique_together = ('user', 'achievement')
        ordering = ['-earned_at']
        verbose_name = 'User Achievement'
        verbose_name_plural = 'User Achievements'

    def __str__(self):
        return f"{self.user.username} earned {self.achievement.name}"
```

### Admin Interface
```python
# profiles/admin.py

from django.contrib import admin
from .models import (
    Profile, Achievement, AchievementCategory,
    UserAchievement, WatchlistItem
)

@admin.register(AchievementCategory)
class AchievementCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'order', 'achievement_count']
    list_editable = ['order']
    search_fields = ['name']

    def achievement_count(self, obj):
        return obj.achievements.count()
    achievement_count.short_description = 'Achievements'

@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'key', 'category', 'rarity', 'points',
        'is_active', 'is_hidden', 'earned_count'
    ]
    list_filter = ['rarity', 'category', 'is_active', 'is_hidden']
    search_fields = ['name', 'key', 'description']
    list_editable = ['is_active', 'is_hidden']

    fieldsets = (
        ('Basic Information', {
            'fields': ('key', 'name', 'description', 'category')
        }),
        ('Visual', {
            'fields': ('icon_url', 'icon_class', 'color')
        }),
        ('Value & Rarity', {
            'fields': ('rarity', 'points')
        }),
        ('Requirements', {
            'fields': ('requirements',),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'is_hidden')
        }),
    )

    readonly_fields = ['created_at', 'updated_at']

@admin.register(UserAchievement)
class UserAchievementAdmin(admin.ModelAdmin):
    list_display = ['user', 'achievement', 'earned_at']
    list_filter = ['achievement__category', 'achievement__rarity', 'earned_at']
    search_fields = ['user__username', 'achievement__name']
    date_hierarchy = 'earned_at'
    raw_id_fields = ['user', 'achievement']

    def has_add_permission(self, request):
        # Admins can manually award achievements
        return True

@admin.register(WatchlistItem)
class WatchlistItemAdmin(admin.ModelAdmin):
    list_display = ['user', 'item_type', 'get_item_name', 'added_at']
    list_filter = ['item_type', 'added_at']
    search_fields = ['user__username', 'nft__name', 'collection__name']
    raw_id_fields = ['user', 'nft', 'collection']

    def get_item_name(self, obj):
        if obj.item_type == 'NFT':
            return obj.nft.name if obj.nft else 'N/A'
        return obj.collection.name if obj.collection else 'N/A'
    get_item_name.short_description = 'Item'
```

### Achievement Awarding Logic
```python
# profiles/utils.py

def award_achievement(user, achievement_key, context=None):
    """
    Award an achievement to a user

    Args:
        user: User instance
        achievement_key: str - Achievement.key
        context: dict - Optional context data

    Returns:
        tuple: (UserAchievement, created: bool)
    """
    try:
        achievement = Achievement.objects.get(key=achievement_key, is_active=True)
        user_achievement, created = UserAchievement.objects.get_or_create(
            user=user,
            achievement=achievement,
            defaults={'context': context or {}}
        )

        if created:
            # Create notification for user
            from notifications.models import Notification
            Notification.objects.create(
                user=user,
                event_type='achievement_earned',
                message=f'You earned the "{achievement.name}" achievement!',
                data={
                    'achievement_key': achievement_key,
                    'achievement_name': achievement.name,
                    'points': achievement.points,
                }
            )

        return user_achievement, created
    except Achievement.DoesNotExist:
        logger.warning(f"Tried to award non-existent achievement: {achievement_key}")
        return None, False

# Example usage in signals or views:
# from profiles.utils import award_achievement

# When user places first bid:
# award_achievement(user, 'FIRST_BID', {'bid_amount': bid.amount})

# When user makes 100th trade:
# award_achievement(user, 'TRADER_100', {'trade_count': 100})
```

---

## 4. NFT Pagination & Collection Grouping

### Template Implementation
```django
{# templates/profile/user_profile.html #}

{/* Portfolio Tab with Collection Grouping */}
<div id="tab-portfolio" class="tab-content active">

  {/* View Controls */}
  <div id="portfolio-controls" class="flex justify-between items-center mb-4">
    <div class="flex gap-2">
      <button id="group-by-collection-btn" class="text-xs px-3 py-1.5 bg-primary text-white rounded-full">
        Group by Collection
      </button>
      <button id="show-all-btn" class="text-xs px-3 py-1.5 bg-accent-light dark:bg-accent-dark rounded-full">
        Show All
      </button>
    </div>
    <div class="flex gap-2">
      <button id="art-view-btn" class="view-toggle-btn active">Art View</button>
      <button id="list-view-btn" class="view-toggle-btn">List View</button>
    </div>
  </div>

  {/* Grouped by Collection View */}
  <div id="grouped-view">
    {% for collection, nfts in nfts_by_collection.items %}
    <div class="collection-group mb-8">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold flex items-center gap-2">
          <img src="{{ collection.image_url }}" alt="{{ collection.name }}" class="w-8 h-8 rounded">
          {{ collection.name }}
          <span class="text-sm text-gray-500">({{ nfts|length }})</span>
        </h3>
        <a href="{% url 'collection_detail' collection.address %}" class="text-xs text-primary hover:underline">
          View Collection →
        </a>
      </div>

      <div class="portfolio-grid">
        {% for nft in nfts %}
        <div class="portfolio-grid-item">
          <img src="{{ nft.image_url }}" alt="{{ nft.name }}">
          <div class="nft-info">
            <p class="font-semibold">{{ nft.name }}</p>
            {% if nft.vitality_score %}
            <p class="text-xs">Vitality: {{ nft.vitality_score }}</p>
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
    </div>
    {% endfor %}
  </div>

  {/* Pagination */}
  {% if nfts_page.has_other_pages %}
  <nav class="mt-6 flex justify-center">
    <ul class="flex gap-2">
      {% if nfts_page.has_previous %}
      <li><a href="?page={{ nfts_page.previous_page_number }}" class="px-3 py-1 bg-primary text-white rounded">Previous</a></li>
      {% endif %}

      <li class="px-3 py-1">Page {{ nfts_page.number }} of {{ nfts_page.paginator.num_pages }}</li>

      {% if nfts_page.has_next %}
      <li><a href="?page={{ nfts_page.next_page_number }}" class="px-3 py-1 bg-primary text-white rounded">Next</a></li>
      {% endif %}
    </ul>
  </nav>
  {% endif %}
</div>
```

---

## 5. Profile Sharing (Privacy Controls)

### Implementation
```python
# profiles/views.py

def profile_view(request, username):
    # ... existing code ...

    # Determine what to show based on privacy
    is_owner = request.user.is_authenticated and request.user.username == username
    profile = profile_user.profile

    # Privacy checks
    if not is_owner and not profile.is_public:
        # Show limited profile for private accounts
        return render(request, 'profiles/private_profile.html', {
            'profile_user': profile_user,
            'is_private': True,
        })

    # What to hide from non-owners even on public profiles
    sensitive_data = {
        'wallet_addresses': user_wallets if is_owner else [],
        'full_pnl': pnl_data if is_owner else {},
        'bids_received': bids_received if is_owner else [],
        'notification_settings': None if not is_owner else notification_prefs,
    }

    # What to show publicly
    public_data = {
        'nfts': user_nfts[:50] if not is_owner else user_nfts,  # Limit for non-owners
        'active_listings': active_sells if profile.is_public else {},
        'watchlist': watchlist_items if profile.is_public else [],
        'achievements': profile_user.achievements.all(),
    }

    context = {
        'profile_user': profile_user,
        'is_owner': is_owner,
        **sensitive_data,
        **public_data,
    }

    return render(request, 'profiles/user_profile.html', context)
```

### Shareable Profile URL
```python
# Generate share links
def get_profile_share_url(user):
    """Generate shareable profile URL"""
    from django.urls import reverse
    from django.contrib.sites.models import Site

    site = Site.objects.get_current()
    path = reverse('profiles:profile', args=[user.username])
    return f"https://{site.domain}{path}"

# Add to profile template
# Share buttons with pre-filled text
```

---

## 6. Enhanced Notification System

### Update Notification Types
```python
# notifications/models.py

class Notification(models.Model):
    EVENT_TYPES = (
        # Existing
        ('transaction', 'Transaction'),
        ('sweep', 'Collection Sweep'),
        ('trait_performance', 'Trait Performance Change'),
        ('high_profile_transfer', 'High Profile Transfer'),
        ('wallet_activity', 'Wallet Activity'),
        # REMOVED: ('collection_approval', 'Collection Approval'),

        # NEW: NFT-specific events
        ('nft_listed', 'Your NFT was listed'),
        ('nft_sold', 'Your NFT was sold'),
        ('bid_received', 'New bid on your NFT'),
        ('bid_accepted', 'Your bid was accepted'),
        ('bid_outbid', 'You were outbid'),
        ('auction_won', 'You won an auction'),
        ('auction_ending', 'Auction ending soon'),
        ('watchlist_activity', 'Activity on watched item'),
        ('achievement_earned', 'Achievement earned'),
    )

    # ... rest of model
```

### Notification Creation Helpers
```python
# notifications/utils.py

def notify_bid_received(nft_owner, bid):
    """Notify NFT owner when they receive a bid"""
    if should_notify(nft_owner, 'bid_received'):
        Notification.objects.create(
            user=nft_owner,
            event_type='bid_received',
            message=f'New bid of {bid.amount} SOL on your {bid.nft.name}',
            data={
                'nft_mint': bid.nft.mint_address,
                'bid_id': bid.bid_id,
                'amount': str(bid.amount),
                'bidder': bid.bidder,
            }
        )

def notify_outbid(previous_bidder, new_bid):
    """Notify user when they're outbid"""
    if should_notify(previous_bidder, 'bid_outbid'):
        Notification.objects.create(
            user=previous_bidder,
            event_type='bid_outbid',
            message=f'You were outbid on {new_bid.nft.name}',
            data={
                'nft_mint': new_bid.nft.mint_address,
                'new_bid_amount': str(new_bid.amount),
            }
        )

def notify_watchlist_activity(watchers, nft, activity_type):
    """Notify users watching an NFT about activity"""
    for watcher in watchers:
        if should_notify(watcher, 'watchlist_activity'):
            Notification.objects.create(
                user=watcher,
                event_type='watchlist_activity',
                message=f'Activity on watched item: {nft.name}',
                data={
                    'nft_mint': nft.mint_address,
                    'activity_type': activity_type,
                }
            )

def should_notify(user, notification_type):
    """Check if user wants this notification"""
    try:
        pref = NotificationPreference.objects.get(
            user=user,
            notification_type=notification_type
        )
        return pref.enabled
    except NotificationPreference.DoesNotExist:
        return True  # Default to enabled
```

---

## 7. Implementation Priority

### Phase 1 (Critical)
1. ✅ Add NFTListing and Bid models to marketplace
2. ✅ Update profile_view to fetch marketplace data
3. ✅ Add pagination to NFT display
4. ✅ Remove collection_approval from notifications

### Phase 2 (High Priority)
1. ✅ Implement Watchlist model and views
2. ✅ Add Achievement models with admin interface
3. ✅ Create collection grouping in templates
4. ✅ Enhanced notification types

### Phase 3 (Nice to Have)
1. ✅ Achievement auto-awarding logic
2. ✅ Share profile functionality
3. ✅ Advanced privacy controls
4. ✅ Notification preferences UI improvements

---

## 8. Migration Plan

```bash
# 1. Create models
python manage.py makemigrations marketplace
python manage.py makemigrations profiles
python manage.py makemigrations notifications

# 2. Apply migrations
python manage.py migrate

# 3. Create default achievement categories
python manage.py shell
```

```python
# In Django shell
from profiles.models import AchievementCategory

categories = [
    {'name': 'Trading', 'icon': 'fas fa-exchange-alt', 'order': 1},
    {'name': 'Collecting', 'icon': 'fas fa-th', 'order': 2},
    {'name': 'Community', 'icon': 'fas fa-users', 'order': 3},
    {'name': 'Special', 'icon': 'fas fa-star', 'order': 4},
]

for cat in categories:
    AchievementCategory.objects.get_or_create(**cat)
```

---

## 9. Testing Checklist

- [ ] Marketplace data shows in profile
- [ ] Listings (direct sell, sell intent, auctions) display correctly
- [ ] Your bids section works
- [ ] Bids received section works
- [ ] Watchlist add/remove functions
- [ ] NFT pagination works
- [ ] Collection grouping displays correctly
- [ ] Admin can create achievements
- [ ] Achievements display on profile
- [ ] Notifications create correctly
- [ ] Privacy controls work
- [ ] Profile sharing URL works
- [ ] collection_approval removed from notification types

---

**This comprehensive plan addresses all your requirements!** 🎉

Ready to implement when you are!
