# TraitKeeper Achievements System Guide

## Table of Contents
1. [Overview](#overview)
2. [Achievement Architecture](#achievement-architecture)
3. [Rarity System](#rarity-system)
4. [Points & Progression](#points--progression)
5. [Achievement Categories](#achievement-categories)
6. [How Achievements Are Earned](#how-achievements-are-earned)
7. [Achievement Examples](#achievement-examples)
8. [User Achievement Tracking](#user-achievement-tracking)
9. [Hidden Achievements](#hidden-achievements)
10. [Integration with Notifications](#integration-with-notifications)
11. [API Reference](#api-reference)
12. [Best Practices](#best-practices)

---

## Overview

TraitKeeper's Achievement System is a comprehensive gamification layer that rewards users for meaningful participation in the NFT ecosystem. Unlike simple badge systems, TraitKeeper achievements are:

- **Multi-Dimensional**: Rewards trading, collecting, social engagement, and platform exploration
- **Rarity-Based**: Five tiers from Common to Legendary with escalating difficulty
- **Points-Driven**: Each achievement awards points that contribute to user status
- **Dynamic**: Automatically awarded based on user actions and milestones
- **Hidden Discoveries**: Secret achievements that surprise and delight users
- **Notification-Integrated**: Real-time alerts when achievements are unlocked

### Philosophy

The achievement system is designed to:
- **Guide Discovery**: Help new users learn platform features through achievement goals
- **Reward Expertise**: Recognize power users and dedicated collectors
- **Build Community**: Encourage social interaction and engagement
- **Create Status**: Points and rare badges signal reputation and experience
- **Maintain Privacy**: No forced social features - achievements are personal milestones

---

## Achievement Architecture

### Data Models

#### AchievementCategory
Organizes achievements into logical groups for better discovery and display.

```python
class AchievementCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)  # e.g., "Trading Master"
    slug = models.SlugField(max_length=50, unique=True)  # e.g., "trading-master"
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50)  # Icon class or emoji
    display_order = models.PositiveIntegerField(default=0)
```

**Built-in Categories:**
- **Trading**: Marketplace buying, selling, bidding achievements
- **Collecting**: NFT collection and portfolio achievements
- **Social**: Profile completion, watchlist, engagement achievements
- **Explorer**: Platform feature discovery achievements
- **Special**: Limited-time, event-based, or unique achievements

#### Achievement
The core achievement definition - what can be earned and its properties.

```python
class Achievement(models.Model):
    class Rarity(models.TextChoices):
        COMMON = 'COMMON', 'Common'
        UNCOMMON = 'UNCOMMON', 'Uncommon'
        RARE = 'RARE', 'Rare'
        EPIC = 'EPIC', 'Epic'
        LEGENDARY = 'LEGENDARY', 'Legendary'

    key = models.CharField(max_length=50, unique=True)  # e.g., "FIRST_BID"
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    category = models.ForeignKey(AchievementCategory, ...)
    rarity = models.CharField(max_length=20, choices=Rarity.choices)
    points = models.PositiveIntegerField(default=10)

    icon_url = models.URLField(max_length=500, blank=True)
    icon_image = models.ImageField(upload_to='achievement_icons/', ...)

    is_active = models.BooleanField(default=True)
    is_hidden = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    criteria = models.JSONField(default=dict)  # Optional automatic criteria
```

**Key Fields Explained:**
- `key`: Unique identifier used in code (e.g., `FIRST_BID`, `WHALE`)
- `rarity`: Determines visual styling and points awarded
- `points`: Base points for earning this achievement
- `is_hidden`: Hidden achievements don't show until earned (surprises!)
- `criteria`: JSON field for automatic award logic (future ML enhancement)

#### UserAchievement
Links users to achievements they've earned - the earned badge record.

```python
class UserAchievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements_earned')
    achievement = models.ForeignKey(Achievement, on_delete=models.CASCADE, related_name='earned_by')
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'achievement')  # Can only earn once
```

**Constraints:**
- Each achievement can only be earned once per user
- Timestamp preserved for achievement history
- Deletion of user cascades to their achievements

---

## Rarity System

Achievements are classified into five rarity tiers that determine visual styling, points awarded, and prestige level.

### Rarity Tiers

| Rarity | Color | Point Range | Difficulty | Example Achievements |
|--------|-------|-------------|------------|----------------------|
| **Common** | Gray/White | 10-20 | Easy | First NFT, First Listing, Profile Complete |
| **Uncommon** | Green | 25-50 | Moderate | 10 Listings, 10 NFTs, First Watch |
| **Rare** | Blue | 75-150 | Challenging | 100 NFTs, Savvy Buyer, Vigilant Watcher |
| **Epic** | Purple | 200-500 | Difficult | Master Collector, Diverse Portfolio |
| **Legendary** | Gold/Orange | 1000+ | Extreme | Whale, Collection Connoisseur, Top Trader |

### Visual Design

Each rarity tier has distinct visual styling:

```css
/* Common - Gray/White */
.achievement-common {
    background: linear-gradient(135deg, #e0e0e0, #f5f5f5);
    border: 2px solid #bdbdbd;
}

/* Uncommon - Green */
.achievement-uncommon {
    background: linear-gradient(135deg, #4caf50, #8bc34a);
    border: 2px solid #2e7d32;
}

/* Rare - Blue */
.achievement-rare {
    background: linear-gradient(135deg, #2196f3, #64b5f6);
    border: 2px solid #1565c0;
}

/* Epic - Purple */
.achievement-epic {
    background: linear-gradient(135deg, #9c27b0, #ba68c8);
    border: 2px solid #6a1b9a;
}

/* Legendary - Gold with animated glow */
.achievement-legendary {
    background: linear-gradient(135deg, #ff9800, #ffc107);
    border: 2px solid #e65100;
    box-shadow: 0 0 20px rgba(255, 152, 0, 0.6);
    animation: pulse-glow 2s infinite;
}

@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 20px rgba(255, 152, 0, 0.6); }
    50% { box-shadow: 0 0 40px rgba(255, 152, 0, 0.9); }
}
```

---

## Points & Progression

### Point Calculation

Points are awarded based on achievement rarity and difficulty:

```python
# Common: 10-20 points
Achievement.objects.create(key='FIRST_NFT', rarity='COMMON', points=10)

# Uncommon: 25-50 points
Achievement.objects.create(key='GROWING_COLLECTION', rarity='UNCOMMON', points=25)

# Rare: 75-150 points
Achievement.objects.create(key='SERIOUS_COLLECTOR', rarity='RARE', points=100)

# Epic: 200-500 points
Achievement.objects.create(key='DIVERSE_PORTFOLIO', rarity='EPIC', points=250)

# Legendary: 1000+ points
Achievement.objects.create(key='WHALE', rarity='LEGENDARY', points=1000)
```

### User Stats Calculation

The system provides comprehensive achievement statistics:

```python
from profiles.utils import get_user_achievement_stats

stats = get_user_achievement_stats(user)
# Returns:
# {
#     'total_earned': 15,
#     'total_available': 50,
#     'completion_percentage': 30.0,
#     'total_points': 485,
#     'rarity_breakdown': {
#         'common': 5,
#         'uncommon': 7,
#         'rare': 2,
#         'epic': 1,
#         'legendary': 0
#     }
# }
```

### Leaderboards (Future Enhancement)

Points enable global and category-specific leaderboards:
- Overall points leaderboard
- Category-specific rankings (Trading, Collecting, etc.)
- Monthly/weekly point challenges
- Milestone rewards at point thresholds

---

## Achievement Categories

### 1. Trading Achievements

Rewards marketplace activity - buying, selling, and bidding.

| Key | Name | Rarity | Points | Criteria |
|-----|------|--------|--------|----------|
| `FIRST_LISTING` | First Sale | Common | 10 | List 1 NFT |
| `ACTIVE_SELLER` | Active Seller | Uncommon | 30 | List 10 NFTs |
| `MARKETPLACE_VETERAN` | Marketplace Veteran | Rare | 150 | List 100 NFTs |
| `FIRST_BID` | First Bid | Common | 10 | Place 1 bid |
| `ACTIVE_BIDDER` | Active Bidder | Uncommon | 30 | Place 10 bids |
| `SAVVY_BUYER` | Savvy Buyer | Rare | 100 | Win 5 bids |
| `MASTER_COLLECTOR` | Master Collector | Epic | 300 | Win 50 bids |

**Automatic Award Trigger:**
```python
from profiles.utils import check_and_award_trading_achievements

# Called after marketplace transactions
awarded = check_and_award_trading_achievements(user)
# Returns list of newly awarded achievement keys
```

### 2. Collection Achievements

Rewards NFT collecting and portfolio building.

| Key | Name | Rarity | Points | Criteria |
|-----|------|--------|--------|----------|
| `FIRST_NFT` | First NFT | Common | 10 | Own 1 NFT |
| `GROWING_COLLECTION` | Growing Collection | Uncommon | 25 | Own 10 NFTs |
| `SERIOUS_COLLECTOR` | Serious Collector | Rare | 100 | Own 100 NFTs |
| `WHALE` | Whale | Legendary | 1000 | Own 500+ NFTs |
| `DIVERSE_PORTFOLIO` | Diverse Portfolio | Uncommon | 40 | Own NFTs from 5 collections |
| `COLLECTION_CONNOISSEUR` | Collection Connoisseur | Legendary | 1500 | Own NFTs from 20 collections |

**Automatic Award Trigger:**
```python
from profiles.utils import check_and_award_collection_achievements

# Called after NFT ownership changes
awarded = check_and_award_collection_achievements(user)
```

### 3. Social Achievements

Rewards profile completion and platform engagement.

| Key | Name | Rarity | Points | Criteria |
|-----|------|--------|--------|----------|
| `PROFILE_COMPLETE` | Profile Complete | Common | 15 | Complete profile (name, bio, avatar, socials) |
| `FIRST_WATCH` | First Watch | Common | 10 | Add 1 NFT to watchlist |
| `VIGILANT_WATCHER` | Vigilant Watcher | Rare | 75 | Add 10 NFTs to watchlist |

**Automatic Award Trigger:**
```python
from profiles.utils import check_and_award_social_achievements

# Called after profile updates or watchlist changes
awarded = check_and_award_social_achievements(user)
```

### 4. Explorer Achievements (Future)

Rewards discovering platform features:
- First use of privacy bidding
- First silent auction participation
- First NFT Memory created
- First vitality check viewed
- Complete onboarding tutorial

### 5. Special Achievements (Future)

Limited-time or event-based achievements:
- Launch week participant
- Seasonal event achievements
- Community milestones
- Referral achievements

---

## How Achievements Are Earned

### Automatic Award System

Most achievements are awarded automatically when criteria are met:

```python
from profiles.utils import award_achievement

# Award a specific achievement to a user
user_achievement, created = award_achievement(
    user=user,
    achievement_key='FIRST_BID',
    create_notification=True
)

if created:
    print(f"🎉 User earned {user_achievement.achievement.name}!")
```

### Trigger Points

Achievements are checked at these key moments:

1. **After Marketplace Transactions**
   ```python
   # In marketplace/views.py after bid placement
   from profiles.utils import check_and_award_trading_achievements
   check_and_award_trading_achievements(request.user)
   ```

2. **After NFT Ownership Changes**
   ```python
   # In indexer after processing sale events
   from profiles.utils import check_and_award_collection_achievements
   check_and_award_collection_achievements(user)
   ```

3. **After Profile Updates**
   ```python
   # In wallet/views.py after profile settings saved
   from profiles.utils import check_and_award_social_achievements
   check_and_award_social_achievements(request.user)
   ```

4. **After Watchlist Changes**
   ```python
   # In profiles/views.py after adding to watchlist
   from profiles.utils import check_and_award_social_achievements
   check_and_award_social_achievements(request.user)
   ```

### Manual Award (Admin Only)

Admins can manually award achievements for special cases:

```python
from profiles.utils import award_achievement

# Manually award special achievement
award_achievement(
    user=user,
    achievement_key='SPECIAL_EVENT_PARTICIPANT',
    create_notification=True
)
```

---

## Achievement Examples

### Example 1: First Bid Achievement

**Definition:**
```python
Achievement.objects.create(
    key='FIRST_BID',
    name='First Bid',
    description='Place your first bid on an NFT listing',
    category=trading_category,
    rarity='COMMON',
    points=10,
    icon_url='https://example.com/icons/first-bid.png',
    is_active=True,
    is_hidden=False
)
```

**Award Logic:**
```python
# In check_and_award_trading_achievements()
bids_count = Bid.objects.filter(bidder__in=user.wallets.values_list('public_key', flat=True)).count()
if bids_count == 1:
    award_achievement(user, 'FIRST_BID')
```

### Example 2: Whale Achievement (Legendary)

**Definition:**
```python
Achievement.objects.create(
    key='WHALE',
    name='Whale',
    description='Own 500 or more NFTs - you are a true collector',
    category=collection_category,
    rarity='LEGENDARY',
    points=1000,
    icon_url='https://example.com/icons/whale.png',
    is_active=True,
    is_hidden=True  # Hidden until earned!
)
```

**Award Logic:**
```python
# In check_and_award_collection_achievements()
wallet_addresses = user.wallets.values_list('public_key', flat=True)
nft_count = NFT.objects.filter(owner__in=wallet_addresses).count()
if nft_count >= 500:
    award_achievement(user, 'WHALE')
```

### Example 3: Profile Complete Achievement

**Definition:**
```python
Achievement.objects.create(
    key='PROFILE_COMPLETE',
    name='Profile Complete',
    description='Complete your profile with name, bio, avatar, and social links',
    category=social_category,
    rarity='COMMON',
    points=15,
    icon_url='https://example.com/icons/profile-complete.png',
    is_active=True,
    is_hidden=False
)
```

**Award Logic:**
```python
# In check_and_award_social_achievements()
profile = user.profile
completion_score = 0
if profile.display_name: completion_score += 1
if profile.bio: completion_score += 1
if profile.get_avatar_url != '/static/img/user-avatar-default.jpg': completion_score += 1
if profile.social_x or profile.social_discord or profile.website_url: completion_score += 1

if completion_score >= 3:
    award_achievement(user, 'PROFILE_COMPLETE')
```

---

## User Achievement Tracking

### Viewing User Achievements

```python
from profiles.models import UserAchievement

# Get all achievements earned by a user
user_achievements = UserAchievement.objects.filter(user=user).select_related('achievement')

for ua in user_achievements:
    print(f"{ua.achievement.name} ({ua.achievement.rarity}) - {ua.earned_at}")
```

### Achievement Progress

```python
from profiles.utils import get_next_achievements

# Get suggested next achievements user can work towards
next_achievements = get_next_achievements(user, limit=3)

for achievement in next_achievements:
    print(f"Next goal: {achievement.name} ({achievement.points} points)")
```

### Display in Profile

User profiles show:
- Total achievements earned / total available
- Completion percentage
- Total points accumulated
- Rarity breakdown (X common, Y uncommon, etc.)
- Featured achievements (highest rarity or most recent)

**Template Example:**
```html
{% load achievement_tags %}

<div class="achievement-stats">
    <h3>Achievements</h3>
    <p>{{ user.achievements_earned.count }} / {{ total_achievements }} ({{ completion_percentage }}%)</p>
    <p>Total Points: {{ total_points }}</p>

    <div class="achievement-grid">
        {% for user_achievement in user.achievements_earned.all %}
            <div class="achievement-badge rarity-{{ user_achievement.achievement.rarity|lower }}">
                <img src="{{ user_achievement.achievement.get_icon_url }}" alt="{{ user_achievement.achievement.name }}">
                <h4>{{ user_achievement.achievement.name }}</h4>
                <p>{{ user_achievement.achievement.points }} points</p>
            </div>
        {% endfor %}
    </div>
</div>
```

---

## Hidden Achievements

Hidden achievements (`is_hidden=True`) are **not shown to users until they earn them**, creating surprise and delight moments.

### Use Cases for Hidden Achievements

1. **Easter Eggs**: Reward discovering obscure features
2. **Milestones**: Surprise users when they hit major thresholds
3. **Special Events**: Limited-time achievements during events
4. **Legendary Unlocks**: Keep legendary achievements mysterious

### Example Hidden Achievements

```python
# Hidden until earned
Achievement.objects.create(
    key='WHALE',
    name='Whale',
    rarity='LEGENDARY',
    is_hidden=True  # Won't show in achievement list until earned
)

Achievement.objects.create(
    key='SECRET_FEATURE_DISCOVERER',
    name='Secret Feature Discoverer',
    description='Found the hidden feature!',
    rarity='RARE',
    is_hidden=True
)
```

### Revealing Hidden Achievements

When a hidden achievement is earned:
1. UserAchievement record is created
2. Notification sent: "You discovered a hidden achievement!"
3. Achievement now visible in user's profile
4. Special "NEW" badge displayed for 7 days

---

## Integration with Notifications

### Automatic Notifications

When an achievement is earned, the system automatically creates a notification:

```python
# In profiles/utils.py award_achievement()
if created and create_notification:
    from notifications.utils import create_achievement_notification
    create_achievement_notification(user, achievement)
```

### Notification Format

Achievement notifications include:
- **Title**: "Achievement Unlocked!"
- **Message**: Achievement name and description
- **Icon**: Achievement icon
- **Points**: Points awarded
- **Rarity**: Visual rarity indicator
- **Link**: Deep link to user's achievement page

**Example Notification:**
```json
{
    "type": "achievement",
    "title": "Achievement Unlocked! 🏆",
    "message": "First Bid - Place your first bid on an NFT listing",
    "data": {
        "achievement_key": "FIRST_BID",
        "achievement_name": "First Bid",
        "rarity": "COMMON",
        "points": 10,
        "icon_url": "https://example.com/icons/first-bid.png"
    },
    "link": "/profile/achievements"
}
```

---

## API Reference

### Award Achievement
Award a specific achievement to a user.

**Function:**
```python
award_achievement(user, achievement_key, create_notification=True)
```

**Parameters:**
- `user` (User): User instance to award achievement to
- `achievement_key` (str): Unique achievement key (e.g., 'FIRST_BID')
- `create_notification` (bool): Whether to create notification (default: True)

**Returns:**
```python
(UserAchievement or None, bool)  # (instance, created)
```

**Example:**
```python
from profiles.utils import award_achievement

user_achievement, created = award_achievement(user, 'WHALE', create_notification=True)
if created:
    print(f"Awarded {user_achievement.achievement.points} points!")
```

### Check Trading Achievements
Check and award all applicable trading achievements.

**Function:**
```python
check_and_award_trading_achievements(user)
```

**Returns:**
```python
List[str]  # List of newly awarded achievement keys
```

**Example:**
```python
awarded = check_and_award_trading_achievements(user)
if awarded:
    print(f"New achievements: {', '.join(awarded)}")
```

### Check Collection Achievements
Check and award all applicable collection achievements.

**Function:**
```python
check_and_award_collection_achievements(user)
```

**Returns:**
```python
List[str]  # List of newly awarded achievement keys
```

### Check Social Achievements
Check and award all applicable social/engagement achievements.

**Function:**
```python
check_and_award_social_achievements(user)
```

**Returns:**
```python
List[str]  # List of newly awarded achievement keys
```

### Get User Achievement Stats
Get comprehensive statistics about user's achievements.

**Function:**
```python
get_user_achievement_stats(user)
```

**Returns:**
```python
{
    'total_earned': int,
    'total_available': int,
    'completion_percentage': float,
    'total_points': int,
    'rarity_breakdown': {
        'common': int,
        'uncommon': int,
        'rare': int,
        'epic': int,
        'legendary': int
    }
}
```

### Get Next Achievements
Get suggested next achievements user can work towards.

**Function:**
```python
get_next_achievements(user, limit=3)
```

**Parameters:**
- `user` (User): User instance
- `limit` (int): Maximum achievements to return (default: 3)

**Returns:**
```python
QuerySet[Achievement]  # Ordered by rarity and display order
```

**Example:**
```python
from profiles.utils import get_next_achievements

next_goals = get_next_achievements(user, limit=5)
for achievement in next_goals:
    print(f"Next: {achievement.name} ({achievement.points}pts)")
```

---

## Best Practices

### For Platform Administrators

1. **Balance Difficulty**
   - Common: Should be achievable within first hour
   - Uncommon: First few days of use
   - Rare: Weeks of active participation
   - Epic: Months of dedicated use
   - Legendary: Reserved for top 1% of users

2. **Point Allocation**
   - Align points with effort required
   - Legendary achievements should be worth 10-100x common
   - Consider point inflation over time

3. **Icon Design**
   - Use consistent visual language across rarities
   - Clear, recognizable icons at small sizes
   - Animated effects for Epic+ rarities

4. **Hidden Achievement Strategy**
   - Use sparingly (10-20% of total achievements)
   - Reserve for true surprises, not frustrating secrets
   - Legendary achievements can be hidden for mystery

5. **Regular Updates**
   - Add new achievements with major feature releases
   - Seasonal/event achievements keep engagement high
   - Retire outdated achievements gracefully

### For Developers

1. **Trigger Achievement Checks Appropriately**
   ```python
   # Good: Check after meaningful action
   def place_bid(request):
       # ... bid logic ...
       check_and_award_trading_achievements(request.user)

   # Bad: Check on every page load
   def view_listing(request):
       check_and_award_trading_achievements(request.user)  # Too frequent!
   ```

2. **Use Transaction Wrappers**
   ```python
   from django.db import transaction

   @transaction.atomic
   def process_sale():
       # ... sale logic ...
       check_and_award_trading_achievements(buyer_user)
       check_and_award_collection_achievements(buyer_user)
   ```

3. **Prevent Duplicate Notifications**
   ```python
   # award_achievement() already prevents duplicates with unique_together
   # But be careful with manual notification creation
   user_achievement, created = award_achievement(user, 'FIRST_BID')
   if created:  # Only notify on first earn
       # Notification already sent by award_achievement()
       pass
   ```

4. **Optimize Queries**
   ```python
   # Good: Prefetch related data
   achievements = UserAchievement.objects.filter(user=user).select_related('achievement', 'achievement__category')

   # Bad: N+1 query problem
   achievements = UserAchievement.objects.filter(user=user)
   for ua in achievements:
       print(ua.achievement.name)  # Separate query for each!
   ```

5. **Test Achievement Logic**
   ```python
   from django.test import TestCase
   from profiles.utils import award_achievement

   class AchievementTestCase(TestCase):
       def test_first_bid_award(self):
           user = User.objects.create_user(username='test')
           user_achievement, created = award_achievement(user, 'FIRST_BID')
           self.assertTrue(created)
           self.assertEqual(user_achievement.achievement.key, 'FIRST_BID')

           # Test duplicate prevention
           user_achievement2, created2 = award_achievement(user, 'FIRST_BID')
           self.assertFalse(created2)
   ```

---

## Future Enhancements

### Planned Features

1. **ML-Based Achievement Suggestions**
   - Predict which achievements user is close to earning
   - Personalized achievement recommendations

2. **Achievement Chains**
   - Multi-step achievements (e.g., "Complete 3 collection achievements to unlock Collector Master")
   - Progressive difficulty tiers

3. **Seasonal Achievements**
   - Limited-time achievements during events
   - Seasonal point multipliers

4. **Achievement Showcase**
   - Featured achievement on profile
   - Achievement showcase widget for external sites

5. **Trading Achievement NFTs** (Future Consideration)
   - Mint major achievements as on-chain NFTs
   - Display legendary achievements in wallet
   - Transfer/trade achievement NFTs (controversial - TBD)

6. **Leaderboards**
   - Global points leaderboard
   - Category-specific rankings
   - Monthly/weekly challenges

7. **Achievement Rewards**
   - Platform fee discounts for point milestones
   - Priority marketplace features
   - Exclusive badges/cosmetics

---

## Conclusion

TraitKeeper's Achievement System transforms NFT trading and collecting into a rewarding, gamified experience. By recognizing meaningful participation across multiple dimensions, achievements guide user discovery, reward expertise, and build community status.

The five-tier rarity system with hidden surprises creates moments of delight, while the points system enables future progression features like leaderboards and rewards.

For questions or suggestions, contact the development team or open an issue in the TraitKeeper repository.

**Happy Achievement Hunting! 🏆**
