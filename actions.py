"""Action classification and the only boundary that can write an outbox message."""

import json
from dataclasses import dataclass
from pathlib import Path

import config
import trace

REVERSIBLE = frozenset(("draft", "label", "archive", "defer"))
IRREVERSIBLE = frozenset(("send", "delete"))


@dataclass(frozen=True)
class ActionProposal:
    message_id: str
    action: str
    to: str
    subject: str
    body: str
    evidence_ids: tuple = ()
    reason: str = ""

    def as_dict(self):
        return {
            "message_id": self.message_id,
            "action": self.action,
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "evidence_ids": list(self.evidence_ids),
            "reason": self.reason,
        }


def action_type(action):
    if action in REVERSIBLE:
        return "reversible"
    if action in IRREVERSIBLE:
        return "irreversible"
    raise ValueError(f"unknown action {action!r}")


def _gate_log(record):
    path = config.STATE_PATH / "gated_actions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return path


def _record_gate(proposal, human_decision, outcome, outbox_path=None):
    record = {
        "message_id": proposal.message_id,
        "action": proposal.action,
        "proposal": proposal.as_dict(),
        "human_decision": human_decision,
        "outcome": outcome,
    }
    if outbox_path:
        record["outbox_path"] = str(Path("outbox") / Path(outbox_path).name)
    _gate_log(record)
    trace.event("gate", **record)
    return record


def gate(proposal, mode):
    """Apply the irreversible-action gate.

    Only ``dry-run`` and ``approve`` may reach this function for a send. There
    is deliberately no delete implementation: classifying it as irreversible
    does not grant any caller a destructive operation.
    """
    kind = action_type(proposal.action)
    if kind == "reversible":
        return _record_gate(proposal, "not_required", "reversible action recorded")
    if proposal.action == "delete":
        return _record_gate(proposal, "refused", "delete is unsupported and was not performed")
    if mode not in ("dry-run", "approve"):
        return _record_gate(proposal, "missing", "send refused: use --dry-run or --approve")
    if mode == "dry-run":
        return _record_gate(proposal, "dry-run", "not written to outbox")

    outbox = config.ROOT / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"{proposal.message_id}.json"
    if path.exists():
        return _record_gate(proposal, "approved", "send refused: outbox file already exists", path)
    payload = {
        "message_id": proposal.message_id,
        "to": proposal.to,
        "subject": proposal.subject,
        "body": proposal.body,
        "evidence_ids": list(proposal.evidence_ids),
        "approved": True,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return _record_gate(proposal, "approved", "written to outbox", path)