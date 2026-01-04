# Profile Page Redesign Plan

## Goal
Redesign the user profile page to have a modern, wallet-dashboard aesthetic inspired by the reference images, while maintaining existing functionality and keeping it uniquely styled.

## User Requirements
- **Profile-first approach**: Profile picture and username prominent at top
- **Show wallet address**: Display primary wallet address truncated (e.g., "0xd953...B990") near profile name
- **Keep NFT toggle**: Maintain existing art view/list view functionality, improve styling
- **No redundant badges**: Use existing achievement system instead of adding tier badges
- **No sidebar**: Works with existing header navigation
- **Subtle animations**: Keep existing card animations

## Implementation Strategy

### 1. Hero Section Redesign
**Current**: Large profile card with avatar on left, info on right, wallet assets at bottom
**New**: More prominent profile identity, cleaner wallet address display

#### Changes to make:
- **Profile Header**:
  - Larger, more centered profile picture (or left-aligned with better prominence)
  - Username as main heading with larger font
  - Primary wallet address displayed prominently below username (truncated format)
  - Copy button next to wallet address
  - Social links as icon pills
  - Join date and edit profile button

- **Stats Cards Row** (new section below profile):
  - Total wallet balance (SOL) - large number with icon
  - NFT count - shows total NFTs owned
  - Collections count - unique collections
  - Active listings count
  - Each card with gradient background, subtle glow on hover

### 2. Wallet Assets Section
**Current**: Expandable section in profile header
**New**: Dedicated prominent card section

#### Changes to make:
- **SOL Balance Card**:
  - Large balance number
  - USD equivalent (if available)
  - Percentage change indicator
  - Gradient background (purple/pink theme)

- **Token Holdings Cards**:
  - Grid layout for top tokens
  - Each token: icon, symbol, balance, USD value
  - "View all tokens" button if >6 tokens
  - Card design with subtle hover effects

### 3. Connected Wallets Display
**Current**: List in expandable section
**New**: Clean card-based display

#### Changes to make:
- Show primary wallet prominently in header
- Other wallets in a collapsible section
- Each wallet: truncated address, "Primary" badge, copy button, Solscan link
- Better visual hierarchy

### 4. Tabs Redesign
**Current**: Underline tabs
**New**: Modern pill/button style tabs

#### Changes to make:
- Rounded pill design
- Active tab: gradient background
- Inactive tabs: ghost style
- Smooth transitions
- Sticky on scroll (keep existing)

### 5. Portfolio Tab Improvements
**Current**: Grid/list toggle with basic cards
**New**: Enhanced visual design

#### Changes to make:
- **Art View**:
  - Better card design with gradient overlays
  - Collection badge on each NFT
  - Vitality score indicator
  - Smooth hover animations

- **List View**:
  - Table-like rows
  - Columns: Image | Name & Collection | Floor Price | Vitality | Actions
  - Alternating row colors
  - Better mobile responsiveness

### 6. Achievements Display
**Current**: Achievement cards in separate tab
**New**: Keep mostly the same, just better styling

#### Changes to make:
- More prominent achievement icons
- Better rarity color scheme
- Progress bars for incomplete achievements
- Tooltip on hover showing details

### 7. Responsive Design
Ensure all new components work well on mobile:
- Stack cards vertically on small screens
- Collapsible sections for wallet details
- Touch-friendly buttons
- Readable text sizes

## File Changes Required

### 1. `templates/profile/user_profile.html`
- Restructure hero section HTML
- Add stats cards row
- Redesign wallet assets section
- Update tabs styling
- Improve portfolio grid/list layouts
- Add copy-to-clipboard functionality

### 2. CSS Updates (in `extra_style` block)
- New gradient definitions
- Card hover effects
- Pill tab styling
- Wallet address styling
- Token card layouts
- Improved responsive breakpoints
- Keep existing animations, enhance them

### 3. JavaScript Updates (in `extra_js` block)
- Copy to clipboard for wallet addresses
- Stats cards animations
- Token card interactions
- Keep existing tab switching
- Keep existing view toggle

### 4. No Backend Changes Needed
- All data already available in context
- wallet_balances provides token data
- user_wallets provides wallet list
- Existing stats object has counts

## Design System

### Colors (from base.html CSS variables)
- Primary: `var(--primary-color)` - Purple
- Accent: `var(--accent-color-light/dark)`
- Text: `var(--text-light/dark)`
- Background: `var(--background-light/dark)`

### Gradients
- Purple to Pink: `linear-gradient(135deg, rgba(128,0,128,0.1), rgba(255,105,180,0.1))`
- Stats cards: `linear-gradient(to-br, from-color, to-color)`
- Token cards: Subtle radial gradients

### Animations (keep existing)
- `subtleFloat` for background orbs
- `fadeInScale` for avatar
- `pulse` for hover effects
- Add: `slideInUp` for stats cards on load

### Typography
- Profile name: `text-3xl sm:text-4xl font-bold`
- Wallet address: `text-sm font-mono text-secondary`
- Balance amounts: `text-2xl sm:text-3xl font-bold`
- Stats labels: `text-xs uppercase tracking-wide`

## Mockup Structure

```
┌─────────────────────────────────────────────────────────┐
│                     HEADER (existing)                    │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  [Avatar]   Username                    [Edit Profile]  │
│             0xd953...B990 📋                             │
│             🌐 🐦 🔗  • Joined Jan 2024                 │
└─────────────────────────────────────────────────────────┘

┌──────────┬──────────┬──────────┬──────────┬──────────┐
│  💰 SOL  │  🖼 NFTs  │  📚 Coll.│  🏷 List │  🎯 Bids │
│   12.5   │    247   │    18    │    5     │    3     │
└──────────┴──────────┴──────────┴──────────┴──────────┘

┌───────────────────────────────────────────────────────┐
│  💎 Wallet Assets                                     │
│  ┌─────────────────┐  ┌─────────────────┐            │
│  │ SOL             │  │ USDC            │  [+ More]  │
│  │ 12.5 SOL        │  │ 1,250 USDC      │            │
│  │ $2,450          │  │ $1,250          │            │
│  └─────────────────┘  └─────────────────┘            │
└───────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────┐
│  [Portfolio] [Achievements] [Watchlist] [Listings]... │
└───────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────┐
│  [🎨 Art] [📋 List]    [Filters ▼] [Sort ▼]          │
│                                                        │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                 │
│  │NFT │ │NFT │ │NFT │ │NFT │ │NFT │  ...             │
│  └────┘ └────┘ └────┘ └────┘ └────┘                 │
└───────────────────────────────────────────────────────┘
```

## Implementation Steps

1. **Create new CSS classes** for:
   - Stats cards
   - Wallet balance cards
   - Token cards
   - Pill tabs
   - Enhanced portfolio items

2. **Restructure hero section**:
   - Profile identity block
   - Wallet address display with copy button
   - Social links row

3. **Add stats cards row**:
   - SOL balance card
   - NFT count card
   - Collections card
   - Listings card
   - Bids card

4. **Redesign wallet assets section**:
   - SOL balance card
   - Token cards grid
   - "View all" expansion

5. **Update tabs styling**:
   - Change from underline to pill style
   - Add gradient to active state
   - Improve mobile overflow scroll

6. **Enhance portfolio layouts**:
   - Better art view card design
   - Improved list view table
   - Keep toggle functionality

7. **Add JavaScript**:
   - Copy to clipboard for wallet addresses
   - Smooth scroll to tabs
   - Stats animation on load
   - Keep existing functionality

8. **Test responsive**:
   - Mobile: stack cards, collapsible sections
   - Tablet: 2-column grids
   - Desktop: full layout

9. **Polish**:
   - Add loading states
   - Error handling for missing data
   - Empty states
   - Tooltips

## Advantages of This Approach

1. **No backend changes**: Uses existing data structure
2. **Progressive enhancement**: Keeps all existing functionality
3. **Responsive**: Works on all screen sizes
4. **Performance**: CSS animations, no heavy JS
5. **Maintainable**: Clear separation of concerns
6. **Accessible**: Semantic HTML, keyboard navigation
7. **Unique**: Inspired by reference but distinct TraitKeeper style

## Edge Cases to Handle

1. **No wallet connected**: Show placeholder with "Connect Wallet" CTA
2. **No tokens**: Show empty state in token section
3. **No NFTs**: Show empty portfolio message
4. **Long usernames**: Truncate with ellipsis
5. **Many tokens**: Pagination or "View all" expansion
6. **Mobile viewport**: Horizontal scroll for stats cards
7. **Dark mode**: Ensure gradients work in both themes

## Testing Checklist

- [ ] Profile loads correctly for authenticated user
- [ ] Profile loads correctly for visitors
- [ ] Wallet address displays and copies correctly
- [ ] Stats cards show accurate numbers
- [ ] Token cards display all wallet tokens
- [ ] Portfolio grid/list toggle works
- [ ] Tabs switch correctly
- [ ] Responsive on mobile
- [ ] Dark mode looks good
- [ ] Animations are smooth
- [ ] Empty states work
- [ ] Loading states work
- [ ] Social links clickable
