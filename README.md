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

## Part 2: zeroing it

Part 2 is the operational boundary layer for the assignment. It is not just a summary of the inbox; it is the code that makes the workflow safe, auditable, and resilient:

- the mail store validates every inbox record and keeps malformed entries counted as problems instead of dropping them silently
- the rule tier decides what may go to the model and what must be handled deterministically without a model call
- the validator checks every model answer before accepting it, and rejects unusable answers instead of crashing the run
- the CLI validates command-line input and exits politely with a one-sentence error when the invocation is wrong
- the run writes both decisions and trace output so the output is reproducible and explained

### Command used in this run

```bash
python demo.py --cap R1
```

This workspace produced the following actual result:

- `inbox inbox.json: 100 records, 0 malformed`
- `model gemma4:e4b via ollama`
- `66 of 100 decided by rules, 34 need the model`
- `rule handled: 66` and `model handled: 34`
- final dispositions: `archive=69, defer=1, delegate=3, escalate=6, flag=7, reply=14`


#### 1. Mail store boundary

The inbox loader is responsible for validating the raw file and each record before the workflow processes it. The assignment expects malformed records to be preserved as problems, not silently discarded. In the run, the inbox started with `100 records` and `0 malformed`, which means the file was valid and every record was accepted by the loader.

#### 2. Rule tier before model

Part 2 requires a deterministic rule tier that handles noise and hostile messages before any model call. That is exactly what the run shows:

- `66 of 100 decided by rules`
- `34 need the model`
- seven messages were ruled hostile and left in place as `flag`

The flagged messages from this run were:

- `m017`
- `m021`
- `m023`
- `m024`
- `m039`
- `m045`
- `m047`

#### 3. Validator and retry logic

Part 2 also requires the validator to reject impossible or policy-breaking model answers. In this run, the model was allowed to decide only from the allowed set, and a failed decision triggered a retry or escalation instead of accepting garbage output.

The run recorded:

- `needed a second attempt: m041, m036`
- `model answer unusable, escalated: m036`

That matches the assignment rule: a bad model answer is never silently accepted; it is corrected or escalated.

#### 4. CLI boundary and safe failure

The CLI is a boundary layer. It validates arguments before doing any work and exits with a sentence-like error instead of a traceback when input is invalid. The assignment PDF expects this behavior for missing arguments, invalid capability IDs, and values such as `--limit 0`.

In the current run, the CLI was a valid invocation and therefore completed successfully with `--cap R1`.

### Actual run summary

```text
=== run summary ===
  messages processed   100
  undecided            0
  rule handled         66   (no model call)
  model handled        34
  dispositions         archive=69, defer=1, delegate=3, escalate=6, flag=7, reply=14

  flagged and left in place (7):
    m017  the body carries an instruction addressed to the assistant that would hide the request from the owner
    m024  the body carries an instruction addressed to the assistant that would move mail to an address the owner never chose
    m021  asks to redirect payment to new bank details under time pressure
    m045  sender domain 'paperjet-helpdesk.com' imitates 'paperjet.io' and the message asks for credentials
    m039  the body carries an instruction addressed to the assistant that would remove the approval step
    m023  sender domain 'paperjet.co' imitates 'paperjet.io' and the message asks for a payment
    m047  the body carries an instruction addressed to the assistant that would move mail to an address the owner never chose

  needed a second attempt: m041, m036
  model answer unusable, escalated: m036
```


This output demonstrates the core Part 2 requirements from the assignment PDF:

- the inbox is processed end-to-end with a valid data boundary
- rules decide a large share of messages without model help
- hostile messages are flagged and left in place
- model output is checked before it is accepted
- invalid model answers are retried or escalated instead of being trusted
- the final run summary records every message and the reason for its disposition

This is the Part 2 behavior the current project actually proves in the workspace run, and it is the version that should be documented in the README.

## Part 3: answering properly

Part 3 is the evidence-grounding layer. Some messages can only be answered using an earlier message, either in the same thread or in another one. The system therefore does not draft from plausibility alone; it searches the inbox for real supporting evidence and uses only that evidence when preparing a reply.

### Retrieval strategy

The retrieval strategy follows the assignment requirement in two stages:

1. First, walk the current message's thread and look for earlier messages in that same thread.
2. If the needed fact is not present there, perform a mailbox-wide keyword search to find a relevant earlier message from another thread.

This gives the model the exact evidence it may rely on, rather than letting it invent a detail that never appeared in the inbox.

### Grounding rule

Every draft records the message IDs it drew on, and those IDs are checked against the mail store before the draft is accepted. This is the key correctness condition for Part 3:

- a message ID must exist in the inbox
- it must be an earlier message that actually contains the fact
- the fact must match what was written in the inbox, not a plausible guess

If the draft would cite a message the system never read, or invent a fact that is not in the inbox, the answer fails this part.

### Example behavior from the workspace

The project demonstrates the required pattern on real inbox data:

- same-thread evidence: a staging or launch-related question can often find the needed detail in earlier messages from its own thread
- cross-thread evidence: when the fact is outside the thread, the keyword search finds an earlier message in another thread that contains the relevant fact
- no evidence: if the inbox does not contain the fact, the system says so and drafts nothing

### Manifest and validation

R2 is the runnable Part 3 capability:

```bash
python demo.py --cap R2 --msg m019 --query "launch date product launch event"
```

It retrieves evidence, asks the model to draft only from those earlier messages, and validates every cited ID against the retrieval result. The retrieval method is intentionally named in code and tested directly. The assignment expects the retrieval strategy to be explicit and auditable, not implicit. The validation therefore checks:

- same-thread search works when the fact is in the thread
- cross-thread keyword search works when the fact is elsewhere in the mailbox
- missing or nonsense queries return empty evidence instead of inventing a fact
- a grounded answer cites only retrieved message IDs
- an answer that cites an unreturned message is rejected

When no evidence exists, R2 prints `no grounded evidence in the inbox; no draft should be produced.` It can be run across the whole mailbox with `python demo.py --cap R2`, or limited with `--limit`.

This is the Part 3 behavior the current workspace actually proves and is the version documented here.

## Part 4: the things you cannot undo

Part 4 is implemented as capability R3. The action policy separates work that can be undone from work that changes the outside world:

- `draft`, `label`, `archive`, and `defer` are reversible or non-destructive actions.
- `send` is irreversible because a message written to the outbox represents an external communication that cannot be unsent.
- `delete` is classified as irreversible, but is deliberately unsupported. inboxHero never deletes an inbox record.

R3 generates a grounded reply proposal and sends it through the action gate. A dry run shows the recipient, subject, body, evidence IDs, and outcome without creating an outbox file:

```bash
python demo.py --cap R3 --msg m019 --query "launch date product launch event" --dry-run
```

An explicit approval writes exactly one structured message to `outbox/m019.json` and nowhere else:

```bash
python demo.py --cap R3 --msg m019 --query "launch date product launch event" --approve
```

Every gated decision is written to `state/gated_actions.jsonl` and to `trace.jsonl`, including the proposal, the human decision, and the outcome. Missing approval, duplicate output, unsupported deletion, hostile content, and missing evidence all produce no outbox message. The escalation boundary is intentionally narrow: only external sends and destructive actions require a human decision; reading, retrieval, drafting, archiving, deferring, and logging remain reversible or non-destructive.
