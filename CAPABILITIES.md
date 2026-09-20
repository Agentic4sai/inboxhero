# inboxHero Capability Manifest

Repository: https://github.com/Agentic4sai/inboxhero

## System

- **Framework:** Moya, used for the pipeline, agent steps, branching, and observability. Python remains responsible for validation and action safety because the framework cannot enforce the inbox policy by itself.
- **Model:** `gemma4:e4b` through Ollama by default. The provider is configured through environment variables in `config.py`.
- **Messages processed:** 100 records from `data/inbox.json`.
- **Rule-handled:** 66 messages in the documented R1 run never reached a model.
- **Dispositions:** `reply`, `archive`, `defer`, `delegate`, `escalate`, and `flag`.
- **Retrieval:** same-thread walk first, followed by mailbox-wide keyword search.
- **Irreversible:** `send` and `delete`. Sending cannot be unsent; deletion would destroy inbox data and is unsupported.
- **Reversible:** `draft`, `label`, `archive`, and `defer`.
- **Gate:** both explicit approval and dry-run are supported.

## Capabilities

### R1: Zero the inbox

- **Tier:** B
- **Claim:** Assigns every inbox record exactly one disposition and reason, routing obvious messages through deterministic rules before the model.
- **Command:** `python demo.py --cap R1`
- **Observable:** Prints the rule/model split, every disposition, the final summary, and writes `state/decisions.json` and `trace.jsonl`.
- **Evidence:** [tests/test_part2.py](tests/test_part2.py), [flow.py](flow.py), [rules.py](rules.py)

### R2: Answer with evidence

- **Tier:** B
- **Claim:** Retrieves earlier same-thread evidence first, then cross-thread keyword evidence, and drafts only with authorized citations.
- **Command:** `python demo.py --cap R2 --msg m019 --query "launch date product launch event"`
- **Observable:** Prints retrieved message IDs and either a grounded draft with `evidence_ids` or a no-evidence refusal.
- **Evidence:** [retrieval.py](retrieval.py), [tests/test_part3.py](tests/test_part3.py), [demo.py](demo.py)

### R3: Gate irreversible actions

- **Tier:** C
- **Claim:** Proposes an evidence-grounded send, supports dry-run and explicit approval, writes approved mail to `outbox/`, and logs every gate decision.
- **Dry-run command:** `python demo.py --cap R3 --msg m019 --query "launch date product launch event" --dry-run`
- **Approval command:** `python demo.py --cap R3 --msg m019 --query "launch date product launch event" --approve`
- **Observable:** Prints the proposed recipient, subject, grounded body, evidence IDs, gate decision, and outcome. Dry-run creates no outbox file; approval creates exactly one `outbox/m019.json` if it does not already exist.
- **Evidence:** [actions.py](actions.py), `state/gated_actions.jsonl`, `trace.jsonl`, [tests/test_part4.py](tests/test_part4.py)

### R4: Persist standing preferences

- **Tier:** C
- **Claim:** Stores the owner's calendar preference and applies it after the process exits and restarts.
- **Commands:** `python demo.py --cap R4 --msg m041`, then `python demo.py --cap R4 --msg m043`
- **Observable:** The first command writes the no-meetings-before-11:00 rule to `state/preferences.json`; the second loads it and refuses the 9:00 AM proposal.
- **Evidence:** [memory.py](memory.py), `state/preferences.json`, `trace.jsonl`, [tests/test_part5.py](tests/test_part5.py)

## Part 4 escalation boundary

Only actions that communicate externally or destroy information require the gate. Reading mail, retrieving evidence, drafting, archiving, deferring, and logging are reversible or non-destructive, so asking for approval for each would create approval fatigue without protecting an irreversible boundary. `delete` is listed as irreversible for policy completeness but has no execution path; inboxHero refuses it and leaves the inbox unchanged.

## Current scope

Parts 2, 3, 4, and 5 are implemented as `R1`, `R2`, `R3`, and `R4`. Parts 6 and 7 still need to be implemented before this manifest can claim the complete required-six submission.
