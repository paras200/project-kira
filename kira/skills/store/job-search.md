---
name: job-search
description: Search for job listings matching criteria and save results
category: job-search
triggers:
  - find jobs
  - job search
  - job listings
  - job openings
  - hiring
  - career opportunities
requires_tools:
  - web_search
  - web_fetch
  - note_save
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Job Search

Search for job listings based on user criteria.

## Steps
1. Clarify the search criteria if not provided: role, location, remote/hybrid/onsite, tech stack
2. Use web_search with targeted queries like "{role} jobs {location} remote site:linkedin.com OR site:lever.co OR site:greenhouse.io"
3. Also search on aggregators: "{role} {location} remote jobs"
4. For the top results, use web_fetch to get more details
5. Present findings in a structured format:
   - Company name
   - Role title
   - Location / Remote status
   - Key requirements (if available)
   - Application URL
6. Save the search results as a note with tag "job-search"
7. Ask if the user wants to draft application emails for any of them

## Success Criteria
- tool success: search completed
- note_saved: results were saved

## Notes
- Focus on recent postings (last 1-2 weeks)
- Filter out staffing agencies unless the user asks for them
- If the user has preferences in USER.md, use those as defaults
