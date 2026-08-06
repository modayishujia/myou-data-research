#!/usr/bin/env python3
"""Markdown-based data store for research topics.

每个话题一个 research.md（本地 markdown 存储，人类可读、可编辑）：
  - 元信息（front matter）
  - 调研方法论（每个话题单独生成，随话题而异，可改写）
  - 数据说明（自动汇总来源/采集方式/情感词汇表）
  - 数据条目 / 信号 / 演变 / 快照（统一行格式，便于追加与解析）

旧 JSON 存储（meta.json/entries.json/...）在首次读取时自动迁移，迁移后删除。
所有对外函数签名与原 JSON 版保持一致，调用方无需改动。
"""

import json
import os
import sys
import hashlib
import re
from datetime import datetime, timezone

# Default data directory - can be overridden via environment variable
DATA_DIR = os.environ.get("RESEARCH_DATA_DIR", os.path.expanduser("~/.local/share/data-research"))

# 行内字段分隔：条目/信号/演变 均用 " || " 分隔附加信息，避免与正文中的顿号/竖线冲突
SEP = " || "
EMPTY = "（暂无）"

FRONT_KEYS = ["topic", "topic_id", "scenario", "keywords", "sources",
              "financial", "created_at", "updated_at", "collection_count", "status"]


# ============================================================
# 话题专属调研方法论（启发式，随场景/关键词/话题而异；可被 set_methodology 改写）
# ============================================================

def detect_scenario(topic, keywords):
    text = (topic + " " + " ".join(keywords or [])).lower()
    if any(k in text for k in ["金融单品", "单品追踪", "热品", "交易机会", "机会发现", "标的", "建仓", "股价背离", "交付量追踪", "销量追踪", "个股追踪", "个股"]):
        return "金融单品追踪"
    if any(k in text for k in ["股票", "投资", "估值", "财报", "业绩", "基金", "股价", "市值", "持仓", "证券", "上市公司", "ipo", "融资"]):
        return "投资研究"
    if any(k in text for k in ["发布", "新品", "上市", "首发", "预售", "交付", "提车", "开售", "发布会"]):
        return "产品发布"
    if any(k in text for k in ["行业", "赛道", "市场", "趋势", "产业", "政策", "创新药", "cxo", "生物医药"]):
        return "行业调研"
    return "舆情监控"


def suggest_methodology(topic, keywords=None, scenario=None):
    """为单个话题生成一套专属调研方法论（随话题目标/场景/关键词而异）。"""
    scenario = scenario or detect_scenario(topic, keywords or [])
    kw = "、".join((keywords or [])[:8]) or "（随采集补充）"

    base = {
        "金融单品追踪": {
            "goal": f"围绕「{topic}」做企业单品的持续追踪：监测单品声量/情绪/口碑势能，横向排名同公司热品，并据此发现潜在交易机会（信号→盈利映射→股价背离→催化剂→机会评分）。",
            "questions": [
                f"「{topic}」单品的声量与情绪势能处于什么位置、趋势如何？",
                f"在同公司产品矩阵（及跨市场）中，它是否属于热品、热度为几何？",
                f"单品势能、口碑与该公司股价/估值之间是否存在背离（错配即机会）？",
                f"近期有哪些催化剂（发布/交付/财报/大单）可能触发重估？",
            ],
            "sources": "社交平台声量（小红书/抖音/微博）、电商与交付数据、东方财富/雪球股价与估值、公司公告与财报、行业销量数据",
            "dims": "单品声量与情绪 / 口碑与痛点 / 竞品对标 / 同公司热品排名 / 股价背离度 / 催化剂日历 / 交易机会评分",
            "metrics": "单品热度分、正向情绪净分、口碑痛点数、同公司热品排名、股价背离度、催化剂密度、机会评分(0-100)与方向",
            "cadence": "常规按天追踪声量与情绪；财报/交付/发布窗口加密到小时级，重点捕捉势能拐点与背离",
        },
        "投资研究": {
            "goal": f"围绕「{topic}」的投资价值与风险变化，持续追踪市场预期、业绩与资金动向，为投资决策提供证据链。",
            "questions": [
                f"「{topic}」的核心驱动因素是什么（基本面/估值/资金/政策）？",
                f"市场对「{topic}」的预期如何形成、如何修正？",
                f"有哪些风险信号需要提前捕捉（业绩变脸/监管/减持/舆情反转）？",
            ],
            "sources": "上市公司公告与财报、券商研报、财经媒体、雪球/股吧等社区、政策文件",
            "dims": "业绩与基本面 / 估值与市场预期 / 机构与资金动向 / 行业政策与竞争格局 / 风险事件与舆情 / 预测研判",
            "metrics": "正面情绪占比、负面情绪占比、估值讨论频次、机构观点方向、风险信号（监管/减持/业绩）数量",
            "cadence": "公告与财报期加密采集；日常按天汇总情绪与资金动向，重大事件当日追踪",
        },
        "产品发布": {
            "goal": f"围绕「{topic}」的产品发布全周期（预热/发布/首销/口碑），监测用户反应、配置口碑与竞品对标，评估产品声量与转化信号。",
            "questions": [
                f"「{topic}」发布会前后声量如何变化、由哪些人群/渠道驱动？",
                f"用户最关注哪些配置/价格点？正负口碑的争议焦点是什么？",
                f"与主要竞品的对比讨论中，用户倾向如何？",
            ],
            "sources": "发布会直播与媒体报道、微博/小红书/抖音用户内容、电商评论、数码/KOL 评测",
            "dims": "声量与热度 / 配置与价格讨论 / 评论区情绪 / KOL 与媒体立场 / 竞品对比 / 首销反馈与预测",
            "metrics": "声量日变化、正面/负面情绪占比、价格焦虑指数、竞品提及频次、争议点（配置/价格/营销）数量",
            "cadence": "预热期每日采样，发布会当天与首销 72 小时加密追踪，之后按天回落",
        },
        "行业调研": {
            "goal": f"以「{topic}」为切口理解行业趋势、竞争格局与政策环境，输出结构化行业认知与可跟踪指标。",
            "questions": [
                f"「{topic}」所在赛道当前处于什么阶段（导入/成长/洗牌）？",
                f"产业链上中下游的关键变量与代表性玩家是谁？",
                f"政策、技术、成本等外部变量如何改变行业走向？",
            ],
            "sources": "行业媒体与研报、企业公告、政策文件、展会与发布会、行业社区讨论",
            "dims": "市场规模与增速 / 竞争格局与玩家 / 产业链变量 / 政策与技术驱动 / 风险与壁垒 / 趋势研判",
            "metrics": "行业事件频次、玩家提及分布、政策/技术关键词涌现、头部公司情绪方向",
            "cadence": "每周系统性采集一轮，关键政策/技术事件触发即时追踪",
        },
        "舆情监控": {
            "goal": f"持续监控「{topic}」的社会化讨论：情绪走向、争议焦点、关键传播者与潜在风险，第一时间发现从讨论演变为危机的信号。",
            "questions": [
                f"「{topic}」的讨论热度与情绪曲线如何变化？",
                f"哪些叙事/争议在主导舆论？谁在推动（KOL/媒体/普通用户）？",
                f"是否存在抹黑、水军、断章取义等操纵痕迹？",
            ],
            "sources": "微博/小红书/抖音/知乎等社交平台、新闻媒体、评论区",
            "dims": "搜索与讨论热度 / 内容生态与KOL / 评论区情绪 / 叙事与争议 / 操纵痕迹 / 风险评估与预测",
            "metrics": "声量趋势、正面/负面/争议占比、KOL 立场分布、新关键词涌现、风险信号（抹黑/投毒/水军）数量",
            "cadence": "每日采集 1-2 轮；出现负面集中或热度飙升时加密到小时级",
        },
    }[scenario]

    return f"""> 本话题的调研方法论为**独立生成**，随话题目标、场景与关键词而异；采集与分析方法以此为准，可随调研进展改写。

**调研目标**：{base['goal']}

**核心问题**：
{'，'.join(base['questions'])}

**数据来源与采集策略**：{base['sources']}

**分析维度**：{base['dims']}

**指标与阈值**：{base['metrics']}

**研判节奏**：{base['cadence']}

**关键词锚点**：{kw}"""


# ============================================================
# research.md 读写（front matter + 分区行格式）
# ============================================================

def get_topic_dir(topic_id: str) -> str:
    """Get the directory path for a research topic."""
    return os.path.join(DATA_DIR, topic_id)


def sanitize_topic_id(topic: str) -> str:
    """Convert a topic string to a safe directory name."""
    clean = "".join(c if c.isalnum() or c in "-_ " else "" for c in topic[:50]).strip()
    clean = clean.replace(" ", "-").lower()
    suffix = hashlib.md5(topic.encode()).hexdigest()[:8]
    return f"{clean}-{suffix}" if clean else f"topic-{suffix}"


def md_path(topic_id):
    return os.path.join(get_topic_dir(topic_id), "research.md")


def _fmt_value(v):
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def _parse_front_matter(text):
    meta = {}
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return meta
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i].strip()
        if line and ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
        i += 1
    for k in ("keywords", "sources"):
        if k in meta and meta[k]:
            meta[k] = [x.strip() for x in meta[k].split(",") if x.strip()]
    for k in ("collection_count",):
        if k in meta and meta[k].isdigit():
            meta[k] = int(meta[k])
    # financial 以 JSON 字符串存储，读回时还原为 dict
    if "financial" in meta and meta["financial"]:
        try:
            meta["financial"] = json.loads(meta["financial"])
        except (json.JSONDecodeError, TypeError):
            meta["financial"] = {}
    return meta


def _dump_front_matter(meta):
    lines = ["---"]
    for k in FRONT_KEYS:
        if k in meta and meta[k] is not None:
            lines.append(f"{k}: {_fmt_value(meta[k])}")
    lines.append("---")
    return "\n".join(lines)


def _read_section(body_lines, title):
    """取 '## title' 到下一个 '## ' 之间的内容（去掉首尾空行）。"""
    lines = body_lines
    out, started = [], False
    for ln in lines:
        if ln.startswith("## "):
            if started:
                break
            if ln.strip() == f"## {title}":
                started = True
            continue
        if started:
            out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


# --- 条目行编解码：- [ts] [source] [sentiment] [content_type] [engagement] [method] {kv} 内容 ---

def _encode_entry(e):
    m = e.get("metadata") or {}
    kv_items = []
    for k, v in m.items():
        if k in ("sentiment", "content_type", "engagement", "collection_method"):
            continue
        if v is None:
            continue
        kv_items.append(f"{k}={str(v).replace(chr(10), ' ').strip()}")
    kv = "{" + "; ".join(kv_items) + "}" if kv_items else ""
    fields = [
        (e.get("timestamp") or "").replace("]", ""),
        (e.get("source") or "unknown").replace("]", ""),
        (m.get("sentiment") or "neutral").replace("]", ""),
        (m.get("content_type") or "未标注").replace("]", ""),
        (m.get("engagement") or "").replace("]", ""),
        (m.get("collection_method") or "").replace("]", ""),
    ]
    content = (e.get("content") or "").replace("\n", " ").replace("]", "」")
    head = f"- [{fields[0]}] [{fields[1]}] [{fields[2]}] [{fields[3]}] [{fields[4]}] [{fields[5]}]"
    return (head + (" " + kv if kv else "") + " " + content).rstrip()


_ENTRY_RE = re.compile(r"^- \[(.*?)\] \[(.*?)\] \[(.*?)\] \[(.*?)\] \[(.*?)\] \[(.*?)\](?:\s*(\{[^}]*\}))?\s?(.*)$")


def _decode_entry_line(line):
    m = _ENTRY_RE.match(line.strip())
    if not m:
        return None
    ts, source, sent, ctype, eng, method, kv, content = m.groups()
    metadata = {
        "sentiment": sent or "neutral",
        "content_type": ctype or "未标注",
        "engagement": eng or "",
        "collection_method": method or "",
    }
    if kv:
        for pair in kv[1:-1].split("; "):
            if "=" in pair:
                k, v = pair.split("=", 1)
                metadata[k.strip()] = v.strip()
    return {"timestamp": ts, "source": source or "unknown", "content": content.strip(), "metadata": metadata}


# --- 信号行编解码：- [ts] [severity] [type] 描述 || 证据：e1；e2 || 建议：xxx ---

def _encode_signal(sig):
    parts = [sig.get("description") or EMPTY]
    if sig.get("evidence"):
        parts.append("证据：" + "；".join(str(x) for x in sig["evidence"]))
    if sig.get("recommended_action"):
        parts.append("建议：" + str(sig["recommended_action"]))
    t = (sig.get("type") or "").replace("]", "")
    return f"- [{(sig.get('timestamp') or '').replace(']', '')}] [{(sig.get('severity') or 'low').replace(']', '')}] [{t}] " + SEP.join(parts)


_SIG_RE = re.compile(r"^- \[(.*?)\] \[(.*?)\] \[(.*?)\](?: ?(.*))$")


def _decode_signal_line(line):
    m = _SIG_RE.match(line.strip())
    if not m:
        return None
    ts, sev, sig_type, rest = m.groups()
    desc, evidence, action = (rest or "").strip(), [], None
    for part in (rest or "").split(SEP)[1:]:
        part = part.strip()
        if part.startswith("证据："):
            evidence = [x.strip() for x in part[3:].split("；") if x.strip()]
        elif part.startswith("建议："):
            action = part[3:].strip()
        elif part:
            evidence.append(part)
    return {"timestamp": ts, "severity": sev or "low", "type": sig_type or "",
            "description": desc, "evidence": evidence, "recommended_action": action}


# --- 演变行编解码：- [ts] [phase] 摘要 || 情感流向：x || 变化：a；b || 事件：e || 关键词：k1,k2 ---

_EVO_RE = re.compile(r"^- \[(.*?)\] \[(.*?)\](?: ?(.*))$")


def _decode_evolution_line(line):
    m = _EVO_RE.match(line.strip())
    if not m:
        return None
    ts, phase, rest = m.groups()
    point = {"timestamp": ts, "phase": phase or "stable", "summary": (rest or "").strip(), "key_changes": []}
    for part in (rest or "").split(SEP)[1:]:
        part = part.strip()
        if part.startswith("情感流向："):
            point["sentiment_shift"] = part[5:].strip()
        elif part.startswith("变化："):
            point["key_changes"] = [x.strip() for x in part[3:].split("；") if x.strip()]
        elif part.startswith("事件："):
            point["notable_events"] = [x.strip() for x in part[3:].split("；") if x.strip()]
        elif part.startswith("关键词："):
            point["new_keywords"] = [x.strip() for x in part[4:].split(",") if x.strip()]
    return point


def _encode_evolution_point(p):
    parts = [p.get("summary") or EMPTY]
    if p.get("sentiment_shift"):
        parts.append("情感流向：" + str(p["sentiment_shift"]))
    if p.get("key_changes"):
        parts.append("变化：" + "；".join(str(x) for x in p["key_changes"]))
    if p.get("notable_events"):
        parts.append("事件：" + "；".join(str(x) for x in p["notable_events"]))
    if p.get("new_keywords"):
        parts.append("关键词：" + ",".join(str(x) for x in p["new_keywords"]))
    return f"- [{(p.get('timestamp') or '').replace(']', '')}] [{(p.get('phase') or 'stable').replace(']', '')}] " + SEP.join(parts)


# --- 快照行编解码：- [ts] [entry_count] [signal_count] {json} ---

def _encode_snapshot(snap):
    payload = {k: v for k, v in snap.items() if k not in ("timestamp", "entry_count", "signal_count")}
    return f"- [{(snap.get('timestamp') or '').replace(']', '')}] [{snap.get('entry_count', 0)}] [{snap.get('signal_count', 0)}] " + json.dumps(payload, ensure_ascii=False)


def _decode_snapshot_line(line):
    s = line.strip()
    if not s.startswith("- ["):
        return None
    rest = s[2:].lstrip()
    fields = []
    for _ in range(3):
        j = rest.find("]")
        if j < 0:
            return None
        fields.append(rest[1:j])
        rest = rest[j + 1:].lstrip()
    ts, ec, sc = fields
    snap = {"timestamp": ts, "entry_count": int(ec or 0), "signal_count": int(sc or 0)}
    if rest.startswith("{"):
        try:
            snap.update(json.loads(rest))
        except Exception:
            pass
    return snap


def _build_data_notes(entries):
    sources = []
    methods = []
    for e in entries:
        src = e.get("source")
        mth = (e.get("metadata") or {}).get("collection_method")
        if src and src not in sources:
            sources.append(src)
        if mth and mth not in methods:
            methods.append(mth)
    lines = ["## 数据说明", ""]
    lines.append("- 数据来源：" + ("、".join(sources) if sources else EMPTY))
    lines.append("- 采集方式：" + ("、".join(methods) if methods else EMPTY))
    lines.append("- 情感标注：positive（正面）、negative（负面）、neutral（中性）、mixed（混合）")
    return "\n".join(lines)


# ============================================================
# 主读写：research.md 整体解析/序列化
# ============================================================

def _load_md(topic_id):
    """解析 research.md → {meta, methodology, entries, signals, evolution, snapshots}"""
    data = {"meta": {}, "methodology": "", "entries": [], "signals": [], "evolution": [], "snapshots": []}
    path = md_path(topic_id)
    if not os.path.exists(path):
        return data
    text = open(path, encoding="utf-8").read()
    lines = text.split("\n")

    # front matter
    if lines and lines[0].strip() == "---":
        end = None
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end = i
                break
        if end:
            data["meta"] = _parse_front_matter("\n".join(lines[: end + 1]))
            body_lines = lines[end + 1:]
        else:
            body_lines = lines[1:]
    else:
        body_lines = lines

    data["methodology"] = _read_section(body_lines, "调研方法论")

    heading_idx = {}
    for i, ln in enumerate(body_lines):
        if ln.startswith("## "):
            heading_idx[ln.strip()[3:]] = i

    def section_lines(title):
        if title not in heading_idx:
            return []
        start = heading_idx[title] + 1
        ends = [v for v in heading_idx.values() if v > start]
        end = min(ends) if ends else len(body_lines)
        return body_lines[start:end]

    data["entries"] = [e for e in (_decode_entry_line(l) for l in section_lines("数据条目")) if e]
    data["signals"] = [s for s in (_decode_signal_line(l) for l in section_lines("信号")) if s]
    data["evolution"] = [e for e in (_decode_evolution_line(l) for l in section_lines("演变")) if e]
    data["snapshots"] = [s for s in (_decode_snapshot_line(l) for l in section_lines("快照")) if s]
    return data


def _save_md(topic_id, data):
    meta = data["meta"]
    meta.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
    meta.setdefault("status", "active")
    notes = _build_data_notes(data["entries"])
    secs = ["## 调研方法论", "", (data.get("methodology") or "").strip(), "",
            notes, "",
            "## 数据条目", ""]
    secs += [("" if not _encode_entry(e) else _encode_entry(e)) for e in data["entries"]]
    secs += ["", "## 信号", ""]
    secs += [_encode_signal(s) for s in data["signals"]]
    secs += ["", "## 演变", ""]
    secs += [_encode_evolution_point(p) for p in data["evolution"]]
    secs += ["", "## 快照", ""]
    secs += [_encode_snapshot(s) for s in data["snapshots"]]

    content = _dump_front_matter(meta) + "\n\n" + "\n".join(secs).rstrip() + "\n"
    os.makedirs(get_topic_dir(topic_id), exist_ok=True)
    with open(md_path(topic_id), "w", encoding="utf-8") as f:
        f.write(content)


# ============================================================
# 旧 JSON 自动迁移（首次访问时执行一次，迁移后删除 JSON）
# ============================================================

_LEGACY_FILES = ["meta.json", "entries.json", "evolution.json", "signals.json", "snapshots.json"]


def _normalize_legacy_entry(e):
    """旧 JSON 条目兼容：顶层字段并入 metadata，title/snippet 兜底为内容。"""
    m = dict(e.get("metadata") or {})
    for k in ("platform", "sentiment", "sentiment_detail", "author", "url", "engagement",
              "content_type", "collection_method", "sentiment_score", "dimension",
              "keywords", "published_at", "is_comment", "is_comment_summary", "title", "snippet"):
        if k in e and e[k] is not None and k not in m:
            m[k] = e[k]
    if not e.get("content"):
        title = (e.get("title") or "").strip()
        snippet = (e.get("snippet") or "").strip()
        e["content"] = title + ("\n" + snippet if snippet else "")
    e["metadata"] = m
    return e


def _migrate_legacy(topic_id):
    topic_dir = get_topic_dir(topic_id)
    if os.path.exists(md_path(topic_id)):
        return
    meta_path = os.path.join(topic_dir, "meta.json")
    if not os.path.isfile(meta_path):
        return

    data = {"meta": {}, "methodology": "", "entries": [], "signals": [], "evolution": [], "snapshots": []}
    with open(meta_path, encoding="utf-8") as f:
        data["meta"] = json.load(f)

    for fname, key in (("entries.json", "entries"), ("evolution.json", "evolution"),
                       ("signals.json", "signals"), ("snapshots.json", "snapshots")):
        p = os.path.join(topic_dir, fname)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                data[key] = json.load(f)

    data["entries"] = [_normalize_legacy_entry(e) for e in data["entries"] if isinstance(e, dict)]
    data["methodology"] = suggest_methodology(data["meta"].get("topic", topic_id),
                                              data["meta"].get("keywords", []),
                                              data["meta"].get("scenario") or detect_scenario(
                                                  data["meta"].get("topic", topic_id), data["meta"].get("keywords", [])))
    data["meta"].setdefault("scenario", detect_scenario(data["meta"].get("topic", topic_id),
                                                        data["meta"].get("keywords", [])))
    _save_md(topic_id, data)
    for fname in _LEGACY_FILES:
        p = os.path.join(topic_dir, fname)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


# ============================================================
# 对外 API（签名与 JSON 版一致）
# ============================================================

def init_topic(topic: str, keywords: list = None, sources: list = None, scenario: str = None, financial: dict = None) -> dict:
    """Initialize a new research topic. Returns the topic metadata.

    financial: 金融单品追踪专用实体块，形如
        {"company": "小米集团", "ticker": "1810.HK", "product": "小米SU7",
         "product_line": "汽车", "watch_type": "single_product",
         "launch_date": "2024-03-28", "price_band": "21.59-29.99万"}
    """
    topic_id = sanitize_topic_id(topic)
    scenario = scenario or detect_scenario(topic, keywords or [])
    meta = {
        "topic_id": topic_id,
        "topic": topic,
        "keywords": keywords or [],
        "sources": sources or [],
        "scenario": scenario,
        "financial": financial or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "collection_count": 0,
        "status": "active",
    }
    data = {"meta": meta, "methodology": suggest_methodology(topic, keywords or [], scenario),
            "entries": [], "signals": [], "evolution": [], "snapshots": []}
    _save_md(topic_id, data)
    return meta


def set_financial(topic_id: str, financial: dict):
    """为话题设置/更新金融实体块（公司/股票代码/单品/追踪类型等）。"""
    data = _load_md(topic_id)
    data["meta"]["financial"] = financial or {}
    data["meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_md(topic_id, data)
    return data["meta"]["financial"]


def load_topic_meta(topic_id: str) -> dict:
    """Load topic metadata."""
    _migrate_legacy(topic_id)
    return _load_md(topic_id)["meta"]


def save_topic_meta(topic_id: str, meta: dict):
    """Save topic metadata."""
    data = _load_md(topic_id)
    data["meta"] = meta
    _save_md(topic_id, data)


def set_methodology(topic_id: str, methodology: str):
    """覆写该话题的调研方法论（每个话题独立，随调研进展可改写）。"""
    data = _load_md(topic_id)
    data["methodology"] = methodology
    _save_md(topic_id, data)


def get_methodology(topic_id: str) -> str:
    """读取该话题的调研方法论文本。"""
    return _load_md(topic_id)["methodology"]


def add_entries(topic_id: str, entries: list) -> int:
    """Add data entries to a topic. Returns count of new entries."""
    _migrate_legacy(topic_id)
    data = _load_md(topic_id)
    existing = data["entries"]

    existing_hashes = {hashlib.md5(e.get("content", "").encode()).hexdigest() for e in existing}
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    for entry in entries:
        entry.setdefault("timestamp", now)
        entry.setdefault("collected_at", now)
        h = hashlib.md5(entry.get("content", "").encode()).hexdigest()
        if h not in existing_hashes:
            existing_hashes.add(h)
            existing.append(entry)
            new_count += 1

    data["meta"]["collection_count"] = len(existing)
    _save_md(topic_id, data)
    return new_count


def add_evolution_point(topic_id: str, point: dict):
    """Record an evolution observation point."""
    _migrate_legacy(topic_id)
    data = _load_md(topic_id)
    point.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    data["evolution"].append(point)
    _save_md(topic_id, data)


def add_signal(topic_id: str, signal: dict):
    """Record a notable signal or insight."""
    _migrate_legacy(topic_id)
    data = _load_md(topic_id)
    signal.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    data["signals"].append(signal)
    _save_md(topic_id, data)


def get_all_entries(topic_id: str) -> list:
    """Get all entries for a topic, sorted by timestamp."""
    _migrate_legacy(topic_id)
    entries = _load_md(topic_id)["entries"]
    entries.sort(key=lambda x: x.get("timestamp", ""))
    return entries


def get_entries_since(topic_id: str, since_iso: str) -> list:
    """Get entries collected after a given timestamp."""
    return [e for e in get_all_entries(topic_id) if e.get("timestamp", "") > since_iso]


def get_evolution(topic_id: str) -> list:
    """Get all evolution points for a topic."""
    _migrate_legacy(topic_id)
    return _load_md(topic_id)["evolution"]


def get_signals(topic_id: str) -> list:
    """Get all signals for a topic, sorted by severity then time."""
    _migrate_legacy(topic_id)
    signals = _load_md(topic_id)["signals"]
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    signals.sort(key=lambda x: (severity_order.get(x.get("severity", "low"), 99), x.get("timestamp", "")))
    return signals


def list_topics() -> list:
    """List all research topics."""
    topics = []
    if not os.path.exists(DATA_DIR):
        return topics
    for name in os.listdir(DATA_DIR):
        if os.path.isfile(os.path.join(DATA_DIR, name, "research.md")):
            _migrate_legacy(name)
            topics.append(load_topic_meta(name))
    topics.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return topics


def get_topic_summary(topic_id: str) -> dict:
    """Get a complete summary of a topic for dashboard rendering."""
    meta = load_topic_meta(topic_id)
    entries = get_all_entries(topic_id)
    evolution = get_evolution(topic_id)
    signals = get_signals(topic_id)

    source_counts = {}
    for e in entries:
        src = e.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

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
    entries = get_all_entries(topic_id)
    signals = get_signals(topic_id)

    keyword_freq = {}
    sentiment_dist = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
    source_counts = {}

    for e in entries:
        content = e.get("content", "")
        for word in content.split():
            if len(word) >= 2:
                keyword_freq[word] = keyword_freq.get(word, 0) + 1
        sent = (e.get("metadata") or {}).get("sentiment", "neutral")
        sentiment_dist[sent] = sentiment_dist.get(sent, 0) + 1
        src = e.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

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

    data = _load_md(topic_id)
    data["snapshots"].append(snapshot)
    data["snapshots"] = data["snapshots"][-10:]
    _save_md(topic_id, data)
    return snapshot


def get_delta(topic_id: str) -> dict:
    """Compare current state with last snapshot. Returns delta analysis."""
    snapshots = _load_md(topic_id)["snapshots"]
    if not snapshots:
        return {"has_previous": False, "message": "No previous snapshot for comparison"}
    if len(snapshots) < 2:
        return {"has_previous": False, "message": "Need at least 2 snapshots for comparison"}

    prev = snapshots[-2]
    curr = snapshots[-1]

    entry_delta = curr["entry_count"] - prev["entry_count"]
    signal_delta = curr["signal_count"] - prev["signal_count"]

    prev_sent = prev.get("sentiment_distribution", {})
    curr_sent = curr.get("sentiment_distribution", {})
    prev_total = sum(prev_sent.values()) or 1
    curr_total = sum(curr_sent.values()) or 1
    prev_positive_rate = prev_sent.get("positive", 0) / prev_total
    curr_positive_rate = curr_sent.get("positive", 0) / curr_total
    sentiment_shift = curr_positive_rate - prev_positive_rate

    prev_kw = set(prev.get("top_keywords", {}).keys())
    curr_kw = set(curr.get("top_keywords", {}).keys())
    new_keywords = list(curr_kw - prev_kw)[:10]
    disappeared_keywords = list(prev_kw - curr_kw)[:10]

    prev_hashes = set(prev.get("content_hashes", []))
    curr_hashes = set(curr.get("content_hashes", []))
    new_entry_count = len(curr_hashes - prev_hashes)

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
        "disappeared_keywords": disappeared_keywords,
        "trend": trend,
    }


# === 异常检测 ===

def detect_anomalies(topic_id: str) -> list:
    """Detect anomalies in the data."""
    entries = get_all_entries(topic_id)
    if len(entries) < 5:
        return []

    anomalies = []
    recent = entries[-10:]
    older = entries[-20:-10] if len(entries) >= 20 else entries[:max(1, len(entries) - 10)]

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
        anomalies.append({"type": "sentiment_shift", "severity": "high",
                          "description": f"情感急转正面：近期情感得分 {recent_score:.2f}，前期 {older_score:.2f}，变化 {shift:+.2f}",
                          "metric": shift})
    elif shift < -0.3:
        anomalies.append({"type": "sentiment_shift", "severity": "high",
                          "description": f"情感急转负面：近期情感得分 {recent_score:.2f}，前期 {older_score:.2f}，变化 {shift:+.2f}",
                          "metric": shift})

    if len(entries) >= 20:
        recent_count = len(recent)
        older_count = len(older)
        if older_count > 0:
            ratio = recent_count / older_count
            if ratio > 2.0:
                anomalies.append({"type": "volume_spike", "severity": "medium",
                                  "description": f"数据量异常增长：近期 {recent_count} 条 vs 前期 {older_count} 条，增长 {ratio:.1f}x",
                                  "metric": ratio})

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

    emergent = []
    for word, count in recent_words.most_common(50):
        if count >= 3:
            old_count = older_words.get(word, 0)
            if old_count == 0 or count / max(old_count, 1) > 3:
                emergent.append((word, count))

    if emergent:
        anomalies.append({"type": "keyword_emergence", "severity": "medium",
                          "description": f"新关键词涌现：{', '.join(w for w, _ in emergent[:5])}",
                          "metric": len(emergent),
                          "keywords": [w for w, _ in emergent[:10]]})

    return anomalies


# === 多话题总览 ===

def get_all_topics_overview() -> list:
    """Get health status overview of all topics."""
    topics = list_topics()
    overview = []

    for t in topics:
        tid = t["topic_id"]
        try:
            entries = get_all_entries(tid)
            signals = get_signals(tid)

            sent_dist = {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}
            for e in entries:
                sent = (e.get("metadata") or {}).get("sentiment", "neutral")
                sent_dist[sent] = sent_dist.get(sent, 0) + 1

            total = sum(sent_dist.values()) or 1
            positive_rate = sent_dist["positive"] / total
            negative_rate = sent_dist["negative"] / total

            crit = len([s for s in signals if s.get("severity") == "critical"])
            high = len([s for s in signals if s.get("severity") == "high"])

            if crit > 0 or negative_rate > 0.25:
                health = "red"
            elif high > 0 or negative_rate > 0.15:
                health = "yellow"
            else:
                health = "green"

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


# === CLI ===

def _cli():
    if len(sys.argv) < 2:
        print("Usage: data_store.py <command> [args...]")
        print("Commands: init, add, evolution, signal, list, summary, entries, methodology, set-methodology")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "init":
        topic = sys.argv[2]
        keywords = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else []
        result = init_topic(topic, keywords)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd == "add":
        topic_id, content = sys.argv[2], sys.argv[3]
        source = sys.argv[4] if len(sys.argv) > 4 else "manual"
        n = add_entries(topic_id, [{"content": content, "source": source}])
        print(json.dumps({"added": n}))
    elif cmd == "evolution":
        topic_id, phase, summary = sys.argv[2], sys.argv[3], sys.argv[4]
        add_evolution_point(topic_id, {"phase": phase, "summary": summary})
        print(json.dumps({"ok": True}))
    elif cmd == "signal":
        topic_id, severity, sig_type, description = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
        add_signal(topic_id, {"severity": severity, "type": sig_type, "description": description})
        print(json.dumps({"ok": True}))
    elif cmd == "list":
        print(json.dumps(list_topics(), ensure_ascii=False, indent=2))
    elif cmd == "summary":
        topic_id = sys.argv[2]
        print(json.dumps(get_topic_summary(topic_id), ensure_ascii=False, indent=2))
    elif cmd == "entries":
        topic_id = sys.argv[2]
        print(json.dumps(get_all_entries(topic_id), ensure_ascii=False, indent=2))
    elif cmd == "methodology":
        topic_id = sys.argv[2]
        print(get_methodology(topic_id))
    elif cmd == "set-methodology":
        topic_id = sys.argv[2]
        text = " ".join(sys.argv[3:])
        set_methodology(topic_id, text)
        print(json.dumps({"ok": True}))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
