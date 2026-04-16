---
name: research-topic
description: Research a topic using web search and summarize findings
category: research
triggers:
  - research
  - look up
  - find out about
  - what is
  - tell me about
  - summarize
requires_tools:
  - web_search
  - web_fetch
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Research a Topic

Perform web research on a given topic and deliver a concise summary.

## Steps
1. Use web_search to find the most relevant results (5-8 results)
2. Use web_fetch on the top 2-3 most relevant URLs to get full content
3. Synthesize the information into a clear summary with:
   - Key facts and findings
   - Different perspectives if applicable
   - Sources cited
4. Save the research as a note using note_save with appropriate tags

## Success Criteria
- tool success: all search and fetch tools completed
- note_saved: research was saved to notes

## Notes
- Always cite sources with URLs
- If results are contradictory, present both sides
- Keep the summary focused — don't dump raw web content
