# TraitKeeper NFT Memories Guide

## Table of Contents
1. [Overview](#overview)
2. [What Are NFT Memories?](#what-are-nft-memories)
3. [Architecture](#architecture)
4. [Collection Events](#collection-events)
5. [NFT Burns](#nft-burns)
6. [User Interactions](#user-interactions)
7. [Significance Levels](#significance-levels)
8. [Rarity Snapshots](#rarity-snapshots)
9. [Use Cases](#use-cases)
10. [API Reference](#api-reference)
11. [Best Practices](#best-practices)

---

## Overview

NFT Memories is TraitKeeper's **social layer for commemorating significant NFT events**. It transforms ephemeral blockchain transactions into lasting community memories by adding context, sentiment, and user engagement to key moments in NFT history.

### The Problem

Traditional blockchain explorers show raw transaction data - addresses, timestamps, amounts - but lack the **human story** behind these events:
- Why was this NFT burned?
- What made this sale significant to the community?
- How did collectors react to major events?

### The Solution

NFT Memories adds a **social and emotional layer** to blockchain events:
- **Commemorate**: Preserve the story behind burns, major sales, and collection milestones
- **React**: Allow community to express sentiment through likes, comments, and reactions
- **Remember**: Create permanent records that outlive the NFT itself (especially for burns)
- **Understand**: Track how rarity and significance evolved over time

---

## What Are NFT Memories?

NFT Memories consists of two core concepts:

### 1. Collection Events
Significant events in a collection's lifecycle that deserve community attention:
- **Major Sales**: High-value transactions that impact floor price
- **First Mints**: The beginning of a collection's journey
- **Burns**: When NFTs are permanently removed from circulation
- **Milestones**: 100th sale, 1000th mint, etc.

### 2. NFT Burns
Permanent historical records of burned NFTs, preserving their metadata, rarity, and story even after they're destroyed on-chain.

**Example Burn Memory:**
```
DeGod #4235 - Burned on March 15, 2024
Rarity: 2.1% (Epic traits)
Reason: "Burned for DeGods Season 3 upgrade"
Community Reactions: 142 🔥 fire, 89 💔 heartbreak, 23 🎉 party
Comments: 47
```

---

## Architecture

### Data Models

#### CollectionEvent
Stores gamification and social data for significant NFT events.

```python
class CollectionEvent(models.Model):
    SIGNIFICANCE_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('LEGENDARY', 'Legendary'),
    ]

    event = models.ForeignKey(NFTEvent, on_delete=models.CASCADE, related_name='memory_events')
    significance = models.CharField(max_length=20, choices=SIGNIFICANCE_LEVELS, default='LOW')
    user_interactions = models.JSONField(default=get_default_user_interactions)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Key Relationships:**
- Links to `NFTEvent` from indexer (core blockchain event)
- Adds social/gamification layer on top of raw event data
- Preserves community engagement over time

#### NFTBurn
Historical record of burned NFTs with full metadata preservation.

```python
class NFTBurn(models.Model):
    burn_event = models.ForeignKey(BurnEvent, on_delete=models.CASCADE, related_name='memory_burns')
    name = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    number = models.IntegerField(null=True, blank=True)
    rarity = models.JSONField(default=dict)  # Full rarity details
    reason = models.TextField(blank=True)
    reason_is_approved = models.BooleanField(default=False)
    added_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    user_interactions = models.JSONField(default=get_default_user_interactions)
    created_at = models.DateTimeField(auto_now_add=True)
```

**Key Features:**
- Preserves NFT metadata that would be lost after burn
- Community-contributed burn reasons with moderation
- Permanent historical record with social engagement

#### CollectionRaritySnapshot
Historical snapshots of collection rarity distribution over time.

```python
class CollectionRaritySnapshot(models.Model):
    collection = models.ForeignKey(NFTCollection, on_delete=models.CASCADE, related_name='rarity_snapshots')
    timestamp = models.DateTimeField(default=timezone.now)
    total_supply = models.IntegerField()
    rarity_base = models.JSONField(default=dict)  # Full rarity distribution
    created_at = models.DateTimeField(auto_now_add=True)
```

**Purpose:**
- Track how burns affect rarity over time
- Historical analysis of collection evolution
- Understand rarity inflation/deflation

---

## Collection Events

### Automatic Significance Determination

When an event is saved, significance is automatically calculated:

```python
def determine_significance(self):
    """Determine the significance of the event for gamification."""
    details = self.event.details if hasattr(self.event, 'details') else {}

    if self.event.event_type == 'BURN':
        self.significance = 'LEGENDARY'  # All burns are legendary

    elif self.event.event_type == 'SALE':
        price = details.get('price', 0)
        if price > 100:  # 100+ SOL
            self.significance = 'HIGH'
        elif price > 10:  # 10-100 SOL
            self.significance = 'MEDIUM'
        else:
            self.significance = 'LOW'

    elif self.event.event_type == 'MINT':
        number = details.get('number', None)
        if number == 1:  # First mint is always significant
            self.significance = 'HIGH'
        else:
            self.significance = 'MEDIUM'

    else:
        self.significance = 'LOW'
```

### User Interaction Structure

```python
def get_default_user_interactions():
    return {
        "likes": 0,
        "comments": [],
        "tributes": [],
        "reactions": {
            "fire": 0,       # 🔥 Fire reaction
            "heartbreak": 0, # 💔 Heartbreak reaction
            "party": 0       # 🎉 Party reaction
        }
    }
```

**Interaction Types:**
- **Likes**: Simple appreciation counter
- **Comments**: Array of comment objects with user, text, timestamp
- **Tributes**: Special recognition (e.g., memorial messages for burns)
- **Reactions**: Emoji reactions for quick sentiment

### Field Protection

CollectionEvent restricts updates after creation to preserve historical integrity:

```python
def save(self, *args, **kwargs):
    """Override save to restrict updates to specific fields."""
    if self.pk and self._meta.model.objects.filter(pk=self.pk).exists():
        original = self._meta.model.objects.get(pk=self.pk)
        allowed_fields = {'user_interactions', 'significance'}
        # Only user_interactions and significance can be updated
        for field in self._meta.fields:
            field_name = field.name
            if field_name not in allowed_fields and field_name not in {'created_at'}:
                setattr(self, field_name, getattr(original, field_name))
    super().save(*args, **kwargs)
```

**Protected Fields:** event reference, timestamp, core metadata
**Updatable Fields:** user_interactions, significance

---

## NFT Burns

### Why Preserve Burn Data?

When an NFT is burned on-chain:
- Metadata URLs may go offline
- Rarity data is lost
- Historical context disappears
- Community loses connection to the memory

NFTBurn solves this by **capturing a complete snapshot** before the burn.

### Burn Record Structure

```python
nft_burn = NFTBurn.objects.create(
    burn_event=burn_event,
    name="DeGod #4235",
    description="A legendary DeGod with rare traits",
    image_url="https://metadata.degods.com/4235.png",
    number=4235,
    rarity={
        "Background": {"value": "Purple", "rarity": 5.2},
        "Skin": {"value": "Zombie", "rarity": 2.1},
        "Clothes": {"value": "Suit", "rarity": 8.4}
    },
    reason="Burned for DeGods Season 3 upgrade program",
    reason_is_approved=True,
    added_by_user=user,
    user_interactions={
        "likes": 142,
        "comments": [...],
        "tributes": [...],
        "reactions": {"fire": 89, "heartbreak": 45, "party": 8}
    }
)
```

### Community-Contributed Burn Reasons

Users can submit reasons for why an NFT was burned:

**Workflow:**
1. User submits reason: "Burned for Season 3 upgrade"
2. `reason_is_approved=False` by default
3. Moderator reviews and approves
4. `reason_is_approved=True`, reason becomes visible

**Moderation Purpose:**
- Prevent spam or offensive content
- Ensure accuracy of historical record
- Maintain community standards

### Burn Memory UI

**Burn Gallery View:**
```html
<div class="burn-memory-card">
    <img src="{{ burn.image_url }}" alt="{{ burn.name }}">
    <h3>{{ burn.name }} 🔥</h3>
    <p class="burn-date">Burned {{ burn.created_at|date:"M d, Y" }}</p>

    <div class="rarity-info">
        <span class="rarity-score">Rarity: 2.1%</span>
        <span class="rarity-tier">Epic</span>
    </div>

    {% if burn.reason_is_approved %}
        <p class="burn-reason">{{ burn.reason }}</p>
        <p class="added-by">Submitted by {{ burn.added_by_user.username }}</p>
    {% endif %}

    <div class="interactions">
        <button class="reaction" data-type="fire">🔥 {{ burn.user_interactions.reactions.fire }}</button>
        <button class="reaction" data-type="heartbreak">💔 {{ burn.user_interactions.reactions.heartbreak }}</button>
        <button class="reaction" data-type="party">🎉 {{ burn.user_interactions.reactions.party }}</button>
    </div>

    <div class="comments-section">
        <h4>Community Tributes ({{ burn.user_interactions.comments|length }})</h4>
        <!-- Comments display -->
    </div>
</div>
```

---

## User Interactions

### Interaction Types

#### 1. Likes
Simple appreciation counter - quick way to acknowledge an event.

**Implementation:**
```python
def add_like(collection_event):
    collection_event.user_interactions['likes'] += 1
    collection_event.save()
```

#### 2. Reactions
Emoji-based sentiment indicators for nuanced expression.

**Available Reactions:**
- 🔥 **Fire**: Hype, excitement, impressive
- 💔 **Heartbreak**: Sad to see it go, emotional
- 🎉 **Party**: Celebration, milestone

**Implementation:**
```python
def add_reaction(collection_event, reaction_type):
    if reaction_type in collection_event.user_interactions['reactions']:
        collection_event.user_interactions['reactions'][reaction_type] += 1
        collection_event.save()
```

#### 3. Comments
Full text comments for detailed thoughts and memories.

**Comment Structure:**
```json
{
    "user_id": 123,
    "username": "collector_pro",
    "text": "This was the first DeGod I ever bought. RIP to a legend.",
    "timestamp": "2024-03-15T14:30:00Z",
    "likes": 12
}
```

**Implementation:**
```python
def add_comment(collection_event, user, text):
    comment = {
        "user_id": user.id,
        "username": user.username,
        "text": text,
        "timestamp": timezone.now().isoformat(),
        "likes": 0
    }
    collection_event.user_interactions['comments'].append(comment)
    collection_event.save()
```

#### 4. Tributes
Special recognition for burns - like comments but more ceremonial.

**Tribute Structure:**
```json
{
    "user_id": 123,
    "username": "collector_pro",
    "tribute": "You served me well, DeGod #4235. Your memory lives on.",
    "timestamp": "2024-03-15T14:30:00Z",
    "is_featured": false
}
```

**Featured Tributes:**
Most upvoted or moderator-selected tributes can be featured on burn page.

---

## Significance Levels

### Level Definitions

| Level | Color | Description | Examples |
|-------|-------|-------------|----------|
| **LOW** | Gray | Standard transactions | Small sales, routine transfers |
| **MEDIUM** | Blue | Notable activity | 10+ SOL sales, regular mints |
| **HIGH** | Purple | Major events | 100+ SOL sales, first mint, rare traits |
| **LEGENDARY** | Gold | Historic moments | All burns, collection milestones, record sales |

### Visual Styling

```css
/* Low Significance - Gray */
.significance-low {
    background: linear-gradient(135deg, #9e9e9e, #bdbdbd);
    border-left: 4px solid #757575;
}

/* Medium Significance - Blue */
.significance-medium {
    background: linear-gradient(135deg, #2196f3, #64b5f6);
    border-left: 4px solid #1976d2;
}

/* High Significance - Purple */
.significance-high {
    background: linear-gradient(135deg, #9c27b0, #ba68c8);
    border-left: 4px solid #7b1fa2;
}

/* Legendary Significance - Gold with glow */
.significance-legendary {
    background: linear-gradient(135deg, #ff9800, #ffb74d);
    border-left: 4px solid #f57c00;
    box-shadow: 0 0 20px rgba(255, 152, 0, 0.5);
    animation: legendary-pulse 2s infinite;
}

@keyframes legendary-pulse {
    0%, 100% { box-shadow: 0 0 20px rgba(255, 152, 0, 0.5); }
    50% { box-shadow: 0 0 30px rgba(255, 152, 0, 0.8); }
}
```

### Significance in Feed

Events are sorted and filtered by significance:

**Collection Event Feed:**
```python
# Show only significant events (HIGH or LEGENDARY)
significant_events = CollectionEvent.objects.filter(
    event__collection=collection,
    significance__in=['HIGH', 'LEGENDARY']
).order_by('-created_at')

# All events with significance filtering
all_events = CollectionEvent.objects.filter(
    event__collection=collection
).order_by('-significance', '-created_at')
```

---

## Rarity Snapshots

### Purpose

Track how collection rarity evolves over time, especially as burns reduce supply.

### Snapshot Creation

```python
from nftmemories.models import CollectionRaritySnapshot
from nft_data.models import NFTCollection, NFT

def create_rarity_snapshot(collection):
    """Create a rarity snapshot for a collection at current moment."""

    # Get current supply
    total_supply = NFT.objects.filter(collection=collection, is_burned=False).count()

    # Calculate rarity distribution
    rarity_base = {}
    traits = NFT.objects.filter(collection=collection, is_burned=False).values('traits')

    # Process trait rarity (simplified)
    for nft in traits:
        for trait_type, trait_value in nft['traits'].items():
            if trait_type not in rarity_base:
                rarity_base[trait_type] = {}
            if trait_value not in rarity_base[trait_type]:
                rarity_base[trait_type][trait_value] = 0
            rarity_base[trait_type][trait_value] += 1

    # Convert counts to percentages
    for trait_type in rarity_base:
        for trait_value in rarity_base[trait_type]:
            count = rarity_base[trait_type][trait_value]
            rarity_base[trait_type][trait_value] = (count / total_supply) * 100

    # Create snapshot
    snapshot = CollectionRaritySnapshot.objects.create(
        collection=collection,
        timestamp=timezone.now(),
        total_supply=total_supply,
        rarity_base=rarity_base
    )

    return snapshot
```

### Snapshot Usage

**Rarity Evolution Chart:**
```python
# Get snapshots over time
snapshots = CollectionRaritySnapshot.objects.filter(
    collection=collection
).order_by('timestamp')

# Track supply changes
for snapshot in snapshots:
    print(f"{snapshot.timestamp}: {snapshot.total_supply} NFTs")

# Analyze rarity changes
trait_type = "Background"
trait_value = "Purple"
for snapshot in snapshots:
    rarity = snapshot.rarity_base.get(trait_type, {}).get(trait_value, 0)
    print(f"{snapshot.timestamp}: Purple Background = {rarity:.2f}%")
```

**Use Cases:**
- Show how burns increased rarity of remaining NFTs
- Visualize collection deflation over time
- Historical rarity analysis for burned NFTs

---

## Use Cases

### 1. Burn Memorial Gallery

**Feature:** Dedicated page showing all burns for a collection with community tributes.

**User Story:**
> "As a collector, I want to see all the NFTs that were burned from my favorite collection, read why they were burned, and pay my respects."

**Implementation:**
```python
# View all burns for a collection
burns = NFTBurn.objects.filter(
    burn_event__collection=collection
).order_by('-created_at')

# Featured burns (most interactions)
featured_burns = burns.annotate(
    total_reactions=F('user_interactions__reactions__fire') +
                    F('user_interactions__reactions__heartbreak') +
                    F('user_interactions__reactions__party')
).order_by('-total_reactions')[:10]
```

### 2. Collection Timeline

**Feature:** Visual timeline of significant events in a collection's history.

**User Story:**
> "As a potential buyer, I want to see the major events in a collection's history to understand its legacy and community strength."

**Implementation:**
```python
timeline_events = CollectionEvent.objects.filter(
    event__collection=collection,
    significance__in=['HIGH', 'LEGENDARY']
).select_related('event').order_by('-event__timestamp')
```

### 3. Rarity Evolution Tracker

**Feature:** Chart showing how rarity changed as burns reduced supply.

**User Story:**
> "As an analyst, I want to see how burns affected trait rarity over time to understand collection dynamics."

**Implementation:**
```python
# Get snapshots
snapshots = CollectionRaritySnapshot.objects.filter(
    collection=collection
).order_by('timestamp')

# Generate chart data
chart_data = {
    'dates': [s.timestamp for s in snapshots],
    'supply': [s.total_supply for s in snapshots],
    'trait_rarity': {
        'Purple Background': [
            s.rarity_base.get('Background', {}).get('Purple', 0)
            for s in snapshots
        ]
    }
}
```

### 4. Community Burn Events

**Feature:** Organized burn events where community burns NFTs together for upgrades.

**User Story:**
> "As a project creator, I want to run a burn event where holders burn old NFTs to receive upgraded versions, and preserve the memory of the original collection."

**Implementation:**
```python
# Mark burn event
burn_event = BurnEvent.objects.create(
    mint_address=nft.mint_address,
    collection=nft.collection,
    timestamp=timezone.now(),
    event_details={
        'event_name': 'Season 3 Upgrade',
        'event_type': 'COMMUNITY_BURN'
    }
)

# Create memory with reason
nft_burn = NFTBurn.objects.create(
    burn_event=burn_event,
    name=nft.name,
    image_url=nft.image_url,
    rarity=nft.rarity_data,
    reason="Burned as part of Season 3 Upgrade Event",
    reason_is_approved=True
)
```

### 5. Sentiment Analysis

**Feature:** Analyze community sentiment around events via reactions.

**User Story:**
> "As a researcher, I want to analyze how the community reacted to major collection events."

**Implementation:**
```python
# Get events with high engagement
events = CollectionEvent.objects.filter(
    event__collection=collection,
    significance='LEGENDARY'
)

for event in events:
    total_reactions = sum(event.user_interactions['reactions'].values())
    fire_pct = (event.user_interactions['reactions']['fire'] / total_reactions) * 100
    heartbreak_pct = (event.user_interactions['reactions']['heartbreak'] / total_reactions) * 100

    print(f"Event: {event.event.event_type}")
    print(f"  🔥 Fire: {fire_pct:.1f}%")
    print(f"  💔 Heartbreak: {heartbreak_pct:.1f}%")
    print(f"  Overall sentiment: {'positive' if fire_pct > heartbreak_pct else 'bittersweet'}")
```

---

## API Reference

### Create Collection Event Memory

```python
from nftmemories.models import CollectionEvent
from indexer.models import NFTEvent

# Create memory for an event
nft_event = NFTEvent.objects.get(event_id='abc123')
collection_event = CollectionEvent.objects.create(
    event=nft_event
    # significance auto-determined on save
)
```

### Add User Interaction

```python
# Add like
collection_event.user_interactions['likes'] += 1
collection_event.save()

# Add reaction
collection_event.user_interactions['reactions']['fire'] += 1
collection_event.save()

# Add comment
comment = {
    "user_id": user.id,
    "username": user.username,
    "text": "Amazing event!",
    "timestamp": timezone.now().isoformat(),
    "likes": 0
}
collection_event.user_interactions['comments'].append(comment)
collection_event.save()
```

### Create Burn Memory

```python
from nftmemories.models import NFTBurn
from indexer.models import BurnEvent

burn_event = BurnEvent.objects.get(burn_id='xyz789')
nft_burn = NFTBurn.objects.create(
    burn_event=burn_event,
    name=nft.name,
    description=nft.description,
    image_url=nft.image_url,
    number=nft.number,
    rarity=nft.rarity_data,
    reason="User-submitted reason here",
    reason_is_approved=False,
    added_by_user=user
)
```

### Query Burns

```python
# All burns for a collection
burns = NFTBurn.objects.filter(
    burn_event__collection=collection
).order_by('-created_at')

# Burns with approved reasons
approved_burns = NFTBurn.objects.filter(
    burn_event__collection=collection,
    reason_is_approved=True
)

# Most engaged burns
from django.db.models import JSONField
# Custom annotation needed for JSONField queries
```

### Create Rarity Snapshot

```python
from nftmemories.models import CollectionRaritySnapshot

snapshot = CollectionRaritySnapshot.objects.create(
    collection=collection,
    timestamp=timezone.now(),
    total_supply=current_supply,
    rarity_base=rarity_distribution_dict
)
```

---

## Best Practices

### For Platform Administrators

1. **Automatic Snapshot Creation**
   - Create snapshots after major burn events
   - Weekly snapshots for active collections
   - Snapshots before/after community events

2. **Moderation of Burn Reasons**
   - Review user-submitted reasons within 24 hours
   - Reject offensive or inaccurate content
   - Provide feedback to users on rejections

3. **Feature Significant Events**
   - Homepage feed of legendary events
   - Email notifications for collection followers
   - Weekly digest of top memories

4. **Preserve Data Integrity**
   - Regularly backup NFTBurn records (critical historical data)
   - Monitor for IPFS/metadata URL changes
   - Re-fetch metadata before it goes offline

### For Developers

1. **Efficient Interaction Updates**
   ```python
   # Good: Update in single save
   event.user_interactions['likes'] += 1
   event.user_interactions['reactions']['fire'] += 1
   event.save()

   # Bad: Multiple saves
   event.user_interactions['likes'] += 1
   event.save()
   event.user_interactions['reactions']['fire'] += 1
   event.save()
   ```

2. **Handle Concurrent Updates**
   ```python
   from django.db import transaction

   @transaction.atomic
   def add_like(event_id, user_id):
       event = CollectionEvent.objects.select_for_update().get(id=event_id)
       event.user_interactions['likes'] += 1
       event.save()
   ```

3. **Preserve Burn Metadata**
   ```python
   # Capture metadata BEFORE burn is processed
   def process_burn(mint_address):
       nft = NFT.objects.get(mint_address=mint_address)

       # Save metadata first
       burn_memory = NFTBurn.objects.create(
           burn_event=burn_event,
           name=nft.name,
           image_url=nft.image_url,
           rarity=nft.rarity_data
       )

       # Then process burn
       nft.is_burned = True
       nft.save()
   ```

4. **Optimize Query Performance**
   ```python
   # Good: Select related data
   events = CollectionEvent.objects.filter(
       event__collection=collection
   ).select_related('event', 'event__collection')

   # Bad: N+1 queries
   events = CollectionEvent.objects.filter(event__collection=collection)
   for event in events:
       print(event.event.collection.name)  # Separate query each time
   ```

---

## Conclusion

NFT Memories transforms TraitKeeper from a marketplace into a **living archive of NFT history**. By preserving context, sentiment, and community reactions, it ensures that significant moments are never forgotten - even when the NFTs themselves are burned.

The system respects privacy (interactions are optional), prevents abuse (moderation system), and preserves historical integrity (field protection), while enabling rich social features that bring collectors together around shared memories.

**Remember the moments. Preserve the memories. 🔥💔🎉**
