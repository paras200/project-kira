---
name: market-analysis
description: Analyze a stock or market for trading opportunities using price data and fundamentals
category: finance
triggers:
  - analyze stock
  - should I buy
  - is it a good trade
  - stock analysis
  - trade analysis
  - investment analysis
  - what do you think about
  - bullish or bearish
requires_tools:
  - stock_price
  - stock_detail
  - stock_screener
  - market_overview
  - web_search
  - note_save
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Market Analysis

Perform a comprehensive analysis of a stock or market instrument.

## Steps
1. Get current price with stock_price
2. Get detailed fundamentals with stock_detail
3. Run the technical screener with stock_screener
4. Search for recent news about the company using web_search ("{ticker} stock news")
5. Synthesize all data into a structured analysis:
   - Current price and trend (above/below moving averages)
   - Fundamental health (P/E, EPS, market cap, dividend)
   - Technical signals (volatility, volume, 52-week position)
   - Recent news sentiment
   - Risk factors
6. Save the analysis as a note with tags ["finance", "analysis", "{ticker}"]
7. Present a clear summary with bull case and bear case

## Success Criteria
- tool success: all finance tools completed
- note_saved: analysis was saved

## Notes
- ALWAYS include the disclaimer: "This is data analysis, not financial advice"
- Present both bull and bear perspectives
- Flag high-risk indicators (high beta, extreme P/E, low volume)
- Compare to sector averages when possible
- If the user asks about crypto, use BTC-USD, ETH-USD format
