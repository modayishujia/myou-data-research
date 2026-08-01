#!/usr/bin/env python3
"""Generate PDF reports from research data."""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import get_topic_summary, list_topics

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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate PDF report")
    parser.add_argument("topic_id", help="Topic ID to generate report for")
    parser.add_argument("--output", "-o", help="Output file path")
    args = parser.parse_args()

    result = generate_pdf(args.topic_id, args.output)
    print(result)


if __name__ == "__main__":
    main()
