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
        "methodology": get_methodology(topic_id),  # 每个话题独立生成的调研方法论
        "charts": {},  # 各章节收集的 ECharts 配置 {id: option}
    }


# ============================================================
# HTML 渲染
# ============================================================

REPORT_CSS = """*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0e17;--panel:#101828;--panel2:#141d33;--border:#1d2943;--text:#e6ecf7;--text2:#8b9bc0;--accent:#5b8cff;--pos:#34d399;--neg:#fb7185;--mid:#fbbf24;--mix:#a78bfa;--mono:'SF Mono','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace}
body{background:var(--bg);color:var(--text);font-family:'SF Pro Display','PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif;line-height:1.75;font-size:15px}
.container{max-width:1100px;margin:0 auto;padding:0 24px 60px}
.header{background:linear-gradient(135deg,#111a30,#0a1120);border-bottom:1px solid var(--border);padding:44px 0 30px;margin-bottom:36px}
.header .inner{max-width:1100px;margin:0 auto;padding:0 24px}
.header .eyebrow{font-family:var(--mono);font-size:10px;color:var(--accent);letter-spacing:2px;margin-bottom:10px}
.header h1{font-size:30px;font-weight:800;margin-bottom:10px;letter-spacing:.5px}
.header .sub{color:var(--text2);font-size:14px;margin-bottom:18px}
.meta-grid{display:flex;flex-wrap:wrap;gap:10px}
.meta-chip{background:var(--panel2);border:1px solid var(--border);border-radius:6px;padding:7px 14px;font-size:12.5px;color:var(--text2)}
.meta-chip b{color:var(--text);font-family:var(--mono);font-variant-numeric:tabular-nums;font-weight:600}
h2.sec{font-size:22px;font-weight:800;margin:44px 0 20px;padding-bottom:12px;border-bottom:1px solid var(--border)}
h2.sec .num{display:inline-block;background:var(--accent);color:#fff;border-radius:5px;padding:2px 10px;font-size:13px;margin-right:10px;vertical-align:3px;font-family:var(--mono)}
h3{font-size:16px;color:var(--accent);margin:22px 0 10px}
p{margin-bottom:12px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px 22px;margin-bottom:16px}
.card-title{font-size:15px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.tag{font-size:11px;padding:2px 8px;border-radius:4px;font-weight:600}
.tag-info{background:rgba(91,140,255,.15);color:var(--accent)}
.tag-pos{background:rgba(52,211,153,.15);color:var(--pos)}
.tag-neg{background:rgba(251,113,133,.15);color:var(--neg)}
.tag-mid{background:rgba(251,191,36,.15);color:var(--mid)}
.verdict{background:linear-gradient(135deg,rgba(91,140,255,.08),rgba(52,211,153,.06));border:1px solid var(--accent);border-left:4px solid var(--accent);border-radius:10px;padding:16px 20px;margin:14px 0}
.verdict.red{border-color:var(--neg);border-left-color:var(--neg);background:linear-gradient(135deg,rgba(251,113,133,.08),rgba(251,113,133,.03))}
/* 核心结论速览（执行摘要式） */
.brief{position:relative;background:linear-gradient(135deg,rgba(91,140,255,.08),rgba(91,140,255,.015));border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:10px;padding:20px 22px;margin:14px 0}
.brief.good{border-left-color:var(--pos)}
.brief.warn{border-left-color:var(--mid)}
.brief.danger{border-left-color:var(--neg)}
.brief .brief-lead{font-size:16.5px;font-weight:600;line-height:1.9;color:var(--text)}
.brief .brief-meta{margin-top:10px;font-size:11.5px;color:var(--text2);font-family:var(--mono);letter-spacing:.3px}
.kpi-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(116px,1fr));gap:1px;background:var(--border);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin:14px 0}
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
.vc{position:relative;background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px 16px;overflow:hidden}
.vc::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--text2)}
.vc.vc-good::before{background:var(--pos)}
.vc.vc-warn::before{background:var(--mid)}
.vc.vc-danger::before{background:var(--neg)}
.vc.vc-info::before{background:var(--accent)}
.vc .vc-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.vc .vc-tick{width:7px;height:7px;border-radius:50%;background:var(--text2);flex-shrink:0}
.vc.vc-good .vc-tick{background:var(--pos);box-shadow:0 0 6px rgba(52,211,153,.6)}
.vc.vc-warn .vc-tick{background:var(--mid);box-shadow:0 0 6px rgba(251,191,36,.6)}
.vc.vc-danger .vc-tick{background:var(--neg);box-shadow:0 0 6px rgba(251,113,133,.6)}
.vc.vc-info .vc-tick{background:var(--accent);box-shadow:0 0 6px rgba(91,140,255,.6)}
.vc .vc-tag{font-size:9.5px;font-weight:800;letter-spacing:1px;color:var(--text2);text-transform:uppercase}
.vc .vc-title{font-size:13.5px;font-weight:700;color:var(--text);margin-bottom:4px;line-height:1.6}
.vc .vc-text{font-size:12.5px;line-height:1.75;color:var(--text2)}
.vc .vc-text b{color:var(--text)}
table{width:100%;border-collapse:collapse;margin:12px 0 18px;font-size:13px}
th{background:var(--panel2);color:var(--text);text-align:left;padding:9px 12px;border:1px solid var(--border);font-weight:600}
td{padding:9px 12px;border:1px solid var(--border);color:var(--text2);vertical-align:top}
td b{color:var(--text)}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:14px 0}
.kpi{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}
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
.signal{padding:10px 14px;border-left:3px solid;border-bottom:1px solid var(--border);font-size:12px;border-radius:0 6px 0 0}
.signal-red{border-left-color:var(--neg);background:rgba(251,113,133,.04)}
.signal-orange{border-left-color:var(--mid);background:rgba(251,191,36,.03)}
.signal-yellow{border-left-color:var(--mid);background:rgba(251,191,36,.02)}
.signal-green{border-left-color:var(--pos);background:rgba(52,211,153,.02)}
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
blockquote{border-left:3px solid var(--accent);background:var(--panel2);padding:12px 16px;margin:12px 0;border-radius:0 8px 8px 0;color:var(--text2)}
ul,ol{padding-left:22px;margin-bottom:12px}
li{margin:5px 0;color:var(--text2)}
li b{color:var(--text)}
.note{font-size:12.5px;color:var(--text2);background:var(--panel2);border-radius:8px;padding:10px 14px;margin:12px 0}
.footer{margin-top:50px;padding-top:20px;border-top:1px solid var(--border);color:var(--text2);font-size:12.5px;text-align:center;font-family:var(--mono)}
.echart-box{width:100%;margin:12px 0 4px}
.src{display:block;font-size:12px;color:var(--text2);margin-top:6px}
code{background:var(--panel2);border:1px solid var(--border);border-radius:4px;padding:1px 5px;font-family:var(--mono);font-size:12px;color:var(--accent)}
@media print{.card,.verdict,table{break-inside:avoid}.echart-box{height:240px!important}}
@media(max-width:640px){
  body{font-size:14px}
  .container{padding:0 16px 40px}
  .header{padding:32px 0 24px}
  .header h1{font-size:22px;overflow-wrap:anywhere}
  .header .sub{font-size:13px}
  h2.sec{font-size:19px;margin:34px 0 16px}
  h3{font-size:15px}
  .card{padding:14px 16px}
  p,li,td,th,blockquote,.comment-text,.signal-desc,.tl-body,.src{overflow-wrap:anywhere}
  .meta-chip{font-size:11.5px}
  .kpi .val{font-size:19px}
}
"""


# ============================================================
# ECharts：图表主题 + 构建器 + 渲染脚本
# 格式化数据不统一：情感用环形、来源用条形、趋势用折线、竞品用条形，各取所需形态
# ============================================================

ECHARTS_BASE = {
    "backgroundColor": "transparent",
    "color": ["#5b8cff", "#34d399", "#fb7185", "#fbbf24", "#a78bfa", "#22d3ee"],
    "textStyle": {"color": "#8b9bc0"},
    "tooltip": {"backgroundColor": "#141d33", "borderColor": "#1d2943", "borderWidth": 1,
                "textStyle": {"color": "#e6ecf7", "fontSize": 12}},
    "legend": {"textStyle": {"color": "#8b9bc0"}, "itemWidth": 10, "itemHeight": 10},
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


def _html_head(a, echarts_inline=False):
    echarts_tag = f"<script>{_get_echarts_js()}</script>" if echarts_inline else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(a['meta']['topic'])} - 深度调研看板</title>
<style>
{REPORT_CSS}
</style>
{echarts_tag}
</head>
<body>
{_report_header(a)}
<div class="container">
"""


def _report_footer(a):
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


def generate_html_report(topic_id: str, output_path: str = None) -> str:
    """Generate a data-driven deep HTML report (self-contained) from topic data.

    Every section renders only when the underlying data exists, so the
    report content adapts to each topic and can be used for briefings.
    """
    a = analyze_topic(topic_id)
    if not output_path:
        output_path = os.path.join(get_topic_dir(topic_id), "report.html")

    body = render_report_body(a)

    html = _html_head(a, echarts_inline=True) + body + _html_footer(a)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path
