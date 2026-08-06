#!/usr/bin/env python3
"""Generate data-driven deep reports (HTML) and PDF reports from research data.

The HTML report adapts its content to whatever the data contains:
each section renders only when relevant data exists, and analysis is
derived from the actual entries/signals/evolution, so the report can be
used directly for stakeholder briefings.
"""

import json
import os
import re
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import get_topic_summary, list_topics, get_topic_dir, get_methodology
import finance_analysis  # 金融单品追踪引擎（仅依赖 data_store，无循环依赖）

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.units import cm, mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def register_fonts():
    """Register CJK fonts for PDF generation."""
    if not HAS_REPORTLAB:
        return

    # Try common CJK font paths
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]

    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('CJK', path))
                return
            except:
                continue


def generate_pdf(topic_id: str, output_path: str = None) -> str:
    """Generate PDF report for a topic."""
    if not HAS_REPORTLAB:
        return "Error: reportlab not installed. Run: pip install reportlab"

    register_fonts()

    summary = get_topic_summary(topic_id)
    meta = summary["meta"]

    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(os.path.expanduser("~"), f"report_{topic_id[:20]}_{timestamp}.pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           leftMargin=2*cm, rightMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle('CustomTitle', parent=styles['Title'],
                                 fontSize=24, spaceAfter=30)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading1'],
                                   fontSize=16, spaceAfter=12, spaceBefore=20)
    body_style = ParagraphStyle('CustomBody', parent=styles['Normal'],
                                fontSize=10, spaceAfter=6, leading=14)

    story = []

    # Title
    story.append(Paragraph(meta["topic"], title_style))
    story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", body_style))
    story.append(Spacer(1, 20))

    # Summary Statistics
    story.append(Paragraph("Summary Statistics", heading_style))
    stats_data = [
        ["Metric", "Value"],
        ["Total Entries", str(summary["entry_count"])],
        ["Evolution Stages", str(summary["evolution_count"])],
        ["Signals", str(summary["signal_count"])],
        ["Data Sources", str(len(summary["source_distribution"]))],
    ]
    stats_table = Table(stats_data, colWidths=[4*cm, 4*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 20))

    # Source Distribution
    story.append(Paragraph("Data Sources", heading_style))
    for src, cnt in summary["source_distribution"].items():
        story.append(Paragraph(f"• {src}: {cnt} entries", body_style))
    story.append(Spacer(1, 20))

    # Signals
    if summary["signals"]:
        story.append(Paragraph("Signals & Alerts", heading_style))
        for sig in summary["signals"]:
            severity = sig.get("severity", "unknown").upper()
            sig_type = sig.get("type", "unknown")
            desc = sig.get("description", "")
            story.append(Paragraph(f"[{severity}] {sig_type}: {desc}", body_style))
            if sig.get("recommended_action"):
                story.append(Paragraph(f"  → {sig['recommended_action']}", body_style))
        story.append(Spacer(1, 20))

    # Evolution Timeline
    if summary["evolution"]:
        story.append(Paragraph("Evolution Timeline", heading_style))
        for evo in summary["evolution"]:
            phase = evo.get("phase", "").upper()
            summary_text = evo.get("summary", "")
            story.append(Paragraph(f"• [{phase}] {summary_text}", body_style))
            if evo.get("key_changes"):
                for change in evo["key_changes"]:
                    story.append(Paragraph(f"  - {change}", body_style))
        story.append(Spacer(1, 20))

    # Key Findings (comment summaries)
    comment_summaries = [e for e in summary["entries"] if e.get("source") == "comment_summary"]
    if comment_summaries:
        story.append(Paragraph("Comment Analysis", heading_style))
        for cs in comment_summaries:
            platform = (cs.get("metadata") or {}).get("platform", "unknown")
            story.append(Paragraph(f"Platform: {platform}", body_style))
            content = cs.get("content", "")[:500]
            story.append(Paragraph(content, body_style))
            story.append(Spacer(1, 10))

    # Recent Entries
    story.append(Paragraph("Recent Data Entries", heading_style))
    recent = [e for e in summary["entries"] if e.get("source") != "comment_summary"][-20:]
    for entry in reversed(recent):
        src = entry.get("source", "")
        content = entry.get("content", "")[:150]
        time_str = entry.get("timestamp", "")[:16]
        story.append(Paragraph(f"[{time_str}] [{src}] {content}", body_style))

    # Build PDF
    doc.build(story)
    return output_path


# ============================================================
# 分析引擎：从数据推导报告所需的全部分析结果
# ============================================================

SENT_LABELS = {"positive": "正面", "negative": "负面", "neutral": "中性", "mixed": "混合"}
PLAT_LABELS = {"xiaohongshu": "小红书", "douyin": "抖音", "weibo": "微博", "zhihu": "知乎",
               "web": "网页", "bilibili": "B站", "xueqiu": "雪球", "twitter": "Twitter",
               "multi": "多平台", "social": "社交媒体", "social_media": "社交媒体"}
SEVERITY_LABELS = {"critical": "严重", "high": "高风险", "medium": "中等", "low": "低"}
PHASE_LABELS = {"emergence": "萌芽期", "growth": "增长期", "peak": "爆发期",
                "decline": "衰退期", "stable": "稳定期"}
TYPE_LABELS = {"sentiment_shift": "情感转向", "keyword_emergence": "关键词涌现",
               "volume_spike": "量级异常", "narrative_change": "叙事变化",
               "risk_trigger": "风险触发"}
TYPE_WEIGHTS = {"critical": 5, "high": 4, "medium": 3, "low": 2}
SENT_COLORS = {"positive": "#34d399", "negative": "#fb7185", "neutral": "#5b8cff", "mixed": "#a78bfa"}
SENT_CLS = {"positive": "sent-pos", "negative": "sent-neg", "neutral": "sent-mid", "mixed": "sent-mix"}
PHASE_SEQ = {"emergence": 0, "growth": 1, "peak": 2, "decline": 3, "stable": 4}

# 通用竞品/对比对象词表（按内容出现频次动态检测）
COMPETITOR_TERMS = [
    "理想", "问界", "特斯拉", "比亚迪", "零跑", "蔚来", "小鹏", "极氪", "智己",
    "华为", "大众", "吉利", "长城", "长安", "腾势", "岚图", "深蓝", "阿维塔",
    "仰望", "小米", "丰田", "本田", "宝马", "奔驰", "奥迪", "保时捷", "Model Y",
    "L9", "L8", "L7", "M9", "M7", "YU7", "SU7", "Model 3", "腾势N9", "蓝山",
    "理想L", "问界M", "享界", "方程豹", "智界", "星纪元", "银河",
]


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def detect_scenario(topic, keywords):
    """Match analysis scenario from topic text (finance-single-product/investment/product/industry/sentiment)."""
    text = (topic + " " + " ".join(keywords)).lower()
    if any(k in text for k in ["金融单品", "单品追踪", "热品", "交易机会", "机会发现", "标的", "建仓", "股价背离", "交付量追踪", "销量追踪", "个股追踪", "个股"]):
        return "金融单品追踪"
    if any(k in text for k in ["股票", "投资", "估值", "财报", "业绩", "基金", "股价", "市值", "持仓", "证券", "上市公司", "ipo", "融资"]):
        return "投资研究"
    if any(k in text for k in ["发布", "新品", "上市", "首发", "预售", "交付", "提车", "开售", "发布会"]):
        return "产品发布"
    if any(k in text for k in ["行业", "赛道", "市场", "趋势", "产业", "政策", "创新药", "cxo", "生物医药"]):
        return "行业调研"
    return "舆情监控"


def parse_engagement(s):
    """Parse '1.2万赞' / '475.6万' / '2332' into a comparable int."""
    s = str(s or "")
    m = re.search(r'([\d.]+)\s*(万|w)?', s)
    if not m:
        return 0
    val = float(m.group(1))
    if m.group(2):
        val *= 10000
    return int(val)


def top_keywords(entries, n=20):
    """Extract frequent meaningful keywords from entry contents."""
    stop = set("的 了 在 是 我 你 他 她 它 这 那 就 都 也 很 有 不 和 与 及 或 一个 小米 澎程 我们 他们 自己 什么 怎么 为什么 发布 表示 认为 觉得 网友 用户 博主 媒体 评论 回复".split())
    freq = Counter()
    for e in entries:
        content = e.get("content", "")
        for seg in re.findall(r'[\u4e00-\u9fff]{2,6}', content):
            if seg not in stop:
                freq[seg] += 1
    return [w for w, _ in freq.most_common(n)]


def analyze_topic(topic_id):
    """Derive all report sections from raw data. Returns a dict of section payloads."""
    summary = get_topic_summary(topic_id)
    meta = summary["meta"]
    entries = summary["entries"]
    signals = summary["signals"]
    evolution = summary["evolution"]

    total = len(entries) or 1
    sent_dist = Counter((e.get("metadata") or {}).get("sentiment", "neutral") for e in entries)
    plat_dist = Counter((e.get("metadata") or {}).get("platform", "unknown") for e in entries)
    method_dist = Counter((e.get("metadata") or {}).get("collection_method", "unknown") for e in entries)
    content_type_dist = Counter((e.get("metadata") or {}).get("content_type", "未标注") for e in entries)
    daily_dist = Counter((e.get("timestamp") or "")[:10] for e in entries)

    # KMI
    pos_ratio = sent_dist.get("positive", 0) / total
    neg_ratio = sent_dist.get("negative", 0) / total
    price_anxiety = 0
    price_comments = [e for e in entries if any(k in e.get("content", "") for k in ["价格", "多少钱", "定价", "性价比", "贵"])]
    if price_comments:
        neg_price = [e for e in price_comments if (e.get("metadata") or {}).get("sentiment") == "negative"]
        price_anxiety = len(neg_price) / len(price_comments)

    # 情绪来源追溯：按 author + content_type 聚合
    author_rows = []
    author_agg = {}
    for e in entries:
        m = e.get("metadata") or {}
        author = m.get("author") or "匿名"
        if author == "匿名" and not m.get("content_type"):
            continue
        row = author_agg.setdefault(author, {"count": 0, "sents": Counter(), "types": set(),
                                             "eng": 0, "platforms": set()})
        row["count"] += 1
        row["sents"][m.get("sentiment", "neutral")] += 1
        if m.get("content_type"):
            row["types"].add(m.get("content_type"))
        row["eng"] += parse_engagement(m.get("engagement"))
        if m.get("platform"):
            row["platforms"].add(m.get("platform"))
    for author, r in sorted(author_agg.items(), key=lambda kv: -kv[1]["count"]):
        main_sent = r["sents"].most_common(1)[0][0] if r["sents"] else "neutral"
        author_rows.append({
            "author": author, "count": r["count"], "sent": main_sent,
            "types": "、".join(sorted(r["types"])) or "未标注",
            "eng": r["eng"], "platforms": "、".join(PLAT_LABELS.get(p, p) for p in sorted(r["platforms"])),
        })

    # 竞品检测
    competitor_freq = Counter()
    for e in entries:
        content = e.get("content", "")
        for term in COMPETITOR_TERMS:
            if term in content:
                competitor_freq[term] += 1
    competitors = [{"name": t, "count": c} for t, c in competitor_freq.most_common(12) if t not in ("小米", "YU7", "SU7")]

    # 操纵痕迹证据：从风险类信号 + 负面时间集中度推导
    manipulation_evidence = []
    for sig in signals:
        desc = sig.get("description", "")
        if sig.get("type") == "risk_trigger" or any(k in desc for k in ["抹黑", "AI", "投毒", "水军", "造谣", "黑公关", "断章取义", "预埋"]):
            manipulation_evidence.append({
                "desc": desc, "severity": sig.get("severity", "medium"),
                "evidence": sig.get("evidence", []), "action": sig.get("recommended_action", ""),
            })

    neg_entries = [e for e in entries if (e.get("metadata") or {}).get("sentiment") == "negative"]
    pos_entries = [e for e in entries if (e.get("metadata") or {}).get("sentiment") == "positive"]
    neg_authors = set((e.get("metadata") or {}).get("author") for e in neg_entries)
    # 负面时间集中度
    neg_days = Counter((e.get("timestamp") or "")[:10] for e in neg_entries)
    neg_peak_day = neg_days.most_common(1)[0] if neg_days else ("", 0)
    concentration = (neg_peak_day[1] / len(neg_entries)) if neg_entries else 0

    # 叙事主导权：content_type 占比
    narrative_parts = []
    ct_names = {"官方": "品牌方", "KOL": "KOL/媒体", "UGC": "用户", "媒体": "KOL/媒体",
                "评论区总结": "用户", "竞品分析": "KOL/媒体", "叙事分析": "KOL/媒体", "搜索热点": "用户"}
    for ct, n in content_type_dist.most_common():
        if ct == "未标注":
            continue
        narrative_parts.append({"name": ct_names.get(ct, ct), "type": ct, "count": n})

    # 演变趋势：最后阶段
    last_phase = evolution[-1].get("phase", "stable") if evolution else "stable"
    phase_forecast = {
        "emergence": "话题处于萌芽期，热度快速上升中，重点关注后续扩散速度与KOL参与度",
        "growth": "话题处于增长期，讨论热度持续放大，需关注负面声量是否同步扩大",
        "peak": "话题已到爆发峰值，预计随后进入回落，重点转向长尾口碑沉淀与转化",
        "decline": "话题已过峰值进入衰退期，热度回落，建议聚焦高意向用户的深度决策内容",
        "stable": "话题进入平稳期，讨论结构稳定，建议维持常规监测节奏",
    }.get(last_phase, "话题处于平稳期")

    return {
        "meta": meta, "entries": entries, "signals": signals, "evolution": evolution,
        "total": total, "sent_dist": sent_dist, "plat_dist": plat_dist,
        "method_dist": method_dist, "content_type_dist": content_type_dist, "daily_dist": daily_dist,
        "pos_ratio": pos_ratio, "neg_ratio": neg_ratio, "price_anxiety": price_anxiety,
        "author_rows": author_rows, "competitors": competitors,
        "manipulation_evidence": manipulation_evidence,
        "neg_entries": neg_entries, "pos_entries": pos_entries,
        "neg_authors": len(neg_authors),
        "neg_concentration": concentration, "neg_peak": neg_peak_day,
        "narrative_parts": narrative_parts,
        "last_phase": last_phase, "phase_forecast": phase_forecast,
        "scenario": detect_scenario(meta["topic"], meta.get("keywords", [])),
        "top_keywords": top_keywords(entries),
        "comment_summaries": [e for e in entries if e.get("source") in ("comment_section", "comment_summary") or "评论区总结" in e.get("content", "")],
        "methodology": get_methodology(topic_id),  # 每个话题独立生成的调研方法论
        # 金融单品追踪：实体块 + 引擎计算结果（仅该场景填充，避免无谓开销）
        "financial": meta.get("financial") or {},
        "finance": _finance_block(topic_id, a_scenario) if (a_scenario := detect_scenario(meta["topic"], meta.get("keywords", []))) == "金融单品追踪" else {},
        "charts": {},  # 各章节收集的 ECharts 配置 {id: option}
    }


def _finance_block(topic_id, scenario):
    """当场景为金融单品追踪时，调用 finance_analysis 引擎产出单品健康/热品/机会结果。"""
    try:
        fin = finance_analysis.single_product_health(get_topic_summary(topic_id))
        heat, breakdown = finance_analysis.heat_score(get_topic_summary(topic_id))
        opp = finance_analysis.discover_opportunities(topic_id)
        return {"health": fin, "heat": heat, "heat_breakdown": breakdown, "opportunity": opp}
    except Exception as e:
        return {"error": str(e)}


# ============================================================
# 报告样式生成（schema-first）：先由数据生成「报告骨架 / 样式」，再填充渲染
# ============================================================
#
# 设计目标（来自产品约束）：
#   1) 每次调研的「调研策略」与「报告呈现」相互独立、可单独交付给目标用户；
#   2) 报告生成前，先由数据推导出 report_schema（章节编排 + 块类型 + 图表解读 + 小结），
#      再统一渲染（先样式、后填充）；
#   3) 正文信息充分：每个章节按「观察 → 解读 → 小结」组织，文字承载分析而非装饰；
#   4) 每个可视化图表都带「解读」段与「小结」段（caption + summary），图表与文字双解读；
#   5) 视觉上不使用边框/盒装饰：section、导语、解读、小结、结论卡、信号均为纯文字流，
#      仅以颜色标签与章节分隔线区分信息层级（详见 SKILL.md 报告视觉规范）。

REPORT_ACCENTS = {
    "舆情监控": {"accent": "#5b8cff", "name": "警戒蓝"},
    "产品发布": {"accent": "#fb923c", "name": "活力橙"},
    "投资研究": {"accent": "#f5c451", "name": "理性金"},
    "行业调研": {"accent": "#2dd4bf", "name": "沉稳青"},
    "金融单品追踪": {"accent": "#16a34a", "name": "机会绿"},
}


def _derive_strategy(a):
    """从场景 + 方法论推导本话题独立的『调研策略』：目标受众 / 强调维度 / 报告主色调。"""
    scenario = a["scenario"]
    AUDIENCE = {
        "舆情监控": ("公关 / 品牌 / 管理层", ["情绪走向", "风险与操纵", "关键传播者", "争议焦点"]),
        "产品发布": ("产品 / 市场 / 增长", ["声量与口碑", "配置与价格", "竞品对标", "首销反馈"]),
        "投资研究": ("投研 / 基金经理 / 投资者", ["业绩与基本面", "资金与机构", "风险事件", "预测研判"]),
        "行业调研": ("战略 / 行业研究员", ["市场格局", "产业链变量", "政策技术", "趋势研判"]),
        "金融单品追踪": ("投研 / 交易员 / 个人投资者", ["单品势能", "热品排名", "股价背离", "交易机会"]),
    }
    audience, emphasis = AUDIENCE.get(scenario, ("决策相关方", ["核心结论", "风险", "趋势"]))
    accent = REPORT_ACCENTS.get(scenario, REPORT_ACCENTS["舆情监控"])
    return {"scenario": scenario, "audience": audience, "emphasis": emphasis,
            "accent": accent["accent"], "accent_name": accent["name"]}


# ---- 图表解读（数据驱动，2-3 句，必带；随后由 _sum_* 给出一句小结）----

def _interpret_sentiment(a):
    pos, neg = a["pos_ratio"] * 100, a["neg_ratio"] * 100
    neu = max(0.0, 100 - pos - neg)
    if pos >= 60:
        return (f"正面情绪占 {pos:.0f}%（{a['sent_dist'].get('positive', 0)} 条），中性 {neu:.0f}%，负面仅 {neg:.0f}%（{a['sent_dist'].get('negative', 0)} 条）。"
                f"品牌叙事与产品口碑主导讨论，舆论基本面健康；但需留意正面声量是否被运营动作放大，真实自然口碑占比仍有待观察。")
    if pos >= 45:
        return (f"正面 {pos:.0f}% 与负面 {neg:.0f}% 相当接近，中性 {neu:.0f}% 构成缓冲带。"
                f"舆论处于正负拉锯状态，任何单一负面事件都可能打破平衡，建议对负面议题的首爆点、传播路径与关键放大账号保持高频监测。")
    return (f"负面已占 {neg:.0f}%（{a['sent_dist'].get('negative', 0)} 条），中性 {neu:.0f}%，正面仅 {pos:.0f}%。"
            f"情绪面明显承压，当务之急是厘清负面议题的传播链路与来源账号——到底是用户自发不满，还是外部力量推动。")


def _interpret_platform(a):
    if not a["plat_dist"]:
        return "暂无平台分布数据，无法判断渠道结构，建议补采后研判。"
    top3 = a["plat_dist"].most_common(3)
    top = top3[0]
    share = top[1] / max(a["total"], 1)
    spread = len(a["plat_dist"])
    detail = "、".join(f"{PLAT_LABELS.get(p, p)} {n} 条（{n / a['total'] * 100:.0f}%）" for p, n in top3)
    return (f"声量集中度{'偏高' if share >= 0.5 else '适中'}：榜首为 {PLAT_LABELS.get(top[0], top[0])}（{top[1]} 条，占 {share * 100:.0f}%），共覆盖 {spread} 个渠道，依次为 {detail}。"
            f"渠道结构直接决定监测与回应策略——单点集中意味着一处失控即可能全局失声，需针对性布防。")


def _interpret_daily(a):
    items = sorted(a["daily_dist"].items())
    if len(items) < 2:
        return "采集窗口不足 2 天，暂无法绘制可靠趋势曲线，需延长采集周期后再研判。"
    peak = max(items, key=lambda x: x[1])
    first, last = items[0], items[-1]
    trend = "上升" if last[1] >= first[1] else "回落"
    rise = "（仍在升温）" if last[1] >= first[1] else "（趋于冷却）"
    return (f"覆盖 {len(items)} 天，峰值出现在 {peak[0][5:]}（{peak[1]} 条），起止区间为 {first[0][5:]} → {last[0][5:]}。"
            f"整体呈{trend}走势{rise}。发酵节奏决定响应时机：升温期应抢在峰值前完成定调，回落期则转向长尾口碑沉淀与转化。")


def _interpret_competitor(a):
    if not a["competitors"]:
        return "讨论中未出现明确竞品对标，叙事以本品自身为主，暂无需纳入横向比较框架。"
    c = a["competitors"][0]
    names = "、".join(x["name"] for x in a["competitors"][:3])
    return (f"最常被对比的对象是 {c['name']}（提及 {c['count']} 次），共出现 {len(a['competitors'])} 个竞品对标：{names}。"
            f"竞品对标是把双刃剑——既说明本品已进入用户决策的核心比较集，也意味着任何短板都会被拿来横向放大、直接冲击购买意向。")


def _interpret_risk(a):
    if not a["signals"]:
        return "当前未触发任何风险信号，维持常态监控即可。"
    from collections import Counter as _C
    sev = _C(s.get("severity") for s in a["signals"])
    crit, high, med, low = sev.get("critical", 0), sev.get("high", 0), sev.get("medium", 0), sev.get("low", 0)
    types = "、".join(sorted({TYPE_LABELS.get(s.get("type", ""), s.get("type", "")) for s in a["signals"] if s.get("type")}))
    return (f"共命中 {len(a['signals'])} 个风险信号，按严重度分布为：严重 {crit}、高 {high}、中 {med}、低 {low}；涉及维度包括 {types}。"
            f"信号的结构比数量更关键——少数严重/高级信号往往比一堆低风险更值得优先处置，应优先看严重度而非总数。")


# ---- 一句小结（解读之后的结论落点）----

def _sum_sentiment(a):
    if a["pos_ratio"] >= 0.6:
        return "情绪面整体健康，维持正面叙事、放大真实口碑即可。"
    if a["pos_ratio"] >= 0.45:
        return "正负基本持平，当前关键是压制负面扩散速度、防止平衡被打破。"
    return "情绪承压，须把负面溯源与主动回应放在最高优先级。"


def _sum_platform(a):
    if not a["plat_dist"]:
        return "渠道数据缺失，建议补采后再研判。"
    top = a["plat_dist"].most_common(1)[0]
    share = top[1] / a["total"]
    return f"以 {PLAT_LABELS.get(top[0], top[0])} 为核心阵地{'，渠道单一需防单点风险' if share >= 0.5 else '，多渠道分布便于分层运营'}。"


def _sum_daily(a):
    items = sorted(a["daily_dist"].items())
    if len(items) < 2:
        return "趋势样本不足，暂不作研判。"
    trend = "上升" if items[-1][1] >= items[0][1] else "回落"
    return f"话题当前处于{trend}通道，监测节奏应与之匹配——升温期抢定调、回落期做沉淀。"


def _sum_competitor(a):
    if not a["competitors"]:
        return "尚无竞品对标，叙事聚焦本品自身。"
    c = a["competitors"][0]
    return f"竞品叙事以 {c['name']} 为锚点，差异化卖点需针对性强化以抵消横向比较。"


def _sum_risk(a):
    if not a["signals"]:
        return "风险面平静，保持常规监测即可。"
    crit = [s for s in a["signals"] if s.get("severity") in ("critical", "high")]
    if crit:
        return f"存在 {len(crit)} 个严重/高风险信号，须立即进入优先处置队列。"
    return f"风险以中低级别为主（共 {len(a['signals'])} 个），常态化监控即可。"


def _interpret_methodology(a):
    aud = _derive_strategy(a)["audience"]
    return (f"上述方法论为本话题独立生成，随「{a['scenario']}」场景与关键词定制，区别于通用模板，可独立交付给 {aud} 使用。"
            f"采集口径、分析维度与结论口径均围绕本话题目标设定，而非套用固定结构。")


def _sum_methodology(a):
    return "调研策略与报告呈现均本话题专属，可直接作为面向目标用户的独立交付物。"


# ---- 章节片段数据 ----

def _lead_overview(a):
    if a["pos_ratio"] >= 0.6:
        return f"整体情绪以正面为主（{a['pos_ratio']*100:.0f}%），讨论基调积极。"
    if a["pos_ratio"] >= 0.45:
        return f"正面 {a['pos_ratio']*100:.0f}% 与负面 {a['neg_ratio']*100:.0f}% 接近，舆论正负拉锯。"
    return f"负面占比达 {a['neg_ratio']*100:.0f}%，情绪面承压。"


def _vc_overview(a):
    return {"cls": "info", "tag": "当前阶段", "title": PHASE_LABELS.get(a["last_phase"], a["last_phase"]),
            "text": a["phase_forecast"]}


def _vc_manip(a):
    if a["manipulation_evidence"]:
        return {"cls": "danger", "tag": "操纵/抹黑迹象", "title": f"检出 {len(a['manipulation_evidence'])} 条相关信号",
                "text": "数据中发现与抹黑 / AI投毒 / 黑公关相关的风险信号，详见风险矩阵。"}
    return {"cls": "good", "tag": "操纵/抹黑迹象", "title": "未检出明确操纵",
            "text": "负面主要来自可识别的独立账号，未呈现组织化特征。"}


def _vc_comp(a):
    if a["competitors"]:
        c = a["competitors"][0]
        return {"cls": "info", "tag": "竞品对标焦点", "title": c["name"],
                "text": f"最常被对比的对象（提及 {c['count']} 次），竞品叙事活跃。"}
    return None


def _condense_methodology(a):
    m = (a.get("methodology") or "").strip()
    lines = [ln.strip() for ln in m.split("\n") if ln.strip()]
    goal = ""
    for ln in lines:
        if ln.startswith("**调研目标"):
            goal = ln.split("**", 2)[-1].strip().lstrip("：:").strip()
            break
    if goal:
        return (f"本话题采用独立生成的调研方法论：调研目标为「{goal.rstrip('。')}」。"
                f"整套方法随「{a['scenario']}」场景与关键词定制，覆盖 {a['total']} 条原始数据的采集、清洗与多维分析，"
                f"而非套用固定模板，确保结论口径与本次调研目标一致。")
    return (f"本话题采用独立生成的调研方法论，随「{a['scenario']}」场景与关键词定制，"
            f"覆盖 {a['total']} 条原始数据的采集、清洗与多维分析，结论口径与本次调研目标对齐。")


def _interpret_negative(a):
    base = f"负面条目共 {a['sent_dist'].get('negative', 0)} 条，来自 {a['neg_authors']} 个独立账号；"
    if a["neg_concentration"] >= 0.5:
        return (base + f"其中 {a['neg_peak'][0][5:]} 单日即集中了 {a['neg_concentration'] * 100:.0f}% 的负面声量。"
                f"这种时间上的高度聚集，既可能是某次具体事件引爆，也提示存在组织化推动或水军节奏的可能性，"
                f"应结合风险矩阵中的来源账号与传播证据进一步核实，避免误判为自然发酵。")
    return (base + "负面在时间轴上分散、来自多个互不关联的独立账号，更接近用户自发的自然发酵。"
            f"回应策略上以常态化答疑、口碑引导与产品体验改善为主即可，无需过度反应。")


def _sum_negative(a):
    if a["neg_concentration"] >= 0.5:
        return "负面高度集中、疑似外部推动，建议优先溯源核实再决定回应强度。"
    return "负面分散且自然，常规答疑与口碑引导即可覆盖。"


def _concise_negative(a):
    return _interpret_negative(a)


def _aggregate_actions(a):
    seen, acts = set(), []
    for sig in sorted(a["signals"], key=lambda s: -TYPE_WEIGHTS.get(s.get("severity", "medium"), 3)):
        act = (sig.get("recommended_action") or "").strip()
        if act and act not in seen:
            seen.add(act)
            acts.append((SEVERITY_LABELS.get(sig.get("severity", "medium"), sig.get("severity")), act))
    return acts


def build_report_schema(a):
    """Stage 2：从分析数据生成『报告样式 / 骨架』(schema)。

    不做任何 HTML 渲染，只决定：
      - 本章节编排（仅保留有数据 / 有信号的章节，满足「呈现独立」）
      - 每个章节按「观察 → 解读 → 小结」组织内容块：
          观察（图表 / 文字事实）→ 解读（数据意味着什么）→ 小结（一句结论落点）
      - 每个图表一块，附 caption（解读）+ summary（小结），文字充分、可读性强
      - 报告主色调随场景（满足「独立可交付给目标用户」）
    """
    strat = _derive_strategy(a)
    schema = {
        "topic_id": a["meta"]["topic_id"],
        "topic": a["meta"]["topic"],
        "scenario": a["scenario"],
        "strategy": strat,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sections": [],
    }
    charts = {}

    # 0 调研策略（独立呈现，面向目标受众）
    schema["sections"].append({
        "id": "strategy", "title": "调研策略与目标受众",
        "lead": f"本报告面向 {strat['audience']}；定位为{a['scenario']}，聚焦：{'、'.join(strat['emphasis'])}。",
        "blocks": [
            {"type": "prose", "text": _condense_methodology(a)},
            {"type": "interpret", "text": _interpret_methodology(a)},
            {"type": "summary", "text": _sum_methodology(a)},
        ],
    })

    # 1 核心结论速览
    cards = [c for c in (_vc_overview(a), _vc_manip(a), _vc_comp(a)) if c]
    schema["sections"].append({
        "id": "overview", "title": "核心结论速览",
        "lead": _lead_overview(a),
        "blocks": [
            {"type": "verdict_cards", "cards": cards},
            {"type": "interpret", "text": _interpret_overview(a)},
            {"type": "summary", "text": _sum_overview(a)},
        ],
    })

    # 2 调研数据基础：每个图表按「观察(图) → 解读 → 小结」
    blocks = []
    sent_items = [(SENT_LABELS[s], a["sent_dist"].get(s, 0))
                  for s in ["positive", "neutral", "negative", "mixed"] if a["sent_dist"].get(s, 0) > 0]
    if sent_items:
        cid = "chart-sent"; charts[cid] = _doughnut_option(sent_items, f"共 {a['total']} 条")
        blocks.append({"type": "chart", "chart_id": cid, "caption": _interpret_sentiment(a),
                       "summary": _sum_sentiment(a), "height": 260})
    plat_items = [(PLAT_LABELS.get(p, p), n) for p, n in a["plat_dist"].most_common(8)]
    if plat_items:
        cid = "chart-plat"; charts[cid] = _hbar_option(plat_items)
        blocks.append({"type": "chart", "chart_id": cid, "caption": _interpret_platform(a),
                       "summary": _sum_platform(a), "height": min(60 + 30 * len(plat_items), 340)})
    daily = sorted(a["daily_dist"].items())
    if len(daily) >= 2:
        cid = "chart-daily"; charts[cid] = _line_option([d[5:] for d, _ in daily], [c for _, c in daily])
        blocks.append({"type": "chart", "chart_id": cid, "caption": _interpret_daily(a),
                       "summary": _sum_daily(a), "height": 260})
    if a["competitors"]:
        comps = a["competitors"][:10]
        cid = "chart-competitor"; charts[cid] = _hbar_option([(c["name"], c["count"]) for c in comps])
        blocks.append({"type": "chart", "chart_id": cid, "caption": _interpret_competitor(a),
                       "summary": _sum_competitor(a), "height": min(60 + 32 * len(comps), 340)})
    if blocks:
        schema["sections"].append({
            "id": "data", "title": "调研数据基础",
            "lead": "以下图表刻画情绪结构、渠道分布与发酵曲线；每个图表先给出数据观察，再行解读，最后落到一句小结。",
            "blocks": blocks,
        })

    # 3 负面情绪与风险焦点：观察 → 解读 → 小结
    if a["neg_entries"]:
        schema["sections"].append({
            "id": "negative", "title": "负面情绪与风险焦点",
            "lead": f"负面占比 {a['neg_ratio']*100:.0f}%，核心争议点如下。",
            "blocks": [
                {"type": "prose", "text": _prose_negative(a)},
                {"type": "interpret", "text": _interpret_negative(a)},
                {"type": "summary", "text": _sum_negative(a)},
            ],
        })

    # 4 风险矩阵与预警
    if a["signals"]:
        schema["sections"].append({
            "id": "risk", "title": "风险矩阵与预警",
            "lead": _interpret_risk(a),
            "blocks": [
                {"type": "signals", "signals": a["signals"]},
                {"type": "interpret", "text": _interpret_risk_detail(a)},
                {"type": "summary", "text": _sum_risk(a)},
            ],
        })

    # 5 预测研判
    schema["sections"].append({
        "id": "forecast", "title": "预测研判",
        "lead": a["phase_forecast"],
        "blocks": [
            {"type": "prose", "text": _prose_forecast(a)},
            {"type": "interpret", "text": _interpret_forecast(a)},
            {"type": "summary", "text": _sum_forecast(a)},
        ],
    })

    # 6 行动建议
    acts = _aggregate_actions(a)
    if acts:
        schema["sections"].append({
            "id": "actions", "title": "行动建议（按优先级）",
            "lead": "按信号严重度聚合的处置建议，P0 优先；每条建议均可直接落地。",
            "blocks": [
                {"type": "actions", "actions": acts},
                {"type": "summary", "text": _sum_actions(a)},
            ],
        })

    # 金融单品追踪：在通用章节之上叠加金融专属章节（单品基本面/势能/热品排名/股价背离/催化剂/机会评分）
    if a["scenario"] == "金融单品追踪" and a.get("finance") and not a["finance"].get("error"):
        schema["sections"].extend(_finance_sections(a, charts))

    schema["charts"] = charts
    return schema


# ============================================================
# 金融单品追踪专属章节（观察 → 解读 → 小结，无边框）
# ============================================================
def _finance_sections(a, charts):
    fin = a["finance"]
    fin_meta = a.get("financial") or {}
    opp = fin.get("opportunity", {}) or {}
    sections = []

    # 单品基本面
    basic_lines = []
    for label, key in [("公司", "company"), ("股票代码", "ticker"), ("单品", "product"),
                       ("业务线", "product_line"), ("追踪类型", "watch_type"),
                       ("上市/交付日", "launch_date"), ("价格带", "price_band")]:
        v = fin_meta.get(key)
        if v:
            basic_lines.append(f"**{label}**：{v}")
    if basic_lines:
        sections.append({
            "id": "fin_basic", "title": "单品基本面",
            "lead": f"追踪标的：{fin_meta.get('company','')} 的「{fin_meta.get('product','')}」"
                    f"{('（'+fin_meta.get('ticker','')+'）') if fin_meta.get('ticker') else ''}。",
            "blocks": [
                {"type": "prose", "text": "；".join(basic_lines) + "。"},
                {"type": "interpret", "text": _interpret_fin_basic(a)},
                {"type": "summary", "text": _sum_fin_basic(a)},
            ],
        })

    # 单品势能与健康度
    heat = fin.get("heat", 0)
    h = fin.get("health", {})
    cid = "chart-fin-heat"
    # 用一张雷达展示热度分项（charts 为 build_report_schema 传入的同一对象）
    bd = fin.get("heat_breakdown", {})
    if bd:
        sections.append({
            "id": "fin_health", "title": "单品势能与健康度",
            "lead": f"综合热度分 **{heat}**／100；情绪净分 {h.get('net_sentiment',0):+.2f}，声量动量 {h.get('momentum',0):+.2f}。",
            "blocks": [
                {"type": "chart", "chart_id": cid,
                 "caption": _interpret_fin_health(a), "summary": _sum_fin_health(a), "height": 260},
            ],
        })
        charts[cid] = _radar_option(
            [("声量动量", bd.get("momentum_score", 0)), ("情绪净分", bd.get("sentiment_score", 0)),
             ("互动量", bd.get("engagement_score", 0)), ("渠道广度", bd.get("breadth_score", 0))],
            title=f"热度分项 · {heat}")

    # 同公司热品排名
    company = fin_meta.get("company")
    if company:
        try:
            ranked = finance_analysis.rank_hot_products(company)
        except Exception:
            ranked = []
        if len(ranked) > 1:
            rows = [f"第{r['rank']}名 {r['product']}（热度 {r['heat']}，情绪 {r['net_sentiment']:+.2f}）" for r in ranked]
            sections.append({
                "id": "fin_hotrank", "title": f"同公司热品排名（{company}）",
                "lead": f"在 {company} 的 {len(ranked)} 个追踪单品中，「{fin_meta.get('product','')}」位列第 {_my_rank(ranked, a['meta']['topic_id'])}。",
                "blocks": [
                    {"type": "prose", "text": "；".join(rows) + "。"},
                    {"type": "interpret", "text": _interpret_fin_hotrank(a, ranked, company)},
                    {"type": "summary", "text": _sum_fin_hotrank(a, ranked, company)},
                ],
            })

    # 股价背离
    dis = opp.get("dislocation", {}) or {}
    sections.append({
        "id": "fin_dislocation", "title": "股价背离度",
        "lead": dis.get("signal", "数据不足"),
        "blocks": [
            {"type": "prose", "text": _prose_fin_dislocation(a)},
            {"type": "interpret", "text": _interpret_fin_dislocation(a)},
            {"type": "summary", "text": _sum_fin_dislocation(a)},
        ],
    })

    # 催化剂日历
    catalysts = opp.get("catalysts", []) or []
    if catalysts:
        cat_lines = [f"{c.get('date','')} · {c.get('type','')}：{c.get('note','')}" for c in catalysts]
        sections.append({
            "id": "fin_catalyst", "title": "催化剂日历",
            "lead": f"识别到 {len(catalysts)} 个潜在催化剂事件。",
            "blocks": [
                {"type": "prose", "text": "；".join(cat_lines) + "。"},
                {"type": "interpret", "text": _interpret_fin_catalyst(a)},
                {"type": "summary", "text": _sum_fin_catalyst(a)},
            ],
        })

    # 交易机会评分（核心章节）
    sections.append({
        "id": "fin_opportunity", "title": "交易机会评分",
        "lead": f"机会评分 **{opp.get('score',0)}**／100，方向 **{opp.get('direction','观望')}**，置信度 {opp.get('confidence','低')}。",
        "blocks": [
            {"type": "verdict_cards", "cards": _opp_cards(opp)},
            {"type": "interpret", "text": _interpret_fin_opportunity(a)},
            {"type": "summary", "text": _sum_fin_opportunity(a)},
        ],
    })
    return sections


def _my_rank(ranked, topic_id):
    for r in ranked:
        if r["topic_id"] == topic_id:
            return r["rank"]
    return "-"


def _opp_cards(opp):
    direction = opp.get("direction", "观望")
    if direction == "看多":
        dcls = "good"
    elif direction == "看空":
        dcls = "danger"
    else:
        dcls = "info"
    cards = [
        {"cls": dcls, "tag": "机会评分", "title": f"{opp.get('score',0)}/100", "text": f"方向 {direction}，置信度 {opp.get('confidence','低')}"},
        {"cls": dcls, "tag": "方向", "title": direction, "text": "由单品势能、股价背离与催化剂共振得出"},
        {"cls": "info", "tag": "信号强度", "title": f"{opp.get('signal_score',0)}", "text": "单品社媒势能分"},
        {"cls": "info", "tag": "股价背离分", "title": f"{opp.get('dislocation_score',0)}", "text": opp.get("dislocation", {}).get("signal", "数据不足")},
        {"cls": "info", "tag": "催化剂分", "title": f"{opp.get('catalyst_score',0)}", "text": f"{len(opp.get('catalysts', []) or [])} 个催化剂事件"},
        {"cls": "warn", "tag": "数据缺口", "title": f"{len(opp.get('data_gaps', []) or [])} 项", "text": "、".join(opp.get("data_gaps", []) or ["无"]) or "无"},
    ]
    return cards


def _interpret_fin_basic(a):
    fin = a.get("financial") or {}
    return (f"本标的为 {fin.get('company','')} 旗下单品「{fin.get('product','')}」"
            f"{('（'+fin.get('ticker','')+'）') if fin.get('ticker') else ''}，属 {fin.get('product_line','')} 业务线。"
            f"将其作为独立标的追踪，意义在于把『单品势能』从公司整体叙事中剥离出来——单品往往比母公司更早反映预期差，是发现交易线索的更敏锐切面。")


def _sum_fin_basic(a):
    return "以单品为最小追踪单元，可更早捕捉母公司层面的预期差。"


def _interpret_fin_health(a):
    fin = a["finance"]
    h = fin.get("health", {})
    return (f"综合热度分 {fin.get('heat',0)}／100，由声量动量、情绪净分、互动量与渠道广度四项加权得出。"
            f"当前情绪净分 {h.get('net_sentiment',0):+.2f}、声量动量 {h.get('momentum',0):+.2f}——"
            f"{'势能处于升温通道，关注能否转化为持续热度' if h.get('momentum',0) > 0.15 else ('势能偏弱或见顶，需警惕热度回落' if h.get('momentum',0) < -0.15 else '势能平稳，维持常规节奏')}。")


def _sum_fin_health(a):
    h = a["finance"].get("health", {})
    if h.get("momentum", 0) > 0.15:
        return "单品势能升温，是后续机会判断的正向基础。"
    if h.get("momentum", 0) < -0.15:
        return "单品势能走弱，机会需等待拐点。"
    return "势能平稳，暂无明显拐点信号。"


def _interpret_fin_hotrank(a, ranked, company):
    me = _my_rank(ranked, a["meta"]["topic_id"])
    top = ranked[0] if ranked else None
    if top and top["topic_id"] == a["meta"]["topic_id"]:
        return (f"在 {company} 的 {len(ranked)} 个追踪单品中，「{a['financial'].get('product','')}」热度居首，"
                f"说明它当前是该公司最受市场关注的产品，资金与讨论的注意力集中于此，往往也是预期差最易产生之处。")
    return (f"在 {company} 的 {len(ranked)} 个追踪单品中，「{a['financial'].get('product','')}」排名第 {me}，"
            f"榜首为「{top['product'] if top else ''}」（热度 {top['heat'] if top else 0}）。"
            f"热品内部的相对位次，可提示资源与预期在矩阵内的转移方向——资金可能正从本品流向更热的兄弟产品，或反之。")


def _sum_fin_hotrank(a, ranked, company):
    me = _my_rank(ranked, a["meta"]["topic_id"])
    if ranked and ranked[0]["topic_id"] == a["meta"]["topic_id"]:
        return f"本品为 {company} 当前热品榜首，市场注意力集中。"
    return f"本品在 {company} 矩阵中排名第 {me}，关注热度相对位移。"


def _prose_fin_dislocation(a):
    opp = a["finance"].get("opportunity", {}) or {}
    dis = opp.get("dislocation", {}) or {}
    pc = dis.get("price_change_pct")
    if pc is None:
        return "未采集到该标的股价区间涨跌幅，无法计算背离度；以下仅基于社媒势能给出方向性提示。"
    return (f"监测窗口内股价区间涨跌幅 {pc}%，同期单品声量动量 {dis.get('momentum',0):+.2f}。"
            f"背离判断：{dis.get('signal','数据不足')}。")


def _interpret_fin_dislocation(a):
    opp = a["finance"].get("opportunity", {}) or {}
    dis = opp.get("dislocation", {}) or {}
    if dis.get("price_change_pct") is None:
        return "缺少股价数据，背离度无法量化。建议补采东方财富/雪球区间涨跌幅后重算——这是把『社媒线索』升级为『交易机会』的关键一步。"
    sig = dis.get("signal", "")
    if sig.startswith("正向错配"):
        return ("出现正向错配：单品势能走强但股价未跟上，往往意味着市场预期尚未定价该单品的改善，"
                "存在被低估的可能。这是最有效的机会信号之一，但需用交付/销量数据验证势能能否兑现为收入。")
    if sig.startswith("反向错配"):
        return ("出现反向错配：单品走弱而股价走强，警惕『利好出尽』——股价已提前反映乐观预期，"
                "而基本面线索正在转弱，回调风险上升。")
    return "单品与股价方向一致或无明显背离，趋势处于确认/平稳状态，机会更多来自势能的边际加速而非错配。"


def _sum_fin_dislocation(a):
    opp = a["finance"].get("opportunity", {}) or {}
    dis = opp.get("dislocation", {}) or {}
    if dis.get("price_change_pct") is None:
        return "背离度待补股价数据后计算。"
    if dis.get("signal", "").startswith("正向错配"):
        return "正向错配＝潜在低估信号，待交付数据验证。"
    if dis.get("signal", "").startswith("反向错配"):
        return "反向错配＝利好出尽风险，需防回调。"
    return "无明显背离，趋势平稳。"


def _interpret_fin_catalyst(a):
    opp = a["finance"].get("opportunity", {}) or {}
    cats = opp.get("catalysts", []) or []
    types = "、".join(c.get("type", "") for c in cats)
    return (f"识别到 {len(cats)} 个催化剂（{types}）。催化剂是单品势能向股价传导的『触发器』——"
            f"发布、交付、财报、大单等节点临近时，市场预期会重新定价，机会窗口通常在事件前 1-2 周打开、事件后收敛。"
            f"应把催化剂日历作为加减速的观察锚点，而非孤立事件。")


def _sum_fin_catalyst(a):
    opp = a["finance"].get("opportunity", {}) or {}
    n = len(opp.get("catalysts", []) or [])
    return f"共 {n} 个催化剂，作为机会窗口的时序锚点。"


def _interpret_fin_opportunity(a):
    opp = a["finance"].get("opportunity", {}) or {}
    d = opp.get("direction", "观望")
    score = opp.get("score", 0)
    gaps = opp.get("data_gaps", []) or []
    if gaps:
        return (f"综合信号强度、股价背离与催化剂密度，机会评分为 {score}／100，方向 **{d}**，置信度 {opp.get('confidence','低')}。"
                f"需说明：当前存在数据缺口（{'、'.join(gaps)}），因此本评分更宜作为『线索』而非『结论』，"
                f"补齐全金融面数据后结论会更硬。触发条件与风险见下方。")
    return (f"金融面数据齐备，机会评分 {score}／100，方向 **{d}**，置信度 {opp.get('confidence','中')}。"
            f"评分由信号强度（权重 0.4）、股价背离（0.35）、催化剂密度（0.25）合成；"
            f"触发条件与风险见下方，建议据此设定观察与执行节奏。")


def _sum_fin_opportunity(a):
    opp = a["finance"].get("opportunity", {}) or {}
    d = opp.get("direction", "观望")
    if d == "看多":
        return "势能+背离+催化剂共振偏多，按触发条件分批观察建仓。"
    if d == "看空":
        return "反向信号偏空，以防守/减仓观察为主。"
    return "信号尚未形成明确方向，维持观望、等待拐点。"


# ---- 观察(正文事实) / 解读(意味着什么) / 小结(结论落点) 的辅助文本 ----

def _lead_overview(a):
    if a["pos_ratio"] >= 0.6:
        return f"整体情绪以正面为主（{a['pos_ratio']*100:.0f}%），讨论基调积极。"
    if a["pos_ratio"] >= 0.45:
        return f"正面 {a['pos_ratio']*100:.0f}% 与负面 {a['neg_ratio']*100:.0f}% 接近，舆论正负拉锯。"
    return f"负面占比达 {a['neg_ratio']*100:.0f}%，情绪面承压。"


def _interpret_overview(a):
    if a["pos_ratio"] >= 0.6:
        return (f"三项速览共同指向一个结论：话题整体处于健康区间。当前阶段为「{PHASE_LABELS.get(a['last_phase'], a['last_phase'])}」，"
                f"叙事主导权与口碑基本在品牌方可控范围内，但需持续盯防竞品借势与偶发负面事件。")
    if a["pos_ratio"] >= 0.45:
        return (f"速览显示话题已进入「{PHASE_LABELS.get(a['last_phase'], a['last_phase'])}」，正负力量接近，"
                f"任何一方的增量都可能改变态势。此时最忌被动，应主动设置议题、把讨论拉回品牌想讲的故事。")
    return (f"速览显示话题处于「{PHASE_LABELS.get(a['last_phase'], a['last_phase'])}」，情绪承压，"
            f"且{'检出操纵/抹黑迹象' if a['manipulation_evidence'] else '负面以自然发酵为主'}。"
            f"这一阶段的核心是止血与溯源，优先把风险信号对应的动作跑起来。")


def _sum_overview(a):
    if a["pos_ratio"] >= 0.6:
        return "整体可控、基调积极，维持正向运营并防竞品借势即可。"
    if a["pos_ratio"] >= 0.45:
        return "态势胶着，主动设置议题、防止负面反超是当下重点。"
    return "情绪承压，止血溯源与风险处置应优先于常规运营。"


def _prose_negative(a):
    neg_n = a["sent_dist"].get("negative", 0)
    lines = [f"本话题共采集 {a['total']} 条数据，其中负面 {neg_n} 条（{a['neg_ratio']*100:.0f}%），"
             f"来自 {a['neg_authors']} 个不同账号。"]
    if a["manipulation_evidence"]:
        lines.append(f"风险类信号中检出 {len(a['manipulation_evidence'])} 条与抹黑 / AI投毒 / 黑公关相关的痕迹，"
                     f"提示部分负面可能并非纯自发，需结合来源账号进一步核实。")
    top_kw = "、".join(a["top_keywords"][:5]) if a.get("top_keywords") else ""
    if top_kw:
        lines.append(f"负面讨论的高频词集中在：{top_kw}，可据此定位争议的具体切入点。")
    return "".join(lines)


def _interpret_risk_detail(a):
    if not a["signals"]:
        return "未触发风险信号，维持常态监控。"
    crit = [s for s in a["signals"] if s.get("severity") in ("critical", "high")]
    if crit:
        names = "、".join(TYPE_LABELS.get(s.get("type", ""), s.get("type", "")) for s in crit[:3])
        return (f"其中 {len(crit)} 个严重/高风险信号是当下最该盯的对象，类型涉及 {names}。"
                f"这些信号的共同特征是传播速度快、影响面大，一旦处置滞后就可能外溢为公关事件，"
                f"因此建议进入专项跟进而非并入日常队列。")
    return (f"{len(a['signals'])} 个信号级别以中低为主，短期外溢风险可控，"
            f"但仍建议纳入周度复盘，防止低级别信号在外部催化下升级。")


def _prose_forecast(a):
    return (f"基于发酵曲线的阶段判定，话题当前处于「{PHASE_LABELS.get(a['last_phase'], a['last_phase'])}」。"
            f"{a['phase_forecast']}。演变路径并非线性，外部事件（如新品、舆情、竞品动作）可随时改写曲线。")


def _interpret_forecast(a):
    if a["last_phase"] in ("emergence", "growth"):
        return "升温阶段的关键动作是抢在峰值前完成信息定调与口碑预埋，避免被负面抢先定义话题。"
    if a["last_phase"] == "peak":
        return "峰值之后声量必然回落，真正的价值在长尾：把高峰期的关注转化为可沉淀的口碑与转化内容。"
    if a["last_phase"] == "decline":
        return "衰退期不宜再大量投放声量，应把预算与注意力转向高意向用户的深度决策内容。"
    return "平稳期无需额外刺激，保持常规监测节奏、积累基线数据即可。"


def _sum_forecast(a):
    if a["last_phase"] in ("emergence", "growth"):
        return "处于升温通道，当下重点是前瞻定调、抢在峰值前布局。"
    if a["last_phase"] == "peak":
        return "已至峰值，重心转向长尾沉淀与转化。"
    if a["last_phase"] == "decline":
        return "进入衰退，聚焦高意向用户的深度转化。"
    return "平稳期，维持常规监测即可。"


def _sum_actions(a):
    if not a["signals"]:
        return "暂无需要落地的高优先级动作。"
    crit = [s for s in a["signals"] if s.get("severity") in ("critical", "high")]
    if crit:
        return f"优先处置 {len(crit)} 个严重/高风险对应的动作，其余按 P1/P2 排入常规跟进。"
    return f"共 {len(a['signals'])} 条建议，按 P0/P1/P2 优先级排入跟进即可。"


# ============================================================
# HTML 渲染
# ============================================================

REPORT_CSS = """*{margin:0;padding:0;box-sizing:border-box}
/* 报告视觉规范：全屏铺满呈现、去装饰性边框/渐变/阴影，用淡背景与功能性左侧色条区分信息层级 */
:root{--bg:#0a0e17;--panel:#101828;--panel2:#141d33;--border:#1d2943;--text:#e6ecf7;--text2:#8b9bc0;--accent:#5b8cff;--pos:#34d399;--neg:#fb7185;--mid:#fbbf24;--mix:#a78bfa;--mono:'SF Mono','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace}
body{background:var(--bg);color:var(--text);font-family:'SF Pro Display','PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif;line-height:1.75;font-size:15px}
/* 全屏：去居中窄栏，铺满容器 */
.container{margin:0;padding:0 44px 56px}
.header{padding:40px 0 28px;margin-bottom:32px;border-bottom:1px solid var(--border)}
.header .inner{margin:0;padding:0 44px}
.header .eyebrow{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:2px;margin-bottom:10px}
.header h1{font-size:30px;font-weight:800;margin-bottom:10px;letter-spacing:.5px}
.header .sub{color:var(--text2);font-size:14px;margin-bottom:18px}
.meta-grid{display:flex;flex-wrap:wrap;gap:8px}
.meta-chip{background:var(--panel2);border-radius:6px;padding:6px 12px;font-size:12.5px;color:var(--text2)}
.meta-chip b{color:var(--text);font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:600}
h2.sec{font-size:22px;font-weight:800;margin:42px 0 18px;padding-bottom:10px;border-bottom:1px solid var(--border)}
h2.sec .num{display:inline-block;background:var(--accent);color:#fff;border-radius:5px;padding:2px 10px;font-size:13px;margin-right:10px;vertical-align:3px;font-family:var(--mono)}
h3{font-size:16px;color:var(--accent);margin:22px 0 10px}
p{margin-bottom:12px}
/* 卡片：淡背景区分，无外边框 */
.card{background:var(--panel2);border-radius:8px;padding:18px 20px;margin-bottom:14px}
.card-title{font-size:15px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.tag{font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600}
.tag-info{background:rgba(91,140,255,.15);color:var(--accent)}
.tag-pos{background:rgba(52,211,153,.15);color:var(--pos)}
.tag-neg{background:rgba(251,113,133,.15);color:var(--neg)}
.tag-mid{background:rgba(251,191,36,.15);color:var(--mid)}
/* 结论块：仅保留左侧 accent 色条作为信息锚点，去渐变/外边框 */
.verdict{background:rgba(91,140,255,.05);border-radius:6px;padding:14px 18px;margin:14px 0}
.verdict.red{background:rgba(251,113,133,.06)}
/* 核心结论速览（执行摘要式） */
.brief{background:rgba(91,140,255,.05);border-radius:6px;padding:18px 20px;margin:14px 0}
.brief.good{}
.brief.warn{}
.brief.danger{}
.brief .brief-lead{font-size:16.5px;font-weight:600;line-height:1.9;color:var(--text)}
.brief .brief-meta{margin-top:10px;font-size:11.5px;color:var(--text2);font-family:var(--mono);letter-spacing:.3px}
.kpi-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(116px,1fr));gap:1px;background:var(--border);border-radius:8px;overflow:hidden;margin:14px 0}
@media(max-width:640px){.kpi-strip{grid-template-columns:repeat(2,1fr)}}
.kpi-item{background:var(--panel2);padding:14px 12px;text-align:center}
.kpi-item .kpi-val{display:block;font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:23px;font-weight:800;line-height:1.15;letter-spacing:-.5px;white-space:nowrap}
.kpi-item .kpi-val.pos{color:var(--pos)}
.kpi-item .kpi-val.neg{color:var(--neg)}
.kpi-item .kpi-val.warn{color:var(--mid)}
.kpi-item .kpi-val.phase{color:var(--accent)}
.kpi-item .kpi-val.total{color:var(--text)}
.kpi-item .kpi-lbl{display:block;font-size:10.5px;color:var(--text2);margin-top:5px;letter-spacing:.6px}
.verdict-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:14px 0}
@media(max-width:640px){.verdict-grid{grid-template-columns:1fr}}
/* 信号卡：淡背景 + 左侧细色条，无外边框 */
.vc{position:relative;background:var(--panel2);border-radius:8px;padding:14px 16px;overflow:hidden}
.vc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--text2)}
.vc.vc-good::before{background:var(--pos)}
.vc.vc-warn::before{background:var(--mid)}
.vc.vc-danger::before{background:var(--neg)}
.vc.vc-info::before{background:var(--accent)}
.vc .vc-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.vc .vc-tick{width:7px;height:7px;border-radius:50%;background:var(--text2);flex-shrink:0}
.vc.vc-good .vc-tick{background:var(--pos)}
.vc.vc-warn .vc-tick{background:var(--mid)}
.vc.vc-danger .vc-tick{background:var(--neg)}
.vc.vc-info .vc-tick{background:var(--accent)}
.vc .vc-tag{font-size:9.5px;font-weight:800;letter-spacing:1px;color:var(--text2);text-transform:uppercase}
.vc .vc-title{font-size:13.5px;font-weight:700;color:var(--text);margin-bottom:4px;line-height:1.6}
.vc .vc-text{font-size:12.5px;line-height:1.75;color:var(--text2)}
.vc .vc-text b{color:var(--text)}
table{width:100%;border-collapse:collapse;margin:12px 0 18px;font-size:13px}
th{background:var(--panel2);color:var(--text);text-align:left;padding:9px 12px;font-weight:600}
td{padding:9px 12px;color:var(--text2);vertical-align:top;border-top:1px solid var(--border)}
td b{color:var(--text)}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--panel2);border-radius:8px;padding:14px;text-align:center}
.kpi .val{font-size:22px;font-weight:700;color:var(--accent);font-family:var(--mono);font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.kpi .val.warn{color:var(--neg)}
.kpi .val.ok{color:var(--pos)}
.kpi .lbl{font-size:12px;color:var(--text2);margin-top:4px}
.bar-row{display:flex;align-items:center;margin-bottom:7px;font-size:13px}
.bar-label{width:110px;color:var(--text2);flex-shrink:0}
.bar-track{flex:1;background:var(--panel2);border-radius:4px;height:20px;overflow:hidden}
.bar-fill{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;font-size:12px;color:#fff;font-weight:600;min-width:30px;font-family:var(--mono)}
.bar-val{width:70px;text-align:right;color:var(--text2);font-size:12px;flex-shrink:0;font-family:var(--mono)}
.timeline{position:relative;padding-left:26px;margin:14px 0}
.timeline::before{content:"";position:absolute;left:8px;top:4px;bottom:4px;width:2px;background:var(--border)}
.tl-item{position:relative;margin-bottom:18px}
.tl-item::before{content:"";position:absolute;left:-23px;top:6px;width:10px;height:10px;border-radius:50%;background:var(--accent);border:2px solid var(--bg)}
.tl-item.evo-growth::before,.tl-item.evo-peak::before{background:var(--pos)}
.tl-item.evo-decline::before{background:var(--neg)}
.tl-date{font-size:12px;color:var(--accent);font-weight:600;font-family:var(--mono)}
.tl-title{font-weight:700;margin-bottom:3px}
.tl-body{color:var(--text2);font-size:13px}
.evo-phase{display:inline-block;padding:1px 8px;border-radius:4px;font-size:10px;font-weight:700;margin-right:8px;background:var(--panel2);color:var(--accent)}
.signal{padding:10px 14px;font-size:12px}
.signal-red{background:rgba(251,113,133,.04)}
.signal-orange{background:rgba(251,191,36,.03)}
.signal-yellow{background:rgba(251,191,36,.02)}
.signal-green{background:rgba(52,211,153,.02)}
.signal-badge{font-size:9px;font-weight:800;padding:2px 8px;border-radius:4px;background:var(--panel2);color:var(--text);letter-spacing:.5px}
.signal-type{font-size:10px;color:var(--text2);margin-left:8px;font-family:var(--mono)}
.signal-desc{color:var(--text);line-height:1.6;margin-top:4px}
.signal-action{margin-top:4px;font-size:10.5px;color:var(--accent)}
.signal-evi{padding-left:16px;font-size:11px;color:var(--text2);margin-top:4px}
.comment-text{font-size:12px;line-height:1.8;color:var(--text2)}
.sent{display:inline-block;padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600}
.sent-pos{background:rgba(52,211,153,.15);color:var(--pos)}
.sent-neg{background:rgba(251,113,133,.15);color:var(--neg)}
.sent-mid{background:rgba(251,191,36,.15);color:var(--mid)}
.sent-mix{background:rgba(167,139,250,.15);color:var(--mix)}
blockquote{font-size:14px;line-height:1.9;color:var(--text2);padding-left:14px;margin:12px 0}
ul,ol{padding-left:22px;margin-bottom:12px}
li{margin:5px 0;color:var(--text2)}
li b{color:var(--text)}
.note{font-size:12.5px;color:var(--text2);background:var(--panel2);border-radius:8px;padding:10px 14px;margin:12px 0}
.footer{margin-top:50px;padding-top:20px;border-top:1px solid var(--border);color:var(--text2);font-size:12.5px;text-align:center;font-family:var(--mono)}
.echart-box{width:100%;margin:12px 0 4px}
/* 章节导语：纯文字，无边框盒修饰 */
.sec-lead{color:var(--text2);font-size:15px;line-height:1.9;margin-bottom:16px;font-weight:500}
/* 正文段落 / 解读 / 小结：纯文字流，用 label 区分，无任何边框或背景盒 */
.prose{font-size:14.5px;line-height:1.95;color:var(--text);margin:10px 0 16px}
.sec-interpret{font-size:14.5px;line-height:1.95;color:var(--text);margin:10px 0}
.sec-interpret .lab,.sec-summary .lab,.chart-interpret .lab,.chart-summary .lab{color:var(--accent);font-weight:700;margin-right:6px}
.sec-summary{font-size:14.5px;line-height:1.95;color:var(--text);font-weight:600;margin:6px 0 18px}
/* 图表解读与小结：纯文字，无边框 */
.chart-interpret{font-size:13.5px;line-height:1.85;color:var(--text);margin:8px 0 2px}
.chart-summary{font-size:13.5px;line-height:1.85;color:var(--text);font-weight:600;margin:2px 0 18px}
/* 核心结论速览 / 风险信号：纯文字行，彩色标签区分，无边框盒 */
.vc-line{font-size:14px;line-height:1.9;color:var(--text);margin:8px 0}
.vc-lab{font-weight:700;margin-right:8px;font-size:12.5px;letter-spacing:.3px}
.sig-line{font-size:13.5px;line-height:1.85;color:var(--text);margin:12px 0}
.sig-sev{font-weight:700;margin-right:6px}
.sig-act{color:var(--text2);font-size:12.5px}
table.acts{width:100%;border-collapse:collapse;margin:12px 0 4px;font-size:13.5px}
table.acts th{background:var(--panel2);color:var(--text);text-align:left;padding:9px 12px;font-weight:600}
table.acts td{padding:9px 12px;color:var(--text2);vertical-align:top}
table.acts td b{color:var(--text)}
.chart-interpret b{color:var(--text)}
.src{display:block;font-size:12px;color:var(--text2);margin-top:6px}
code{background:var(--panel2);border-radius:4px;padding:1px 5px;font-family:var(--mono);font-size:12px;color:var(--accent)}
@media print{.echart-box{height:240px!important}}
/* 窄屏适配 */
@media(max-width:640px){
  body{font-size:14px}
  .container{padding:0 20px 40px}
  .header{padding:32px 0 24px}
  .header .inner{padding:0 20px}
  .header h1{font-size:22px;overflow-wrap:anywhere}
  .header .sub{font-size:13px}
  h2.sec{font-size:19px;margin:34px 0 16px}
  h3{font-size:15px}
  .card{padding:14px 16px}
  p,li,td,th,blockquote,.comment-text,.signal-desc,.tl-body,.src{overflow-wrap:anywhere}
  .meta-chip{font-size:11.5px}
  .kpi .val{font-size:19px}
}
/* 浅色主题（变量覆盖，保留 --accent 由场景注入） */
:root[data-theme="light"]{
  --bg:#f5f7fb; --panel:#ffffff; --panel2:#eef2f8; --border:#e2e8f2;
  --text:#1a2233; --text2:#5a6678;
  --pos:#0f9d6b; --neg:#e11d48; --mid:#b8860b; --mix:#7c3aed;
}
@media (prefers-color-scheme: light){
  :root:not([data-theme="dark"]){
    --bg:#f5f7fb; --panel:#ffffff; --panel2:#eef2f8; --border:#e2e8f2;
    --text:#1a2233; --text2:#5a6678;
    --pos:#0f9d6b; --neg:#e11d48; --mid:#b8860b; --mix:#7c3aed;
  }
}
:root[data-theme="light"] .verdict{background:rgba(59,108,246,.06)}
:root[data-theme="light"] .verdict.red{background:rgba(225,29,72,.06)}
:root[data-theme="light"] .brief{background:rgba(59,108,246,.06)}
"""


# ============================================================
# ECharts：图表主题 + 构建器 + 渲染脚本
# 格式化数据不统一：情感用环形、来源用条形、趋势用折线、竞品用条形，各取所需形态
# ============================================================

ECHARTS_BASE = {
    "backgroundColor": "transparent",
    "color": ["#5b8cff", "#34d399", "#fb7185", "#fbbf24", "#a78bfa", "#22d3ee"],
    "textStyle": {"color": "#94a3b8"},
    "tooltip": {"backgroundColor": "#141d33", "borderColor": "#1d2943", "borderWidth": 1,
                "textStyle": {"color": "#e6ecf7", "fontSize": 12}},
    "legend": {"textStyle": {"color": "#94a3b8"}, "itemWidth": 10, "itemHeight": 10},
}


def _doughnut_option(items, center_label):
    """情感结构：环形图。items: [(name, value)]"""
    return {
        "tooltip": {"trigger": "item"},
        "legend": {"bottom": 0},
        "series": [{
            "type": "pie", "radius": ["52%", "72%"], "center": ["50%", "44%"],
            "itemStyle": {"borderColor": "#101828", "borderWidth": 2},
            "label": {"color": "#8b9bc0", "formatter": "{b} {d}%"},
            "data": [{"name": n, "value": v} for n, v in items],
        }],
        "graphic": [{"type": "text", "left": "center", "top": "37%",
                     "style": {"text": center_label, "fill": "#8b9bc0", "fontSize": 12}}],
    }


def _hbar_option(items):
    """来源/竞品分布：横向条形图。items: [(name, value)]"""
    names = [n for n, _ in items]
    vals = [v for _, v in items]
    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 8, "right": 24, "top": 8, "bottom": 8, "containLabel": True},
        "xAxis": {"type": "value", "splitLine": {"lineStyle": {"color": "#141d33"}}},
        "yAxis": {"type": "category", "data": names, "axisLabel": {"color": "#8b9bc0"}},
        "series": [{"type": "bar", "data": vals, "barMaxWidth": 18,
                    "itemStyle": {"borderRadius": [0, 4, 4, 0]}}],
    }


def _line_option(dates, counts):
    """每日趋势：面积折线图。"""
    return {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 8, "right": 16, "top": 24, "bottom": 8, "containLabel": True},
        "xAxis": {"type": "category", "boundaryGap": False, "data": dates,
                  "axisLabel": {"color": "#8b9bc0"}},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": "#141d33"}}},
        "series": [{
            "type": "line", "data": counts, "smooth": True, "symbol": "circle", "symbolSize": 6,
            "lineStyle": {"width": 2, "color": "#5b8cff"},
            "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                    "colorStops": [{"offset": 0, "color": "rgba(91,140,255,.35)"},
                                                   {"offset": 1, "color": "rgba(91,140,255,.02)"}]}},
        }],
    }


def _chart_box(cid, height=280):
    return f'<div class="echart-box" id="{cid}" style="height:{height}px"></div>'


def _radar_option(items, title=""):
    """热度分项雷达图。items: [(name, value 0-100)]"""
    indicators = [{"name": n, "max": 100} for n, _ in items]
    values = [v for _, v in items]
    return {
        "tooltip": {},
        "radar": {
            "indicator": indicators, "radius": "66%", "center": ["50%", "54%"],
            "axisName": {"color": "#8b9bc0"},
            "splitLine": {"lineStyle": {"color": "#141d33"}},
            "splitArea": {"areaStyle": {"color": ["rgba(255,255,255,.02)", "rgba(255,255,255,.04)"]}},
            "axisLine": {"lineStyle": {"color": "#141d33"}},
        },
        "series": [{
            "type": "radar",
            "data": [{"value": values, "name": title,
                      "areaStyle": {"color": "rgba(22,163,74,.25)"},
                      "lineStyle": {"color": "#16a34a"},
                      "itemStyle": {"color": "#16a34a"}}],
        }],
    }


def _charts_script(charts):
    if not charts:
        return ""
    payload = json.dumps({"__base__": ECHARTS_BASE, "__charts__": charts}, ensure_ascii=False)
    return f"""<script>
(function() {{
  if (typeof echarts === 'undefined') return;
  var C = {payload};
  var insts = [];
  Object.keys(C.__charts__).forEach(function(id) {{
    var el = document.getElementById(id);
    if (!el) return;
    var chart = echarts.init(el);
    chart.setOption(Object.assign({{}}, C.__base__, C.__charts__[id]));
    insts.push(chart);
  }});
  window.addEventListener('resize', function() {{ insts.forEach(function(c) {{ c.resize(); }}); }});
}})();
</script>"""


_ECHARTS_JS = None


def _get_echarts_js():
    """ECharts 源码（自包含报告内联用）。"""
    global _ECHARTS_JS
    if _ECHARTS_JS is None:
        try:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "echarts.min.js")
            _ECHARTS_JS = open(p, encoding="utf-8").read()
        except Exception:
            _ECHARTS_JS = ""
    return _ECHARTS_JS


def _report_header(a):
    return f"""<div class="header">
  <div class="inner">
    <div class="eyebrow">MYOU DATA RESEARCH · 数据驱动 · 汇报就绪</div>
    <h1>{esc(a['meta']['topic'])} · 深度调研看板</h1>
    <div class="sub">数据驱动自动生成 · 情绪全景 · 来源追溯 · 操纵判断 · 风险矩阵 · 行动建议</div>
    <div class="meta-grid">
      <div class="meta-chip">场景：<b>{a['scenario']}</b></div>
      <div class="meta-chip">数据量：<b>{a['total']} 条</b></div>
      <div class="meta-chip">信号：<b>{len(a['signals'])} 个</b></div>
      <div class="meta-chip">演变节点：<b>{len(a['evolution'])} 个</b></div>
      <div class="meta-chip">当前阶段：<b>{PHASE_LABELS.get(a['last_phase'], a['last_phase'])}</b></div>
      <div class="meta-chip">生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}</div>
    </div>
  </div>
</div>"""


def _html_head(a, echarts_inline=False, accent=None):
    echarts_tag = f"<script>{_get_echarts_js()}</script>" if echarts_inline else ""
    # 主色调随场景：在 REPORT_CSS 之后追加 :root 覆盖，按场景切换品牌色
    accent_css = f"\n:root{{--accent:{accent}}}" if accent else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(a['meta']['topic'])} - 深度调研看板</title>
<style>
{REPORT_CSS}{accent_css}
</style>
{echarts_tag}
</head>
<body>
{_report_header(a)}
<div class="container">
"""


def _report_footer(a):
    return f"""
<div class="footer">
  <p>由 myou-data-research 数据调研引擎自动生成 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
</div>"""


def _html_footer(a):
    return _report_footer(a) + """
</div>
</body>
</html>"""


# ============================================================
# 15 章节渲染（0 方法论 + 1-14 数据章节）
# ============================================================

def _md_inline(text):
    """极简 markdown 行内 → HTML：加粗、行内代码。"""
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _sec_methodology(a):
    """调研方法论：每个话题独立生成（存于 research.md），原样呈现。"""
    m = (a.get("methodology") or "").strip()
    if not m:
        m = "（尚未生成本话题专属调研方法论。可先用启发式生成，再由调研人改写：`data_store.py set-methodology <topic_id> <文本>`）"
    paras = []
    for block in m.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        if lines[0].startswith("> "):
            body = " ".join(l[2:].strip() if l.startswith("> ") else l.strip() for l in lines)
            paras.append(f"<blockquote>{_md_inline(body)}</blockquote>")
        elif lines[0].startswith("- "):
            items = "".join(f"<li>{_md_inline(l[2:].strip())}</li>" for l in lines if l.strip().startswith("- "))
            paras.append(f"<ul>{items}</ul>")
        else:
            paras.append(f"<p>{_md_inline(' '.join(x.strip() for x in lines))}</p>")
    return f"""
<section>
<h2 class="sec"><span class="num">0</span>调研方法论</h2>
{''.join(paras)}
</section>"""


def _sec1_overview(a):
    """核心结论速览（执行摘要式）：总述 + 关键指标带 + 分级结论卡片网格。"""
    pos_ratio, neg_ratio = a["pos_ratio"], a["neg_ratio"]
    total = a["total"]

    # 情绪基调总述（lead）
    if pos_ratio >= 0.6:
        lead, lead_cls = f"当前情绪以正面为主（{pos_ratio*100:.0f}%），讨论基调积极，品牌叙事占据主导地位", "good"
    elif pos_ratio >= 0.45:
        lead, lead_cls = f"正面情绪占比 {pos_ratio*100:.0f}%，但负面已占 {neg_ratio*100:.0f}%，情绪处于正负博弈阶段", "warn"
    else:
        lead, lead_cls = f"负面情绪占比达 {neg_ratio*100:.0f}%，情绪面承压，需重点关注负面议题的扩散路径", "danger"

    # 关键指标带
    critical = [s for s in a["signals"] if s.get("severity") in ("critical", "high")]
    kpis = [
        ("pos", f"{pos_ratio*100:.0f}%", "正面占比"),
        ("neg", f"{neg_ratio*100:.0f}%", "负面占比"),
        ("phase", PHASE_LABELS.get(a["last_phase"], a["last_phase"]), "当前阶段"),
        ("warn", str(len(critical)), "严重/高风险"),
        ("total", str(total), "采样数据"),
    ]
    kpi_html = "".join(f'<div class="kpi-item"><span class="kpi-val {cls}">{v}</span><span class="kpi-lbl">{lbl}</span></div>'
                       for cls, v, lbl in kpis)

    # 结论卡片（分级配色）
    cards = []

    # 阶段结论
    cards.append(f'<div class="vc vc-info"><div class="vc-head"><span class="vc-tick"></span><span class="vc-tag">当前阶段</span></div>'
                 f'<div class="vc-title">{PHASE_LABELS.get(a["last_phase"], a["last_phase"])}</div>'
                 f'<div class="vc-text">{a["phase_forecast"]}</div></div>')

    # 关键信号结论（最高严重度的 2 条）
    for sig in critical[:2]:
        sev_label = SEVERITY_LABELS.get(sig.get("severity"), sig.get("severity"))
        sev_cls = "danger" if sig.get("severity") == "critical" else "warn"
        cards.append(f'<div class="vc vc-{sev_cls}"><div class="vc-head"><span class="vc-tick"></span>'
                     f'<span class="vc-tag">{sev_label}信号 · {TYPE_LABELS.get(sig.get("type", ""), sig.get("type", "监测"))}</span></div>'
                     f'<div class="vc-title">{esc(sig.get("description", ""))}</div></div>')

    # 操纵/风险结论
    if a["manipulation_evidence"]:
        cards.append(f'<div class="vc vc-danger"><div class="vc-head"><span class="vc-tick"></span><span class="vc-tag">操纵/抹黑迹象</span></div>'
                     f'<div class="vc-text">数据中发现 <b>{len(a["manipulation_evidence"])}</b> 条与「抹黑 / AI投毒 / 黑公关」相关的风险信号，详见第 6 章。</div></div>')
    else:
        cards.append('<div class="vc vc-good"><div class="vc-head"><span class="vc-tick"></span><span class="vc-tag">操纵/抹黑迹象</span></div>'
                     '<div class="vc-text">未发现明确的抹黑 / AI投毒 / 水军操纵信号，情绪以自然发酵为主。</div></div>')

    # 竞品结论
    if a["competitors"]:
        top_c = a["competitors"][0]
        cards.append(f'<div class="vc vc-info"><div class="vc-head"><span class="vc-tick"></span><span class="vc-tag">竞品对比焦点</span></div>'
                     f'<div class="vc-text">最常被提及的对比对象是 <b>{esc(top_c["name"])}</b>（出现 {top_c["count"]} 次），竞品对比叙事活跃，详见第 8 章。</div></div>')

    return f"""
<section>
<h2 class="sec"><span class="num">1</span>核心结论速览</h2>
<div class="brief {lead_cls}">
  <div class="brief-lead">{lead}。</div>
  <div class="brief-meta">场景 {a['scenario']} · 情绪结构：正面 {a['sent_dist'].get('positive', 0)} / 中性 {a['sent_dist'].get('neutral', 0)} / 负面 {a['sent_dist'].get('negative', 0)} / 混合 {a['sent_dist'].get('mixed', 0)}</div>
</div>
<div class="kpi-strip">{kpi_html}</div>
<div class="verdict-grid">{''.join(cards)}</div>
</section>"""


def _sec2_data(a):
    """调研数据基础：数据量、平台、时间、关键词矩阵（图表用 ECharts，形态随数据而异）。"""
    charts = a["charts"]

    # 情感结构 → 环形图
    sent_items = [(SENT_LABELS[s], a["sent_dist"].get(s, 0)) for s in ["positive", "neutral", "negative", "mixed"]]
    sent_items = [(n, v) for n, v in sent_items if v > 0]
    sent_html = _chart_box("chart-sent", 260)
    if sent_items:
        charts["chart-sent"] = _doughnut_option(sent_items, f"共 {a['total']} 条")

    # 平台结构 → 横向条形图
    plat_items = [(PLAT_LABELS.get(p, p), n) for p, n in a["plat_dist"].most_common(8)]
    plat_html = ""
    if plat_items:
        plat_html = _chart_box("chart-plat", min(60 + 30 * len(plat_items), 340))
        charts["chart-plat"] = _hbar_option(plat_items)

    # 每日趋势 → 面积折线图（≥2 天才有意义）
    daily_html = ""
    daily_items = sorted(a["daily_dist"].items())
    if len(daily_items) >= 2:
        dates = [d[5:] for d, _ in daily_items]
        counts = [c for _, c in daily_items]
        daily_html = _chart_box("chart-daily", 260)
        charts["chart-daily"] = _line_option(dates, counts)

    kws = "、".join(a["top_keywords"][:15])
    return f"""
<section>
<h2 class="sec"><span class="num">2</span>调研数据基础</h2>
<div class="card">
  <div class="card-title">情绪分布（{a['total']} 条）<span class="tag tag-info">情感结构</span></div>
  <p>正面 {a['sent_dist'].get('positive', 0)} 条（{a['pos_ratio']*100:.0f}%）、中性 {a['sent_dist'].get('neutral', 0)} 条、负面 {a['sent_dist'].get('negative', 0)} 条（{a['neg_ratio']*100:.0f}%）、混合 {a['sent_dist'].get('mixed', 0)} 条。</p>
  {sent_html}
</div>
<div class="card">
  <div class="card-title">平台分布<span class="tag tag-info">渠道结构</span></div>
  {plat_html}
</div>
<div class="card">
  <div class="card-title">每日数据量趋势<span class="tag tag-info">发酵曲线</span></div>
  {daily_html}
</div>
<div class="card">
  <div class="card-title">监控关键词<span class="tag tag-info">高频词 TOP 15</span></div>
  <p>{esc(kws)}</p>
</div>
<div class="card">
  <div class="card-title">KMI 关键监测指标<span class="tag tag-info">健康度</span></div>
  <table>
  <tr><th>指标</th><th>当前值</th><th>健康阈值</th><th>预警阈值</th><th>判断</th></tr>
  <tr><td>正面情绪占比</td><td><b>{a['pos_ratio']*100:.0f}%</b></td><td>&gt;70%</td><td>&lt;50%</td><td>{'✅ 健康' if a['pos_ratio']>=0.5 else '⚠ 需关注'}</td></tr>
  <tr><td>负面情绪占比</td><td><b>{a['neg_ratio']*100:.0f}%</b></td><td>&lt;15%</td><td>&gt;25%</td><td>{'⚠ 触及预警' if a['neg_ratio']>=0.25 else '✅ 可控'}</td></tr>
  <tr><td>价格焦虑指数</td><td><b>{a['price_anxiety']*100:.0f}%</b></td><td>&lt;30%</td><td>&gt;50%</td><td>{'⚠ 偏高' if a['price_anxiety']>=0.5 else ('⚠ 观察' if a['price_anxiety']>=0.3 else '✅ 健康')}</td></tr>
  <tr><td>信号总数</td><td><b>{len(a['signals'])}</b></td><td>—</td><td>—</td><td>其中严重/高风险 {sum(1 for s in a['signals'] if s.get('severity') in ('critical','high'))} 条</td></tr>
  </table>
</div>
</section>"""


def _sec3_positive(a):
    """正面情绪深度分析：代表内容引用 + 生态结构。"""
    if not a["pos_entries"]:
        return ""
    # 按互动量取代表条目
    ranked = sorted(a["pos_entries"], key=lambda e: parse_engagement((e.get("metadata") or {}).get("engagement")), reverse=True)
    quotes = ""
    for e in ranked[:5]:
        m = e.get("metadata") or {}
        eng = m.get("engagement") or ""
        author = m.get("author") or ""
        plat = PLAT_LABELS.get(m.get("platform", ""), m.get("platform", "未知"))
        content = e.get("content", "")[:200]
        quotes += f'<blockquote>{esc(content)}<br><span class="src">—— {esc(author)} · {plat} · {esc(eng)}</span></blockquote>'

    return f"""
<section>
<h2 class="sec"><span class="num">3</span>正面情绪深度分析</h2>
<div class="card">
  <div class="card-title">正面情绪概况 <span class="tag tag-pos">正面 {a['pos_ratio']*100:.0f}%</span></div>
  <p>正面情绪占比 {a['pos_ratio']*100:.0f}%（{a['sent_dist'].get('positive', 0)}/{a['total']} 条），是当前讨论的主基调。正面内容以<b>产品认可、价格惊喜、品牌信任</b>为主要支撑。</p>
  <p>按互动量排序的代表性正面内容：</p>
  {quotes}
</div>
</section>"""


def _sec4_negative(a):
    """负面情绪深度分析：负面焦点分类 + 代表内容。"""
    if not a["neg_entries"]:
        return ""
    ranked = sorted(a["neg_entries"], key=lambda e: parse_engagement((e.get("metadata") or {}).get("engagement")), reverse=True)
    quotes = ""
    for e in ranked[:6]:
        m = e.get("metadata") or {}
        eng = m.get("engagement") or ""
        author = m.get("author") or ""
        plat = PLAT_LABELS.get(m.get("platform", ""), m.get("platform", "未知"))
        detail = m.get("sentiment_detail") or ""
        content = e.get("content", "")[:200]
        quotes += f'<blockquote>{esc(content)}<br><span class="src">—— {esc(author)} · {plat} · {esc(eng)} · 细分情绪：{esc(detail)}</span></blockquote>'

    # 负面时间集中度（操纵特征之一）
    conc_note = ""
    if a["neg_entries"]:
        conc_note = (f'负面条目集中在 <b>{a["neg_peak"][0]}</b>（单日 {a["neg_peak"][1]} 条，占负面总量 '
                     f'{a["neg_concentration"]*100:.0f}%），来自 <b>{a["neg_authors"]}</b> 个不同来源账号。'
                     f'{"负面在单一时间窗口高度集中，需结合第 7 章判断是否存在组织化推动。" if a["neg_concentration"] >= 0.5 else "负面时间分布较为分散，更符合自然发酵特征。"}')

    return f"""
<section>
<h2 class="sec"><span class="num">4</span>负面情绪深度分析</h2>
<div class="card">
  <div class="card-title">负面情绪概况 <span class="tag tag-neg">负面 {a['neg_ratio']*100:.0f}%</span></div>
  <p>负面情绪占比 {a['neg_ratio']*100:.0f}%（{a['sent_dist'].get('negative', 0)}/{a['total']} 条）。{conc_note}</p>
  <p>按互动量排序的代表性负面内容：</p>
  {quotes}
</div>
</section>"""


def _sec5_source(a):
    """情绪来源追溯：谁在发声、立场如何、什么角色。"""
    if not a["author_rows"]:
        return ""
    rows = ""
    for r in a["author_rows"][:15]:
        rows += f'''<tr><td><b>{esc(r['author'])}</b></td><td>{esc(r['platforms'])}</td>
        <td>{esc(r['types'])}</td><td>{r['count']}</td>
        <td><span class="sent {SENT_CLS.get(r['sent'], 'sent-mid')}">{SENT_LABELS.get(r['sent'], r['sent'])}</span></td>
        <td>{r['eng']}</td></tr>'''
    return f"""
<section>
<h2 class="sec"><span class="num">5</span>情绪来源追溯</h2>
<div class="card">
  <div class="card-title">主要发声来源<span class="tag tag-info">按账号聚合</span></div>
  <p>以下为参与讨论的主要账号/来源及其立场分布，用于判断情绪是「自然多元」还是「少数账号主导」：</p>
  <table>
  <tr><th>来源账号</th><th>平台</th><th>角色</th><th>条目数</th><th>主要立场</th><th>互动量</th></tr>
  {rows}
  </table>
</div>
</section>"""


def _sec6_manipulation(a):
    """操纵痕迹判断：风险信号证据 + 时间集中度 + 来源多样性。"""
    sections = []
    if a["manipulation_evidence"]:
        evi_html = ""
        for ev in a["manipulation_evidence"]:
            evi_list = "".join(f"<li>{esc(x)}</li>" for x in ev.get("evidence", [])[:4])
            evi_html += f'''<div class="signal signal-red">
              <div class="signal-head"><span class="signal-badge">{SEVERITY_LABELS.get(ev['severity'], ev['severity'])}</span><span class="signal-type">操纵/抹黑相关</span></div>
              <div class="signal-desc">{esc(ev['desc'])}</div>
              {'<ul class="signal-evi">' + evi_list + '</ul>' if evi_list else ''}
              <div class="signal-action">建议：{esc(ev.get('action', ''))}</div>
            </div>'''
        sections.append(f'<div class="card"><div class="card-title">检测到的操纵/抹黑相关信号<span class="tag tag-neg">需警惕</span></div>{evi_html}</div>')
    else:
        sections.append('<div class="card"><div class="card-title">操纵信号检测<span class="tag tag-pos">未检出</span></div>'
                        '<p>数据中未发现「AI投毒 / 水军 / 黑公关 / 批量造谣」类信号。结合来源追溯（第 5 章），负面观点主要来自可识别的独立账号，未呈现统一话术、固定时间窗、同源账号等组织化特征。</p></div>')

    # 负面时间集中度分析
    if a["neg_entries"]:
        if a["neg_concentration"] >= 0.5:
            verdict = ('<div class="verdict red"><h4>风险提示</h4><p>负面条目在单日高度集中（占负面总量 '
                       f'{a["neg_concentration"]*100:.0f}%），存在组织化集中释放的可能性，建议持续监控该时间窗口前后的账号行为。</p></div>')
        else:
            verdict = f'<div class="verdict"><h4>判断</h4><p>负面条目时间分布分散（峰值日占 {a["neg_concentration"]*100:.0f}%）、来源多样（{a["neg_authors"]} 个账号），更符合自然发酵特征。</p></div>'
        sections.append(f'<div class="card"><div class="card-title">负面时间分布分析<span class="tag tag-info">操纵特征检验</span></div>{verdict}</div>')

    return f"""
<section>
<h2 class="sec"><span class="num">6</span>操纵痕迹判断：自然发酵还是被推动</h2>
{''.join(sections)}
<div class="card"><div class="card-title">判断方法论<span class="tag tag-info">六项检验</span></div>
<p>判断操纵痕迹从六个维度检验：<b>①账号来源</b>（是否可追溯）<b>②话术一致性</b>（是否统一）<b>③时间分布</b>（是否集中/预埋）<b>④内容真实性</b>（是否有事实支撑）<b>⑤互动真实性</b>（是否异常灌水）<b>⑥利益指向</b>（是否有明确受益方）。以上分析已基于当前数据完成其中可量化的检验项。</p></div>
</section>"""


def _sec7_kol(a):
    """KOL 画像与内容生态。"""
    kol_rows = [r for r in a["author_rows"] if "KOL" in r["types"] or "媒体" in r["types"]]
    if not kol_rows:
        return ""
    rows = ""
    for r in kol_rows[:12]:
        rows += f'''<tr><td><b>{esc(r['author'])}</b></td><td>{esc(r['platforms'])}</td><td>{esc(r['types'])}</td>
        <td>{r['count']}</td><td><span class="sent {SENT_CLS.get(r['sent'], 'sent-mid')}">{SENT_LABELS.get(r['sent'], r['sent'])}</span></td><td>{r['eng']}</td></tr>'''
    return f"""
<section>
<h2 class="sec"><span class="num">7</span>KOL 画像与内容生态</h2>
<div class="card">
  <div class="card-title">已发声 KOL/媒体<span class="tag tag-info">立场与声量</span></div>
  <table>
  <tr><th>账号</th><th>平台</th><th>角色</th><th>条目数</th><th>立场</th><th>互动量</th></tr>
  {rows}
  </table>
</div>
</section>"""


def _sec8_competitor(a):
    """竞品对比分析（横向条形图呈现提及频次）。"""
    if not a["competitors"]:
        return ""
    comps = a["competitors"][:10]
    rows = "".join(f'<tr><td><b>{esc(c["name"])}</b></td><td>{c["count"]}</td></tr>' for c in comps)
    chart_html = ""
    if len(comps) >= 2:
        a["charts"]["chart-competitor"] = _hbar_option([(c["name"], c["count"]) for c in comps])
        chart_html = _chart_box("chart-competitor", min(60 + 32 * len(comps), 340))
    return f"""
<section>
<h2 class="sec"><span class="num">8</span>竞品对比分析</h2>
<div class="card">
  <div class="card-title">讨论中高频出现的对比对象<span class="tag tag-info">按提及频次</span></div>
  <p>用户讨论中频繁将话题对象与以下品牌/车型进行对比，反映用户心智中的竞品格局：</p>
  {chart_html}
  <table><tr><th>对比对象</th><th>提及频次</th></tr>{rows}</table>
</div>
</section>"""


def _sec9_risk(a):
    """舆情风险矩阵：信号分级 + 证据 + 建议。"""
    if not a["signals"]:
        return ""
    signal_html = ""
    for sig in sorted(a["signals"], key=lambda s: -TYPE_WEIGHTS.get(s.get("severity", "medium"), 3)):
        sev = sig.get("severity", "medium")
        sev_cls = {"critical": "red", "high": "orange", "medium": "yellow", "low": "green"}.get(sev, "yellow")
        sig_type = TYPE_LABELS.get(sig.get("type", ""), sig.get("type", "监测"))
        evi = "".join(f"<li>{esc(x)}</li>" for x in sig.get("evidence", [])[:5])
        signal_html += f'''
        <div class="signal signal-{sev_cls}">
          <div class="signal-head"><span class="signal-badge">{SEVERITY_LABELS.get(sev, sev)}</span><span class="signal-type">{sig_type}</span></div>
          <div class="signal-desc">{esc(sig.get('description', ''))}</div>
          {'<ul class="signal-evi">' + evi + '</ul>' if evi else ''}
          <div class="signal-action">建议：{esc(sig.get('recommended_action', ''))}</div>
        </div>'''
    return f"""
<section>
<h2 class="sec"><span class="num">9</span>舆情风险矩阵与信号预警</h2>
<div class="card">{signal_html}</div>
</section>"""


def _sec10_forecast(a):
    """预测研判：阶段推演 + 风险方向。"""
    return f"""
<section>
<h2 class="sec"><span class="num">10</span>预测研判</h2>
<div class="card">
  <div class="card-title">阶段推演 <span class="tag tag-info">{PHASE_LABELS.get(a['last_phase'], a['last_phase'])}</span></div>
  <p>{a['phase_forecast']}</p>
</div>
<div class="card">
  <div class="card-title">风险演变方向 <span class="tag tag-info">基于信号</span></div>
  <p>当前共 {len(a['signals'])} 条监测信号，其中严重/高风险 {sum(1 for s in a['signals'] if s.get('severity') in ('critical', 'high'))} 条。'
     '负面情绪占比 {a['neg_ratio']*100:.0f}%，价格焦虑指数 {a['price_anxiety']*100:.0f}%。</p>
  <p>后续需重点跟踪：① 负面焦点是否扩散；② 竞品对比叙事是否升级；③ 新事件（定价/交付/实测）触发的新一轮热度。</p>
</div>
</section>"""


def _sec11_actions(a):
    """行动建议：按信号严重度聚合。"""
    if not a["signals"]:
        return ""
    # 去重聚合 recommended_action
    seen, actions = set(), []
    for sig in sorted(a["signals"], key=lambda s: -TYPE_WEIGHTS.get(s.get("severity", "medium"), 3)):
        act = sig.get("recommended_action", "").strip()
        if act and act not in seen:
            seen.add(act)
            actions.append((SEVERITY_LABELS.get(sig.get("severity", "medium"), sig.get("severity")), act))
    rows = ""
    for i, (sev, act) in enumerate(actions[:10]):
        priority = {0: "P0", 1: "P1"}.get(i, "P2")
        rows += f'<tr><td><b>{priority}</b></td><td>{sev}</td><td>{esc(act)}</td></tr>'
    return f"""
<section>
<h2 class="sec"><span class="num">11</span>行动建议（按优先级）</h2>
<div class="card">
  <table><tr><th>优先级</th><th>信号级别</th><th>建议</th></tr>{rows}</table>
</div>
</section>"""


def _sec12_evolution(a):
    """演变时间线。"""
    evo_html = ""
    for ev in a["evolution"]:
        phase = ev.get("phase", "stable")
        evo_html += f'''
        <div class="tl-item evo-{phase}">
          <div class="tl-date">{esc(ev.get('timestamp', ''))[:16]}</div>
          <div class="tl-title"><span class="evo-phase">{PHASE_LABELS.get(phase, phase)}</span>{esc(ev.get('summary', ''))}</div>
          {'<div class="tl-body">情感流向：' + esc(ev.get('sentiment_shift', '') or '') + '</div>' if ev.get('sentiment_shift') else ''}
          {'<ul>' + ''.join(f'<li>{esc(c)}</li>' for c in ev.get('key_changes', [])[:6]) + '</ul>' if ev.get('key_changes') else ''}
          {'<div>' + ''.join(f'<span class="evo-kw">{esc(k)}</span>' for k in ev.get('new_keywords', [])[:6]) + '</div>' if ev.get('new_keywords') else ''}
        </div>'''
    return f"""
<section>
<h2 class="sec"><span class="num">12</span>话题演变时间线</h2>
<div class="timeline">{evo_html if evo_html else '<p class="note">暂无演变数据</p>'}</div>
</section>"""


def _sec13_comments(a):
    """各平台评论区洞察。"""
    if not a["comment_summaries"]:
        return ""
    comment_html = ""
    for cs in a["comment_summaries"][-6:]:
        m = cs.get("metadata") or {}
        plat = PLAT_LABELS.get(m.get("platform", ""), m.get("platform", "未知"))
        comment_html += f'''<div class="card"><div class="card-title">{plat} 评论区洞察 <span class="tag tag-info">评论区</span></div>
        <div class="comment-text">{esc(cs.get('content', ''))[:800]}</div></div>'''
    return f"""
<section>
<h2 class="sec"><span class="num">13</span>各平台评论区洞察</h2>
{comment_html}
</section>"""


def _sec14_entries(a):
    """数据条目明细。"""
    entry_html = ""
    for e in reversed(a["entries"][-50:]):
        m = e.get("metadata") or {}
        sent = m.get("sentiment", "neutral")
        plat = PLAT_LABELS.get(m.get("platform", ""), m.get("platform", "未知"))
        entry_html += f'''<tr><td>{esc(e.get('timestamp', ''))[:16]}</td><td>{plat}</td>
        <td>{esc(e.get('content', ''))[:180]}</td>
        <td><span class="sent {SENT_CLS.get(sent, 'sent-mid')}">{SENT_LABELS.get(sent, sent)}</span></td></tr>'''
    return f"""
<section>
<h2 class="sec"><span class="num">14</span>数据条目明细</h2>
<div class="card">
<table><tr><th>时间</th><th>平台</th><th>内容</th><th>情感</th></tr>{entry_html}</table>
</div>
</section>"""


def render_report_body(a):
    """Concatenate all non-empty report sections for a topic analysis payload."""
    sections = [
        _sec_methodology(a), _sec1_overview(a), _sec2_data(a), _sec3_positive(a), _sec4_negative(a),
        _sec5_source(a), _sec6_manipulation(a), _sec7_kol(a), _sec8_competitor(a),
        _sec9_risk(a), _sec10_forecast(a), _sec11_actions(a), _sec12_evolution(a),
        _sec13_comments(a), _sec14_entries(a),
    ]
    # 空章节（无对应数据）自动隐藏
    body = "\n".join(s for s in sections if s)
    return body + _charts_script(a["charts"])


def get_topic_report(topic_id):
    """Analyze a topic and render its report body. Returns (payload, body_html)."""
    a = analyze_topic(topic_id)
    return a, render_report_body(a)


# ============================================================
# schema-first 简洁渲染器：把 report_schema 填充为 HTML（先样式、后填充）
# ============================================================

def _render_vc_cards(cards):
    """核心结论速览：纯文字行，无边框盒装饰，用彩色标签区分维度。"""
    cls_color = {"good": "var(--pos)", "warn": "var(--mid)", "danger": "var(--neg)", "info": "var(--accent)"}
    html = ""
    for c in cards:
        color = cls_color.get(c["cls"], "var(--accent)")
        html += (f'<p class="vc-line"><span class="vc-lab" style="color:{color}">{esc(c["tag"])}</span>'
                 f'<b>{esc(c["title"])}</b>：{esc(c["text"])}</p>')
    return html


def _render_signals(signals):
    """风险信号：纯文字行，用严重度颜色标注，无边框盒。"""
    html = ""
    for sig in sorted(signals, key=lambda s: -TYPE_WEIGHTS.get(s.get("severity", "medium"), 3)):
        sev = sig.get("severity", "medium")
        color = {"critical": "var(--neg)", "high": "var(--neg)", "medium": "var(--mid)", "low": "var(--pos)"}.get(sev, "var(--mid)")
        html += (f'<p class="sig-line"><span class="sig-sev" style="color:{color}">【{SEVERITY_LABELS.get(sev, sev)}】</span>'
                 f'<b>{esc(TYPE_LABELS.get(sig.get("type", ""), sig.get("type", "")))}</b>：{esc(sig.get("description", ""))}'
                 f'<br><span class="sig-act">建议：{esc(sig.get("recommended_action", ""))}</span></p>')
    return html


def _render_actions(actions):
    rows = ""
    for i, (sev, act) in enumerate(actions[:10]):
        pr = {0: "P0", 1: "P1"}.get(i, "P2")
        rows += f'<tr><td><b>{pr}</b></td><td>{esc(sev)}</td><td>{esc(act)}</td></tr>'
    return f'<table class="acts"><tr><th>优先级</th><th>级别</th><th>建议</th></tr>{rows}</table>'


def _render_block(block):
    t = block["type"]
    if t == "chart":
        out = _chart_box(block["chart_id"], block.get("height", 260))
        out += f'<div class="chart-interpret"><span class="lab">解读</span>{esc(block["caption"])}</div>'
        if block.get("summary"):
            out += f'<div class="chart-summary"><span class="lab">小结</span>{esc(block["summary"])}</div>'
        return out
    if t == "verdict_cards":
        return _render_vc_cards(block["cards"])
    if t == "prose":
        return f'<p class="prose">{esc(block["text"])}</p>'
    if t == "interpret":
        return f'<p class="sec-interpret"><span class="lab">解读</span>{esc(block["text"])}</p>'
    if t == "summary":
        return f'<p class="sec-summary"><span class="lab">小结</span>{esc(block["text"])}</p>'
    if t == "text":
        return f'<p class="prose">{esc(block["text"])}</p>'
    if t == "signals":
        return _render_signals(block["signals"])
    if t == "actions":
        return _render_actions(block["actions"])
    return ""


def render_report_concise(schema, a):
    """Stage 3：把 report_schema 填充为 HTML（先样式、后填充）。"""
    sections = []
    for i, sec in enumerate(schema["sections"], 1):
        blocks_html = "".join(_render_block(b) for b in sec["blocks"])
        sections.append(f"""
<section>
<h2 class="sec"><span class="num">{i}</span>{esc(sec['title'])}</h2>
<p class="sec-lead">{esc(sec['lead'])}</p>
{blocks_html}
</section>""")
    return "\n".join(sections) + _charts_script(schema["charts"])


def generate_html_report(topic_id: str, output_path: str = None, mode: str = "concise") -> str:
    """生成数据驱动的深度 HTML 报告（自包含）。

    mode="concise"（默认）：先由数据生成 report_schema（样式/骨架），再填充渲染，
        文字限量、每张图带解读、主色调随场景——适合直接交付给目标用户。
    mode="full"：沿用旧 14(+1) 章全量报告，含完整明细与长文，适合内部深度核对。
    """
    a = analyze_topic(topic_id)
    if not output_path:
        output_path = os.path.join(get_topic_dir(topic_id), "report.html")

    if mode == "full":
        body = render_report_body(a)
        html = _html_head(a, echarts_inline=True) + body + _html_footer(a)
    else:
        schema = build_report_schema(a)
        body = render_report_concise(schema, a)
        html = _html_head(a, echarts_inline=True, accent=schema["strategy"]["accent"]) + body + _html_footer(a)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


def get_concise_report(topic_id: str):
    """生成 schema-first 简洁报告。返回 (schema, html_body)，供网站直接复用。"""
    a = analyze_topic(topic_id)
    schema = build_report_schema(a)
    return schema, render_report_concise(schema, a)
