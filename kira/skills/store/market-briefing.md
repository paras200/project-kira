---
name: market-briefing
description: Daily market overview with indices, sectors, and notable movers
category: finance
triggers:
  - market update
  - market briefing
  - how are the markets
  - market overview
  - market summary
  - what happened in the market
requires_tools:
  - market_overview
  - web_search
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Market Briefing

Deliver a concise market overview.

## Steps
1. Run market_overview to get all major indices, commodities, and crypto prices
2. Use web_search for "stock market today" to get context on major movers
3. Present a structured briefing:
   - Major indices (S&P 500, Dow, NASDAQ) with direction
   - Notable movers or sectors
   - Commodities (gold, oil)
   - Crypto (BTC, ETH)
   - Key forex pairs
   - Any significant news driving the markets
4. Keep it under 300 words

## Success Criteria
- tool success: market_overview completed

## Notes
- Run this as part of the morning briefing if the user cares about markets
- Focus on what changed, not raw numbers
- Highlight anything unusual (VIX spike, volume anomaly, major gap)
