"""金融单品追踪引擎：单品健康度 / 热品榜 / 交易机会发现。

设计定位
--------
本模块是「金融单品追踪」场景的计算核心，叠加在现有 8 维度调研框架之上：
  - 单品健康度 / 热度分：完全由现有社媒 entries（sentiment/platform/engagement/timestamp）算出，无需额外数据；
  - 交易机会发现：在社媒势能基础上，叠加金融面信号（股价/估值/交付量）。金融数据由采集阶段
    （agent 经 websearch 抓取东方财富/雪球/公告，或接入金融 MCP）写入话题 meta.financial 的
    时点字段（price_change_pct / delivery_latest / sales_latest / consensus 等）；缺失时引擎
    自动降级为「社媒单品信号」并标注数据缺口，不臆造数字。

依赖：仅依赖 data_store（避免与 report_generator 形成循环 import）。
"""
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import get_topic_summary, list_topics  # noqa: E402


def parse_engagement(s):
    """Parse '1.2万赞' / '475.6万' into a comparable int."""
    s = str(s or "")
    import re
    m = re.search(r"([\d.]+)\s*(万|w)?", s)
    if not m:
        return 0
    val = float(m.group(1))
    if m.group(2):
        val *= 10000
    return int(val)


# ============================================================
# 单品健康度
# ============================================================
def single_product_health(summary):
    """从社媒 entries 派生单品健康度指标。返回 dict。"""
    entries = summary.get("entries", [])
    total = len(entries) or 1
    sent_dist = Counter((e.get("metadata") or {}).get("sentiment", "neutral") for e in entries)
    pos = sent_dist.get("positive", 0)
    neg = sent_dist.get("negative", 0)
    pos_ratio = pos / total
    neg_ratio = neg / total
    net_sentiment = pos_ratio - neg_ratio  # [-1, 1]

    # 声量动量：后半窗口 vs 前半窗口
    daily = Counter((e.get("timestamp") or "")[:10] for e in entries)
    days = sorted(daily.items())
    momentum = 0.0
    if len(days) >= 2:
        mid = len(days) // 2
        early = sum(c for _, c in days[:mid]) or 1
        recent = sum(c for _, c in days[mid:])
        momentum = recent / early - 1.0  # >0 升温
    elif days:
        momentum = 0.0

    engagement_total = sum(parse_engagement((e.get("metadata") or {}).get("engagement")) for e in entries)
    platforms = set((e.get("metadata") or {}).get("platform") for e in entries if (e.get("metadata") or {}).get("platform"))

    # 口碑痛点 / 好评点：从负/正面条目抽高频词
    def top_words(subset, n=6):
        stop = set("的 了 在 是 我 你 他 她 它 这 那 就 都 也 很 有 不 和 与 及 或 一个 我们 他们 自己 什么 怎么 为什么 发布 表示 认为 觉得 网友 用户 博主 媒体 评论 回复 这个 那个".split())
        freq = Counter()
        for e in subset:
            for seg in re.findall(r"[\u4e00-\u9fff]{2,5}", e.get("content", "")):
                if seg not in stop:
                    freq[seg] += 1
        return [w for w, _ in freq.most_common(n)]

    neg_entries = [e for e in entries if (e.get("metadata") or {}).get("sentiment") == "negative"]
    pos_entries = [e for e in entries if (e.get("metadata") or {}).get("sentiment") == "positive"]

    return {
        "total": total,
        "pos_ratio": pos_ratio,
        "neg_ratio": neg_ratio,
        "net_sentiment": net_sentiment,
        "momentum": momentum,
        "engagement_total": engagement_total,
        "platform_count": len(platforms),
        "pain_points": top_words(neg_entries),
        "praise_points": top_words(pos_entries),
        "sent_dist": dict(sent_dist),
    }


# ============================================================
# 热度分（跨单品可比，0-100）
# ============================================================
def heat_score(summary):
    """综合声量动量 / 情绪净分 / 互动量 / 渠道广度，输出 0-100 热度分。"""
    h = single_product_health(summary)
    momentum = h["momentum"]
    momentum_score = max(0.0, min(100.0, 50.0 + momentum * 50.0))
    net = h["net_sentiment"]
    sentiment_score = max(0.0, min(100.0, 50.0 + net * 50.0))
    engagement_score = max(0.0, min(100.0, h["engagement_total"] / 500.0 * 100.0))
    breadth_score = max(0.0, min(100.0, h["platform_count"] / 5.0 * 100.0))
    heat = (0.40 * momentum_score + 0.30 * sentiment_score +
            0.20 * engagement_score + 0.10 * breadth_score)
    return round(heat, 1), {
        "momentum_score": round(momentum_score, 1),
        "sentiment_score": round(sentiment_score, 1),
        "engagement_score": round(engagement_score, 1),
        "breadth_score": round(breadth_score, 1),
    }


# ============================================================
# 热品榜：同公司矩阵 + 跨市场
# ============================================================
def _financial_topics(company=None):
    """列出带 financial.product 的话题（可按公司过滤）。"""
    out = []
    for meta in list_topics():
        fin = meta.get("financial") or {}
        if not fin.get("product"):
            continue
        if company and fin.get("company") != company:
            continue
        out.append(meta)
    return out


def rank_hot_products(company=None):
    """同公司（company 指定）或全市场（company=None）的单品热度排名。

    返回 [{topic_id, topic, company, ticker, product, product_line,
           heat, heat_breakdown, net_sentiment, momentum, updated_at}]，按 heat 降序。
    """
    rows = []
    for meta in _financial_topics(company):
        fin = meta.get("financial") or {}
        try:
            summary = get_topic_summary(meta["topic_id"])
        except Exception:
            continue
        heat, breakdown = heat_score(summary)
        h = single_product_health(summary)
        rows.append({
            "topic_id": meta["topic_id"],
            "topic": meta.get("topic", ""),
            "company": fin.get("company", ""),
            "ticker": fin.get("ticker", ""),
            "product": fin.get("product", ""),
            "product_line": fin.get("product_line", ""),
            "watch_type": fin.get("watch_type", ""),
            "heat": heat,
            "heat_breakdown": breakdown,
            "net_sentiment": round(h["net_sentiment"], 3),
            "momentum": round(h["momentum"], 3),
            "updated_at": meta.get("updated_at", ""),
        })
    rows.sort(key=lambda r: r["heat"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def cross_market_hot():
    """跨市场（全公司）热品榜。"""
    return rank_hot_products(company=None)


# ============================================================
# 交易机会发现
# ============================================================
def _extract_catalysts(summary):
    """从 evolution 笔记中识别催化剂事件（发布/交付/财报/大单/预订等）。"""
    cats = {
        "发布": ["发布", "发布会", "亮相", "官宣"],
        "交付": ["交付", "提车", "量产", "下线"],
        "财报": ["财报", "业绩", "季报", "年报", "预告"],
        "大单/合作": ["大单", "合作", "中标", "签约", "订单"],
        "预订/预售": ["预订", "预售", "盲订", "小订"],
    }
    found = []
    for ev in summary.get("evolution", []):
        note = (ev.get("note") or ev.get("phase") or "")
        ts = ev.get("timestamp", "")[:10]
        for cat, kws in cats.items():
            if any(k in note for k in kws):
                found.append({"type": cat, "note": note, "date": ts})
                break
    return found


def discover_opportunities(topic_id):
    """对某单品话题发现潜在交易机会。

    返回结构化结果：信号强度 / 盈利映射 / 股价背离 / 催化剂 / 机会评分(0-100) /
    方向(看多|看空|观望) / 触发条件 / 风险 / 数据缺口。
    金融数据缺失时自动降级并标注。
    """
    summary = get_topic_summary(topic_id)
    meta = summary["meta"]
    fin = meta.get("financial") or {}
    h = single_product_health(summary)

    # 1) 单品信号强度（社媒势能）
    heat, _ = heat_score(summary)
    signal_strength = round((heat / 100.0) * 0.6 + max(0.0, h["momentum"]) * 0.4 * 100.0 / 100.0, 3)
    # 归一到 0-100
    signal_score = round(min(100.0, heat * 0.7 + max(0.0, h["momentum"]) * 40.0), 1)

    # 2) 盈利映射（需交付/销量 vs 共识）
    delivery = fin.get("delivery_latest") or fin.get("sales_latest")
    consensus = fin.get("consensus")
    earnings_link = {
        "delivery_or_sales": delivery,
        "consensus": consensus,
        "beat": None,
        "note": "",
    }
    if delivery and consensus:
        earnings_link["note"] = f"最新交付/销量「{delivery}」vs 市场预期「{consensus}」，需对比判断超预期幅度。"
        earnings_link["beat"] = "待比对"  # 由人工/agent 在采集时填 beat 标记更准确
    else:
        earnings_link["note"] = "缺少交付量/销量或市场预期数据，盈利映射暂不计入评分。"

    # 3) 股价背离度
    price_change = fin.get("price_change_pct")
    dislocation = {"price_change_pct": price_change, "momentum": round(h["momentum"], 3), "signal": "数据不足"}
    dislocation_score = 0.0
    if price_change is not None:
        try:
            pc = float(price_change)
        except (TypeError, ValueError):
            pc = None
        if pc is not None:
            # 单品升温(pc 相对) 与股价反向 → 错配
            if h["momentum"] > 0.15 and pc <= 0:
                dislocation["signal"] = "正向错配（单品走强而股价走弱，潜在低估）"
                dislocation_score = min(100.0, 50.0 + h["momentum"] * 100.0)
            elif h["momentum"] < -0.15 and pc > 0:
                dislocation["signal"] = "反向错配（单品走弱而股价走强，警惕利好出尽）"
                dislocation_score = min(100.0, 50.0 + abs(h["momentum"]) * 100.0)
            elif h["momentum"] > 0.15 and pc > 0:
                dislocation["signal"] = "同向确认（单品与股价齐升，趋势强化）"
                dislocation_score = 30.0
            else:
                dislocation["signal"] = "无明显背离"
                dislocation_score = 10.0

    # 4) 催化剂密度
    catalysts = _extract_catalysts(summary)
    catalyst_score = min(100.0, len(catalysts) / 3.0 * 100.0)

    # 5) 评分
    data_gaps = []
    if price_change is None:
        data_gaps.append("缺少股价区间涨跌幅（price_change_pct）")
    if not delivery:
        data_gaps.append("缺少交付量/销量时点数据")
    if not consensus:
        data_gaps.append("缺少市场预期共识")

    weights = {
        "signal": 0.40,
        "dislocation": 0.35,
        "catalyst": 0.25,
    }
    if price_change is None and not delivery:
        # 纯社媒信号，机会评分降权
        score = round(signal_score * 0.8, 1)
        confidence = "低（仅社媒信号，缺金融面验证）"
    else:
        score = round(
            signal_score * weights["signal"] +
            dislocation_score * weights["dislocation"] +
            catalyst_score * weights["catalyst"], 1)
        confidence = "中" if data_gaps else "高"

    # 方向
    if price_change is not None:
        try:
            pc = float(price_change)
        except (TypeError, ValueError):
            pc = 0.0
    else:
        pc = 0.0
    if dislocation["signal"].startswith("正向错配") or (h["momentum"] > 0.15 and pc <= 0):
        direction = "看多"
    elif dislocation["signal"].startswith("反向错配") or (h["momentum"] < -0.15 and pc > 0):
        direction = "看空"
    else:
        direction = "观望"

    # 触发条件 & 风险
    triggers = []
    if h["momentum"] > 0.15 and pc <= 0:
        triggers.append("单品势能持续走强且股价未反映时，分批建仓/加仓观察")
    if catalysts:
        triggers.append("临近催化剂（" + "、".join(c["type"] for c in catalysts[:3]) + "）前 1-2 周提高关注")
    if not triggers:
        triggers.append("等待单品势能或股价出现明确拐点信号再加库")

    risks = []
    if h["neg_ratio"] > 0.4:
        risks.append(f"负面情绪占比 {h['neg_ratio']*100:.0f}% 偏高，口碑拐点可能反噬销量")
    if price_change is None:
        risks.append("金融面数据缺失，机会判断未经验证，仅作线索而非结论")
    if not delivery:
        risks.append("缺少交付/销量验证，势能能否转化为收入存疑")
    if not risks:
        risks.append("需持续监控势能拐点与股价背离收敛节奏")

    return {
        "topic_id": topic_id,
        "company": fin.get("company", ""),
        "ticker": fin.get("ticker", ""),
        "product": fin.get("product", ""),
        "score": score,
        "direction": direction,
        "confidence": confidence,
        "signal_score": signal_score,
        "dislocation": dislocation,
        "dislocation_score": round(dislocation_score, 1),
        "catalysts": catalysts,
        "catalyst_score": round(catalyst_score, 1),
        "earnings_link": earnings_link,
        "triggers": triggers,
        "risks": risks,
        "data_gaps": data_gaps,
    }
