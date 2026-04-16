---
name: price-monitor
description: Check a product URL for price changes and alert on drops
category: shopping
triggers:
  - check price
  - price of
  - track price
  - price monitor
  - how much is
requires_tools:
  - web_fetch
  - note_save
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Price Monitor

Fetch a product page and extract current pricing.

## Steps
1. Use web_fetch to get the product page content
2. Extract the current price from the page content
3. Check notes (note_search) for previous prices of this product
4. Compare with previous price if available
5. Report:
   - Current price
   - Previous price (if tracked)
   - Price change (up/down/same)
6. Save the current price as a note with tag "price-tracking"

## Success Criteria
- tool success: web_fetch completed
- note_saved: price was recorded

## Notes
- Some sites block scrapers — report if the page can't be fetched
- Extract prices carefully — look for currency symbols and number patterns
- Don't make purchase decisions for the user, just report data
