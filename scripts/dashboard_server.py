#!/usr/bin/env python3
"""Dynamic data-driven monitoring dashboard. Adapts layout/visualization to data shape."""

import json, os, sys
from datetime import datetime
from flask import Flask, render_template_string, jsonify, send_from_directory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import (
    DATA_DIR, list_topics, get_topic_summary, load_topic_meta,
    get_all_entries, get_evolution, get_signals, get_entries_since
)

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
app = Flask(__name__)

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ topic }} - 数据调研看板</title>
<script src="/assets/d3.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0b0f1a;--card:#111827;--card2:#0f172a;--border:#1e293b;--text:#e2e8f0;--dim:#64748b;--accent:#3b82f6;--green:#22c55e;--red:#ef4444;--orange:#f59e0b;--purple:#a855f7;--cyan:#06b6d4;--yellow:#eab308}
html{scroll-behavior:smooth}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei","SF Pro Display",sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.6;word-break:keep-all}

/* 顶栏 */
.topbar{position:sticky;top:0;z-index:100;background:rgba(15,23,42,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);padding:10px 20px;display:flex;justify-content:space-between;align-items:center}
.topbar .left{display:flex;align-items:center;gap:12px}
.topbar .live{display:flex;align-items:center;gap:5px;color:var(--green);font-weight:700;font-size:11px}
.topbar .live::before{content:'';width:7px;height:7px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(34,197,94,.4)}50%{opacity:.6;box-shadow:0 0 0 5px rgba(34,197,94,0)}}
.topbar .topic{font-size:15px;font-weight:800;color:#fff}
.topbar .scenario{font-size:10px;font-weight:700;padding:2px 8px;border-radius:3px;background:var(--accent);color:#fff}
.topbar .right{display:flex;align-items:center;gap:14px;font-size:11px;color:var(--dim)}
.topbar .countdown{color:var(--orange);font-weight:700;font-variant-numeric:tabular-nums}
.about-btn{cursor:pointer;font-size:16px;opacity:.6;transition:opacity .2s}
.about-btn:hover{opacity:1}

/* 网格系统 */
.grid{display:grid;gap:1px;background:var(--border);margin:0}
.grid-1{grid-template-columns:1fr}
.grid-2{grid-template-columns:1fr 1fr}
.grid-3{grid-template-columns:1fr 1fr 1fr}
@media(max-width:1200px){.grid-2,.grid-3{grid-template-columns:1fr}}

/* 通用卡片 */
.card{background:var(--card);padding:16px 20px}
.card-title{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center}
.card-title .count{color:var(--orange)}

/* 关键发现卡片 */
.finding{display:flex;gap:10px;padding:12px 14px;border-left:3px solid;font-size:11px;line-height:1.7;margin-bottom:8px}
.finding:last-child{margin-bottom:0}
.finding-critical{border-left-color:var(--red);background:rgba(239,68,68,.06)}
.finding-high{border-left-color:var(--orange);background:rgba(245,158,11,.05)}
.finding-medium{border-left-color:var(--yellow);background:rgba(234,179,8,.04)}
.finding-insight{border-left-color:var(--cyan);background:rgba(6,182,212,.05)}
.finding-badge{font-size:9px;font-weight:800;padding:2px 8px;border-radius:3px;flex-shrink:0;height:fit-content;margin-top:2px}
.finding-critical .finding-badge{background:var(--red);color:#fff}
.finding-high .finding-badge{background:var(--orange);color:#000}
.finding-medium .finding-badge{background:var(--yellow);color:#000}
.finding-insight .finding-badge{background:var(--cyan);color:#000}
.finding-body{flex:1;min-width:0}
.finding-title{color:var(--text)}
.finding-action{margin-top:4px;font-size:10px;color:var(--cyan)}

/* 分析模块 */
.analysis-item{padding:10px 0;border-bottom:1px solid var(--border);font-size:12px;line-height:1.8}
.analysis-item:last-child{border:none}
.analysis-item strong{color:var(--cyan)}

/* 图表容器 */
.chart-box{height:280px;position:relative}

/* 评论区卡片 */
.comment-card{padding:12px 16px;border-bottom:1px solid var(--border)}
.comment-card:last-child{border:none}
.comment-header{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.comment-src{font-size:9px;font-weight:700;padding:2px 8px;border-radius:3px}
.src-xiaohongshu{background:rgba(254,226,226,.15);color:#f87171}
.src-douyin{background:rgba(219,234,254,.15);color:#60a5fa}
.src-web{background:rgba(209,250,229,.12);color:#4ade80}
.comment-sent{font-size:10px}
.comment-text{font-size:11px;line-height:1.8;color:var(--text);white-space:pre-wrap}
.comment-expand{font-size:10px;color:var(--cyan);cursor:pointer;margin-top:8px}
.comment-expand:hover{text-decoration:underline}

/* 信号卡片 */
.signal{padding:10px 16px;border-left:3px solid;border-bottom:1px solid var(--border);font-size:11px}
.signal-critical{border-left-color:var(--red);background:rgba(239,68,68,.04)}
.signal-high{border-left-color:var(--orange);background:rgba(245,158,11,.03)}
.signal-medium{border-left-color:var(--yellow);background:rgba(234,179,8,.02)}
.signal-low{border-left-color:var(--green);background:rgba(34,197,94,.02)}
.signal-head{display:flex;gap:8px;align-items:center;margin-bottom:4px}
.signal-badge{font-size:9px;font-weight:800;padding:2px 8px;border-radius:3px}
.signal-critical .signal-badge{background:var(--red);color:#fff}
.signal-high .signal-badge{background:var(--orange);color:#000}
.signal-medium .signal-badge{background:var(--yellow);color:#000}
.signal-low .signal-badge{background:var(--green);color:#000}
.signal-type{font-size:10px;color:var(--dim)}
.signal-desc{color:var(--text);line-height:1.6}
.signal-action{margin-top:4px;font-size:10px;color:var(--cyan)}

/* 数据表格 */
.data-table{width:100%;border-collapse:collapse;font-size:11px}
.data-table th{position:sticky;top:0;background:var(--card2);color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:8px 12px;text-align:left;border-bottom:1px solid var(--border)}
.data-table td{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
.data-table tr:hover{background:rgba(59,130,246,.05)}
.tag{font-size:9px;padding:2px 7px;border-radius:3px;font-weight:700;white-space:nowrap}
.tag-xiaohongshu{background:rgba(254,226,226,.15);color:#f87171}
.tag-douyin{background:rgba(219,234,254,.15);color:#60a5fa}
.tag-web_search{background:rgba(209,250,229,.12);color:#4ade80}
.tag-social_media{background:rgba(243,232,255,.12);color:#c084fc}
.tag-comment_section{background:rgba(254,243,199,.12);color:#fbbf24}
.tag-kwb{font-size:8px;padding:1px 5px;border-radius:2px;background:rgba(6,182,212,.15);color:var(--cyan);margin-left:3px}
.sent-dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px;vertical-align:middle}
.sent-positive{background:var(--green)}
.sent-negative{background:var(--red)}
.sent-neutral{background:var(--dim)}
.sent-mixed{background:var(--orange)}

/* 演变时间线 */
.evo{padding:12px 16px;border-left:3px solid var(--accent);border-bottom:1px solid var(--border);position:relative}
.evo::before{content:'';position:absolute;left:-5px;top:16px;width:8px;height:8px;background:var(--accent);border-radius:50%;border:2px solid var(--bg)}
.evo-phase{display:inline-block;padding:2px 10px;border-radius:3px;font-size:9px;font-weight:800;margin-right:8px}
.phase-emergence{background:var(--accent);color:#fff}
.phase-growth{background:var(--green);color:#000}
.phase-peak{background:var(--orange);color:#000}
.phase-decline{background:var(--red);color:#fff}
.phase-stable{background:var(--purple);color:#fff}
.evo-time{font-size:10px;color:var(--dim)}
.evo-summary{margin-top:6px;font-size:12px;line-height:1.7}
.evo-changes{margin-top:6px;padding-left:16px;font-size:10px;color:var(--dim);line-height:1.7}
.evo-kw{display:inline-block;font-size:9px;background:rgba(6,182,212,.12);color:var(--cyan);padding:2px 8px;border-radius:3px;margin:2px}

/* 弹窗 */
.modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.75);z-index:200;justify-content:center;align-items:center;padding:20px}
.modal.show{display:flex}
.modal-box{background:var(--card);border:1px solid var(--border);border-radius:8px;max-width:800px;width:100%;max-height:85vh;overflow-y:auto;position:relative}
.modal-header{position:sticky;top:0;background:var(--card);border-bottom:1px solid var(--border);padding:16px 20px;display:flex;justify-content:space-between;align-items:center}
.modal-header h3{font-size:15px;margin:0}
.modal-close{font-size:20px;color:var(--dim);cursor:pointer;background:none;border:none;padding:4px 8px}
.modal-close:hover{color:var(--text)}
.modal-body{padding:20px}

/* 底栏 */
.footer{background:var(--card2);border-top:1px solid var(--border);padding:10px 20px;display:flex;justify-content:space-between;font-size:10px;color:var(--dim)}

/* 滚动条 */
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--dim)}
</style>
</head>
<body>

<!-- 顶栏 -->
<div class="topbar">
  <div class="left">
    <span class="live">LIVE</span>
    <span class="scenario">{{ scenario }}</span>
    <span class="topic">{{ topic }}</span>
  </div>
  <div class="right">
    <span>更新: <span id="lastUpdate">{{ rendered_at }}</span></span>
    <span>刷新: <span class="countdown" id="countdown">30:00</span></span>
    <span class="about-btn" onclick="document.getElementById('aboutModal').classList.add('show')">ℹ️</span>
  </div>
</div>

<!-- 关于弹窗 -->
<div class="modal" id="aboutModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal-box" style="position:relative;max-width:360px;text-align:center;padding:28px 32px">
    <span class="modal-close" onclick="document.getElementById('aboutModal').classList.remove('show')" style="position:absolute;top:12px;right:16px">&times;</span>
    <h3>数据调研看板</h3>
    <p style="font-size:11px;color:var(--dim);margin-bottom:16px">全天候数据采集 · 问题发现导向</p>
    <div style="width:260px;margin:12px auto;border:1px solid var(--border);border-radius:4px;overflow:hidden">
      <img src="/assets/qrcode.png" alt="公众号二维码" style="width:100%;display:block">
    </div>
    <a href="https://x.com/iGaves" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:6px;margin-top:14px;padding:8px 16px;background:var(--card2);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;text-decoration:none">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
      @iGaves
    </a>
  </div>
</div>

<!-- 评论分析全屏弹窗 -->
<div class="modal" id="commentModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="modal-box">
    <div class="modal-header">
      <h3 id="commentModalTitle">评论区分析</h3>
      <span class="modal-close" onclick="document.getElementById('commentModal').classList.remove('show')">&times;</span>
    </div>
    <div class="modal-body" id="commentModalBody"></div>
  </div>
</div>

<div style="max-width:100%;margin:0 auto">

  <!-- 关键发现 -->
  <div class="card">
    <div class="card-title">关键发现</div>
    {% set crit = signals|selectattr('severity','equalto','critical')|list %}
    {% set high = signals|selectattr('severity','equalto','high')|list %}
    {% set med = signals|selectattr('severity','equalto','medium')|list %}
    {% set cs_list = entries|selectattr('source','equalto','comment_summary')|list %}
    <div class="grid grid-2">
      <div>
        {% for sig in crit[:2] %}
        <div class="finding finding-critical"><div class="finding-badge">严重</div><div class="finding-body"><div class="finding-title">{{ sig.description }}</div>{% if sig.recommended_action %}<div class="finding-action">▶ {{ sig.recommended_action }}</div>{% endif %}</div></div>
        {% endfor %}
        {% for sig in high[:2] %}
        <div class="finding finding-high"><div class="finding-badge">高风险</div><div class="finding-body"><div class="finding-title">{{ sig.description }}</div>{% if sig.recommended_action %}<div class="finding-action">▶ {{ sig.recommended_action }}</div>{% endif %}</div></div>
        {% endfor %}
      </div>
      <div>
        {% for cs in cs_list[:2] %}
        <div class="finding finding-insight"><div class="finding-badge">{% if cs.metadata and cs.metadata.platform == 'xiaohongshu' %}小红书{% elif cs.metadata and cs.metadata.platform == 'douyin' %}抖音{% elif cs.metadata and cs.metadata.platform == 'web' %}百度新闻{% else %}{{ cs.metadata.platform if cs.metadata else '' }}{% endif %}</div><div class="finding-body"><div class="finding-title">{{ cs.content[:150] }}{% if cs.content|length > 150 %}...{% endif %}</div></div></div>
        {% endfor %}
        {% for sig in med[:2] %}
        <div class="finding finding-medium"><div class="finding-badge">中等</div><div class="finding-body"><div class="finding-title">{{ sig.description }}</div></div></div>
        {% endfor %}
      </div>
    </div>
  </div>

  <!-- 态势 + 风险 -->
  <div class="grid grid-2">
    <div class="card">
      <div class="card-title">态势判断</div>
      {% if evolution %}
      <div style="margin-bottom:8px">
        <span style="font-size:20px;font-weight:900;color:var(--green)">{% if evolution[-1].phase == 'emergence' %}萌芽{% elif evolution[-1].phase == 'growth' %}增长{% elif evolution[-1].phase == 'peak' %}爆发{% elif evolution[-1].phase == 'decline' %}衰退{% elif evolution[-1].phase == 'stable' %}稳定{% else %}{{ evolution[-1].phase }}{% endif %}</span>
        <span style="font-size:10px;color:var(--dim);margin-left:6px">阶段{% if evolution|length > 1 %} ← {{ evolution[-2].phase }}{% endif %}</span>
      </div>
      <div class="analysis-item">{{ evolution[-1].summary }}</div>
      {% if evolution[-1].sentiment_shift %}<div class="analysis-item"><strong>情感流向：</strong>{{ evolution[-1].sentiment_shift }}</div>{% endif %}
      {% if evolution[-1].new_keywords %}<div class="analysis-item"><strong>新关键词：</strong>{% for kw in evolution[-1].new_keywords[:5] %}<span class="evo-kw">{{ kw }}</span>{% endfor %}</div>{% endif %}
      {% if evolution[-1].key_changes %}<div class="analysis-item"><strong>关键变化：</strong>{{ evolution[-1].key_changes[:4]|join('；') }}</div>{% endif %}
      {% if evolution[-1].notable_events %}<div class="analysis-item"><strong>标志性事件：</strong>{{ evolution[-1].notable_events[:3]|join('；') }}</div>{% endif %}
      {% endif %}
    </div>
    <div class="card">
      <div class="card-title"><a href="#signals-section" style="color:var(--dim);text-decoration:none">风险预警 ↗</a></div>
      <div style="display:flex;gap:16px;margin-bottom:12px">
        <a href="#signals-section" style="text-decoration:none;color:inherit"><span style="font-size:24px;font-weight:900;color:var(--red)">{{ crit|length }}</span><span style="font-size:10px;color:var(--dim);margin-left:4px">严重</span></a>
        <a href="#signals-section" style="text-decoration:none;color:inherit"><span style="font-size:24px;font-weight:900;color:var(--orange)">{{ high|length }}</span><span style="font-size:10px;color:var(--dim);margin-left:4px">高风险</span></a>
        <a href="#signals-section" style="text-decoration:none;color:inherit"><span style="font-size:24px;font-weight:900;color:var(--yellow)">{{ med|length }}</span><span style="font-size:10px;color:var(--dim);margin-left:4px">中等</span></a>
      </div>
      {% if signals %}
      {% set top_sig = signals[0] %}
      <div class="analysis-item" style="font-size:11px"><strong style="color:{% if top_sig.severity=='critical' %}var(--red){% elif top_sig.severity=='high' %}var(--orange){% else %}var(--yellow){% endif %}">[{{ top_sig.severity }}]</strong> {{ top_sig.description[:100] }}{% if top_sig.description|length > 100 %}...{% endif %}</div>
      {% if top_sig.recommended_action %}<div class="analysis-item" style="font-size:10px;color:var(--cyan)">▶ {{ top_sig.recommended_action[:80] }}{% if top_sig.recommended_action|length > 80 %}...{% endif %}</div>{% endif %}
      {% endif %}
    </div>
  </div>

  <!-- 数据来源汇总 -->
  {% set source_dist = source_distribution|default({}) %}
  {% if source_dist %}
  <div class="card">
    <div class="card-title">数据来源汇总 <span class="count">{{ entry_count }}条</span></div>
    <div style="display:flex;flex-wrap:wrap;gap:12px">
      {% for src, cnt in source_dist.items() %}
      <div style="display:flex;align-items:center;gap:6px;font-size:12px">
        <span class="tag tag-{{ src }}">{% if src == 'xiaohongshu' %}小红书{% elif src == 'douyin' %}抖音{% elif src == 'web_search' %}网页搜索{% elif src == 'social_media' %}社交媒体{% elif src == 'comment_section' %}评论区{% elif src == 'comment_summary' %}分析总结{% else %}{{ src }}{% endif %}</span>
        <span style="font-weight:700;color:var(--text)">{{ cnt }}</span>
        <span style="font-size:10px;color:var(--dim)">条 ({{ "%.0f"|format(cnt / entry_count * 100) }}%)</span>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- 时间趋势 -->
  {% set daily_dist = daily_distribution|default({}) %}
  {% if daily_dist and daily_keys|length > 1 %}
  <div class="card">
    <div class="card-title">时间趋势</div>
    <div class="chart-box" id="timeChart"></div>
  </div>
  {% endif %}

  <!-- 评论区洞察 -->
  {% if cs_list %}
  <div class="card">
    <div class="card-title">各平台评论区洞察 <span class="count">{{ cs_list|length }}个平台</span></div>
    {% for cs in cs_list %}
    <div class="comment-card">
      <div class="comment-header">
        <span class="comment-src src-{{ cs.metadata.platform if cs.metadata else '' }}">{% if cs.metadata and cs.metadata.platform == 'xiaohongshu' %}小红书{% elif cs.metadata and cs.metadata.platform == 'douyin' %}抖音{% elif cs.metadata and cs.metadata.platform == 'web' %}百度新闻{% else %}{{ cs.metadata.platform if cs.metadata else '' }}{% endif %}</span>
        {% set sent = cs.metadata.get('sentiment','neutral') if cs.metadata else 'neutral' %}
        <span class="sent-dot sent-{{ sent }}"></span>
        <span class="comment-sent">{% if sent == 'positive' %}正面{% elif sent == 'negative' %}负面{% elif sent == 'mixed' %}有争议{% else %}中性{% endif %}</span>
      </div>
      {% set cs_lines = cs.content.split('\n') %}
      <div class="comment-text" id="comment-summary-{{ loop.index }}">{% for line in cs_lines[:4] %}{{ line }}
{% endfor %}</div>
      <div class="comment-expand" onclick="openCommentModal({{ loop.index }}, '{% if cs.metadata %}{% if cs.metadata.platform == 'xiaohongshu' %}小红书{% elif cs.metadata.platform == 'douyin' %}抖音{% elif cs.metadata.platform == 'web' %}百度新闻{% else %}{{ cs.metadata.platform }}{% endif %}{% endif %}', '{% if sent == 'positive' %}正面{% elif sent == 'negative' %}负面{% elif sent == 'mixed' %}有争议{% else %}中性{% endif %}')">展开完整分析 ▾</div>
      <div class="comment-full-data" data-content="{{ cs.content|e }}" style="display:none"></div>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- 信号面板 -->
  {% if signals %}
  <div class="card" id="signals-section">
    <div class="card-title">信号与建议 <span class="count">{{ signals|length }}个</span></div>
    {% for sig in signals %}
    <div class="signal signal-{{ sig.severity }}">
      <div class="signal-head">
        <span class="signal-badge">{% if sig.severity == 'critical' %}严重{% elif sig.severity == 'high' %}高风险{% elif sig.severity == 'medium' %}中等{% else %}低{% endif %}</span>
        <span class="signal-type">{% if sig.type == 'sentiment_shift' %}情感转向{% elif sig.type == 'keyword_emergence' %}关键词涌现{% elif sig.type == 'volume_spike' %}热度飙升{% elif sig.type == 'narrative_change' %}叙事变化{% elif sig.type == 'risk_trigger' %}风险触发{% else %}{{ sig.type }}{% endif %} · {{ sig.timestamp[:10] }}</span>
      </div>
      <div class="signal-desc">{{ sig.description }}</div>
      {% if sig.evidence %}<div class="signal-action" style="color:var(--dim)">证据: {{ sig.evidence[:3]|join('；') }}</div>{% endif %}
      {% if sig.recommended_action %}<div class="signal-action">▶ {{ sig.recommended_action }}</div>{% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- 演变时间线 -->
  {% if evolution %}
  <div class="card">
    <div class="card-title">演变过程 <span class="count">{{ evolution|length }}个阶段</span></div>
    {% for evo in evolution %}
    <div class="evo">
      <span class="evo-phase phase-{{ evo.phase }}">{% if evo.phase == 'emergence' %}萌芽{% elif evo.phase == 'growth' %}增长{% elif evo.phase == 'peak' %}爆发{% elif evo.phase == 'decline' %}衰退{% elif evo.phase == 'stable' %}稳定{% else %}{{ evo.phase }}{% endif %}</span>
      <span class="evo-time">{{ evo.timestamp[:16] }}</span>
      <div class="evo-summary">{{ evo.summary }}</div>
      {% if evo.key_changes %}<ul class="evo-changes">{% for ch in evo.key_changes %}<li>{{ ch }}</li>{% endfor %}</ul>{% endif %}
      {% if evo.new_keywords %}<div style="margin-top:6px">{% for kw in evo.new_keywords %}<span class="evo-kw">{{ kw }}</span>{% endfor %}</div>{% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}

  <!-- 数据条目 -->
  {% set raw = entries|rejectattr('source','equalto','comment_summary')|list %}
  {% if raw %}
  <div class="card">
    <div class="card-title">数据条目 <span class="count">{{ raw|length }}条</span></div>
    <div style="overflow-x:auto">
      <table class="data-table">
        <thead><tr>
          <th style="width:90px">时间</th>
          <th style="width:70px">来源</th>
          <th>内容</th>
          <th style="width:50px">情感</th>
          <th style="width:80px">互动</th>
        </tr></thead>
        <tbody>
        {% for entry in raw|reverse %}
        {% set is_social = entry.source in ['xiaohongshu', 'douyin'] %}
        <tr{% if is_social %} style="cursor:pointer" onclick="toggleCommentRow(this)"{% endif %}>
          <td style="white-space:nowrap;font-size:10px;color:var(--dim)">{% if entry.metadata and entry.metadata.platform_time %}{{ entry.metadata.platform_time }}{% else %}{{ entry.timestamp[5:10] }}<br>{{ entry.timestamp[11:16] }}{% endif %}</td>
          <td><span class="tag tag-{{ entry.source }}">{% if entry.source == 'xiaohongshu' %}小红书{% elif entry.source == 'douyin' %}抖音{% elif entry.source == 'web_search' %}网页搜索{% elif entry.source == 'social_media' %}社交媒体{% elif entry.source == 'comment_section' %}评论区{% else %}{{ entry.source }}{% endif %}</span>{% if entry.metadata and entry.metadata.get('collection_method') == 'kimi-webbridge' %}<span class="tag-kwb">浏览器</span>{% endif %}</td>
          <td style="font-size:11px;line-height:1.6;max-width:400px">{{ entry.content }}{% if is_social %}<span style="font-size:9px;color:var(--cyan);margin-left:8px">▾ 评论区</span>{% endif %}</td>
          <td>{% set sent = entry.metadata.get('sentiment','neutral') if entry.metadata else 'neutral' %}<span class="sent-dot sent-{{ sent }}"></span><span style="font-size:10px">{% if sent == 'positive' %}正面{% elif sent == 'negative' %}负面{% elif sent == 'mixed' %}混合{% else %}中性{% endif %}</span></td>
          <td style="font-size:10px;color:var(--dim);white-space:nowrap">{{ entry.metadata.get('engagement','')[:12] if entry.metadata else '' }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
  {% endif %}

</div>

<div class="footer">
  <span>数据目录: {{ data_dir }}</span>
  <span>自动刷新: 30分钟</span>
  <span>渲染: <span id="renderedAt">{{ rendered_at }}</span></span>
</div>

<script>
const TOPIC_ID='{{topic_id}}';
let cd=1800;

// D3.js 图表渲染
function renderTimeChart(containerId, data) {
  const el = document.getElementById(containerId);
  if (!el || !data || Object.keys(data).length <= 1) return;
  const keys = Object.keys(data).sort();
  const vals = keys.map(k=>data[k]);
  const w = el.clientWidth, h = 260, margin = {top:20,right:20,bottom:40,left:40};
  const iw = w-margin.left-margin.right, ih = h-margin.top-margin.bottom;

  const svg = d3.select('#'+containerId).append('svg').attr('width',w).attr('height',h);
  const g = svg.append('g').attr('transform',`translate(${margin.left},${margin.top})`);
  const x = d3.scaleBand().domain(keys.map(k=>k.slice(5))).range([0,iw]).padding(0.3);
  const y = d3.scaleLinear().domain([0,d3.max(vals)*1.1]).range([ih,0]);

  g.append('g').attr('transform',`translate(0,${ih})`).call(d3.axisBottom(x)).selectAll('text').attr('fill','#64748b').attr('font-size','9px');
  g.append('g').call(d3.axisLeft(y)).selectAll('text').attr('fill','#64748b').attr('font-size','9px');
  g.selectAll('.domain,.tick line').attr('stroke','#1e293b');

  g.selectAll('rect').data(keys.map((k,i)=>({k:k.slice(5),v:vals[i]}))).enter().append('rect')
    .attr('x',d=>x(d.k)).attr('y',d=>y(d.v)).attr('width',x.bandwidth()).attr('height',d=>ih-y(d.v))
    .attr('fill',{type:'linear',x1:0,y1:0,x2:0,y2:1, stops:[{offset:0,color:'#3b82f6'},{offset:1,color:'#1e40af'}]})
    .attr('rx',2);
}

// 评论弹窗
function openCommentModal(idx, platform, sent) {
  const dataEl = document.querySelector(`#comment-summary-${idx}`).closest('.comment-card').querySelector('.comment-full-data');
  const content = dataEl ? dataEl.dataset.content : '无数据';
  document.getElementById('commentModalTitle').textContent = platform + ' 评论区分析';
  document.getElementById('commentModalBody').innerHTML = `
    <div class="card" style="background:var(--card2);border:1px solid var(--border);border-radius:0;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:var(--cyan);margin-bottom:10px">📋 完整分析报告</div>
      <div style="font-size:12px;line-height:2;white-space:pre-wrap">${content}</div>
    </div>
    <div class="card" style="background:var(--card2);border:1px solid var(--border);border-radius:0;margin-bottom:12px">
      <div style="font-size:13px;font-weight:700;color:var(--cyan);margin-bottom:10px">📈 情绪分析</div>
      <div style="font-size:12px">整体情绪：<span class="sent-dot sent-${sent==='正面'?'positive':sent==='负面'?'negative':sent==='有争议'?'mixed':'neutral'}" style="display:inline-block"></span>${sent}</div>
    </div>`;
  document.getElementById('commentModal').classList.add('show');
}

// 关闭弹窗 ESC
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal.show').forEach(m => m.classList.remove('show'));
  }
});

// 行展开
function toggleCommentRow(row) {
  const next = row.nextElementSibling;
  if (next && next.classList.contains('comment-expand-row')) {
    next.style.display = next.style.display === 'none' ? 'table-row' : 'none';
  }
}

// 轮询
function fmt(s){return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
async function poll(){
  try{
    const r=await fetch(`/api/topic/${TOPIC_ID}`);if(!r.ok)return;
    const now=new Date().toLocaleString('zh-CN');
    document.getElementById('lastUpdate').textContent=now;
    document.getElementById('renderedAt').textContent=now;
  }catch(e){}
}
setInterval(()=>{cd--;if(cd<=0){cd=1800;poll()}document.getElementById('countdown').textContent=fmt(cd)},1000);

// 初始化图表
document.addEventListener('DOMContentLoaded',()=>{
  {% if daily_distribution %}
  renderTimeChart('timeChart', {{ daily_distribution | tojson }});
  {% endif %}
});
</script>
</body>
</html>"""


def detect_scenario(topic, keywords):
    text = (topic + " " + " ".join(keywords)).lower()
    if any(k in text for k in ["股票","投资","估值","财报","业绩","基金","股价","市值","持仓","证券","上市公司","ipo","融资"]):
        return "投资研究"
    if any(k in text for k in ["发布","新品","上市","首发","预售","交付","提车","开售","发布会"]):
        return "产品发布"
    if any(k in text for k in ["行业","赛道","市场","趋势","产业","政策","创新药","cxo","生物医药"]):
        return "行业调研"
    return "舆情监控"


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


@app.route("/")
def index():
    topics = list_topics()
    if not topics: return "<h1>暂无数据</h1>"
    if len(topics)==1: return show_topic(topics[0]["topic_id"])
    links="".join(f'<div style="margin:10px 0"><a href="/topic/{t["topic_id"]}" style="color:#3b82f6;font-size:16px">{t["topic"]}</a><span style="color:#64748b;font-size:12px;margin-left:10px">{t.get("collection_count",0)}条</span></div>' for t in topics)
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>数据调研看板</title><style>body{{background:#0b0f1a;color:#e2e8f0;font-family:sans-serif;max-width:600px;margin:60px auto;padding:20px}}a{{text-decoration:none}}</style></head><body><h1>数据调研看板</h1>{links}</body></html>'


@app.route("/topic/<topic_id>")
def show_topic(topic_id):
    try: summary=get_topic_summary(topic_id)
    except FileNotFoundError: return f"<h1>未找到</h1>",404
    meta=summary["meta"]
    dk=sorted(summary["daily_distribution"].keys()) if summary["daily_distribution"] else []
    dv=[summary["daily_distribution"][k] for k in dk]
    scenario=detect_scenario(meta["topic"], meta.get("keywords",[]))
    return render_template_string(DASHBOARD_HTML,
        topic_id=topic_id,topic=meta["topic"],scenario=scenario,
        created_at=meta.get("created_at","")[:16],updated_at=meta.get("updated_at","")[:16],
        collection_count=meta.get("collection_count",0),keywords=meta.get("keywords",[]),
        entry_count=summary["entry_count"],evolution_count=summary["evolution_count"],
        signal_count=summary["signal_count"],sources_count=len(summary["source_distribution"]),
        source_distribution=summary["source_distribution"],daily_distribution=summary["daily_distribution"],
        daily_keys=dk,daily_values=dv,
        signals=summary["signals"],evolution=summary["evolution"],entries=summary["entries"],
        data_dir=DATA_DIR,rendered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@app.route("/api/topic/<topic_id>")
def api_topic(topic_id):
    try: return jsonify(get_topic_summary(topic_id))
    except FileNotFoundError: return jsonify({"error":"not found"}),404

@app.route("/api/topics")
def api_topics(): return jsonify(list_topics())


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--port",type=int,default=8765)
    p.add_argument("--host",default="127.0.0.1")
    p.add_argument("--topic",default=None)
    a=p.parse_args()
    print(f"http://{a.host}:{a.port}")
    app.run(host=a.host,port=a.port,debug=False)

if __name__=="__main__":main()
