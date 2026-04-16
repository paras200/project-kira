---
name: email-triage
description: Triage inbox — check unread emails, flag urgent ones, summarize the rest
category: email
triggers:
  - check email
  - check my email
  - inbox
  - unread emails
  - morning emails
  - email triage
requires_tools:
  - gmail_search
  - gmail_read
  - gmail_label
created_by: manual
success_rate: 1.0
use_count: 0
success_count: 0
version: 1
status: active
---

# Email Triage

Triage the user's inbox by checking unread emails and organizing them.

## Steps
1. Search for unread emails: use gmail_search with query "is:unread"
2. For each email, note the sender, subject, and preview
3. Categorize emails:
   - **Urgent**: from known contacts, about deadlines or time-sensitive matters
   - **Actionable**: needs a reply or action
   - **Informational**: newsletters, notifications, updates
4. Star urgent emails using gmail_label with add_labels ["STARRED"]
5. Present a summary to the user organized by category
6. Ask if they want to read any specific email, draft replies, or archive

## Success Criteria
- emails_found: at least one search was performed
- tool success: all gmail tools completed without errors

## Known Pitfalls
- Don't mark emails as read unless the user asks to read them
- Don't archive or delete without explicit confirmation
- Keep the summary concise — just sender, subject, and one-line preview
