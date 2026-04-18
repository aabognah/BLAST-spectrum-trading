# Public Simulation Summary

Public-safe inferred summary from observable data only. No hidden model chain-of-thought is included.

## Inputs

- Results: public-results/scenario_1_price_discovery_second_price_results.json
- Blockchain: public-results/scenario_1_price_discovery_second_price_blockchain.json

## Market Summary

- Ticks: 50
- Auctions started: 65
- Bids submitted: 40
- Successful auctions: 12
- Failed auctions: 29
- Transactions: 12
- Avg transaction price: 150.0000
- Avg transaction price per MHz: 15.0000

## Blockchain Summary

- Blocks: 51
- Transactions recorded on-chain: 146
- Transactions by type:
  - auction_resolution: 41
  - place_bid: 40
  - start_auction: 65

## Per-Agent Summary

### agent-0

- Decisions: no_action=12, place_bid=0, start_auction=38, buy_now=0, other=0
- Bidding: bids_placed=0, avg_bid_amount=0.0000, avg_bid_shading=0.000000
- Selling: auctions_started=38, avg_reserve_price=112.8092, avg_reserve_markup=1.130219
- Outcomes: won=0, sold=12, failed_auctions=18, buyer_profit_total=0.0000, seller_profit_total=1200.0000

### agent-1

- Decisions: no_action=39, place_bid=11, start_auction=0, buy_now=0, other=0
- Bidding: bids_placed=11, avg_bid_amount=100.0000, avg_bid_shading=0.000000
- Selling: auctions_started=0, avg_reserve_price=0.0000, avg_reserve_markup=0.000000
- Outcomes: won=0, sold=0, failed_auctions=0, buyer_profit_total=0.0000, seller_profit_total=0.0000

### agent-2

- Decisions: no_action=33, place_bid=17, start_auction=0, buy_now=0, other=0
- Bidding: bids_placed=17, avg_bid_amount=154.4118, avg_bid_shading=0.000000
- Selling: auctions_started=0, avg_reserve_price=0.0000, avg_reserve_markup=0.000000
- Outcomes: won=0, sold=0, failed_auctions=0, buyer_profit_total=0.0000, seller_profit_total=0.0000

### agent-3

- Decisions: no_action=11, place_bid=12, start_auction=27, buy_now=0, other=0
- Bidding: bids_placed=12, avg_bid_amount=200.0000, avg_bid_shading=0.000000
- Selling: auctions_started=27, avg_reserve_price=148.8278, avg_reserve_markup=-0.110889
- Outcomes: won=12, sold=0, failed_auctions=11, buyer_profit_total=600.0000, seller_profit_total=0.0000

## Tick-by-Tick Inferred Narrative

These are inferred market behavior summaries from observed actions and outcomes.

| Tick | Auctions | Bids | Success | Failed | Avg Price | Avg Price/MHz | Inferred Summary |
|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 2 | 0 | 3 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 3 | 0 | 0 | 1 | 0 | 75.0000 | 15.0000 | Stable clearing behavior with observable market-based price discovery. |
| 4 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 5 | 1 | 3 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 6 | 0 | 2 | 1 | 0 | 150.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 7 | 1 | 1 | 1 | 0 | 75.0000 | 15.0000 | Stable clearing behavior with observable market-based price discovery. |
| 8 | 1 | 3 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 9 | 1 | 2 | 1 | 0 | 150.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 10 | 1 | 2 | 1 | 0 | 150.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 11 | 1 | 2 | 1 | 0 | 75.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 12 | 1 | 3 | 1 | 0 | 225.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 13 | 1 | 1 | 1 | 0 | 225.0000 | 15.0000 | Stable clearing behavior with observable market-based price discovery. |
| 14 | 1 | 2 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 15 | 0 | 1 | 1 | 0 | 225.0000 | 15.0000 | Stable clearing behavior with observable market-based price discovery. |
| 16 | 1 | 1 | 1 | 0 | 225.0000 | 15.0000 | Stable clearing behavior with observable market-based price discovery. |
| 17 | 1 | 3 | 1 | 0 | 75.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 18 | 2 | 1 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 19 | 2 | 2 | 1 | 0 | 150.0000 | 15.0000 | Competitive bidding pressure with multiple bids per cleared auction. |
| 20 | 2 | 1 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 21 | 2 | 2 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 22 | 1 | 1 | 0 | 1 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 23 | 2 | 2 | 0 | 2 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 24 | 1 | 1 | 0 | 1 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 25 | 1 | 0 | 0 | 2 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 26 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 27 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 28 | 2 | 0 | 0 | 2 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 29 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 30 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 31 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 32 | 1 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 33 | 1 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 34 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 35 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 36 | 1 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 37 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 38 | 0 | 1 | 0 | 0 | 0.0000 | 0.0000 | Demand appeared, but bids did not clear reserve conditions. |
| 39 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 40 | 2 | 0 | 0 | 2 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 41 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 42 | 2 | 0 | 0 | 2 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 43 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 44 | 2 | 0 | 0 | 2 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 45 | 1 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 46 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 47 | 1 | 0 | 0 | 2 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 48 | 2 | 0 | 0 | 0 | 0.0000 | 0.0000 | Mixed activity with incremental adjustment in agent behavior. |
| 49 | 2 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
| 50 | 0 | 0 | 0 | 1 | 0.0000 | 0.0000 | Supply posted, but no demand matched reserve constraints. |
