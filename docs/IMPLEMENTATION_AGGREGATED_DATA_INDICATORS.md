# Implementation Guide: Aggregated Data Source Indicators

## Overview

This guide shows how to add visual indicators to mark aggregated data (floor price, volume, etc.) across the TraitKeeper frontend.

---

## Step 1: Add CSS File to Base Template

**File:** `templates/index page/base.html`

**Location:** After line 27 (after tailwind-compiled.css)

```html
<!-- Add this line -->
<link rel="stylesheet" href="{% static 'css/data-source-indicator.css' %}" type="text/css">
```

---

## Step 2: Add Legend to Footer

**File:** `templates/index page/base.html`

**Location:** After TPS span (line 1108), before Support span (line 1110)

### Desktop Footer (Line 1108):

```html
<!-- After TPS span -->
</span>

<!-- ADD THIS NEW LEGEND -->
<span class="data-sources-legend">
    <span class="legend-icon">ⓘ</span>
    <span>Aggregated Data</span>
</span>

<!-- Before Support -->
<span class="support...">Support</span>
```

### Mobile Footer (Line 1152):

Add the same legend after mobile TPS:

```html
<!-- After mobile TPS span -->
</span>

<!-- ADD THIS -->
<span class="data-sources-legend text-[10px]">
    <span class="legend-icon">ⓘ</span>
    <span>Agg. Data</span>
</span>
```

---

## Step 3: Create Reusable Indicator Component

**File:** Create `templates/index page/components/data_indicator.html`

```html
<!-- Data Source Indicator Component -->
<span class="data-source-indicator">
    <span class="data-source-icon" aria-label="Aggregated from multiple sources">ⓘ</span>
    <span class="data-source-tooltip">
        Aggregated from Magic Eden, Tensor & Blockchain
    </span>
</span>
```

---

## Step 4: Add Indicators to Collection Detail Page

**File:** `templates/index page/collection_detail.html`

### Location 1: Mobile Stats (Line 1334-1339)

```html
<!-- BEFORE -->
<strong id="mobile-floor">-- SOL</strong>
<span>Floor Price</span>

<!-- AFTER -->
<strong id="mobile-floor">-- SOL{% include "index page/components/data_indicator.html" %}</strong>
<span>Floor Price</span>
```

```html
<!-- BEFORE -->
<strong id="mobile-volume-24h">-- SOL</strong>
<span>24h Volume</span>

<!-- AFTER -->
<strong id="mobile-volume-24h">-- SOL{% include "index page/components/data_indicator.html" %}</strong>
<span>24h Volume</span>
```

### Location 2: Desktop Stats (Lines 1991-2002)

```html
<!-- BEFORE -->
<strong>${floorPrice} SOL</strong>

<!-- AFTER -->
<strong>${floorPrice} SOL<span class="data-source-indicator">
    <span class="data-source-icon">ⓘ</span>
    <span class="data-source-tooltip">Aggregated from Magic Eden, Tensor & Blockchain</span>
</span></strong>
```

Apply same pattern to:
- `${volume24h} SOL` (line 1999)
- `${totalVolume} SOL` (line 2005)
- `${marketCap} SOL` (line 2007)

### Location 3: Fallback Stats (Lines 2024-2027)

Add same indicator after each SOL value in the fallback section.

---

## Step 5: Add Indicators to Index Page

**File:** `templates/index page/index.html`

### Location 1: Hero Collection Cards (Lines 242, 281)

```html
<!-- BEFORE -->
{{ collection_stats.total_volume_24h|floatformat:2 }} SOL

<!-- AFTER -->
{{ collection_stats.total_volume_24h|floatformat:2 }} SOL{% include "index page/components/data_indicator.html" %}
```

### Location 2: Trending Collections (Lines 408-413)

```html
<!-- BEFORE -->
<strong class="text-lg font-bold">{{ collection.floor_price|floatformat:2|default:"--" }} SOL</strong>

<!-- AFTER -->
<strong class="text-lg font-bold">
    {{ collection.floor_price|floatformat:2|default:"--" }} SOL{% include "index page/components/data_indicator.html" %}
</strong>
```

Apply same to `{{ collection.volume_24h }}` on line 413.

### Location 3: Collections Table (Line 642)

```html
<!-- BEFORE -->
{{ collection.volume|floatformat:2 }} SOL

<!-- AFTER -->
{{ collection.volume|floatformat:2 }} SOL{% include "index page/components/data_indicator.html" %}
```

### Location 4: Collection Modal (Lines 1194, 1202)

```html
<!-- BEFORE -->
<span id="collection-modal-floor" class="...">-- SOL</span>

<!-- AFTER -->
<span id="collection-modal-floor" class="...">
    -- SOL{% include "index page/components/data_indicator.html" %}
</span>
```

Apply same to `collection-modal-volume` (line 1202).

### Location 5: JavaScript-rendered Content

For dynamically rendered stats (lines 1438-1442, 1582, 1618-1621), add indicator in JavaScript:

```javascript
// BEFORE
${sweep.total_volume.toFixed(2)} SOL

// AFTER
${sweep.total_volume.toFixed(2)} SOL<span class="data-source-indicator">
    <span class="data-source-icon">ⓘ</span>
    <span class="data-source-tooltip">Aggregated from Magic Eden, Tensor & Blockchain</span>
</span>
```

---

## Step 6: Add Indicators to Trait Analytics (Index Page)

**File:** `templates/index page/index.html`

### Location: Trait Table (Lines 979-982)

```html
<!-- Volume column -->
{{ trait.volume|floatformat:2 }} SOL{% include "index page/components/data_indicator.html" %}

<!-- Floor price column -->
{{ trait.floor_price|floatformat:2 }} SOL{% include "index page/components/data_indicator.html" %}

<!-- Market cap column -->
{{ trait.market_cap|floatformat:2 }} SOL{% include "index page/components/data_indicator.html" %}
```

Apply same to JavaScript-rendered trait rows (lines 1618-1621).

---

## Visual Result

### Before:
```
Floor: 2.34 SOL
24h Vol: 15.2K SOL
```

### After:
```
Floor: 2.34 SOL ⓘ
       └─ [Tooltip: Aggregated from Magic Eden, Tensor & Blockchain]

24h Vol: 15.2K SOL ⓘ
         └─ [Tooltip: Aggregated from Magic Eden, Tensor & Blockchain]
```

### Footer Legend:
```
SOL: $98.45 | TPS: 3,542 | ⓘ Aggregated Data | Support
```

---

## Testing

1. **Desktop view:**
   - Hover over ⓘ icon → See tooltip
   - Check footer shows "ⓘ Aggregated Data"

2. **Mobile view:**
   - Tap ⓘ icon (may not show tooltip on mobile - that's OK)
   - Check footer shows "ⓘ Agg. Data" (shorter text)

3. **Dark mode:**
   - Toggle dark mode
   - Verify icon colors change appropriately

4. **Verify locations:**
   - [ ] Collection detail stats
   - [ ] Index page hero cards
   - [ ] Trending collections
   - [ ] Collections table
   - [ ] Sweeps cards
   - [ ] Trait analytics table
   - [ ] Footer legend

---

## Files Modified

1. ✅ `static/css/data-source-indicator.css` - CSS component (CREATED)
2. 🔨 `templates/index page/base.html` - Add CSS link + footer legend
3. 🔨 `templates/index page/components/data_indicator.html` - Reusable component (CREATE)
4. 🔨 `templates/index page/collection_detail.html` - Add indicators
5. 🔨 `templates/index page/index.html` - Add indicators

---

## Quick Implementation Script

For faster implementation, here's a Python script to add indicators automatically:

```python
# add_data_indicators.py
import re

def add_indicator(html_content, pattern, replacement):
    """Add data indicator after SOL values"""
    return re.sub(pattern, replacement, html_content)

# Run this script to automatically add indicators to all SOL values
# Usage: python add_data_indicators.py
```

---

## Maintenance

**When adding new pages/components:**

1. If showing floor price or volume → Add indicator
2. If data comes from CollectionMarketStats → Add indicator
3. If data is TraitKeeper proprietary (vitality, etc.) → NO indicator

**Rule of thumb:**
- Aggregated data (floor, volume, listed count) → ⓘ indicator
- Proprietary metrics (vitality, trait performance) → NO indicator
- Blockchain-only data (sales count, holders) → NO indicator

---

**Last Updated:** December 18, 2025
**Version:** 1.0.0
**Author:** TraitKeeper Frontend Team
