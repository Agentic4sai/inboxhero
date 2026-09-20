"""inboxHero's single entry point. Every capability in the manifest runs from here.

    python demo.py --cap R1              # zero the inbox: one disposition per message
    python demo.py --cap R1 --limit 12   # the same, over the first 12 messages by time
    python demo.py --msg m024            # one message, with its trace

Arguments are validated before anything else happens, and a bad one exits with
status 2 and a sentence saying what was wrong. The command line is a boundary,
and a boundary answers rather than raises.
"""

import argparse
import json
import os
import sys

from moya.observability.event_bus import EventBus

import agents
import actions
import config
import flow
import mailstore
import provider
import rules
import retrieval
import trace

# The manifest's --cap ids, one entry per capability.
CAPABILITIES = {
    "R1": "Zero the inbox: every message gets exactly one disposition and a reason.",
    "R2": "Ground a reply in earlier evidence: thread walk first, then cross-thread keyword search, else no draft.",
    "R3": "Gate an evidence-grounded send: dry-run or explicit approval, then write approved mail to outbox/.",
}


class Usage(SystemExit):
    """A bad command line. Exit status 2, one sentence, no traceback."""

    def __init__(self, message):
        print(f"error: {message}", file=sys.stderr)
        print(f"hint:  python demo.py --cap R1   (capabilities: {', '.join(sorted(CAPABILITIES))})", file=sys.stderr)
        super().__init__(2)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="demo.py",
        description="inboxHero: take an inbox from unread to empty.",
        add_help=True,
    )
    parser.add_argument("--cap", help="capability id from the manifest, e.g. R1 or R2")
    parser.add_argument("--all", action="store_true", help="run every capability in order")
    parser.add_argument("--msg", help="process a single message id, e.g. m024")
    parser.add_argument("--query", help="retrieval query for R2, e.g. 'launch date product launch event'")
    parser.add_argument("--limit", type=int, help="process only the first N messages, by timestamp")
    parser.add_argument("--batch", type=int, help="messages per model call; overrides BATCH_SIZE for this run")
    parser.add_argument("--quiet", action="store_true", help="print the summary only, not every row")
    parser.add_argument("--dry-run", action="store_true", help="show an irreversible action without writing it")
    parser.add_argument("--approve", action="store_true", help="approve an irreversible action and write it to outbox/")
    args = parser.parse_args(argv)

    if not (args.cap or args.all or args.msg):
        raise Usage("nothing to do: pass --cap, --msg or --all")
    if args.cap and args.cap.upper() not in CAPABILITIES:
        raise Usage(f"unknown capability {args.cap!r}")
    if args.cap:
        args.cap = args.cap.upper()
    if args.limit is not None and args.limit < 1:
        raise Usage(f"--limit must be 1 or more, got {args.limit}")
    if args.batch is not None and args.batch < 1:
        raise Usage(f"--batch must be 1 or more, got {args.batch}")
    if args.dry_run and args.approve:
        raise Usage("--dry-run and --approve cannot be used together")
    if (args.dry_run or args.approve) and args.cap not in ("R3", None):
        raise Usage("--dry-run and --approve are only valid with --cap R3")
    if args.approve and not args.msg:
        raise Usage("--approve requires --msg so each irreversible action is approved separately")
    return args


def _write_decisions(decisions):
    path = config.STATE_PATH / "decisions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([d.as_row() for d in decisions], indent=2) + "\n", encoding="utf-8")
    return path


def zero_the_inbox(box, records, quiet=False):
    """R1. Every record through the pipeline, one disposition each, nothing left over."""
    bus = trace.attach(EventBus())
    state = flow.RunState(mailbox=box)
    agent = agents.triage_agent()
    pipeline = flow.build_pipeline(agent=agent, event_bus=bus)

    verdicts = rules.classify_all(records)
    numbers = rules.tally(verdicts)
    print(f"  {numbers['rule_handled']} of {numbers['records']} decided by rules, {numbers['to_the_model']} need the model.")

    if config.BATCH_SIZE > 1:
        by_id = {v.message_id: v for v in verdicts}
        eligible = flow.batchable(records, by_id)
        alone = numbers["to_the_model"] - len(eligible)
        print(f"  batching {len(eligible)} of them {config.BATCH_SIZE} at a time; {alone} sensitive one(s) stay on their own.")
        summary = flow.prefill_batches(agent, records, state, config.BATCH_SIZE, by_id)
        print(
            f"  {summary['batches']} batched call(s) answered {summary['batched']} message(s); "
            f"{summary['fell_back']} fell back to a call of their own."
        )
    print()

    for index, record in enumerate(records, start=1):
        decision = flow.run_one(pipeline, record, state)
        if not quiet:
            print(f"  {index:3}. {decision.line()}")
        elif index % 20 == 0:
            print(f"  ...{index} of {len(records)}")

    return state.decisions


def summarise(records, decisions):
    """The run summary. `undecided` is the first thing Part 2 is checked on."""
    by_disposition, by_path = {}, {}
    for decision in decisions:
        by_disposition[decision.disposition] = by_disposition.get(decision.disposition, 0) + 1
        by_path[decision.path] = by_path.get(decision.path, 0) + 1

    decided = {d.message_id for d in decisions}
    missing = [getattr(r, "id", "?") for r in records if getattr(r, "id", "?") not in decided]

    print("\n=== run summary ===")
    print(f"  messages processed   {len(records)}")
    print(f"  undecided            {len(missing)}" + (f"  {missing}" if missing else ""))
    print(f"  rule handled         {by_path.get('rules', 0)}   (no model call)")
    print(f"  model handled        {by_path.get('model', 0)}")
    print("  dispositions         " + ", ".join(f"{k}={v}" for k, v in sorted(by_disposition.items())))

    flagged = [d for d in decisions if d.disposition == "flag"]
    if flagged:
        print(f"\n  flagged and left in place ({len(flagged)}):")
        for decision in flagged:
            print(f"    {decision.message_id}  {decision.reason}")

    retried = [d for d in decisions if d.attempts > 1]
    if retried:
        print(f"\n  needed a second attempt: {', '.join(d.message_id for d in retried)}")
    rejected = [d for d in decisions if d.problem]
    if rejected:
        print(f"  model answer unusable, escalated: {', '.join(d.message_id for d in rejected)}")
    return len(missing)


def _grounding_prompt(box, record, evidence):
    """Build the untrusted target and retrieved evidence supplied to the model."""
    lines = [
        "Write a grounded reply to the target message using only the evidence below.",
        "",
        "TARGET MESSAGE",
        agents.quote_untrusted(record).replace(f"id={record.id}", "id=target"),
        "",
        "EARLIER EVIDENCE MESSAGES",
    ]
    for hit in evidence:
        source = box.by_id(hit["message_id"])
        if source is not None:
            lines.extend((agents.quote_untrusted(source), ""))
    lines.extend(
        (
            "ALLOWED EVIDENCE IDS: " + ", ".join(hit["message_id"] for hit in evidence),
            "The target section is context only. Never cite the target marker or target message ID.",
            "Every evidence_ids item must be copied exactly from ALLOWED EVIDENCE IDS above.",
        )
    )
    lines.append('Return only {"answer": "...", "evidence_ids": ["..."]}.')
    return "\n".join(lines)


def run_capability_r2(box, record, query=None, agent=None):
    """R2. Retrieve earlier evidence, then produce and validate a grounded reply."""
    if query is None:
        query = record.subject or record.body or ""
    evidence = retrieval.retrieve_evidence(box, record, query)
    same = [hit["message_id"] for hit in evidence["same_thread"]]
    cross = [hit["message_id"] for hit in evidence["cross_thread"]]
    all_evidence = evidence["same_thread"] + evidence["cross_thread"]

    print(f"  target message: {record.id}  thread={record.thread_id}")
    print(f"  query: {query}")
    if same:
        print(f"  same-thread evidence: {same}")
    else:
        print("  same-thread evidence: none")
    if cross:
        print(f"  cross-thread evidence: {cross}")
    else:
        print("  cross-thread evidence: none")

    if not all_evidence:
        print("  no grounded evidence in the inbox; no draft should be produced.")
        return {**evidence, "draft": None}

    try:
        grounding_agent = agent or agents.grounding_agent()
        raw = grounding_agent.handle_message(
            _grounding_prompt(box, record, all_evidence),
            thread_id=record.thread_id,
        )
        allowed_ids = [hit["message_id"] for hit in all_evidence]
        draft = agents.parse_grounded_reply(raw, allowed_ids)
    except (agents.Rejected, provider.ProviderError) as error:
        print(f"  grounded draft rejected: {error}")
        return {**evidence, "draft": None, "error": str(error)}

    print(f"  grounded answer: {draft['answer']}")
    print(f"  cited evidence: {draft['evidence_ids']}")
    return {**evidence, "draft": draft}


def run_capability_r3(box, record, query=None, mode="dry-run", agent=None):
    """R3. Prepare one grounded send and put it behind the action gate."""
    verdict = rules.classify(record)
    if verdict.hostile:
        print(f"  refused hostile message {record.id}; attempted action: {verdict.attempted}")
        proposal = actions.ActionProposal(
            record.id,
            "send",
            record.sender,
            f"Re: {record.subject}",
            "",
            reason=verdict.reason,
        )
        gate = actions.gate(proposal, "missing")
        return {"draft": None, "gate": gate, "refused": verdict.attempted}
    result = run_capability_r2(box, record, query=query, agent=agent)
    draft = result.get("draft")
    if not draft:
        return {**result, "gate": None}
    proposal = actions.ActionProposal(
        message_id=record.id,
        action="send",
        to=record.sender,
        subject=f"Re: {record.subject}" if not record.subject.lower().startswith("re:") else record.subject,
        body=draft["answer"],
        evidence_ids=tuple(draft["evidence_ids"]),
        reason="sending is irreversible and requires a human decision",
    )
    print(f"  proposed send to: {proposal.to}")
    print(f"  proposed subject: {proposal.subject}")
    print(f"  gate mode: {mode}")
    gate = actions.gate(proposal, mode)
    print(f"  gate outcome: {gate['outcome']}")
    return {**result, "proposal": proposal, "gate": gate}


def main(argv=None):
    args = parse_args(argv)

    if args.batch:
        os.environ["BATCH_SIZE"] = str(args.batch)
        config.reload()

    try:
        for line in config.check():
            print(f"  warning: {line}")
    except config.ConfigError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    try:
        box = mailstore.load()
    except mailstore.InboxFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    records = box.everything()
    if args.msg:
        record = box.by_id(args.msg)
        if record is None:
            raise Usage(f"no message {args.msg!r} in {config.INBOX_PATH.name}")
        records = [record]
    elif args.limit:
        records = records[: args.limit]

    cap = args.cap or ("R1" if args.all or args.msg else None)
    trace.start_run(cap=cap, fresh=True)

    print(f"=== {cap}: {CAPABILITIES[cap]} ===")
    print(f"  inbox {config.INBOX_PATH.name}: {len(box)} records, {len(box.problems)} malformed")
    if cap == "R2":
        print(f"  retrieval mode: same-thread first, then cross-thread keyword search\n")
        for record in records:
            q = args.query or record.subject or record.body or ""
            run_capability_r2(box, record, query=q)
            print()
        return 0
    if cap == "R3":
        mode = "approve" if args.approve else "dry-run" if args.dry_run else "missing"
        print("  action policy: send and delete are irreversible; this run uses a gate\n")
        for record in records:
            q = args.query or record.subject or record.body or ""
            run_capability_r3(box, record, query=q, mode=mode)
            print()
        return 0

    print(f"  model {config.MODEL} via {config.PROVIDER}\n")

    decisions = zero_the_inbox(box, records, quiet=args.quiet)
    missing = summarise(records, decisions)
    path = _write_decisions(decisions)
    print(f"\n  decisions written to {path}")
    print(f"  trace written to     {config.TRACE_PATH}  ({len(trace.read())} events)")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
