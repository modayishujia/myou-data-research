#!/usr/bin/env python3
"""Auto-collection pipeline. Can be triggered by cron/loop for scheduled data collection."""

import json
import os
import sys
import time
import subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import (
    DATA_DIR, list_topics, get_all_entries, load_topic_meta,
    add_entries, snapshot_topic, get_delta, detect_anomalies
)

COLLECTION_DIR = os.path.join(DATA_DIR, "_collection_log")


def log_collection(topic_id: str, status: str, details: dict):
    """Log collection attempt."""
    os.makedirs(COLLECTION_DIR, exist_ok=True)
    log_file = os.path.join(COLLECTION_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic_id": topic_id,
        "status": status,
        **details
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_collection_schedule(topic_id: str) -> str:
    """Determine collection frequency based on topic activity."""
    entries = get_all_entries(topic_id)
    if not entries:
        return "immediate"

    # Check recent activity
    now = datetime.now(timezone.utc)
    recent = [e for e in entries if e.get("timestamp", "") > (now - __import__('datetime').timedelta(hours=2)).isoformat()]

    if len(recent) > 10:
        return "frequent"  # Every 15 min
    elif len(recent) > 3:
        return "normal"    # Every 30 min
    else:
        return "slow"      # Every 2 hours


def generate_search_queries(topic_meta: dict) -> list[str]:
    """Generate search queries from topic keywords."""
    keywords = topic_meta.get("keywords", [])
    topic = topic_meta.get("topic", "")

    queries = []
    # Direct topic search
    queries.append(topic)

    # Keyword combinations
    for kw in keywords:
        queries.append(f"{kw} 最新")
        queries.append(f"{kw} 评价")

    # Platform-specific queries
    for kw in keywords[:3]:
        queries.append(f"site:xiaohongshu.com {kw}")
        queries.append(f"site:douyin.com {kw}")

    return queries[:10]  # Limit to 10 queries per collection


def collect_web_data(queries: list[str]) -> list[dict]:
    """Collect data from web search."""
    entries = []
    for query in queries:
        try:
            # Use webfetch to search
            import urllib.request
            import urllib.parse

            url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}&rn=5"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            response = urllib.request.urlopen(req, timeout=10)
            content = response.read().decode("utf-8", errors="ignore")

            # Simple extraction - look for text between > and <
            import re
            texts = re.findall(r'>([^<]{20,200})<', content)
            for text in texts[:3]:
                if any(kw in text for kw in query.split()[:2]):
                    entries.append({
                        "source": "web_search",
                        "content": text.strip(),
                        "metadata": {
                            "platform": "web",
                            "collection_method": "auto_pipeline",
                            "query": query,
                            "sentiment": "neutral"
                        }
                    })
        except Exception as e:
            log_collection("", "error", {"query": query, "error": str(e)})

    return entries


def run_collection(topic_id: str) -> dict:
    """Run a full collection cycle for a topic."""
    start_time = time.time()

    # Load topic
    try:
        meta = load_topic_meta(topic_id)
    except FileNotFoundError:
        return {"status": "error", "message": f"Topic {topic_id} not found"}

    # Generate queries
    queries = generate_search_queries(meta)

    # Collect web data
    web_entries = collect_web_data(queries)

    # Store entries
    new_count = add_entries(topic_id, web_entries)

    # Snapshot for delta comparison
    snapshot_topic(topic_id)

    # Detect anomalies
    anomalies = detect_anomalies(topic_id)

    # Get delta
    delta = get_delta(topic_id)

    elapsed = time.time() - start_time

    result = {
        "status": "success",
        "topic_id": topic_id,
        "new_entries": new_count,
        "total_entries": len(get_all_entries(topic_id)),
        "anomalies": len(anomalies),
        "delta": delta,
        "elapsed_seconds": round(elapsed, 2),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    log_collection(topic_id, "success", result)
    return result


def run_all_topics() -> list[dict]:
    """Run collection for all active topics."""
    topics = list_topics()
    results = []

    for t in topics:
        if t.get("status") == "active":
            result = run_collection(t["topic_id"])
            results.append(result)

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Auto-collection pipeline")
    parser.add_argument("--topic", help="Topic ID to collect (default: all active)")
    parser.add_argument("--status", action="store_true", help="Show collection status")
    args = parser.parse_args()

    if args.status:
        topics = list_topics()
        for t in topics:
            schedule = get_collection_schedule(t["topic_id"])
            entries = get_all_entries(t["topic_id"])
            print(f"{t['topic_id']}: {len(entries)} entries, schedule={schedule}")
        return

    if args.topic:
        result = run_collection(args.topic)
    else:
        results = run_all_topics()
        result = {"topics": len(results), "results": results}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
