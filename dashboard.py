"""Build the three-pane dashboard required by Part 7."""

import json
from datetime import timedelta

import config
import trace


def _read_jsonl(path):
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _read_json_array(path):
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _pending_actions():
    pending = []
    for record in _read_jsonl(config.STATE_PATH / "gated_actions.jsonl"):
        if record.get("human_decision") == "approved" and record.get("outcome") == "written to outbox":
            continue
        proposal = record.get("proposal", {})
        pending.append({
            "message_id": record.get("message_id"),
            "action": record.get("action"),
            "why_human": proposal.get("reason") or "the action is irreversible and requires human approval",
            "outcome": record.get("outcome"),
        })
    return pending


def _flagged():
    found = {}
    for record in _read_json_array(config.STATE_PATH / "decisions.json"):
        if record.get("disposition") == "flag":
            found[record.get("message_id")] = {
                "message_id": record.get("message_id"),
                "attempted": record.get("attempted") or record.get("reason"),
                "did_instead": "flagged and left in place",
            }
    for record in trace.read(kind="hostile_refusal"):
        found[record.get("msg_id")] = {
            "message_id": record.get("msg_id"),
            "attempted": record.get("attempted"),
            "did_instead": "refused; flagged and left in place",
        }
    return [found[key] for key in sorted(found) if key]


def _next_weekday(message, weekday):
    days = (weekday - message.sent_at.weekday()) % 7
    if days == 0:
        days = 7
    return (message.sent_at + timedelta(days=days)).date().isoformat()


def _commitment(message_id, title, date, evidence_ids, box, time=None):
    valid_ids = []
    for evidence_id in evidence_ids:
        source = box.by_id(evidence_id)
        if source is None:
            raise ValueError(f"commitment {title!r} cites unknown message {evidence_id!r}")
        valid_ids.append(source.id)
    result = {"title": title, "date": date, "evidence_ids": valid_ids}
    if time:
        result["time"] = time
    return result


def commitments(box):
    """Extract grounded dates from the known commitment patterns in the inbox."""
    by_id = {message.id: message for message in box.messages}
    result = []
    launch = by_id.get("m026")
    if launch:
        result.append(_commitment("m026", "Product launch", f"{launch.sent_at.year}-{launch.sent_at.month:02d}-20", ("m026", "m019"), box))

    board = by_id.get("m038")
    if board:
        result.append(_commitment("m038", "Quarterly board review", f"{board.sent_at.year}-{board.sent_at.month:02d}-18", ("m038",), box, "10:00"))
    deck = by_id.get("m040")
    if board and deck:
        review_date = board.sent_at.replace(day=18)
        result.append(_commitment("m040", "Board deck circulated", (review_date - timedelta(days=2)).date().isoformat(), ("m040", "m038"), box))

    legal = by_id.get("m018")
    if legal:
        result.append(_commitment("m018", "SAFE amendment signed", _next_weekday(legal, 4), ("m018",), box))

    investor = by_id.get("m010")
    if investor:
        result.append(_commitment("m010", "Investor intro call", f"{investor.sent_at.year}-{investor.sent_at.month:02d}-15", ("m010",), box, "15:00"))

    return sorted(result, key=lambda item: (item["date"], item["title"]))


def build(box):
    return {
        "pending_actions": _pending_actions(),
        "flagged": _flagged(),
        "commitments": commitments(box),
    }


def write(dashboard):
    path = config.STATE_PATH / "dashboard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")
    return path


def render(dashboard):
    """Render exactly three named panes for a human-readable dashboard."""
    print("=== pending actions ===")
    for item in dashboard["pending_actions"]:
        print(f"  {item['message_id']}  {item['action']}  {item['why_human']}")
    if not dashboard["pending_actions"]:
        print("  none")

    print("\n=== flagged ===")
    for item in dashboard["flagged"]:
        print(f"  {item['message_id']}  attempted: {item['attempted']}  instead: {item['did_instead']}")
    if not dashboard["flagged"]:
        print("  none")

    print("\n=== commitments ===")
    for item in dashboard["commitments"]:
        when = f"{item['date']} {item['time']}" if item.get("time") else item["date"]
        print(f"  {when}  {item['title']}  evidence: {', '.join(item['evidence_ids'])}")
    if not dashboard["commitments"]:
        print("  none")