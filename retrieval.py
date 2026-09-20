import re
import sqlite3

_STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "being",
    "by", "for", "from", "has", "have", "how", "if", "in", "is", "it",
    "its", "no", "not", "of", "on", "or", "our", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "us",
    "was", "we", "were", "what", "when", "where", "which", "who", "why",
    "with", "you", "your"
}


def _normalize_tokens(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [token for token in text.split() if token and token not in _STOPWORDS]


def thread_walk(box, message, keywords):
    """Return earlier messages in this same thread whose text matches the keywords."""
    if not message:
        return []
    prior = box.earlier_in_thread(message)
    hits = []
    for msg in prior:
        text = (msg.subject + " " + msg.body).lower()
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        if score > 0:
            hits.append({
                "message_id": msg.id,
                "thread_id": msg.thread_id,
                "score": score,
                "text": msg.body,
            })
    return sorted(hits, key=lambda item: item["message_id"])


def _fts_connect():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(message_id, thread_id, subject, body)")
    return conn


def _plain_text_keyword_search(box, message, tokens):
    """Fallback when FTS misses cross-thread evidence: rank by token overlap."""
    scored = []
    for msg in box.messages:
        if msg.id == getattr(message, "id", None):
            continue
        if message is not None and msg.sent_at >= message.sent_at:
            continue
        text = (msg.subject + " " + msg.body).lower()
        score = sum(1 for token in tokens if token in text)
        if score > 0:
            scored.append({
                "message_id": msg.id,
                "thread_id": msg.thread_id,
                "subject": msg.subject,
                "body": msg.body,
                "score": score,
            })
    return [
        {
            "message_id": item["message_id"],
            "thread_id": item["thread_id"],
            "subject": item["subject"],
            "body": item["body"],
        }
        for item in sorted(scored, key=lambda x: (-x["score"], x["message_id"]))[:10]
    ]


def keyword_search(box, message, query):
    """Search the whole mailbox with SQLite FTS for relevant terms.

    `message` is included for thread context only; the search itself is across all messages.
    """
    if not query:
        return []
    tokens = [t for t in _normalize_tokens(query) if len(t) > 2]
    if len(tokens) < 2:
        return []

    q = " OR ".join(f'"{t}"' for t in tokens)
    conn = _fts_connect()
    for msg in box.messages:
        conn.execute(
            "INSERT INTO messages_fts(message_id, thread_id, subject, body) VALUES (?, ?, ?, ?)",
            (msg.id, msg.thread_id, msg.subject, msg.body),
        )
    conn.commit()
    rows = conn.execute(
        "SELECT message_id, thread_id, subject, body FROM messages_fts WHERE messages_fts MATCH ? ORDER BY rank LIMIT 20",
        (q,),
    ).fetchall()
    conn.close()

    results = []
    for message_id, thread_id, subject, body in rows:
        if message_id == getattr(message, "id", None):
            continue
        candidate = box.by_id(message_id)
        if message is not None and (candidate is None or candidate.sent_at >= message.sent_at):
            continue
        results.append({
            "message_id": message_id,
            "thread_id": thread_id,
            "subject": subject,
            "body": body,
        })

    if not results:
        return _plain_text_keyword_search(box, message, tokens)
    return results


def retrieve_evidence(box, message, query):
    """Run thread-walk first, then FTS search across the mailbox.

    Returns a dict with `same_thread` and `cross_thread` evidence.
    """
    keywords = [t for t in _normalize_tokens(query) if len(t) > 2]
    same_thread = thread_walk(box, message, keywords) if keywords else []
    cross_thread = keyword_search(box, message, " ".join(keywords)) if len(keywords) >= 2 else []
    return {
        "same_thread": same_thread,
        "cross_thread": cross_thread,
    }
