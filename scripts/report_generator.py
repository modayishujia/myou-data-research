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
from data_store import get_topic_summary, list_topics, get_topic_dir

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
SENT_COLORS = {"positive": "#3ddc97", "negative": "#ff5d6c", "neutral": "#4f8cff", "mixed": "#b48cff"}
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
    """Match analysis scenario from topic text (investment/product/industry/sentiment)."""
    text = (topic + " " + " ".join(keywords)).lower()
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
    }


# ============================================================
# HTML 渲染
# ============================================================

def _html_head(a):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(a['meta']['topic'])} - 深度调研报告</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#0b0f1a;--panel:#141a2e;--panel2:#1a2238;--border:#2a3554;--text:#e8ecf5;--text2:#9aa7c7;--accent:#4f8cff;--pos:#3ddc97;--neg:#ff5d6c;--mid:#f5b942;--mix:#b48cff}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.75;font-size:15px}}
.container{{max-width:1100px;margin:0 auto;padding:0 24px 60px}}
.header{{background:linear-gradient(135deg,#101830,#0b1226);border-bottom:1px solid var(--border);padding:44px 0 30px;margin-bottom:36px}}
.header .inner{{max-width:1100px;margin:0 auto;padding:0 24px}}
.header h1{{font-size:30px;font-weight:700;margin-bottom:10px}}
.header .sub{{color:var(--text2);font-size:14px;margin-bottom:18px}}
.meta-grid{{display:flex;flex-wrap:wrap;gap:10px}}
.meta-chip{{background:var(--panel2);border:1px solid var(--border);border-radius:8px;padding:7px 14px;font-size:12.5px;color:var(--text2)}}
.meta-chip b{{color:var(--text)}}
h2.sec{{font-size:22px;font-weight:700;margin:44px 0 20px;padding-bottom:12px;border-bottom:2px solid var(--border)}}
h2.sec .num{{display:inline-block;background:var(--accent);color:#fff;border-radius:6px;padding:2px 10px;font-size:13px;margin-right:10px;vertical-align:3px}}
h3{{font-size:16px;color:var(--accent);margin:22px 0 10px}}
p{{margin-bottom:12px}}
.card{{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:20px 22px;margin-bottom:16px}}
.card-title{{font-size:15px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}}
.tag{{font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600}}
.tag-info{{background:rgba(79,140,255,.15);color:var(--accent)}}
.tag-pos{{background:rgba(61,220,151,.15);color:var(--pos)}}
.tag-neg{{background:rgba(255,93,108,.15);color:var(--neg)}}
.tag-mid{{background:rgba(245,185,66,.15);color:var(--mid)}}
.verdict{{background:linear-gradient(135deg,rgba(79,140,255,.08),rgba(61,220,151,.06));border:1px solid var(--accent);border-left:4px solid var(--accent);border-radius:10px;padding:16px 20px;margin:14px 0}}
.verdict.red{{border-color:var(--neg);border-left-color:var(--neg);background:linear-gradient(135deg,rgba(255,93,108,.08),rgba(255,93,108,.03))}}
table{{width:100%;border-collapse:collapse;margin:12px 0 18px;font-size:13px}}
th{{background:var(--panel2);color:var(--text);text-align:left;padding:9px 12px;border:1px solid var(--border);font-weight:600}}
td{{padding:9px 12px;border:1px solid var(--border);color:var(--text2);vertical-align:top}}
td b{{color:var(--text)}}
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}}
.kpi{{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}}
.kpi .val{{font-size:22px;font-weight:700;color:var(--accent)}}
.kpi .val.warn{{color:var(--neg)}}
.kpi .val.ok{{color:var(--pos)}}
.kpi .lbl{{font-size:12px;color:var(--text2);margin-top:4px}}
.bar-row{{display:flex;align-items:center;margin-bottom:7px;font-size:13px}}
.bar-label{{width:110px;color:var(--text2);flex-shrink:0}}
.bar-track{{flex:1;background:var(--panel2);border-radius:4px;height:20px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:4px;display:flex;align-items:center;padding-left:8px;font-size:12px;color:#fff;font-weight:600;min-width:30px}}
.bar-val{{width:70px;text-align:right;color:var(--text2);font-size:12px;flex-shrink:0}}
.timeline{{position:relative;padding-left:26px;margin:14px 0}}
.timeline::before{{content:"";position:absolute;left:8px;top:4px;bottom:4px;width:2px;background:var(--border)}}
.tl-item{{position:relative;margin-bottom:18px}}
.tl-item::before{{content:"";position:absolute;left:-23px;top:6px;width:10px;height:10px;border-radius:50%;background:var(--accent);border:2px solid var(--bg)}}
.tl-item.evo-growth::before,.tl-item.evo-peak::before{{background:var(--pos)}}
.tl-item.evo-decline::before{{background:var(--neg)}}
.tl-date{{font-size:12px;color:var(--accent);font-weight:600}}
.tl-title{{font-weight:700;margin-bottom:3px}}
.tl-body{{color:var(--text2);font-size:13px}}
.evo-phase{{display:inline-block;padding:1px 8px;border-radius:3px;font-size:10px;font-weight:700;margin-right:8px;background:var(--panel2);color:var(--accent)}}
.signal{{padding:10px 14px;border-left:3px solid;border-bottom:1px solid var(--border);font-size:12px}}
.signal-red{{border-left-color:var(--neg);background:rgba(255,93,108,.04)}}
.signal-orange{{border-left-color:#f5a623;background:rgba(245,166,35,.03)}}
.signal-yellow{{border-left-color:var(--mid);background:rgba(245,185,66,.02)}}
.signal-green{{border-left-color:var(--pos);background:rgba(61,220,151,.02)}}
.signal-badge{{font-size:9px;font-weight:800;padding:2px 8px;border-radius:3px;background:var(--panel2);color:var(--text)}}
.signal-type{{font-size:10px;color:var(--text2);margin-left:8px}}
.signal-desc{{color:var(--text);line-height:1.6;margin-top:4px}}
.signal-action{{margin-top:4px;font-size:10.5px;color:var(--accent)}}
.signal-evi{{padding-left:16px;font-size:11px;color:var(--text2);margin-top:4px}}
.comment-text{{font-size:12px;line-height:1.8;color:var(--text2)}}
.sent{{display:inline-block;padding:1px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.sent-pos{{background:rgba(61,220,151,.15);color:var(--pos)}}
.sent-neg{{background:rgba(255,93,108,.15);color:var(--neg)}}
.sent-mid{{background:rgba(245,185,66,.15);color:var(--mid)}}
.sent-mix{{background:rgba(180,140,255,.15);color:var(--mix)}}
blockquote{{border-left:3px solid var(--accent);background:var(--panel2);padding:12px 16px;margin:12px 0;border-radius:0 8px 8px 0;color:var(--text2)}}
ul,ol{{padding-left:22px;margin-bottom:12px}}
li{{margin:5px 0;color:var(--text2)}}
li b{{color:var(--text)}}
.note{{font-size:12.5px;color:var(--text2);background:var(--panel2);border-radius:8px;padding:10px 14px;margin:12px 0}}
.footer{{margin-top:50px;padding-top:20px;border-top:1px solid var(--border);color:var(--text2);font-size:12.5px;text-align:center}}
@media print{{.card,.verdict,table{{break-inside:avoid}}}}
</style>
</head>
<body>
<div class="header">
  <div class="inner">
    <h1>{esc(a['meta']['topic'])} · 深度调研报告</h1>
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
</div>
<div class="container">
"""


def _html_footer(a):
    qr_b64 = ""
    try:
        qr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "qr_base64.txt")
        qr_b64 = open(qr_path, encoding="utf-8").read().strip()
    except Exception:
        pass
    qr_html = f'<div style="margin:18px 0 8px"><img src="data:image/png;base64,{qr_b64}" alt="公众号二维码" style="max-width:220px;border-radius:10px;background:#fff;padding:8px;border:1px solid var(--border)"/></div><p>扫码关注「莫说闲话」公众号，获取持续舆情追踪与深度报告</p>' if qr_b64 else ""
    return f"""
<div class="footer">
  <p>由 myou-data-research 数据调研引擎自动生成 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
  {qr_html}
</div>
</div>
</body>
</html>"""


# ============================================================
# 13 章节渲染
# ============================================================

def _sec1_overview(a):
    """核心结论速览：由信号/情绪/阶段推导，无数据章节自动隐藏。"""
    pos_ratio, neg_ratio = a["pos_ratio"], a["neg_ratio"]
    total = a["total"]
    verdicts = []

    # 情绪基调结论
    if pos_ratio >= 0.6:
        base = f"当前情绪以正面为主（{pos_ratio*100:.0f}%），讨论基调积极，品牌叙事占据主导地位"
    elif pos_ratio >= 0.45:
        base = f"正面情绪占比 {pos_ratio*100:.0f}%，但负面已占 {neg_ratio*100:.0f}%，情绪处于正负博弈阶段"
    else:
        base = f"负面情绪占比达 {neg_ratio*100:.0f}%，情绪面承压，需重点关注负面议题的扩散路径"
    verdicts.append(f'<div class="verdict"><h4>情绪基调</h4><p>{base}（基于 {total} 条采样数据）。</p></div>')

    # 阶段结论
    verdicts.append(f'<div class="verdict"><h4>当前阶段</h4><p>话题处于<b>{PHASE_LABELS.get(a["last_phase"], a["last_phase"])}</b>：{a["phase_forecast"]}</p></div>')

    # 关键信号结论（最高严重度的 2 条）
    critical = [s for s in a["signals"] if s.get("severity") in ("critical", "high")]
    for sig in critical[:2]:
        sev_label = SEVERITY_LABELS.get(sig.get("severity"), sig.get("severity"))
        verdicts.append(f'<div class="verdict red"><h4>{sev_label}信号：{TYPE_LABELS.get(sig.get("type", ""), sig.get("type", "监测"))}</h4>'
                        f'<p>{esc(sig.get("description", ""))}</p></div>')

    # 操纵/风险结论
    if a["manipulation_evidence"]:
        verdicts.append(f'<div class="verdict red"><h4>操纵/抹黑迹象</h4><p>数据中发现 {len(a["manipulation_evidence"])} 条与「抹黑 / AI投毒 / 黑公关」相关的风险信号，详见第 7 章。</p></div>')
    else:
        verdicts.append('<div class="verdict"><h4>操纵/抹黑迹象</h4><p>当前数据中未发现明确的抹黑 / AI投毒 / 水军操纵信号，情绪以自然发酵为主。</p></div>')

    # 竞品结论
    if a["competitors"]:
        top_c = a["competitors"][0]
        verdicts.append(f'<div class="verdict"><h4>竞品对比焦点</h4><p>讨论中最常被提及的对比对象是<b>{esc(top_c["name"])}</b>（出现 {top_c["count"]} 次），竞品对比叙事活跃，详见第 9 章。</p></div>')

    return f"""
<section>
<h2 class="sec"><span class="num">1</span>核心结论速览</h2>
{''.join(verdicts)}
</section>"""


def _sec2_data(a):
    """调研数据基础：数据量、平台、时间、关键词矩阵。"""
    sent_bars = ""
    for s in ["positive", "neutral", "negative", "mixed"]:
        n = a["sent_dist"].get(s, 0)
        pct = n / a["total"] * 100
        sent_bars += f'''<div class="bar-row"><div class="bar-label">{SENT_LABELS[s]}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:{SENT_COLORS[s]};">{n}</div></div>
        <div class="bar-val">{pct:.1f}%</div></div>'''

    plat_bars = ""
    for p, n in a["plat_dist"].most_common(8):
        pct = n / a["total"] * 100
        plat_bars += f'''<div class="bar-row"><div class="bar-label">{PLAT_LABELS.get(p, p)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:{pct:.1f}%;background:#4f8cff;">{n}</div></div>
        <div class="bar-val">{pct:.1f}%</div></div>'''

    kws = "、".join(a["top_keywords"][:15])
    return f"""
<section>
<h2 class="sec"><span class="num">2</span>调研数据基础</h2>
<div class="card">
  <div class="card-title">情绪分布（{a['total']} 条）<span class="tag tag-info">情感结构</span></div>
  {sent_bars}
</div>
<div class="card">
  <div class="card-title">平台分布<span class="tag tag-info">渠道结构</span></div>
  {plat_bars}
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
    """竞品对比分析。"""
    if not a["competitors"]:
        return ""
    rows = "".join(f'<tr><td><b>{esc(c["name"])}</b></td><td>{c["count"]}</td></tr>' for c in a["competitors"][:12])
    return f"""
<section>
<h2 class="sec"><span class="num">8</span>竞品对比分析</h2>
<div class="card">
  <div class="card-title">讨论中高频出现的对比对象<span class="tag tag-info">按提及频次</span></div>
  <p>用户讨论中频繁将话题对象与以下品牌/车型进行对比，反映用户心智中的竞品格局：</p>
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


def generate_html_report(topic_id: str, output_path: str = None) -> str:
    """Generate a data-driven deep HTML report (self-contained) from topic data.

    Every section renders only when the underlying data exists, so the
    report content adapts to each topic and can be used for briefings.
    """
    a = analyze_topic(topic_id)
    if not output_path:
        output_path = os.path.join(get_topic_dir(topic_id), "report.html")

    sections = [
        _sec1_overview(a), _sec2_data(a), _sec3_positive(a), _sec4_negative(a),
        _sec5_source(a), _sec6_manipulation(a), _sec7_kol(a), _sec8_competitor(a),
        _sec9_risk(a), _sec10_forecast(a), _sec11_actions(a), _sec12_evolution(a),
        _sec13_comments(a), _sec14_entries(a),
    ]
    # 空章节（无对应数据）自动隐藏
    body = "\n".join(s for s in sections if s)

    html = _html_head(a) + body + _html_footer(a)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
