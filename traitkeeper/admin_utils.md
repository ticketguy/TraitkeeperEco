# README: `admin_utils.py` in `traitkeeper`

This README provides a detailed yet simple explanation of the `admin_utils.py` file in the `traitkeeper` module of the TraitKeeper Django project. The file defines the `AdvancedFilterAdmin` class, which customizes the Django admin interface by adding advanced filtering and counting capabilities for models such as `NFTCollection`, `NFT`, `TraitType`, `TraitValue`, and `TrendingTrait`. Below, we outline its purpose, features, structure, usage, and maintenance tips.

## Purpose

The `admin_utils.py` file enhances the Django admin interface by providing dynamic, field-based filtering and filter option counts for model list views. It enables admin users to filter data (e.g., NFTs, collections, traits) using various criteria, such as numeric ranges, text searches, boolean toggles, and related fields, while displaying the number of records matching each filter option. This functionality simplifies data analysis and management in the admin panel for large NFT datasets.

### Example Use Cases
- Filter `NFTCollection` by the number of NFTs or name (e.g., collections with ≥100 NFTs).
- Filter `TraitValue` by rarity or trending status (e.g., traits with rarity ≥5% that are trending).
- Filter `NFT` by event counts, such as listings or sales, using `NFTEvent` data.

## Key Features

1. **Dynamic Filtering**:
   - Automatically generates filters based on model fields (numeric, text, boolean, date, related fields).
   - Supports custom filters tailored to specific models (e.g., NFT count for collections, event count for NFTs).
2. **Filter Option Counts**:
   - Displays counts for each filter option (e.g., `True`/`False` for boolean fields, counts per related object).
   - Helps admins understand data distribution before applying filters.
3. **Customized Admin Views**:
   - Enhances the admin changelist view with filter fields, counts, and pagination.
   - Preserves standard Django admin actions (e.g., bulk delete, custom actions).
4. **Model-Specific Logic**:
   - Provides tailored filters and counts for `NFTCollection`, `NFT`, `TraitType`, `TraitValue`, and `TrendingTrait`.

## File Structure

The `admin_utils.py` file contains a single class, `AdvancedFilterAdmin`, which inherits from `django.contrib.admin.ModelAdmin`. It includes the following methods:

- **`get_queryset(request)`**:
  - Modifies the queryset to apply filters based on query parameters (e.g., `?name__icontains=ape`).
  - Handles numeric ranges, text searches, boolean toggles, date ranges, and related field filters.
- **`get_filter_counts(request)`**:
  - Calculates counts for filter options (e.g., number of trending `TraitValue` objects).
  - Supports boolean fields, choice fields, and related fields (e.g., `NFTCollection` for `TraitType`).
- **`changelist_view(request, extra_context)`**:
  - Customizes the admin list view to include filter fields, counts, and pagination.
  - Renders the `admin/change_list.html` template with additional context.
- **`get_changelist_template()`**:
  - Specifies the template (`admin/change_list.html`) for the changelist view.

## How It Works

### 1. Dynamic Filtering (`get_queryset`)

- **Field-Based Filters**:
  - Iterates through the model’s fields (e.g., `CharField`, `IntegerField`, `ForeignKey`).
  - Applies filters based on query parameters:
    - **Numeric**: `field__gte`, `field__lte` (e.g., `rarity__gte=10` for `TraitValue`).
    - **Text**: `field__icontains` (e.g., `name__icontains=ape` for `NFT`).
    - **Boolean**: `field=true` or `field=false` (e.g., `is_listed=true` for `NFTCollection`).
    - **Date**: `field__gte`, `field__lte` (e.g., `created_at__gte=2025-01-01` for `NFT`).
    - **Related**: `field__pk__in` (e.g., `collection__address__in=abc123` for `NFT`).
  - Uses `mint_address` for `NFT` and `address` for `NFTCollection` as primary keys in related field lookups.

- **Custom Filters**:
  - **NFTCollection**: Filter by NFT count (`nfts_count__gte`) or name.
  - **NFT**: Filter by name or event count (`events_count__gte`) via `NFTEvent` (e.g., listings, sales).
  - **TraitValue**: Filter by rarity, trending status (`trendingtrait__isnull`), collection (`trait_type__collection__address__in`), or NFT names.
  - **TraitType**: Filter by NFT associations (`values__nfts__mint_address__in`), name, or trait value count.
  - **TrendingTrait**: Filter by trend score (`trend_score__gte`, `trend_score__lte`) or collection.

### 2. Filter Option Counts (`get_filter_counts`)

- **Boolean Fields**:
  - Counts records for `True`/`False` values (e.g., `is_listed` for `NFTCollection`).
- **Choice Fields**:
  - Counts records for each choice (e.g., `event_type` in `NFTEvent`).
- **Related Fields**:
  - Counts records per related object (e.g., `TraitValue` objects per `NFTCollection`).
  - Uses `mint_address` for `NFT` and `address` for `NFTCollection`.
- **Custom Counts**:
  - **NFTCollection**: Counts associated NFTs.
  - **NFT**: Counts collections, trait values, and listing events (`NFTEvent` with `event_type='LISTING'`).
  - **TraitValue**: Counts collections, NFTs, and trending status (`trendingtrait__isnull`).
  - **TraitType**: Counts NFTs via trait values.
  - **TrendingTrait**: Counts collections via `trait_type`.

### 3. Admin View Customization (`changelist_view`)

- **Field Information**:
  - Generates a list of model fields (name, verbose name, type, choices) for the template.
  - Includes related objects for `ForeignKey` and `ManyToManyField` (e.g., `NFTCollection` list for `TraitType`).
- **Selected Filters**:
  - Tracks selected related field primary keys from query parameters (e.g., selected `NFTCollection` addresses).
- **Pagination**:
  - Computes a pagination range (e.g., pages 1–5 around the current page) for navigation.
- **Template Context**:
  - Adds `model_fields`, `pagination_range`, `filter_counts`, and `selected_related_pks` to the template context.
  - Renders `admin/change_list.html` with these enhancements.

### 4. Template Selection (`get_changelist_template`)

- Specifies `admin/change_list.html` as the default template, which can be customized for styling or additional UI elements.

## Supported Models

The `AdvancedFilterAdmin` class supports the following models from `nft_data/models.py` and `indexer/models.py`:

- **NFTCollection**:
  - Fields: `address` (PK), `name`, `is_listed`, `is_featured`, `symbol`, etc.
  - Filters: NFT count, name, `is_listed`, `is_featured`.
- **NFT**:
  - Fields: `mint_address` (PK), `name`, `collection`, `trait_values`, `highest_bid`.
  - Filters: Name, event count (via `NFTEvent`), collection, trait values.
- **TraitType**:
  - Fields: `name`, `collection`.
  - Filters: Name, NFT associations, trait value count.
- **TraitValue**:
  - Fields: `value`, `trait_type`, `rarity`, `count`, `trendingtrait`.
  - Filters: Rarity, count, trending status, collection, NFTs.
- **TrendingTrait**:
  - Fields: `trait_type`, `trait_value`, `trend_score`, `count`.
  - Filters: Trend score, collection.

**Note**: The file previously referenced a non-existent `NFTListing` model, which has been removed. Listing-related filters now use `NFTEvent` with `event_type='LISTING'`.

## Usage

### 1. Register Models in `admin.py`
In your `admin.py`, register models with `AdvancedFilterAdmin` to enable enhanced filtering:

```python
from django.contrib import admin
from traitkeeper.admin_utils import AdvancedFilterAdmin
from nft_data.models import NFTCollection, NFT, TraitType, TraitValue, TrendingTrait

@admin.register(NFTCollection)
class NFTCollectionAdmin(AdvancedFilterAdmin):
    list_display = ['name', 'address', 'is_listed', 'is_featured']
    search_fields = ['name', 'address']

@admin.register(NFT)
class NFTAdmin(AdvancedFilterAdmin):
    list_display = ['name', 'mint_address', 'collection']
    search_fields = ['name', 'mint_address']

@admin.register(TraitType)
class TraitTypeAdmin(AdvancedFilterAdmin):
    list_display = ['name', 'collection']

@admin.register(TraitValue)
class TraitValueAdmin(AdvancedFilterAdmin):
    list_display = ['value', 'trait_type', 'rarity', 'count']

@admin.register(TrendingTrait)
class TrendingTraitAdmin(AdvancedFilterAdmin):
    list_display = ['trait_type', 'trait_value', 'trend_score']