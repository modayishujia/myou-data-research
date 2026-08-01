#!/usr/bin/env python3
"""JSON-based data store for research topics. Manages incremental data collection and evolution tracking."""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path

# Default data directory - can be overridden via environment variable
DATA_DIR = os.environ.get("RESEARCH_DATA_DIR", os.path.expanduser("~/.local/share/data-research"))


def get_topic_dir(topic_id: str) -> str:
    """Get the directory path for a research topic."""
    return os.path.join(DATA_DIR, topic_id)


def sanitize_topic_id(topic: str) -> str:
    """Convert a topic string to a safe directory name."""
    # Use first 50 chars + hash suffix for uniqueness
    clean = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic[:50]).strip()
    clean = clean.replace(" ", "-").lower()
    suffix = hashlib.md5(topic.encode()).hexdigest()[:8]
    return f"{clean}-{suffix}" if clean else f"topic-{suffix}"


def init_topic(topic: str, keywords: list[str] = None, sources: list[str] = None) -> dict:
    """Initialize a new research topic. Returns the topic metadata."""
    topic_id = sanitize_topic_id(topic)
    topic_dir = get_topic_dir(topic_id)
    os.makedirs(topic_dir, exist_ok=True)

    meta = {
        "topic_id": topic_id,
        "topic": topic,
        "keywords": keywords or [],
        "sources": sources or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "collection_count": 0,
        "status": "active",
    }

    meta_path = os.path.join(topic_dir, "meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Initialize empty collections
    for fname in ["entries.json", "evolution.json", "signals.json"]:
        fpath = os.path.join(topic_dir, fname)
        if not os.path.exists(fpath):
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump([], f)

    return meta


def load_topic_meta(topic_id: str) -> dict:
    """Load topic metadata."""
    meta_path = os.path.join(get_topic_dir(topic_id), "meta.json")
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_topic_meta(topic_id: str, meta: dict):
    """Save topic metadata."""
    meta_path = os.path.join(get_topic_dir(topic_id), "meta.json")
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def add_entries(topic_id: str, entries: list[dict]) -> int:
    """Add data entries to a topic. Returns count of new entries.
    
    Each entry should have:
        - source: str (e.g., "web_search", "social_media", "comment_section")
        - content: str (the actual text content)
        - url: str (optional, source URL)
        - timestamp: str (ISO format, optional - defaults to now)
        - metadata: dict (optional, extra fields like author, platform, etc.)
    """
    entries_path = os.path.join(get_topic_dir(topic_id), "entries.json")
    with open(entries_path, "r", encoding="utf-8") as f:
        existing = json.load(f)

    # Deduplicate by content hash
    existing_hashes = set()
    for e in existing:
        h = hashlib.md5(e.get("content", "").encode()).hexdigest()
        existing_hashes.add(h)

    new_count = 0
    now = datetime.now(timezone.utc).isoformat()
    for entry in entries:
        entry.setdefault("timestamp", now)
        entry.setdefault("collected_at", now)
        h = hashlib.md5(entry.get("content", "").encode()).hexdigest()
        if h not in existing_hashes:
            existing_hashes.add(h)
            existing.append(entry)
            new_count += 1

    with open(entries_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    # Update meta
    meta = load_topic_meta(topic_id)
    meta["collection_count"] = len(existing)
    save_topic_meta(topic_id, meta)

    return new_count


def add_evolution_point(topic_id: str, point: dict):
    """Record an evolution observation point.
    
    Each point should have:
        - timestamp: str (ISO format)
        - phase: str (e.g., "emergence", "growth", "peak", "decline", "stable")
        - summary: str (what changed)
        - key_changes: list[str]
        - sentiment_shift: str (optional, e.g., "positive -> negative")
        - new_keywords: list[str] (optional)
        - notable_events: list[str] (optional)
    """
    evo_path = os.path.join(get_topic_dir(topic_id), "evolution.json")
    with open(evo_path, "r", encoding="utf-8") as f:
        points = json.load(f)

    point.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    points.append(point)

    with open(evo_path, "w", encoding="utf-8") as f:
        json.dump(points, f, ensure_ascii=False, indent=2)


def add_signal(topic_id: str, signal: dict):
    """Record a notable signal or insight.
    
    Each signal should have:
        - timestamp: str (ISO format)
        - type: str (e.g., "sentiment_shift", "keyword_emergence", "volume_spike", "narrative_change")
        - severity: str ("low", "medium", "high", "critical")
        - description: str
        - evidence: list[str] (supporting data points)
        - recommended_action: str (optional)
    """
    sig_path = os.path.join(get_topic_dir(topic_id), "signals.json")
    with open(sig_path, "r", encoding="utf-8") as f:
        signals = json.load(f)

    signal.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    signals.append(signal)

    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(signals, f, ensure_ascii=False, indent=2)


def get_all_entries(topic_id: str) -> list[dict]:
    """Get all entries for a topic, sorted by timestamp."""
    entries_path = os.path.join(get_topic_dir(topic_id), "entries.json")
    with open(entries_path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    entries.sort(key=lambda x: x.get("timestamp", ""))
    return entries


def get_entries_since(topic_id: str, since_iso: str) -> list[dict]:
    """Get entries collected after a given timestamp."""
    all_entries = get_all_entries(topic_id)
    return [e for e in all_entries if e.get("timestamp", "") > since_iso]


def get_evolution(topic_id: str) -> list[dict]:
    """Get all evolution points for a topic."""
    evo_path = os.path.join(get_topic_dir(topic_id), "evolution.json")
    with open(evo_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_signals(topic_id: str) -> list[dict]:
    """Get all signals for a topic, sorted by severity then time."""
    sig_path = os.path.join(get_topic_dir(topic_id), "signals.json")
    with open(sig_path, "r", encoding="utf-8") as f:
        signals = json.load(f)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    signals.sort(key=lambda x: (severity_order.get(x.get("severity", "low"), 99), x.get("timestamp", "")))
    return signals


def list_topics() -> list[dict]:
    """List all research topics."""
    topics = []
    if not os.path.exists(DATA_DIR):
        return topics
    for name in os.listdir(DATA_DIR):
        meta_path = os.path.join(DATA_DIR, name, "meta.json")
        if os.path.isfile(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                topics.append(json.load(f))
    topics.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return topics


def get_topic_summary(topic_id: str) -> dict:
    """Get a complete summary of a topic for dashboard rendering."""
    meta = load_topic_meta(topic_id)
    entries = get_all_entries(topic_id)
    evolution = get_evolution(topic_id)
    signals = get_signals(topic_id)

    # Source distribution
    source_counts = {}
    for e in entries:
        src = e.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    # Time distribution (by day)
    daily_counts = {}
    for e in entries:
        day = e.get("timestamp", "")[:10]
        if day:
            daily_counts[day] = daily_counts.get(day, 0) + 1

    return {
        "meta": meta,
        "entry_count": len(entries),
        "evolution_count": len(evolution),
        "signal_count": len(signals),
        "source_distribution": source_counts,
        "daily_distribution": daily_counts,
        "entries": entries,
        "evolution": evolution,
        "signals": signals,
    }


# CLI interface
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: data_store.py <command> [args...]")
        print("Commands: init, add, evolution, signal, list, summary, entries")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        topic = sys.argv[2]
        keywords = sys.argv[3].split(",") if len(sys.argv) > 3 else []
        result = init_topic(topic, keywords)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "list":
        topics = list_topics()
        print(json.dumps(topics, ensure_ascii=False, indent=2))

    elif cmd == "summary":
        topic_id = sys.argv[2]
        summary = get_topic_summary(topic_id)
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    elif cmd == "entries":
        topic_id = sys.argv[2]
        entries = get_all_entries(topic_id)
        print(json.dumps(entries, ensure_ascii=False, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
