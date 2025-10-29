# NFT_Data App

## Overview

The nft_data app is the **core data foundation** of TraitKeeper. It defines the fundamental models for NFT collections, individual NFTs, traits, and pending submissions. All other apps build upon these models.

## Purpose

- **Central NFT catalog** - Store all NFT collections and their NFTs
- **Trait system** - Manage trait types and values with rarity calculations
- **Collection submissions** - Handle user-submitted collections for admin approval
- **Data normalization** - Clean and standardize collection/NFT names

## Models

### NFTCollection

**Core collection model** - Represents an entire NFT collection.

**Key Fields:**

- `address` - Collection mint address (PK)
- `name` - Raw collection name from blockchain
- `display_name` - Cleaned, user-friendly name (auto-generated)
- `slug` - URL-friendly identifier (auto-generated)
- `image_url` - Collection image
- `description` - Collection description
- `creator_address` - Creator wallet
- `social_media_links` - JSON of links
- `is_featured` - Manual admin flag for homepage
- `is_listed` - Controls public visibility
- `source` - How added (webhook, submission, partnership)
- `priority_tier` - VIP, ACTIVE, or INACTIVE (for update scheduling)
- `update_frequency_minutes` - How often to refresh data
- `next_update_due` - When next update should occur
- `last_fetched` - Last successful data fetch timestamp

**Auto-Cleaning Logic:**

```python
# Removes common suffixes like "#1234", "(Official)", "Collection"
raw_name = "Mad Lads #5678 (Official) Collection"
display_name = "Mad Lads"  # Auto-generated
slug = "mad_lads"          # Auto-generated
```

**Priority Tiers:**

- **VIP**: High-volume collections, update every 15 min
- **ACTIVE**: Medium activity, update hourly
- **INACTIVE**: Low activity, update every 4 hours

**Relationships:**

- Has many `NFT` instances
- Has many `TraitType` instances
- Has one `AggregatedCollectionStats` (analytics)
- Has one `CollectionVitality` (marketplace)

### NFT

**Individual NFT model** - Represents a single NFT.

**Key Fields:**

- `mint_address` - NFT mint address (PK)
- `collection` - FK to NFTCollection
- `name` - NFT name
- `image_url` - NFT image
- `owner` - Current owner wallet address
- `traits` - JSON dict of trait_type: value pairs
- `trait_values` - M2M relationship to TraitValue
- `listing_price` - Current listing price (denormalized cache)
- `is_listed` - Currently listed for sale
- `is_burned` - NFT has been burned
- `created_at` / `updated_at` - Timestamps

**Example traits JSON:**

```json
{
  "Background": "Blue",
  "Hat": "Crown",
  "Eyes": "Laser",
  "Outfit": "Suit"
}
```

**Relationships:**

- Belongs to one `NFTCollection`
- Has many `TraitValue` instances (M2M)
- Has one `NFTVitality` (marketplace)
- Has many `NFTEvent` instances (indexer)

### TraitType

**Trait category** - E.g., "Hat", "Background", "Eyes".

**Key Fields:**

- `name` - Trait type name
- `collection` - FK to NFTCollection

**Unique Constraint:** `(name, collection)` - Each collection has its own trait types

**Relationships:**

- Belongs to one `NFTCollection`
- Has many `TraitValue` instances

### TraitValue

**Specific trait value** - E.g., "Crown", "Blue", "Laser".

**Key Fields:**

- `trait_type` - FK to TraitType
- `value` - Trait value name
- `count` - Number of NFTs with this trait
- `rarity` - Percentage of NFTs with this trait (0-100)

**Rarity Calculation:**

```python
rarity = (count / total_nfts_in_collection) * 100
```

**Unique Constraint:** `(trait_type, value)` - Each trait value is unique per type

**Relationships:**

- Belongs to one `TraitType`
- Has many `NFT` instances (M2M)
- Has many `TraitPerformanceScore` instances (analytics)

**Example:**

```
Collection: Mad Lads
TraitType: "Hat"
TraitValue: "Crown", count=50, rarity=5.0%  # 50/1000 NFTs
```

### PendingCollection

**Staging area for user submissions**.

**Key Fields:**

- `mint_address` - Collection mint address (unique)
- `name` - Collection name
- `creator` - Creator address
- `description` - Collection description
- `image_url` - Collection image
- `status` - pending, approved, rejected
- `submitted_by` - User who submitted
- `social_media_links` - JSON of links
- `validation_error` - Error message if validation failed

**Workflow:**

1. User submits collection via form
2. System validates mint address using Helius API
3. Stored in PendingCollection with status="pending"
4. Admin reviews in Django admin
5. If approved → creates NFTCollection
6. If rejected → status="rejected" with reason

**Indexes:**

- `(status, created_at)` - Fast pending submission queries

### Creator

**NFT creator tracking**.

**Key Fields:**

- `address` - Creator wallet address (unique)
- `name` - Creator name (optional)

**Purpose:** Track creators for discovery and filtering.

## Services

### NFT Retrieval

Located in separate service files (not in this app).

**Handled by:**

- `indexer` app - Fetches NFT metadata and events
- `marketplace` app - Calculates vitality

## Data Flow

```
User/Indexer
    ↓
NFTCollection created
    ↓
NFTs added with traits → TraitType/TraitValue created
    ↓
Rarity calculated for each TraitValue
    ↓
Other apps use this data:
    - indexer (events linking)
    - analytics (trait performance)
    - marketplace (vitality calculation)
```

## Admin Interface

### Collection Management

- View all collections
- Mark collections as featured
- Set priority tiers
- Approve/reject pending submissions

### NFT Management

- View NFTs by collection
- Check trait distribution
- Monitor burned NFTs

### Pending Submissions

- Review user submissions
- Validate collection addresses
- Approve/reject with notes

## Common Operations

### Add New Collection

```python
from nft_data.models import NFTCollection

collection = NFTCollection.objects.create(
    address="collection_mint_address",
    name="Raw Collection Name #1234",  # Will be auto-cleaned
    creator_address="creator_wallet",
    source="submission",
    priority_tier="ACTIVE"
)

# display_name and slug auto-generated on save
print(collection.display_name)  # "Raw Collection Name"
print(collection.slug)           # "raw_collection_name"
```

### Add NFT with Traits

```python
from nft_data.models import NFT, TraitType, TraitValue

# Create NFT
nft = NFT.objects.create(
    mint_address="nft_mint_address",
    collection=collection,
    name="NFT Name #5678",
    owner="owner_wallet",
    traits={"Hat": "Crown", "Background": "Blue"}
)

# Create/get trait types and values
for trait_type_name, trait_value_name in nft.traits.items():
    trait_type, _ = TraitType.objects.get_or_create(
        name=trait_type_name,
        collection=collection
    )

    trait_value, created = TraitValue.objects.get_or_create(
        trait_type=trait_type,
        value=trait_value_name
    )

    # Update count and rarity
    trait_value.count = nft.collection.nfts.filter(
        traits__contains={trait_type_name: trait_value_name}
    ).count()
    trait_value.rarity = (trait_value.count / collection.nfts.count()) * 100
    trait_value.save()

    # Link to NFT
    nft.trait_values.add(trait_value)
```

### Query Traits

```python
# Get all traits for a collection
traits = TraitType.objects.filter(collection=collection)

# Get rarest trait values
rare_traits = TraitValue.objects.filter(
    trait_type__collection=collection
).order_by('rarity')[:10]

# Find NFTs with specific trait
crown_nfts = NFT.objects.filter(
    collection=collection,
    trait_values__value="Crown"
)
```

## Integration with Other Apps

### → Indexer

- Uses NFTCollection for event linking
- Creates/updates NFT instances
- Populates trait data

### → Analytics

- Reads collections for stats calculation
- Uses traits for performance scoring
- Queries NFTs for wallet analysis

### → Marketplace

- Uses NFT for vitality calculation
- Reads traits for trait_performance component
- Links auctions to NFTs

## TODO List

- [ ] Add bulk import for collections
- [ ] Implement collection verification badges
- [ ] Add trait combination tracking
- [ ] Create collection family grouping
- [ ] Add creator verification system

## Related Documentation

- [../indexer/README.md](../indexer/README.md) - How data is populated
- [../analytics/README.md](../analytics/README.md) - How data is analyzed
- [../marketplace/README.md](../marketplace/README.md) - How vitality uses this data
