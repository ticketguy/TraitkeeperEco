TraitKeeper Vitality & Analytics System Documentation

## Quick Reference: Data Sources

### 🏆 TraitKeeper Proprietary Calculations (Source of Truth)

These metrics are **calculated entirely by TraitKeeper** and represent our intellectual property:

| Metric | Calculated By | Input Data | Purpose |
|--------|---------------|------------|---------|
| **Vitality Score (0-100)** | VitalityCalculationService | 8-component weighted formula | Overall NFT/collection health |
| **Trait Performance Score** | TraitAnalyticsService | NFT sales history + trait data | Trait demand & pricing premium |
| **Market Efficiency Score** | MarketAggregationService | Volume, liquidity, bid-floor ratio | Price discovery effectiveness |
| **Holder Confidence Index** | MarketAggregationService | Listing trends, price trends | Holder sentiment |
| **Liquidity Health Score** | MarketAggregationService | Volume depth, listing depth, bid depth | Market liquidity quality |
| **Wallet Prominence** | WalletAnalyticsService | Wallet transaction history | Holder quality assessment |
| **Sweep Detection** | SweepDetector | Transaction patterns | Whale activity identification |
| **Collection Rarity Rank** | TraitService | Trait frequencies | Statistical rarity (one-time calc) |

**Storage Location:** `analytics/models.py`, `marketplace/models/vitality_models.py`

**Update Frequency:** VIP (15min), ACTIVE (1hr), INACTIVE (4hr)

---

### 🌐 External Data Sources (Aggregated)

These metrics come from **external APIs** and are aggregated/validated by TraitKeeper:

| Metric | Source APIs | How We Use It | Update Frequency |
|--------|-------------|---------------|------------------|
| **Floor Price** | Magic Eden, Tensor, Blockchain | Aggregate minimum across sources | Per priority tier |
| **24h Volume** | Magic Eden, Tensor, Blockchain | Sum unique transactions | Per priority tier |
| **Listed Count** | Magic Eden, Tensor | Maximum across sources | Per priority tier |
| **Total Supply** | Blockchain (primary), APIs (backup) | Use blockchain if available | Once on import, then hourly |
| **Sales Count** | Blockchain events (NFTEvent) | Count SALE events | Real-time |
| **Recent Sales** | Magic Eden, Tensor APIs | Fill gaps in blockchain data | Per priority tier |

**Storage Location:** `indexer/models.py` (CollectionMarketStats - stores per-source data)

**Aggregation Logic:** See `indexer/services/main.py:fetch_and_store_all_market_stats()`

---

### 🔗 Core External Dependencies

**Critical (System cannot function without):**
- **Solana RPC Provider** (Helius/QuickNode) - Blockchain data ingestion
- **PostgreSQL Database** - All data storage
- **Redis Cache** - Performance optimization

**Important (Enhances data quality):**
- **Magic Eden API** - Marketplace listings & floor prices
- **Tensor API** - Marketplace analytics & UUID mappings

**Optional (Future features):**
- **Twitter API** - Sentiment analysis (Perception Index)
- **Discord API** - Community engagement metrics
- **CoinGecko API** - SOL price for USD conversions

---

### 📊 Data Source Priority

When multiple sources provide conflicting data:

```
Blockchain (100% trust) > Tensor (90%) > Magic Eden (85%) > TraitKeeper Internal (70%)
```

**Example - Floor Price Determination:**
1. Check blockchain for lowest active listing → **Use if found**
2. If no blockchain data, check Tensor API → **Use if found**
3. If no Tensor data, check Magic Eden API → **Use if found**
4. If no external data, use TraitKeeper calculated estimate → **Last resort**

**Code Reference:** `indexer/services/aggregation_service.py`

---

1. 🎯 OverviewThe TraitKeeper Analytics System is a proprietary, three-tiered service architecture designed to replace traditional floor price metrics with a more holistic and dynamic Vitality Score. The system is optimized for performance, using decoupled services and asynchronous database operations to ensure data freshness and integrity.The core philosophy is to generate independent, high-signal metrics (Levels 1 & 2) that are then synthesized into a single, comprehensive asset valuation score (Level 3).2. 🏛️ System Architecture and Data FlowThe calculation process is sequential, with each level feeding the next:LevelServicePrimary OutputDependencies (Inputs)IMarketAggregationServiceAggregatedCollectionStatsRaw CollectionMarketStats (Multi-Source APIs, Indexer)II-ATraitAnalyticsServiceTraitPerformanceScoreLevel I Output (AggregatedCollectionStats), Raw NFT Sales (NFTEvent)II-BWalletAnalyticsServiceWalletProminence / WalletBehaviorProfileRaw NFT Events (NFTEvent)IIIVitalityCalculationServiceNFTVitality / CollectionVitalityOutputs from Level I, II-A, and II-B3. ⚙️ Level I: Market Aggregation and Health ScoreThe MarketAggregationService is the foundational data cleaning and normalization layer. It is responsible for creating a single, trusted source of market truth.A. Core Aggregation LogicMetricAggregation RuleRationaleFloor PriceMinimum across all active marketplace sources (e.g., Magic Eden, Tensor).Captures the true lowest barrier to entry in the market.Listed CountMaximum value across all sources.Provides the most comprehensive view of available supply.Volume (24h)Sum of volume from authoritative, unique transaction sources (e.g., Blockchain/Indexer).Prevents double-counting of volumes reported by different marketplaces.Total SupplyPrioritize Blockchain Source, then highest quality API source.Ensures the most accurate circulating supply count.B. Proprietary Health Scores (Stored in AggregatedCollectionStats)These scores are normalized from 0-100 and represent the collective collection health.MetricCalculation (Weighted Components)InterpretationMarket Efficiency Score$\approx (0.4 \times \text{Bid-Floor Ratio}) + (0.3 \times \text{Sales Velocity}) + (0.3 \times \text{Percent Listed})$Measures how effectively prices are discovered and assets are traded.Holder Confidence Index$\approx \text{Base} + \text{Boosts for Rising Price} + \text{Boosts for Decreasing Listings}$Measures the collective belief in the collection's future (holders not selling).Liquidity Health Score$\approx (0.4 \times \text{Volume Depth}) + (0.35 \times \text{Listing Depth}) + (0.25 \times \text{Bid Depth})$Measures how easily an asset can be bought or sold without impacting the price.4. 📈 Level II-A: Trait Performance Score (The Core IP)The TraitAnalyticsService generates the score that is the primary indicator of intrinsic asset value (Trait Value). This metric is independent of the overall collection market sentiment.Trait Performance ScoreThe final performance_score for a trait is a function of three weighted sub-metrics.$$\text{Raw Score} = (0.5 \times \text{Premium}) + (0.3 \times \text{Velocity} \times 10) + (0.2 \times (\text{Momentum} + 1))$$$$\text{Final Performance Score (0-100)} = \text{Normalized}(\text{Raw Score})$$Sub-MetricCalculationRationalePremium Score$\text{Avg}(\frac{\text{Sale Price}}{\text{Collection Floor Price}})$Directly measures the trait's power to command a price above the average NFT.Velocity Score$\frac{\text{Recent Sales with Trait}}{\text{Total NFTs with Trait}}$Measures demand and liquidity for the trait, relative to its rarity.Momentum Score$\text{Price Trend}$ calculated from the ratio change between early sales and recent sales.Measures the recent, current trajectory of the trait's value.5. 🧬 Level III: Vitality Score Synthesis (NFT and Collection)The VitalityCalculationService combines the outputs from Levels I and II using a fixed, proprietary weighting system to produce the final vitality_score (0-100).NFT and Collection Vitality Score Formula$$\text{Vitality Score} = \sum (\text{Component Score} \times \text{Weight}) \times 100$$ComponentWeightCalculation SourceFocusMarket Momentum25%Derived from Level I: Collection price_change_24h and volume_24h.Recent market interest.Trait Performance20%Level II-A: Average of the TraitPerformanceScore for all traits on the NFT.Intrinsic asset value.Collection Health15%Derived from Level I: Weighted average of Efficiency, Confidence, and Liquidity scores.Parent collection reliability.Holder Quality10%Level II-B: Reads the owner's WalletProminence score.Value attributed to ownership.Rarity Score10%Calculated from trait rarities using log scaling (combination rarity).Scarcity (Statistical Value).Collection Utility10%Placeholder (0.5) - Requires external tagging/analysis.Functional value beyond art.Sentiment Score5%Placeholder (0.5) - Requires social media implementation.Community perception.Market Influence5%Derived from Level I: Weighted average of volume, holder count, and marketplace presence.Ecosystem impact.6. ⚠️ Critical Dependency Note for ViewsACTION REQUIRED: For views that read Level I and Level III data (index, collection_detail, SSE streams), developers must ensure they query the correct models:For Proprietarily Calculated Metrics (Health, Confidence, Velocity): Use AggregatedCollectionStats.For Final Scores (Vitality): Use NFTVitality or CollectionVitality.For Trait Scores: Use TraitPerformanceScore.This prevents errors arising from the initial architectural bug where Level III was incorrectly querying raw CollectionMarketStats for final proprietary scores.
