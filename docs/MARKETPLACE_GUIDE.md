# TraitKeeper Marketplace - Complete Guide

## Table of Contents
1. [Overview](#overview)
2. [Four Trading Methods](#four-trading-methods)
3. [NFT Vitality Protection](#nft-vitality-protection)
4. [Solana Smart Contracts](#solana-smart-contracts)
5. [Privacy Features](#privacy-features)
6. [Platform Fees](#platform-fees)
7. [API Reference](#api-reference)

---

## Overview

TraitKeeper's marketplace revolutionizes NFT trading on Solana with:

- **Individual NFT Valuation**: Every NFT gets a Vitality Score (0-100), not just floor price
- **Privacy-First Trading**: Encrypted bids prevent front-running
- **Four Trading Methods**: Flexible options for buyers and sellers
- **Smart Protection**: Vitality-based validation prevents lowball offers
- **Peer-to-Peer**: Direct negotiations without intermediaries

### Key Differentiators

| Traditional Marketplaces | TraitKeeper |
|-------------------------|-------------|
| Floor price valuation | Individual Vitality Scores |
| Public order books | Encrypted private bids |
| One way to trade | Four distinct methods |
| No price protection | Vitality-based validation |
| Centralized escrow | On-chain smart contracts |

---

## Four Trading Methods

### 1. 💰 Instant Buy (Fixed Price)

**What It Is**: Seller sets a non-negotiable "Buy Now" price.

**How It Works**:
```
Seller: "This NFT is exactly 5.0 SOL. Take it or leave it."
Buyer: Either pays 5.0 SOL immediately OR walks away.
```

**Use Cases**:
- Quick sales for immediate liquidity
- NFTs with established market value
- Sellers who don't want to negotiate

**Protection**:
- Price must pass Vitality validation
- Warning if price deviates significantly from Vitality Score
- Prevents accidental mispricing

**Smart Contract Flow**:
```rust
1. Seller calls create_listing() with fixed price
2. NFT locked in escrow smart contract
3. Buyer calls execute_sale() with exact SOL amount
4. Atomic swap: NFT to buyer, SOL to seller (minus fee)
```

**API Endpoints**:
```
POST /api/marketplace/instant-buy/create/
POST /api/marketplace/instant-buy/remove/
POST /api/marketplace/instant-buy/execute/
```

---

### 2. 🤝 Sell Intent (Negotiable Asking Price)

**What It Is**: Seller sets an asking price but signals "open to offers".

**How It Works**:
```
Seller: "I want 5.0 SOL, but I'm open to reasonable offers."

Buyer Option 1: Accept 5.0 SOL immediately → Instant sale
Buyer Option 2: Counter with 4.5 SOL → Negotiation begins
```

**Key Difference from Instant Buy**:
- **Instant Buy**: Rigid - "5.0 SOL or nothing"
- **Sell Intent**: Flexible - "5.0 SOL preferred, but make an offer"

**Use Cases**:
- Testing market demand
- Willing to negotiate but have target price
- Encouraging competitive offers

**Negotiation Flow**:
```
1. Seller sets asking price: 5.0 SOL
2. Buyer counters: 4.5 SOL (validated against Vitality)
3. Seller options:
   a) Accept 4.5 SOL → Sale executes
   b) Reject → Buyer can try again
   c) Counter 4.8 SOL → Buyer reviews
4. Back-and-forth until agreement or expiry
```

**Protection**:
- Asking price gets non-blocking validation warning
- All counter-offers must be within -20% to -25% of Vitality Score
- Prevents ridiculous lowball offers

**API Endpoints**:
```
POST /api/marketplace/sell-intent/create/
POST /api/marketplace/sell-intent/accept/     # Buyer accepts asking price
POST /api/marketplace/sell-intent/counter/    # Buyer/seller counter-offer
POST /api/marketplace/sell-intent/remove/
```

---

### 3. 🔒 Private Bid (Unsolicited Encrypted Offer)

**What It Is**: Buyer makes an encrypted bid on **any NFT**, even if not listed.

**How It Works**:
```
Buyer: "I'll offer [ENCRYPTED AMOUNT] for your NFT."
Owner: *Decrypts bid* "Oh, 4.5 SOL? Interesting..."
Owner Options: Accept, Reject, or Counter
```

**Use Cases**:
- NFT you want isn't listed for sale
- Private negotiations without public price discovery
- Making an offer directly to a holder

**Privacy Features**:
- **Encrypted on-chain**: Bid amount encrypted using Solana state encryption
- **Owner-only decryption**: Only NFT owner can see the amount
- **Escrowed funds**: SOL locked in smart contract
- **Hidden from others**: Third parties cannot see bid amounts

**Smart Contract Flow**:
```rust
1. Buyer calls place_encrypted_bid(nft_mint, encrypted_amount)
2. Smart contract:
   - Validates buyer has sufficient SOL
   - Escrows SOL
   - Stores encrypted bid on-chain
3. Owner decrypts via decrypt_my_bid(bid_id)
4. Owner chooses:
   - accept_bid() → Atomic swap
   - reject_bid() → SOL returned to buyer
   - counter_bid(new_encrypted_amount) → Continue negotiation
```

**Protection**:
- Minimum bid threshold: Vitality Score - 20% to -25%
- Expiry time: 72 hours default (prevents stale bids)
- Cancellation: Buyer can cancel before acceptance

**Example**:
```
Mad Lad #1234 (not listed)
Vitality Score: 6.0 SOL

Valid bids: 4.5 - 6.0+ SOL
Invalid bid: 3.0 SOL (below -25% threshold)

Flow:
1. Buyer places bid: 5.2 SOL (encrypted)
2. Funds escrowed
3. Owner decrypts: "Someone offered 5.2 SOL"
4. Owner counters: 5.8 SOL (encrypted)
5. Buyer accepts → Sale executes at 5.8 SOL
```

**API Endpoints**:
```
POST /api/marketplace/private-bid/place/
POST /api/marketplace/private-bid/accept/
POST /api/marketplace/private-bid/reject/
POST /api/marketplace/private-bid/counter/
POST /api/marketplace/private-bid/cancel/
GET  /api/marketplace/private-bid/decrypt/{bid_id}/
```

---

### 4. 🏛️ Silent Auction (Encrypted Competitive Bidding)

**What It Is**: Time-based auction where all bids are encrypted - bidders can't see each other's amounts.

**How It Works**:
```
Seller: Creates 48-hour auction, starting price 3.0 SOL
Bidder A: Bids [ENCRYPTED] → "You're the high bidder"
Bidder B: Bids [ENCRYPTED] → A gets "You've been outbid"
Bidder C: Bids [ENCRYPTED] → B gets "You've been outbid"
```

**The Genius**:
- **Traditional Auctions**: Bidders see amounts → Everyone bids $1 more
- **TraitKeeper**: Blind bidding → Must bid TRUE maximum value

**Use Cases**:
- High-value NFTs needing price discovery
- Multiple interested buyers
- Want competitive bidding without showing cards

**Privacy Features**:
- All bid amounts encrypted on-chain
- Binary feedback: "winning" or "outbid" (no amounts shown)
- Final price revealed only after auction ends
- Optional encrypted reserve price

**Auction Lifecycle**:
```
Phase 1: Creation
- Seller sets starting price & duration
- Optional: Set reserve price (encrypted)
- NFT locked in escrow

Phase 2: Bidding
- Bidders place encrypted bids
- Each gets feedback: "high bidder" or "outbid"
- Can't see other bid amounts
- Each bid extends auction by 5 minutes if near end (anti-snipe)

Phase 3: Conclusion
- Time expires
- Highest bidder revealed
- If reserve met: Sale executes
- If reserve not met: NFT returned to seller
```

**Protection**:
- Starting price validated against Vitality
- Minimum bid increment: 2% above current high
- Anti-sniping: Bids in last 5min extend time
- Reserve price protects seller

**Smart Contract Flow**:
```rust
1. Seller: create_auction(nft_mint, start_price, duration, reserve?)
2. NFT escrowed in auction PDA
3. Bidders: place_auction_bid(auction_id, encrypted_amount)
   - Validates: amount > current_high * 1.02
   - Escrows SOL
   - Returns previous bidder's SOL
4. Auction expires
5. finalize_auction():
   - Decrypt winning bid
   - Check reserve
   - Execute swap or return NFT
```

**Example**:
```
Auction: Okay Bear #456
- Starting: 3.0 SOL
- Reserve: 5.0 SOL (encrypted)
- Duration: 48 hours

Timeline:
Hour 0:  Auction starts
Hour 2:  Bidder A → 4.0 SOL → "High bidder"
Hour 10: Bidder B → 4.5 SOL → A: "Outbid", B: "High bidder"
Hour 30: Bidder C → 3.8 SOL → "Outbid" (lower than B)
Hour 45: Bidder A → 5.5 SOL → B: "Outbid", A: "High bidder"
Hour 48: Auction ends
         → Winner: Bidder A at 5.5 SOL
         → Reserve met (5.0 SOL)
         → Sale executes
```

**API Endpoints**:
```
POST /api/marketplace/auction/create/
POST /api/marketplace/auction/bid/
POST /api/marketplace/auction/cancel/  # Only if no bids
GET  /api/marketplace/auction/{id}/status/
```

---

## NFT Vitality Protection

All marketplace activities are validated against **NFT Vitality Scores** to protect users.

### Vitality Score (0-100)

Calculated from:
- Trait performance and rarity
- Collection health
- Market momentum
- Holder quality
- Historical stability

### Validation Levels

| Action | Validation Type | Threshold |
|--------|----------------|-----------|
| Instant Buy listing | Warning | ± 30% of Vitality |
| Sell Intent asking price | Warning | ± 30% of Vitality |
| Private bid | Blocking | -20% to -25% minimum |
| Auction starting price | Warning | ± 30% of Vitality |
| Counter-offers | Blocking | -20% to -25% minimum |

**Warning**: User sees alert but can proceed
**Blocking**: Transaction rejected

### Example Validation:
```
NFT: Mad Lad #789
Vitality Score: 10.0 SOL

Valid Actions:
✅ List for instant buy: 7.0 - 13.0 SOL (warning outside)
✅ Private bid: 7.5+ SOL (blocks below)
✅ Counter-offer: 7.5+ SOL (blocks below)

Invalid Actions:
❌ Private bid: 6.0 SOL (blocked - below threshold)
❌ Counter: 5.0 SOL (blocked - lowball offer)
```

---

## Solana Smart Contracts

### Architecture

TraitKeeper uses **Anchor framework** (Rust) for Solana programs.

**Program Structure**:
```
/marketplace
  ├── instructions/
  │   ├── create_listing.rs
  │   ├── execute_sale.rs
  │   ├── place_bid.rs
  │   ├── accept_bid.rs
  │   ├── create_auction.rs
  │   └── finalize_auction.rs
  ├── state/
  │   ├── listing.rs
  │   ├── bid.rs
  │   └── auction.rs
  └── lib.rs
```

### Key Program Accounts (PDAs)

```rust
// Listing Account
pub struct Listing {
    pub seller: Pubkey,
    pub nft_mint: Pubkey,
    pub price: u64,
    pub listing_type: ListingType, // InstantBuy or SellIntent
    pub created_at: i64,
    pub bump: u8,
}

// Encrypted Bid Account
pub struct PrivateBid {
    pub bidder: Pubkey,
    pub nft_mint: Pubkey,
    pub encrypted_amount: Vec<u8>, // Encrypted SOL amount
    pub escrow_amount: u64,        // Actual escrowed SOL
    pub expires_at: i64,
    pub status: BidStatus,
    pub bump: u8,
}

// Auction Account
pub struct Auction {
    pub seller: Pubkey,
    pub nft_mint: Pubkey,
    pub starting_price: u64,
    pub encrypted_reserve: Option<Vec<u8>>,
    pub current_high_bidder: Option<Pubkey>,
    pub encrypted_high_bid: Vec<u8>,
    pub ends_at: i64,
    pub status: AuctionStatus,
    pub bump: u8,
}
```

### Security Features

- **Escrow Safety**: All funds and NFTs locked in PDAs
- **Atomic Swaps**: Either both transfer or both revert
- **Access Control**: Only authorized parties can modify
- **Time Locks**: Prevent premature withdrawals
- **Reentrancy Guards**: Protect against attacks

---

## Privacy Features

### Encryption Layer

**Method**: Solana state encryption (accounts with restricted read access)

**How It Works**:
1. Bid amount encrypted client-side with owner's public key
2. Encrypted data stored on-chain
3. Only owner can decrypt with private key
4. Third parties see gibberish

**Example**:
```javascript
// Client-side encryption
const encryptedAmount = encryptBidAmount(
  bidAmountSOL,
  nftOwnerPublicKey
);

// Send to smart contract
await program.methods
  .placeBid(encryptedAmount)
  .accounts({ ... })
  .rpc();

// Owner decrypts
const actualAmount = decryptBidAmount(
  encryptedData,
  ownerPrivateKey
);
```

### What's Private, What's Public?

| Information | Visibility |
|-------------|-----------|
| Instant Buy price | 🌍 Public |
| Sell Intent asking price | 🌍 Public |
| Private bid amounts | 🔒 Owner only |
| Auction bid amounts | 🔒 Bidders get binary feedback |
| Final auction price | 🌍 Public (after close) |
| Counter-offer amounts | 🔒 Between two parties |

---

## Platform Fees

### Fee Structure

- **Platform Fee**: 2.5% on all sales
- **Royalties**: Passed to collection creators (if applicable)
- **No listing fees**: Free to list NFTs

### Fee Distribution

```
Sale Price: 10.0 SOL

Breakdown:
- Seller receives:    9.75 SOL (97.5%)
- Platform fee:       0.25 SOL (2.5%)
- Creator royalty:    Variable (from seller's portion)
```

### Rebate Rewards

Active traders earn fee rebates:

| Monthly Volume | Rebate Rate |
|---------------|-------------|
| 0 - 100 SOL | 0% |
| 100 - 500 SOL | 10% |
| 500 - 1000 SOL | 25% |
| 1000+ SOL | 50% |

See [REBATE_REWARDS.md](REBATE_REWARDS.md) for details.

---

## API Reference

### Authentication

All marketplace APIs require authentication:

```bash
# Token-based auth
curl -H "Authorization: Token YOUR_TOKEN" \
  https://api.traitkeeper.io/api/marketplace/...
```

### Listing Endpoints

#### Create Instant Buy Listing
```
POST /api/marketplace/instant-buy/create/

Request:
{
  "nft_mint": "Abc...123",
  "price_sol": 5.0
}

Response:
{
  "listing_id": "xyz789",
  "signature": "5kN...",
  "status": "active"
}
```

#### Create Sell Intent
```
POST /api/marketplace/sell-intent/create/

Request:
{
  "nft_mint": "Abc...123",
  "asking_price_sol": 5.0
}
```

#### Execute Sale
```
POST /api/marketplace/instant-buy/execute/

Request:
{
  "listing_id": "xyz789",
  "buyer_wallet": "Def...456"
}
```

### Bidding Endpoints

#### Place Private Bid
```
POST /api/marketplace/private-bid/place/

Request:
{
  "nft_mint": "Abc...123",
  "bid_amount_sol": 4.5,
  "expiry_hours": 72
}

Response:
{
  "bid_id": "bid123",
  "encrypted_data": "...",
  "escrow_signature": "..."
}
```

#### Decrypt Bid (Owner Only)
```
GET /api/marketplace/private-bid/decrypt/{bid_id}/

Response:
{
  "bid_id": "bid123",
  "bidder": "Ghi...789",
  "amount_sol": 4.5,
  "expires_at": "2025-11-01T12:00:00Z"
}
```

### Auction Endpoints

#### Create Auction
```
POST /api/marketplace/auction/create/

Request:
{
  "nft_mint": "Abc...123",
  "starting_price_sol": 3.0,
  "duration_hours": 48,
  "reserve_price_sol": 5.0  // optional
}
```

#### Place Auction Bid
```
POST /api/marketplace/auction/bid/

Request:
{
  "auction_id": "auc456",
  "bid_amount_sol": 4.5
}

Response:
{
  "status": "high_bidder"  // or "outbid"
}
```

---

## Best Practices

### For Sellers

1. **Set realistic prices** - Use Vitality Score as guidance
2. **Choose right method**:
   - Need quick sale? → Instant Buy
   - Want to negotiate? → Sell Intent
   - High-value NFT? → Auction
3. **Monitor bids** - Check private bids regularly
4. **Set reserve prices** - Protect yourself in auctions

### For Buyers

1. **Check Vitality Score** - Don't overpay
2. **Use private bids** - Better privacy than public listings
3. **Bid your maximum** - Especially in auctions (you can't see others)
4. **Act fast on listings** - Good deals get snapped up quickly

### For Everyone

- **Verify transactions** - Always check signatures
- **Use hardware wallets** - Enhanced security
- **Enable notifications** - Don't miss bid responses
- **Read smart contract** - Open source on GitHub

---

## Troubleshooting

### Common Issues

**"Bid rejected - below threshold"**
- Your bid is more than 20-25% below Vitality Score
- Increase your offer or wait for price to drop

**"Transaction failed - insufficient funds"**
- Need enough SOL for: bid amount + transaction fee + rent
- Keep ~0.05 SOL buffer for fees

**"Can't decrypt bid"**
- Ensure you're the NFT owner
- Check your wallet is connected
- Try refreshing the page

**"Auction bid not accepted"**
- Must be at least 2% higher than current high bid
- Check current bid status first

---

## Support

- **Documentation**: https://github.com/ticketguy/TraitkeeperEco/tree/main/docs
- **System Status**: http://localhost:8000/system-health/dashboard/
- **Smart Contracts**: `/solana programs/marketplace/`

---

*TraitKeeper Marketplace - Where Privacy Meets Value*
