# inboxHero

Repository:https://github.com/Agentic4sai/inboxhero

An agentic workflow that processes `data/inbox.json` from unread to empty. Each message must receive exactly one disposition and one reason, reversible work is completed in place, irreversible actions pass through a validation gate, and hostile content is rejected and reported.

## Part 1: what is in the inbox

Read this in full before writing any code. `data/inbox.json` is the assignment input file, copied unchanged.

**Messages processed: 100** (all records in the file, not just the 77 unread ones).

### Assumptions about the data format

- The file is a top-level JSON array containing 100 objects, not a dictionary. Every record has exactly eight keys: `id`, `thread_id`, `from`, `to`, `subject`, `timestamp`, `body`, and `unread`. All values are strings except `unread`, which is a boolean. No field is empty. The loader still validates every record and escalates malformed input instead of crashing.
- Message IDs run from `m001` through `m119` with 19 gaps, and the file is not sorted by `id`. Messages are processed in timestamp order.
- Timestamps are ISO 8601 without timezone offsets (for example, `2026-09-02T09:12:00`), spanning 2 to 9 September 2026, and are treated as the owner's local time. Dates mentioned inside bodies such as "the 20th" or "Friday" have no month attached, so they must be resolved relative to the message timestamp.
- `to` is a single email address string. There is no `CC` field, so the system applies a "CC someone" preference to the recipients of the drafted reply.
- The file mixes incoming and outgoing mail. Four messages come from the owner, `sam@paperjet.io` (m003 and m044 to colleagues, m039 and m041 to self), so a sender matching the owner's address is not proof that the owner authored the message.
- There are 88 threads in total, but only three have more than one message: `t-api` (4), `t-launch` (9), and `t-invest` (2). Following only thread context is insufficient for cross-thread requests such as m019, so keyword search is also required.
- There is no attachments field. When a body references an attachment, it means a portal or similar mechanism exists; the system never claims to have read an attachment.
- Four bodies span multiple lines (m017, m021, m024, m047). Quoted text prefixed with `>` is still message content and remains untrusted.
- `paperjet.io` is the owner's trusted domain. Lookalike domains such as `paperjet.co` and `paperjet-helpdesk.com` are treated as fraud only when paired with urgency and a request for money, credentials, or a link. The board's `paperjet-board.org` must therefore not be misclassified.

### First design decision: what needs a model and what does not

| Tier | Messages | Count |
| --- | --- | --- |
| Rules, no model: noise | receipts, newsletters, notifications, alerts (m062 to m116); internal automated notices (m117 to m119); automated "no action needed" mail (m049, m053, m057); the dentist reminder m061, deferred with its slot recorded | 62 |
| Rules, no model: hostile | instructions addressed to the assistant (m017, m024, m047); phishing and social engineering (m021, m023, m045); a spoofed "assistant settings" note from the owner's own address (m039) | 7 |
| Model, workflow-shaped: classify, retrieve, draft, validate | the staging thread (m001, m003, m005, m008); the launch thread with the real ask buried in m030 (m026 to m036); board review and deck (m038, m040); legal (m018, m048, m055); venue m019, press m046, candidate m042, the owner's own unanswered m044, PTO m059, coffee m051, and the ambiguous m012 | 25 |
| Model, agent-shaped: memory, planning, human in the loop | scheduling requests that must be checked against the calendar rule and each other (m010, m043, m013, m016); standing preferences to record (m015, m041) | 6 |

Roughly 69 messages never require a model call. The exact `rule_handled` value is reported by the run and included in the manifest.
