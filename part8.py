"""Custom Part 8 capabilities: lookup, thread analysis, and follow-up planning."""

import json
import re
from datetime import datetime

import actions
import config
import trace


def unread_from(box, sender=None):
    """Tier A: list unread messages, optionally restricted to one sender."""
    sender = sender.lower() if sender else None
    return [
        {
            "message_id": message.id,
            "sender": message.sender,
            "timestamp": message.timestamp,
            "subject": message.subject,
            "thread_id": message.thread_id,
        }
        for message in sorted(box.messages, key=lambda item: item.sent_at)
        if message.unread and (sender is None or message.sender == sender)
    ]


def _question_sentences(text):
    return [sentence.strip() for sentence in re.findall(r"[^?]+\?", text.replace("\n", " "))]


def thread_open_questions(box, message):
    """Tier B: inspect one complete thread and expose question candidates."""
    thread = box.thread(message.thread_id)
    questions = []
    for item in thread:
        for sentence in _question_sentences(item.body):
            questions.append({"message_id": item.id, "text": sentence.rstrip("?") + "?"})
    latest = thread[-1] if thread else message
    return {
        "message_id": message.id,
        "thread_id": message.thread_id,
        "messages": [
            {"message_id": item.id, "timestamp": item.timestamp, "sender": item.sender, "subject": item.subject}
            for item in thread
        ],
        "open_questions": questions,
        "latest_message_id": latest.id,
    }


def _has_later_reply(box, message):
    return any(item.sent_at > message.sent_at and item.sender != config.OWNER for item in box.thread(message.thread_id))


def follow_up_candidates(box, now=None):
    """Tier C: plan human-gated follow-ups for unanswered owner messages."""
    if now is None:
        now = max((message.sent_at for message in box.messages), default=datetime.now())
    candidates = []
    for message in box.messages:
        if not message.from_owner or message.to == config.OWNER or _has_later_reply(box, message):
            continue
        days_waiting = max(0, (now - message.sent_at).days)
        if days_waiting < 3:
            continue
        proposal = actions.ActionProposal(
            message_id=message.id,
            action="send",
            to=message.to,
            subject=f"Re: {message.subject}" if not message.subject.lower().startswith("re:") else message.subject,
            body=f"Following up on my message: {message.subject}. Do you have an update when you have a moment?",
            evidence_ids=(message.id,),
            reason="follow-up is an external send and requires human approval",
        )
        candidates.append({"message_id": message.id, "days_waiting": days_waiting, "proposal": proposal})
    return candidates


def run_follow_ups(box, mode="dry-run"):
    """Create and gate each follow-up proposal, returning JSON-safe records."""
    results = []
    for candidate in follow_up_candidates(box):
        proposal = candidate["proposal"]
        gate = actions.gate(proposal, mode)
        result = {
            "message_id": candidate["message_id"],
            "days_waiting": candidate["days_waiting"],
            "draft": proposal.body,
            "gate": gate,
        }
        trace.event("part8_follow_up", cap="X3", msg_id=proposal.message_id, outcome=gate["outcome"])
        results.append(result)
    return results


def print_json(value):
    print(json.dumps(value, indent=2))
