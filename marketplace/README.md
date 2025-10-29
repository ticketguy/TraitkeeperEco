# Marketplace App - TraitKeeper's Privacy-First NFT Marketplace

## Overview

The marketplace app powers TraitKeeper's **privacy-first, peer-to-peer NFT marketplace** with the innovative **NFT Vitality** valuation system.

### Core Philosophy

Unlike traditional NFT marketplaces that rely on floor price and public order books, TraitKeeper's marketplace:

- **Individual NFT Valuation**: Uses NFT Vitality (0-100 score) as the primary value metric, not collection floor price
- **Privacy-First Trading**: Encrypted bids via Arcium prevent front-running and public speculation
- **Peer-to-Peer Negotiations**: Direct negotiations between buyers and sellers without intermediaries
- **Vitality Protection**: All prices and bids validated against NFT vitality to prevent lowball offers and overpricing

---

## The 4 Ways to Trade on TraitKeeper

TraitKeeper supports 4 distinct trading methods, each designed for different use cases:

### 1. 💰 Direct Sell (Fixed Price, Non-Negotiable)

**What It Is:**  
Owner sets a **fixed "Buy Now" price** with **zero negotiation**.

**How It Works:**

```
Owner: "This NFT is exactly 5.0 SOL. Take it or leave it."
Buyer: Either pays 5.0 SOL immediately OR walks away.
```

**Use Cases:**

- Quick sales when owner needs immediate liquidity
- NFTs with well-known market value
- When owner doesn't want to negotiate

**Protection:**

- Price must pass vitality validation (can't be too far from vitality score)
- Prevents owner from accidentally pricing 10x below market value

**API Endpoints:**

- `POST /api/direct-sell/set/` - Owner sets fixed price
- `POST /api/direct-sell/remove/` - Owner removes listing
- `POST /api/direct-sell/buy/` - Buyer purchases at fixed price

---

### 2. 🤝 Sell Intent (Asking Price + Negotiable)

**What It Is:**  
Owner sets an **asking price** but signals **"I'm open to offers"**.

**How It Works:**

```
Owner: "I want 5.0 SOL, but I'm open to reasonable offers."
Buyer Option 1: Accepts 5.0 SOL immediately (instant sale)
Buyer Option 2: Counters with 4.2 SOL (negotiation starts)
```

**The Key Difference from Direct Sell:**

- **Direct Sell**: "5.0 SOL or nothing" (rigid)
- **Sell Intent**: "I want 5.0 SOL, but make me an offer" (flexible)

**Use Cases:**

- Owner has target price but willing to negotiate
- Testing the market to see what buyers will offer
- Encouraging serious buyers to make competitive offers

**Protection:**

- Asking price gets vitality validation (warning only, not blocking)
- Counter-offers must pass vitality validation (-20% to -25% threshold)
- Prevents buyers from making ridiculous lowball offers

**API Endpoints:**

- `POST /api/sell-intent/set/` - Owner sets asking price
- `POST /api/sell-intent/remove/` - Owner removes intent
- `POST /api/sell-intent/accept/` - Buyer accepts asking price (instant sale)
- `POST /api/bid/counter/` - Buyer counters with different amount

**Example Flow:**

```
1. Owner sets asking price: 5.0 SOL
2. Buyer sees: "Owner wants 5.0 SOL (Open to Offers)"
3. Buyer options:
   a) Accept 5.0 SOL → Instant sale
   b) Counter with 4.5 SOL → Owner reviews
4. If countered:
   - Owner can: Accept, Reject, or Counter back
   - All counters validated against vitality (-20% threshold)
```

---

### 3. 🔒 Private Bid (Unsolicited Offer)

**What It Is:**  
Buyer makes an **encrypted, private bid** on **ANY NFT**, even if not for sale.

**How It Works:**

```
Buyer: "I'll offer [ENCRYPTED AMOUNT] for your NFT."
Owner: Only the owner can see the bid amount.
Owner Options: Accept, Reject, or Counter
```

**Use Cases:**

- Buyer wants an NFT that's not explicitly for sale
- Private negotiations without public price discovery
- Shooting your shot on a specific NFT you love

**Privacy Features:**

- Bid amount is **encrypted on-chain** (Arcium)
- Only NFT owner can decrypt and view amount
- Other users cannot see bid amounts
- Funds are **escrowed in smart contract**

**Protection:**

- All bids validated against vitality score
- Minimum threshold: -20% to -25% below vitality
- Prevents ridiculous lowball offers
- Expiry time (default 72 hours) prevents stale bids

**API Endpoints:**

- `POST /api/bid/place/` - Buyer places private bid
- `POST /api/bid/accept/` - Owner accepts bid
- `POST /api/bid/reject/` - Owner rejects bid
- `POST /api/bid/cancel/` - Bidder cancels own bid
- `POST /api/bid/counter/` - Owner counters with new price

**Example Flow:**

```
1. Buyer sees Mad Lad #1234 (not for sale)
2. Buyer places encrypted bid: 4.5 SOL
3. Funds escrowed on-chain
4. Owner receives notification: "New private bid"
5. Owner reveals bid: 4.5 SOL
6. Owner decides:
   a) Accept → Sale executes, funds released
   b) Reject → Funds returned to bidder
   c) Counter → "How about 5.0 SOL instead?"
```

---

### 4. 🏛️ Auction (Time-Based, Encrypted Bids)

**What It Is:**  
**Silent auction** where all bids are encrypted - bidders compete without seeing each other's amounts.

**How It Works:**

```
Owner: Creates auction with starting price and duration
Bidders: Place encrypted bids
Feedback: Bidders only know "you're high bidder" or "you've been outbid"
Outcome: At auction end, highest bidder wins
```

**The Genius:**

- Traditional auctions: Bidders see each other's amounts → incremental \$1 increases
- TraitKeeper: Bidders are blind → must bid their TRUE maximum value

**Use Cases:**

- Owner wants competitive bidding
- High-value NFTs where price discovery is needed
- When owner believes NFT will attract multiple serious buyers

**Privacy Features:**

- All bid amounts **encrypted on-chain**
- Bidders only get binary feedback: "winning" or "outbid"
- Final price only revealed **after auction ends**

**Protection:**

- Starting price validated against vitality
- All bids validated against vitality threshold
- Optional reserve price (encrypted)

**API Endpoints:**

- `POST /api/auction/create/` - Owner creates auction
- `POST /api/auction/bid/` - Bidder places encrypted bid
- `POST /api/auction/cancel/` - Owner cancels (only if no bids)

**Example Flow:**

```
1. Owner creates auction:
   - Starting price: 3.0 SOL
   - Duration: 48 hours
   - Reserve: 5.0 SOL (encrypted, optional)

2. Bidding phase:
   - Bidder A bids 4.0 SOL → "You're the high bidder"
   - Bidder B bids 4.5 SOL → A gets "You've been outbid", B gets "You're the high bidder"
   - Bidder A bids 5.5 SOL → B gets "You've been outbid", A gets "You're the high bidder"

3. Auction ends after 48 hours:
   - Winner: Bidder A at 5.5 SOL
   - Price revealed for first time
   - NFT transferred, funds released
```

1. How Your System Works Now (The "Open Negotiation" Model 핑 pong)
This is the logic your code currently follows:

Bidder: "I'll offer 4.0 SOL for this NFT you aren't selling." (Creates a PrivateBid)

Owner: "I wasn't planning to sell, but 4.0 is too low. I'll sell it for 5.0 SOL." (Calls owner_counter_bid)

Your Code: "Aha! The owner has named a price. This means has_sell_intent is now True and the asking_price is 5.0."

Bidder: "Great, they're selling. 5.0 is still high. I'll counter with 4.5 SOL." (Calls bidder_counter_sell_intent)

Your Code: "This is a valid action because has_sell_intent is True."

In this model, the owner's counter-offer is not a final answer. It's the owner entering the negotiation. By countering, they are changing their "no plan to sell" status into a "plan to sell at the right price."
---

## Summary Comparison Table

| Feature | Direct Sell | Sell Intent | Private Bid | Auction |
|---------|-------------|-------------|-------------|---------|
| **Owner Sets Price?** | ✅ Fixed | ✅ Asking | ❌ None | ✅ Starting |
| **Negotiable?** | ❌ No | ✅ Yes | ✅ Yes | ✅ Competitive |
| **Buyer Can Accept Immediately?** | ✅ Yes | ✅ Yes | ❌ No (owner must accept) | ❌ No (must wait for end) |
| **Encrypted?** | ❌ Public | ❌ Public | ✅ Yes | ✅ Yes |
| **Time-Limited?** | ❌ No | ❌ No | ✅ Yes (72hr default) | ✅ Yes (set by owner) |
| **Best For** | Quick sales | Flexible sales | Unsolicited offers | High-value competitive bidding |
| **Vitality Protection** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |

See full README at: /mnt/user-data/outputs/README.md




