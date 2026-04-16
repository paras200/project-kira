---
name: morning-briefing
description: Generate a morning briefing with email summary, weather, and top news
category: daily
triggers:
  - morning briefing
  - daily briefing
  - good morning
  - start my day
  - what did I miss
requires_tools:
  - gmail_search
  - web_search
  - web_fetch
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Morning Briefing

Generate a concise morning briefing for the user.

## Steps
1. Search for unread emails from the last 12 hours using gmail_search with "is:unread newer_than:12h"
2. Summarize the top 5 most important emails (sender, subject, one-line preview)
3. Use web_search to find top news headlines for today
4. Present everything in a clean, scannable format:
   - Email summary (urgent first, then actionable, then informational)
   - Top 3-5 news headlines with one-line summaries
5. End with "Anything you'd like me to dig into?"

## Success Criteria
- tool success: all tools completed without errors

## Notes
- Keep the briefing under 500 words
- Prioritize emails from known contacts over newsletters
- Don't read full email bodies unless asked — just use subjects and snippets
