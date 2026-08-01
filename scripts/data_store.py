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


# === 时间对比引擎 ===

def snapshot_topic(topic_id: str) -> dict:
    """Save a snapshot of current state for delta comparison."""
    topic_dir = get_topic_dir(topic_id)
    entries = get_all_entries(topic_id)
    signals = get_signals(topic_id)

    # Extract current keywords and sentiment distribution
    keyword_freq = {}
    sentiment_dist = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    source_counts = {}

    for e in entries:
        # Keywords from content (simple word extraction)
        content = e.get("content", "")
        for word in content.split():
            if len(word) >= 2:
                keyword_freq[word] = keyword_freq.get(word, 0) + 1

        # Sentiment
        sent = (e.get("metadata") or {}).get("sentiment", "neutral")
        sentiment_dist[sent] = sentiment_dist.get(sent, 0) + 1

        # Source
        src = e.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    # Top keywords
    top_keywords = sorted(keyword_freq.items(), key=lambda x: -x[1])[:30]

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(entries),
        "signal_count": len(signals),
        "source_distribution": source_counts,
        "sentiment_distribution": sentiment_dist,
        "top_keywords": dict(top_keywords),
        "content_hashes": [hashlib.md5(e.get("content", "").encode()).hexdigest() for e in entries],
    }

    # Save snapshot
    snap_path = os.path.join(topic_dir, "snapshots.json")
    snapshots = []
    if os.path.exists(snap_path):
        with open(snap_path, "r", encoding="utf-8") as f:
            snapshots = json.load(f)
    snapshots.append(snapshot)
    # Keep only last 10 snapshots
    snapshots = snapshots[-10:]
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, ensure_ascii=False, indent=2)

    return snapshot


def get_delta(topic_id: str) -> dict:
    """Compare current state with last snapshot. Returns delta analysis."""
    topic_dir = get_topic_dir(topic_id)
    snap_path = os.path.join(topic_dir, "snapshots.json")

    if not os.path.exists(snap_path):
        return {"has_previous": False, "message": "No previous snapshot for comparison"}

    with open(snap_path, "r", encoding="utf-8") as f:
        snapshots = json.load(f)

    if len(snapshots) < 2:
        return {"has_previous": False, "message": "Need at least 2 snapshots for comparison"}

    prev = snapshots[-2]
    curr = snapshots[-1]

    # Delta calculations
    entry_delta = curr["entry_count"] - prev["entry_count"]
    signal_delta = curr["signal_count"] - prev["signal_count"]

    # Sentiment shift
    prev_sent = prev["sentiment_distribution"]
    curr_sent = curr["sentiment_distribution"]
    prev_total = sum(prev_sent.values()) or 1
    curr_total = sum(curr_sent.values()) or 1
    prev_positive_rate = prev_sent.get("positive", 0) / prev_total
    curr_positive_rate = curr_sent.get("positive", 0) / curr_total
    sentiment_shift = curr_positive_rate - prev_positive_rate

    # New keywords (in current but not in previous)
    prev_kw = set(prev.get("top_keywords", {}).keys())
    curr_kw = set(curr.get("top_keywords", {}).keys())
    new_keywords = list(curr_kw - prev_kw)[:10]
    disappeared_keywords = list(prev_kw - curr_kw)[:10]

    # New entries
    prev_hashes = set(prev.get("content_hashes", []))
    curr_hashes = set(curr.get("content_hashes", []))
    new_entry_count = len(curr_hashes - prev_hashes)

    # Determine trend
    if entry_delta > 5 and sentiment_shift > 0.1:
        trend = "rapidly_improving"
    elif entry_delta > 5 and sentiment_shift < -0.1:
        trend = "rapidly_declining"
    elif sentiment_shift > 0.1:
        trend = "improving"
    elif sentiment_shift < -0.1:
        trend = "declining"
    elif entry_delta > 0:
        trend = "growing"
    else:
        trend = "stable"

    return {
        "has_previous": True,
        "snapshot_time": curr["timestamp"],
        "prev_snapshot_time": prev["timestamp"],
        "entry_delta": entry_delta,
        "new_entry_count": new_entry_count,
        "signal_delta": signal_delta,
        "sentiment_shift": round(sentiment_shift, 3),
        "prev_positive_rate": round(prev_positive_rate, 3),
        "curr_positive_rate": round(curr_positive_rate, 3),
        "new_keywords": new_keywords,
        "消失_keywords": 消失_keywords,
        "trend": trend,
    }


# === 异常检测 ===

def detect_anomalies(topic_id: str) -> list[dict]:
    """Detect anomalies in the data."""
    entries = get_all_entries(topic_id)
    if len(entries) < 5:
        return []

    anomalies = []

    # 1. Sentiment shift detection
    recent = entries[-10:]  # Last 10 entries
    older = entries[-20:-10] if len(entries) >= 20 else entries[:max(1, len(entries)-10)]

    def sentiment_score(entry_list):
        if not entry_list:
            return 0.5
        pos = sum(1 for e in entry_list if (e.get("metadata") or {}).get("sentiment") == "positive")
        neg = sum(1 for e in entry_list if (e.get("metadata") or {}).get("sentiment") == "negative")
        return (pos - neg) / len(entry_list) + 0.5

    recent_score = sentiment_score(recent)
    older_score = sentiment_score(older)
    shift = recent_score - older_score

    if shift > 0.3:
        anomalies.append({
            "type": "sentiment_shift",
            "severity": "high",
            "description": f"情感急转正面：近期情感得分 {recent_score:.2f}，前期 {older_score:.2f}，变化 {shift:+.2f}",
            "metric": shift,
        })
    elif shift < -0.3:
        anomalies.append({
            "type": "sentiment_shift",
            "severity": "high",
            "description": f"情感急转负面：近期情感得分 {recent_score:.2f}，前期 {older_score:.2f}，变化 {shift:+.2f}",
            "metric": shift,
        })

    # 2. Volume spike detection
    if len(entries) >= 20:
        recent_count = len(recent)
        older_count = len(older)
        if older_count > 0:
            ratio = recent_count / older_count
            if ratio > 2.0:
                anomalies.append({
                    "type": "volume_spike",
                    "severity": "medium",
                    "description": f"数据量异常增长：近期 {recent_count} 条 vs 前期 {older_count} 条，增长 {ratio:.1f}x",
                    "metric": ratio,
                })

    # 3. Keyword emergence detection
    from collections import Counter
    recent_words = Counter()
    older_words = Counter()
    for e in recent:
        for w in e.get("content", "").split():
            if len(w) >= 2:
                recent_words[w] += 1
    for e in older:
        for w in e.get("content", "").split():
            if len(w) >= 2:
                older_words[w] += 1

    # Find words that appeared much more frequently recently
    emergent = []
    for word, count in recent_words.most_common(50):
        if count >= 3:
            old_count = older_words.get(word, 0)
            if old_count == 0 or count / max(old_count, 1) > 3:
                emergent.append((word, count))

    if emergent:
        anomalies.append({
            "type": "keyword_emergence",
            "severity": "medium",
            "description": f"新关键词涌现：{', '.join(w for w, _ in emergent[:5])}",
            "metric": len(emergent),
            "keywords": [w for w, _ in emergent[:10]],
        })

    return anomalies


# === 多话题总览 ===

def get_all_topics_overview() -> list[dict]:
    """Get health status overview of all topics."""
    topics = list_topics()
    overview = []

    for t in topics:
        tid = t["topic_id"]
        try:
            entries = get_all_entries(tid)
            signals = get_signals(tid)

            # Sentiment distribution
            sent_dist = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
            for e in entries:
                sent = (e.get("metadata") or {}).get("sentiment", "neutral")
                sent_dist[sent] = sent_dist.get(sent, 0) + 1

            total = sum(sent_dist.values()) or 1
            positive_rate = sent_dist["positive"] / total
            negative_rate = sent_dist["negative"] / total

            # Health status
            crit = len([s for s in signals if s.get("severity") == "critical"])
            high = len([s for s in signals if s.get("severity") == "high"])

            if crit > 0 or negative_rate > 0.25:
                health = "red"
            elif high > 0 or negative_rate > 0.15:
                health = "yellow"
            else:
                health = "green"

            # Latest activity
            latest_time = max((e.get("timestamp", "") for e in entries), default="")

            overview.append({
                "topic_id": tid,
                "topic": t["topic"],
                "entry_count": len(entries),
                "signal_count": len(signals),
                "critical_signals": crit,
                "high_signals": high,
                "positive_rate": round(positive_rate, 2),
                "negative_rate": round(negative_rate, 2),
                "health": health,
                "latest_activity": latest_time[:16],
                "updated_at": t.get("updated_at", "")[:16],
            })
        except Exception:
            overview.append({
                "topic_id": tid,
                "topic": t["topic"],
                "health": "unknown",
                "entry_count": 0,
            })

    return overview


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
