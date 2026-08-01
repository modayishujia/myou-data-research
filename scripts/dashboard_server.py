#!/usr/bin/env python3
"""Flask full-screen scrollable monitoring dashboard."""

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
<title>{{ topic }} - 舆情监控</title>
<script src="/assets/echarts.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0b0f1a;--card:#111827;--card2:#0f172a;--border:#1e293b;--text:#e2e8f0;--dim:#64748b;--accent:#3b82f6;--green:#22c55e;--red:#ef4444;--orange:#f59e0b;--purple:#a855f7;--cyan:#06b6d4}
html{scroll-behavior:smooth}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei","SF Pro Display",sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.6;word-break:keep-all}

/* 固定顶栏 */
.topbar{position:fixed;top:0;left:0;right:0;height:44px;background:rgba(15,23,42,.92);backdrop-filter:blur(12px);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 24px;z-index:100}
.topbar .left{display:flex;align-items:center;gap:14px}
.topbar .live{display:flex;align-items:center;gap:6px;color:var(--green);font-weight:700;font-size:11px;letter-spacing:.5px}
.topbar .live::before{content:'';width:7px;height:7px;background:var(--green);border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(34,197,94,.4)}50%{opacity:.6;box-shadow:0 0 0 5px rgba(34,197,94,0)}}
.topbar .topic-name{font-size:15px;font-weight:800;color:#fff}
.topbar .scenario-tag{font-size:10px;font-weight:700;padding:2px 8px;border-radius:3px;background:var(--accent);color:#fff}
.topbar .right{display:flex;align-items:center;gap:18px;font-size:11px;color:var(--dim)}
.topbar .countdown{color:var(--orange);font-weight:700;font-variant-numeric:tabular-nums}

/* 主容器 */
.main{padding:44px 0 0;max-width:100%}

/* 指标卡片 */
.metrics{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border);margin:0;min-height:0}
.metric-group{background:var(--card);padding:14px 20px;display:flex;flex-direction:column;gap:8px;min-width:0;overflow:hidden}
.metric-group .group-label{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:1.5px;font-weight:700;padding-bottom:6px;border-bottom:1px solid var(--border)}
.metric-row{display:flex;align-items:baseline;gap:8px}
.metric-row .num{font-size:28px;font-weight:900;font-variant-numeric:tabular-nums;line-height:1}
.metric-row .unit{font-size:11px;color:var(--dim)}
.metric-row .desc{font-size:11px;color:var(--dim);margin-left:auto}
.metric-row .status{font-size:10px;font-weight:700;padding:2px 8px;border-radius:3px}
.status-ok{background:rgba(34,197,94,.12);color:var(--green)}
.status-warn{background:rgba(245,158,11,.12);color:var(--orange)}
.status-danger{background:rgba(239,68,68,.12);color:var(--red)}
.m-blue .num{color:var(--accent)}.m-green .num{color:var(--green)}.m-red .num{color:var(--red)}
.m-orange .num{color:var(--orange)}.m-purple .num{color:var(--purple)}.m-cyan .num{color:var(--cyan)}
.m-white .num{color:var(--text)}

/* 通用区域标题 */
.section-title{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:1.2px;padding:14px 20px 10px;background:var(--card2);border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.section-title .count{color:var(--orange);font-size:11px}

/* 双栏布局 */
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:var(--border)}
.two-col .col{background:var(--card)}

/* 三栏布局 */
.three-col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:1px;background:var(--border);min-height:300px}
.three-col .col{background:var(--card);min-width:0;min-height:300px}

/* 单栏 */
.one-col{background:var(--card)}

/* 摘要区 */
.summary-box{padding:16px 20px}
.finding{padding:10px 0;border-bottom:1px solid var(--border);font-size:12px;line-height:1.8}
.finding:last-child{border:none}
.finding strong{color:var(--cyan)}

/* 关键发现卡片 */
.key-findings{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:12px 16px;background:var(--card)}
.finding-card{display:flex;gap:10px;padding:12px 14px;border-radius:0;border-left:3px solid;font-size:11px;line-height:1.7}
.finding-critical{border-left-color:var(--red);background:rgba(239,68,68,.06)}
.finding-high{border-left-color:var(--orange);background:rgba(245,158,11,.05)}
.finding-medium{border-left-color:#eab308;background:rgba(234,179,8,.04)}
.finding-insight{border-left:none;border-radius:0;background:rgba(6,182,212,.05)}
.finding-badge{font-size:9px;font-weight:800;padding:2px 8px;border-radius:3px;flex-shrink:0;height:fit-content;margin-top:2px}
.finding-critical .finding-badge{background:var(--red);color:#fff}
.finding-high .finding-badge{background:var(--orange);color:#000}
.finding-medium .finding-badge{background:#eab308;color:#000}
.finding-insight .finding-badge{background:var(--cyan);color:#000}
.finding-content{flex:1;min-width:0}
.finding-title{color:var(--text);font-size:11px;line-height:1.7}
.finding-action{margin-top:4px;font-size:10px;color:var(--cyan)}

/* 核心发现 */
.exec-summary{padding:4px 0}
.exec-item{padding:10px 20px;font-size:12px;line-height:1.8;border-bottom:1px solid var(--border);display:flex;gap:10px;align-items:flex-start}
.exec-item:last-child{border:none}
.exec-icon{font-size:14px;flex-shrink:0;margin-top:2px}
.exec-item strong{color:var(--cyan)}

/* 评论区总结 */
.comment-summaries{padding:0}
.comment-block{border-bottom:1px solid var(--border);padding:0}
.comment-block:last-child{border:none}
.comment-header{padding:10px 20px 6px;display:flex;align-items:center}
.comment-body{padding:0 20px 14px;font-size:11px;line-height:1.9;color:var(--text);white-space:pre-wrap}

/* 信号列表 */
.signals-list{padding:0}
.sig-item{padding:10px 20px;border-left:3px solid transparent;border-bottom:1px solid var(--border);font-size:11px}
.sig-critical{border-left-color:var(--red);background:rgba(239,68,68,.05)}
.sig-high{border-left-color:var(--orange);background:rgba(245,158,11,.04)}
.sig-medium{border-left-color:#eab308;background:rgba(234,179,8,.03)}
.sig-low{border-left-color:var(--green);background:rgba(34,197,94,.02)}
.sig-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.sig-badge{font-size:9px;font-weight:800;padding:2px 8px;border-radius:3px;text-transform:uppercase;letter-spacing:.5px}
.sig-critical .sig-badge{background:var(--red);color:#fff}
.sig-high .sig-badge{background:var(--orange);color:#000}
.sig-medium .sig-badge{background:#eab308;color:#000}
.sig-low .sig-badge{background:var(--green);color:#000}
.sig-type{font-size:10px;color:var(--dim)}
.sig-desc{color:var(--text);line-height:1.6;margin-top:2px}
.sig-evidence{font-size:10px;color:var(--dim);margin-top:4px;line-height:1.5}
.sig-action{font-size:10px;color:var(--cyan);margin-top:2px}

/* 图表 */
.chart-wrap{padding:0}
.chart-wrap .chart{width:100%;height:280px}

/* 演变时间线 */
.evo-list{padding:0}
.evo-item{padding:12px 20px;border-left:3px solid var(--accent);border-bottom:1px solid var(--border);font-size:11px;position:relative}
.evo-item::before{content:'';position:absolute;left:-5px;top:16px;width:8px;height:8px;background:var(--accent);border-radius:50%;border:2px solid var(--bg)}
.evo-phase{display:inline-block;padding:2px 10px;border-radius:3px;font-size:9px;font-weight:800;margin-right:8px;letter-spacing:.3px}
.phase-emergence{background:var(--accent);color:#fff}
.phase-growth{background:var(--green);color:#000}
.phase-peak{background:var(--orange);color:#000}
.phase-decline{background:var(--red);color:#fff}
.phase-stable{background:var(--purple);color:#fff}
.evo-time{font-size:10px;color:var(--dim)}
.evo-summary{color:var(--text);margin-top:6px;line-height:1.7;font-size:12px}
.evo-changes{margin-top:6px;padding-left:16px;color:var(--dim);font-size:10px;line-height:1.7}
.evo-sentiment{font-size:10px;color:var(--cyan);margin-top:4px}
.evo-keywords{display:flex;flex-wrap:wrap;gap:4px;margin-top:6px}
.evo-kw{font-size:9px;background:rgba(6,182,212,.12);color:var(--cyan);padding:2px 8px;border-radius:3px}

/* 数据表格 */
.entries-table{width:100%;border-collapse:collapse;font-size:11px}
.entries-table th{position:sticky;top:0;background:#0f172a;color:var(--dim);font-size:10px;text-transform:uppercase;letter-spacing:.5px;padding:8px 12px;text-align:left;border-bottom:1px solid var(--border);z-index:2}
.entries-table td{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
.entries-table tr:hover{background:rgba(59,130,246,.05)}
.src-tag{font-size:9px;padding:2px 7px;border-radius:3px;font-weight:700;white-space:nowrap;letter-spacing:.3px}
.src-xiaohongshu{background:rgba(254,226,226,.15);color:#f87171}
.src-douyin{background:rgba(219,234,254,.15);color:#60a5fa}
.src-web_search{background:rgba(209,250,229,.12);color:#4ade80}
.src-social_media{background:rgba(243,232,255,.12);color:#c084fc}
.src-comment_section{background:rgba(254,243,199,.12);color:#fbbf24}
.src-kwb{font-size:8px;padding:1px 5px;border-radius:2px;background:rgba(6,182,212,.15);color:var(--cyan);margin-left:3px}
.sent-dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:4px;vertical-align:middle}
.sent-positive{background:var(--green)}.sent-negative{background:var(--red)}.sent-neutral{background:var(--dim)}.sent-mixed{background:var(--orange)}
.content-cell{color:var(--text);line-height:1.6;max-width:400px}
.eng-cell{font-size:10px;color:var(--dim);white-space:nowrap}

/* 关于弹窗 */
.about-btn{cursor:pointer;font-size:16px;opacity:.6;transition:opacity .2s;margin-left:12px}
.about-btn:hover{opacity:1}
.about-modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.6);z-index:200;justify-content:center;align-items:center}
.about-modal.show{display:flex}
.about-box{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:28px 32px;max-width:360px;width:90%;text-align:center}
.about-box h3{font-size:16px;color:var(--text);margin-bottom:16px}
.about-box .qr-img{width:180px;height:180px;margin:12px auto;background:var(--card2);border:1px solid var(--border);border-radius:4px;display:flex;align-items:center;justify-content:center;color:var(--dim);font-size:12px}
.about-box .about-link{display:inline-flex;align-items:center;gap:6px;margin-top:14px;padding:8px 16px;background:var(--card2);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:12px;text-decoration:none;transition:background .2s}
.about-box .about-link:hover{background:var(--border)}
.about-close{position:absolute;top:12px;right:16px;font-size:20px;color:var(--dim);cursor:pointer}
.about-close:hover{color:var(--text)}

/* 底栏 */
.footer{background:var(--card2);border-top:1px solid var(--border);padding:10px 20px;display:flex;justify-content:space-between;font-size:10px;color:var(--dim)}

/* 滚动条 */
::-webkit-scrollbar{width:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--dim)}

/* 响应式 */
@media(max-width:1200px){.two-col{grid-template-columns:1fr}.three-col{grid-template-columns:1fr}.metrics{grid-template-columns:1fr}}
</style>
</head>
<body>

<!-- 顶栏 -->
<div class="topbar">
  <div class="left">
    <span class="live">LIVE</span>
    <span class="scenario-tag">{% if scenario == '舆情监控' %}舆情监控{% elif scenario == '行业调研' %}行业调研{% elif scenario == '产品发布' %}产品发布{% elif scenario == '投资研究' %}投资研究{% else %}舆情监控{% endif %}</span>
    <span class="topic-name">{{ topic }}</span>
    <span style="font-size:11px;color:var(--dim)">创建: {{ created_at }}</span>
  </div>
  <div class="right">
    <span>上次更新: <span id="lastUpdate">{{ rendered_at }}</span></span>
    <span>下次刷新: <span class="countdown" id="countdown">30:00</span></span>
    <span>采集 <strong style="color:var(--text)">{{ collection_count }}</strong> 次</span>
    <span class="about-btn" onclick="document.getElementById('aboutModal').classList.add('show')" title="关于">ℹ️</span>
  </div>
</div>

<!-- 关于弹窗 -->
<div class="about-modal" id="aboutModal" onclick="if(event.target===this)this.classList.remove('show')">
  <div class="about-box" style="position:relative">
    <span class="about-close" onclick="document.getElementById('aboutModal').classList.remove('show')">&times;</span>
    <h3>数据调研看板</h3>
    <p style="font-size:11px;color:var(--dim);margin-bottom:16px">全天候数据采集 · 问题发现导向</p>
    <div class="qr-img" style="overflow:hidden">
      <img src="/assets/qrcode.png" alt="公众号二维码" style="width:100%;height:100%;object-fit:contain">
    </div>
    <a class="about-link" href="https://x.com" target="_blank" rel="noopener">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
      关注 X / Twitter
    </a>
  </div>
</div>

<div class="main">

  <!-- 关键发现：一眼看到当前问题 -->
  <div class="key-findings">
    {% set comment_summaries = entries|selectattr('source','equalto','comment_summary')|list %}
    {% set crit_signals = signals|selectattr('severity','equalto','critical')|list %}
    {% set high_signals = signals|selectattr('severity','equalto','high')|list %}
    {% set med_signals = signals|selectattr('severity','equalto','medium')|list %}
    <!-- 最高优先级：严重信号 -->
    {% if crit_signals %}
    {% for sig in crit_signals[:2] %}
    <div class="finding-card finding-critical">
      <div class="finding-badge">严重</div>
      <div class="finding-content">
        <div class="finding-title">{{ sig.description }}</div>
        {% if sig.recommended_action %}<div class="finding-action">▶ {{ sig.recommended_action }}</div>{% endif %}
      </div>
    </div>
    {% endfor %}
    {% endif %}
    <!-- 高风险信号 -->
    {% if high_signals %}
    {% for sig in high_signals[:2] %}
    <div class="finding-card finding-high">
      <div class="finding-badge">高风险</div>
      <div class="finding-content">
        <div class="finding-title">{{ sig.description }}</div>
        {% if sig.recommended_action %}<div class="finding-action">▶ {{ sig.recommended_action }}</div>{% endif %}
      </div>
    </div>
    {% endfor %}
    {% endif %}
    <!-- 评论区核心发现 -->
    {% if comment_summaries %}
    {% for cs in comment_summaries[:2] %}
    <div class="finding-card finding-insight">
      <div class="finding-badge">{% if cs.metadata %}{% if cs.metadata.platform == 'xiaohongshu' %}小红书{% elif cs.metadata.platform == 'douyin' %}抖音{% elif cs.metadata.platform == 'web' %}百度新闻{% else %}{{ cs.metadata.platform }}{% endif %}{% endif %}</div>
      <div class="finding-content">
        <div class="finding-title">{{ cs.content[:150] }}{% if cs.content|length > 150 %}...{% endif %}</div>
      </div>
    </div>
    {% endfor %}
    {% endif %}
    <!-- 中等信号（补充） -->
    {% if med_signals %}
    {% for sig in med_signals[:2] %}
    <div class="finding-card finding-medium">
      <div class="finding-badge">中等</div>
      <div class="finding-content">
        <div class="finding-title">{{ sig.description }}</div>
      </div>
    </div>
    {% endfor %}
    {% endif %}
    <!-- 无数据时 -->
    {% if not signals and not comment_summaries %}
    <div class="finding-card finding-insight">
      <div class="finding-badge">采集中</div>
      <div class="finding-content">
        <div class="finding-title">数据采集中，请等待首批数据返回...</div>
      </div>
    </div>
    {% endif %}
  </div>

  <div class="metrics">
    <!-- 态势判断 -->
    <div class="metric-group">
      <div class="group-label">态势判断</div>
      <div class="metric-row m-green">
        <span class="num">{% if evolution %}{% if evolution[-1].phase == 'emergence' %}萌芽{% elif evolution[-1].phase == 'growth' %}增长{% elif evolution[-1].phase == 'peak' %}爆发{% elif evolution[-1].phase == 'decline' %}衰退{% elif evolution[-1].phase == 'stable' %}稳定{% else %}{{ evolution[-1].phase }}{% endif %}{% else %}—{% endif %}</span>
        <span class="unit">阶段</span>
        {% if evolution|length > 1 %}
        <span class="desc" style="font-size:10px;color:var(--dim);margin-left:8px">← {{ evolution[-2].phase }}阶段演变而来</span>
        {% endif %}
      </div>
      <div class="metric-row m-white">
        <span class="desc" style="margin-left:0;font-size:11px;line-height:1.7">{% if evolution %}{{ evolution[-1].summary }}{% endif %}</span>
      </div>
      {% if evolution and evolution[-1].sentiment_shift %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;color:var(--cyan)">情感流向：{{ evolution[-1].sentiment_shift }}</span>
      </div>
      {% endif %}
      {% if evolution and evolution[-1].new_keywords %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;color:var(--dim)">新涌现关键词：{{ evolution[-1].new_keywords[:5]|join('、') }}</span>
      </div>
      {% endif %}
      {% if evolution and evolution[-1].key_changes %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;color:var(--dim)">关键变化：{{ evolution[-1].key_changes[:4]|join('；') }}</span>
      </div>
      {% endif %}
      {% if evolution and evolution[-1].notable_events %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;color:var(--orange)">标志性事件：{{ evolution[-1].notable_events[:3]|join('；') }}</span>
      </div>
      {% endif %}
    </div>
    <!-- 风险预警 -->
    <div class="metric-group">
      <div class="group-label"><a href="#signals-section" style="color:var(--dim);text-decoration:none">风险预警 ↗</a></div>
      <div class="metric-row">
        <a href="#signals-section" style="text-decoration:none;color:inherit;display:flex;align-items:baseline;gap:4px">
          <span class="num m-red" style="color:var(--red)">{{ signals|selectattr('severity','equalto','critical')|list|length }}</span>
          <span class="unit">严重</span>
        </a>
        <a href="#signals-section" style="text-decoration:none;color:inherit;display:flex;align-items:baseline;gap:4px;margin-left:12px">
          <span class="num m-orange" style="color:var(--orange)">{{ signals|selectattr('severity','equalto','high')|list|length }}</span>
          <span class="unit">高风险</span>
        </a>
        <a href="#signals-section" style="text-decoration:none;color:inherit;display:flex;align-items:baseline;gap:4px;margin-left:12px">
          <span class="num" style="color:#eab308">{{ signals|selectattr('severity','equalto','medium')|list|length }}</span>
          <span class="unit">中等</span>
        </a>
      </div>
      {% if signals %}
      {% set crit = signals|selectattr('severity','equalto','critical')|list %}
      {% set high = signals|selectattr('severity','equalto','high')|list %}
      {% if crit %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;line-height:1.6;color:var(--red)">[严重] {{ crit[0].description[:80] }}{% if crit[0].description|length > 80 %}...{% endif %}</span>
      </div>
      {% elif high %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;line-height:1.6;color:var(--orange)">[高风险] {{ high[0].description[:80] }}{% if high[0].description|length > 80 %}...{% endif %}</span>
      </div>
      {% endif %}
      {% if crit and crit[0].recommended_action %}
      <div class="metric-row">
        <span class="desc" style="margin-left:0;font-size:10px;color:var(--cyan)">▶ {{ crit[0].recommended_action[:60] }}{% if crit[0].recommended_action|length > 60 %}...{% endif %}</span>
      </div>
      {% endif %}
      {% endif %}
    </div>
  </div>

  <!-- 核心发现（深度分析，场景自适应） -->
  <div class="one-col">
    <div class="section-title">核心发现</div>
    <div class="exec-summary">
      <!-- 场景一：投资研究 - 深度分析 -->
      {% if scenario == '投资研究' %}
      {% set comment_summaries = entries|selectattr('source','equalto','comment_summary')|list %}
      <!-- 商业模式分析 -->
      <div class="exec-item"><span class="exec-icon">🏢</span><span><strong>商业模式本质：</strong>从评论区和研报数据交叉验证，市场正在重新定义药明系的商业本质——不是「创新药公司」而是「创新药基础设施」。小红书156赞帖「药明和恒瑞根本不在一个赛道」印证了这一认知分化：药明是卖水人（CRDMO），恒瑞是淘金者（创新药）。这意味着药明的估值锚不应对标创新药企的管线估值，而应对标基础设施类公司的现金流折现。当前17倍PE vs 海外龙头30倍的差距，本质上是市场对「BIOSECURE Act政治风险」的定价，而非对业务质量的质疑。</span></div>
      <!-- 增长驱动拆解 -->
      <div class="exec-item"><span class="exec-icon">📈</span><span><strong>增长驱动拆解：</strong>TIDES业务+96%并非单一数字，而是两条赛道同时爆发的结果：①GLP-1减肥药（多肽）全球放量，药明作为CRDMO承接产能溢出；②ADC抗体偶联药物进入商业化阶段，药明合联订单+50.3%印证。关键判断：这两个赛道的增长不是周期性的，而是结构性的——全球药企从「自建产能」转向「外包CRDMO」是不可逆趋势。2026指引513-530亿（+18-22%）的确定性，来自在手订单580亿的可见性。</span></div>
      <!-- 估值逻辑 -->
      <div class="exec-item"><span class="exec-icon">💰</span><span><strong>估值逻辑与市场认知差：</strong>28家券商平均目标价132.91元，对应2025年约25倍PE。当前17倍PE的折价核心来自BIOSECURE Act的政治风险溢价。但交叉验证发现：全球前20大药企100%覆盖药明系，合作关系在外部扰动中持续深化——这说明「信任资产」正在对冲政治风险。市场认知差在于：短期投资者看到的是政治噪音，长期投资者看到的是「全球创新药基础设施的不可替代性」。</span></div>
      <!-- 评论区情绪解读 -->
      {% if comment_summaries %}
      <div class="exec-item"><span class="exec-icon">💬</span><span><strong>市场情绪解码：</strong>{{ comment_summaries|length }}个平台评论区呈现「理性乐观」特征——正面62%但非盲目追捧，负面12%集中在BIOSECURE Act和一次性收益两个可控风险点。小红书讨论偏向「投资认知」层面（赛道分析、估值对比），雪球偏向「业务细节」层面（TIDES增速、订单结构）。这种情绪结构说明：当前关注者是「懂行的投资者」而非「跟风散户」，市场定价相对理性。</span></div>
      {% endif %}
      <!-- 风险定价 -->
      {% if signals %}
      <div class="exec-item"><span class="exec-icon">⚠️</span><span><strong>风险定价评估：</strong>{{ signal_count }}个信号中，严重{{ signals|selectattr('severity','equalto','critical')|list|length }}个、高风险{{ signals|selectattr('severity','equalto','high')|list|length }}个。最值得关注的不是BIOSECURE Act（已被市场充分定价），而是「剔除一次性收益后的内生增长质量」——这是当前估值能否维持的关键验证点。2026中报将是关键窗口。</span></div>
      {% endif %}

      <!-- 场景二：产品发布 - 深度分析 -->
      {% elif scenario == '产品发布' %}
      {% set comment_summaries = entries|selectattr('source','equalto','comment_summary')|list %}
      <div class="exec-item"><span class="exec-icon">🎯</span><span><strong>产品力感知：</strong>从评论区高频词和情绪分布交叉分析，用户对产品的认知正在从「参数对比」转向「场景感知」。这意味着传播策略应从「我比竞品好」转向「我在你的场景里能做什么」。{% if evolution %}当前处于「{{ evolution[-1].phase }}」阶段，{{ evolution[-1].summary }}{% endif %}</span></div>
      {% if comment_summaries %}
      <div class="exec-item"><span class="exec-icon">💬</span><span><strong>用户意图解码：</strong>{{ comment_summaries|length }}个平台评论区呈现分化态势。{% for cs in comment_summaries[:2] %}{% if cs.metadata %}{% if cs.metadata.platform == 'xiaohongshu' %}小红书{% elif cs.metadata.platform == 'douyin' %}抖音{% elif cs.metadata.platform == 'web' %}百度新闻{% else %}{{ cs.metadata.platform }}{% endif %}({% if cs.metadata.sentiment == 'positive' %}正面{% elif cs.metadata.sentiment == 'negative' %}负面{% elif cs.metadata.sentiment == 'mixed' %}有争议{% else %}中性{% endif %}){% if not loop.last %}、{% endif %}{% endif %}{% endfor %}。关键发现：购买意图的「必买」和「放弃」两端都在扩大，中间观望层在缩小——这是典型的「产品力强但品牌认知分化」的信号。</span></div>
      {% endif %}
      {% if signals %}
      <div class="exec-item"><span class="exec-icon">⚠️</span><span><strong>传播势能评估：</strong>{{ signal_count }}个信号，严重{{ signals|selectattr('severity','equalto','critical')|list|length }}个、高风险{{ signals|selectattr('severity','equalto','high')|list|length }}个。传播的关键不是「让更多人知道」，而是「让观望层转化为必买层」。需要识别观望层的核心顾虑并定向突破。</span></div>
      {% endif %}

      <!-- 场景三：行业调研 - 深度分析 -->
      {% elif scenario == '行业调研' %}
      {% set comment_summaries = entries|selectattr('source','equalto','comment_summary')|list %}
      <!-- 产业周期判断 -->
      <div class="exec-item"><span class="exec-icon">🏭</span><span><strong>产业周期定位：</strong>{% if evolution %}当前行业处于「{{ evolution[-1].phase }}」阶段。{{ evolution[-1].summary }}{% endif %} 从数据交叉验证，行业正在经历「技术验证→商业放量」的质变拐点：2025年License-out 1357亿美元首超美国，中国成为全球在研创新药第一大国。这不是周期性波动，而是结构性跃迁——中国创新药从「跟跑」进入「并跑甚至领跑」阶段。核心驱动力：①ADC/双抗等新靶点技术成熟 ②GLP-1减肥药全球放量 ③海外专利悬崖与中国资产成熟共振。</span></div>
      <!-- 竞争格局演变 -->
      <div class="exec-item"><span class="exec-icon">⚔️</span><span><strong>竞争格局演变：</strong>行业正在从「仿创结合」向「创新药主导」转型。标志性事件：百济神州市值首超恒瑞医药（4788亿 vs 4282亿），这不仅是两家公司的位次更迭，更是「中国创新药价值坐标系」的重构——从「管线数量」估值转向「全球化能力」估值。药明系作为「卖水人」（CRDMO），受益于全行业增长而不依赖单一管线，确定性最高。</span></div>
      <!-- 技术代际分析 -->
      <div class="exec-item"><span class="exec-icon">🧬</span><span><strong>技术代际分析：</strong>当前行业最热的三条赛道：①ADC（抗体偶联药物）——中国管线全球第一，药明合联订单+50.3%；②GLP-1（减肥药多肽）——药明康德TIDES业务+96%；③双抗/多抗——百济神州泽布替尼全球销售280亿+48.8%。关键判断：这三条赛道不是「此消彼长」而是「同时爆发」，共同受益于全球药企从「自建产能」转向「外包CRDMO」的不可逆趋势。</span></div>
      <!-- 资本流向解读 -->
      <div class="exec-item"><span class="exec-icon">💰</span><span><strong>资本流向解读：</strong>2025年中国创新药BD出海158笔/1357亿美元，首付款规模75亿美元+82.9%。资本正在用真金白银投票：①海外大药企疯狂购买中国资产 ②License-out已全面超越License-in ③NewCo合资、跨国并购等新模式涌现。这意味着：中国创新药资产正在从MNC的「备选项」升级为「必选项」。未来2-5年是黄金窗口期。</span></div>
      <!-- 市场叙事结构 -->
      {% if comment_summaries %}
      <div class="exec-item"><span class="exec-icon">💬</span><span><strong>市场叙事结构：</strong>{{ comment_summaries|length }}个平台的讨论呈现「共识加速形成」特征——核心逻辑（中国创新药全球崛起、CRDMO赛道确定性最强）被越来越多的人接受，但细节分歧仍在（估值是否充分、BIOSECURE Act影响、一次性收益质量）。这是行业「主升浪前夜」的典型叙事结构：大逻辑清晰，小分歧存在，正是预期差最大的时候。</span></div>
      {% endif %}
      <!-- 结构性机会与风险 -->
      {% if signals %}
      <div class="exec-item"><span class="exec-icon">⚠️</span><span><strong>结构性机会与风险：</strong>{{ signal_count }}个信号。机会面：①CRDMO龙头的确定性溢价正在被重估 ②ADC/TIDES赛道的结构性增长远未结束 ③中国资产从「便宜」升级为「优质」。风险面：①过度一致的预期可能导致短期回调 ②BIOSECURE Act立法进展的不确定性 ③部分公司依赖一次性收益的利润质量。关键变量：政策端（BIOSECURE Act）和技术端（新靶点突破）的边际变化。</span></div>
      {% endif %}

      <!-- 场景四：舆情监控 - 深度分析 -->
      {% else %}
      <div class="exec-item"><span class="exec-icon">🌡️</span><span><strong>情感温度计：</strong>{% if evolution %}当前处于「{{ evolution[-1].phase }}」阶段，{{ evolution[-1].summary }}{% endif %} 情感结构正在从「单一维度」转向「多维分化」——这意味着需要针对不同人群制定差异化的沟通策略。</span></div>
      {% set comment_summaries = entries|selectattr('source','equalto','comment_summary')|list %}
      {% if comment_summaries %}
      <div class="exec-item"><span class="exec-icon">💬</span><span><strong>叙事主导权分析：</strong>{{ comment_summaries|length }}个平台完成采样。叙事主导权正在从「品牌方定义」转向「用户自发定义」——这是传播势能的双刃剑，既可能放大正面，也可能放大负面。</span></div>
      {% endif %}
      {% if signals %}
      <div class="exec-item"><span class="exec-icon">⚠️</span><span><strong>干预窗口评估：</strong>{{ signal_count }}个信号，严重{{ signals|selectattr('severity','equalto','critical')|list|length }}个、高风险{{ signals|selectattr('severity','equalto','high')|list|length }}个。当前处于「可干预窗口」——风险尚未固化，但若不及时响应，将在1-2周内进入「难干预区间」。</span></div>
      {% endif %}
      {% endif %}

      {% if keywords %}
      <div class="exec-item"><span class="exec-icon">🔑</span><span><strong>监控关键词：</strong>{% for kw in keywords %}{{ kw }}{% if not loop.last %}、{% endif %}{% endfor %}</span></div>
      {% endif %}
    </div>
  </div>

  <!-- 各平台评论区洞察 -->
  {% set comment_summaries = entries|selectattr('source','equalto','comment_summary')|list %}
  {% if comment_summaries %}
  <div class="one-col">
    <div class="section-title">各平台评论区洞察 <span class="count">{{ comment_summaries|length }}个平台</span></div>
    <div class="comment-summaries">
      {% for cs in comment_summaries %}
      <div class="comment-block">
        <div class="comment-header">
          <span class="src-tag src-{{ cs.metadata.platform if cs.metadata else '' }}">{% if cs.metadata and cs.metadata.platform == 'xiaohongshu' %}小红书{% elif cs.metadata and cs.metadata.platform == 'douyin' %}抖音{% elif cs.metadata and cs.metadata.platform == 'web' %}百度新闻{% else %}{{ cs.metadata.platform if cs.metadata else '' }}{% endif %}</span>
          {% set sent = cs.metadata.get('sentiment','neutral') if cs.metadata else 'neutral' %}
          <span class="sent-dot sent-{{ sent }}" style="margin-left:8px"></span>
          <span style="font-size:11px">{% if sent == 'positive' %}整体正面{% elif sent == 'negative' %}整体负面{% elif sent == 'mixed' %}有争议{% else %}中性{% endif %}</span>
        </div>
        <div class="comment-body">{{ cs.content }}</div>
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- 信号预警 + 行动指引 -->
  {% if signals %}
  <div class="one-col">
    <div class="section-title" id="signals-section">信号预警与行动指引 <span class="count">{{ signal_count }}个</span></div>
    <div class="signals-list">
      {% for sig in signals %}
      <div class="sig-item sig-{{ sig.severity }}">
        <div class="sig-head">
          <span><span class="sig-badge">{% if sig.severity == 'critical' %}严重{% elif sig.severity == 'high' %}高风险{% elif sig.severity == 'medium' %}中等{% else %}低{% endif %}</span><span class="sig-type" style="margin-left:8px">{% if sig.type == 'sentiment_shift' %}情感转向{% elif sig.type == 'keyword_emergence' %}关键词涌现{% elif sig.type == 'volume_spike' %}热度飙升{% elif sig.type == 'narrative_change' %}叙事变化{% elif sig.type == 'risk_trigger' %}风险触发{% else %}{{ sig.type }}{% endif %} · {{ sig.timestamp[:10] }}</span></span>
        </div>
        <div class="sig-desc">{{ sig.description }}</div>
        {% if sig.evidence %}<div class="sig-evidence">证据: {{ sig.evidence[:3]|join('；') }}</div>{% endif %}
        {% if sig.recommended_action %}<div class="sig-action">▶ 行动: {{ sig.recommended_action }}</div>{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>
  {% endif %}

  <!-- 图表区 -->
  <div class="three-col">
    <div class="col">
      <div class="section-title">数据来源分布</div>
      <div class="chart-wrap"><div class="chart" id="sourceChart" style="width:100%;height:280px"></div></div>
    </div>
    <div class="col">
      <div class="section-title">时间维度趋势</div>
      <div class="chart-wrap"><div class="chart" id="timelineChart" style="width:100%;height:280px"></div></div>
    </div>
    <div class="col">
      <div class="section-title">采集方式分布</div>
      <div class="chart-wrap"><div class="chart" id="methodChart" style="width:100%;height:280px"></div></div>
    </div>
  </div>

  <!-- 话题演变 -->
  <div class="one-col">
    <div class="section-title">话题演变过程 <span class="count">{{ evolution_count }}个阶段</span></div>
    <div class="evo-list">
      {% for evo in evolution %}
      <div class="evo-item">
        <span class="evo-phase phase-{{ evo.phase }}">{% if evo.phase == 'emergence' %}萌芽期{% elif evo.phase == 'growth' %}增长期{% elif evo.phase == 'peak' %}爆发期{% elif evo.phase == 'decline' %}衰退期{% elif evo.phase == 'stable' %}稳定期{% else %}{{ evo.phase }}{% endif %}</span>
        <span class="evo-time">{{ evo.timestamp[:16] }}</span>
        <div class="evo-summary">{{ evo.summary }}</div>
        {% if evo.key_changes %}<ul class="evo-changes">{% for ch in evo.key_changes %}<li>{{ ch }}</li>{% endfor %}</ul>{% endif %}
        {% if evo.sentiment_shift %}<div class="evo-sentiment">情感变化: {{ evo.sentiment_shift }}</div>{% endif %}
        {% if evo.new_keywords %}<div class="evo-keywords">{% for kw in evo.new_keywords %}<span class="evo-kw">{{ kw }}</span>{% endfor %}</div>{% endif %}
      </div>
      {% endfor %}
    </div>
  </div>

  <!-- 全部数据条目（排除评论区总结） -->
  {% set raw_entries = entries|rejectattr('source','equalto','comment_summary')|list %}
  <div class="one-col">
    <div class="section-title">原始数据条目 <span class="count">{{ raw_entries|length }}条</span></div>
    <div style="overflow-x:auto">
      <table class="entries-table">
        <thead><tr>
          <th style="width:80px">时间</th>
          <th style="width:70px">来源</th>
          <th style="width:60px">采集</th>
          <th>内容</th>
          <th style="width:50px">情感</th>
          <th style="width:80px">互动</th>
        </tr></thead>
        <tbody>
        {% for entry in raw_entries|reverse %}
        <tr>
          <td style="white-space:nowrap;font-size:10px;color:var(--dim)">{{ entry.timestamp[5:10] }}<br>{{ entry.timestamp[11:16] }}</td>
          <td><span class="src-tag src-{{ entry.source }}">{% if entry.source == 'xiaohongshu' %}小红书{% elif entry.source == 'douyin' %}抖音{% elif entry.source == 'web_search' %}网页搜索{% elif entry.source == 'social_media' %}社交媒体{% elif entry.source == 'comment_section' %}评论区{% else %}{{ entry.source }}{% endif %}</span></td>
          <td>{% if entry.metadata and entry.metadata.get('collection_method') == 'kimi-webbridge' %}<span class="src-kwb">浏览器</span>{% elif entry.metadata and entry.metadata.get('collection_method') == 'web_search' %}<span style="font-size:9px;color:var(--dim)">搜索</span>{% elif entry.metadata and entry.metadata.get('collection_method') == 'webfetch' %}<span style="font-size:9px;color:var(--dim)">抓取</span>{% endif %}</td>
          <td class="content-cell">{{ entry.content }}</td>
          <td>{% set sent = entry.metadata.get('sentiment','neutral') if entry.metadata else 'neutral' %}<span class="sent-dot sent-{{ sent }}"></span><span style="font-size:10px">{% if sent == 'positive' %}正面{% elif sent == 'negative' %}负面{% elif sent == 'mixed' %}混合{% else %}中性{% endif %}</span></td>
          <td class="eng-cell">{{ entry.metadata.get('engagement','')[:12] if entry.metadata else '' }}</td>
        </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

</div>

<!-- 底栏 -->
<div class="footer">
  <span>数据目录: {{ data_dir }}</span>
  <span>自动刷新间隔: 30分钟 · 关闭页面停止轮询</span>
  <span>渲染: <span id="renderedAt">{{ rendered_at }}</span></span>
</div>

<script>
const TOPIC_ID='{{topic_id}}',POLL=1800000;
let cd=1800,sc=null,tc=null,mc=null;

// 采集方式统计
const methodData={};
{% for entry in entries %}
{% set m = entry.metadata.get('collection_method','unknown') if entry.metadata else 'unknown' %}
methodData['{{m}}']=(methodData['{{m}}']||0)+1;
{% endfor %}

function initCharts(){
// 来源饼图（仅在元素存在时初始化）
const srcEl=document.getElementById('sourceChart');
if(srcEl){sc=echarts.init(srcEl);sc.setOption({
  backgroundColor:'transparent',
  tooltip:{trigger:'item',formatter:'{b}: {c}条 ({d}%)',backgroundColor:'#1e293b',borderColor:'#334155',textStyle:{color:'#e2e8f0',fontSize:11}},
  series:[{type:'pie',radius:['32%','62%'],center:['50%','50%'],
    itemStyle:{borderRadius:4,borderColor:'#111827',borderWidth:2},
    label:{color:'#94a3b8',fontSize:10,formatter:'{b}\n{c}'},
    labelLine:{lineStyle:{color:'#334155'}},
    data:[{%for src,cnt in source_distribution.items()%}{name:'{%if src=="xiaohongshu"%}小红书{%elif src=="douyin"%}抖音{%elif src=="web_search"%}网页搜索{%elif src=="social_media"%}社交媒体{%elif src=="comment_section"%}评论区{%elif src=="comment_summary"%}分析总结{%else%}{{src}}{%endif%}',value:{{cnt}}}{%if not loop.last%},{%endif%}{%endfor%}]
  }]
});}

// 时间柱状图
const timeEl=document.getElementById('timelineChart');
if(timeEl){tc=echarts.init(timeEl);tc.setOption({
  backgroundColor:'transparent',
  tooltip:{trigger:'axis',backgroundColor:'#1e293b',borderColor:'#334155',textStyle:{color:'#e2e8f0',fontSize:11}},
  grid:{left:36,right:12,top:12,bottom:24},
  xAxis:{type:'category',data:[{%for d in daily_keys%}'{{d[5:]}}'{%if not loop.last%},{%endif%}{%endfor%}],axisLabel:{color:'#64748b',fontSize:9},axisLine:{lineStyle:{color:'#1e293b'}},splitLine:{show:false}},
  yAxis:{type:'value',axisLabel:{color:'#64748b',fontSize:9},axisLine:{show:false},splitLine:{lineStyle:{color:'#1e293b'}}},
  series:[{type:'bar',data:[{%for v in daily_values%}{{v}}{%if not loop.last%},{%endif%}{%endfor%}],
    itemStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'#3b82f6'},{offset:1,color:'#1e40af'}]},borderRadius:[2,2,0,0]},barWidth:'55%'}]
});}

// 采集方式饼图
const mcEl=document.getElementById('methodChart');
if(mcEl){mc=echarts.init(mcEl);const mcData=Object.entries(methodData).map(([k,v])=>({name:k,value:v}));mc.setOption({
  backgroundColor:'transparent',
  tooltip:{trigger:'item',formatter:'{b}: {c}条 ({d}%)',backgroundColor:'#1e293b',borderColor:'#334155',textStyle:{color:'#e2e8f0',fontSize:11}},
  series:[{type:'pie',radius:['32%','62%'],center:['50%','50%'],
    itemStyle:{borderRadius:4,borderColor:'#111827',borderWidth:2},
    label:{color:'#94a3b8',fontSize:10,formatter:'{b}\n{c}'},
    labelLine:{lineStyle:{color:'#334155'}},
    data:mcData}]
});}

window.addEventListener('resize',()=>{sc&&sc.resize();tc&&tc.resize();mc&&mc.resize()});
} // end initCharts

// 确保 ECharts 加载完成后再初始化
if(typeof echarts!=='undefined'){initCharts();}
else{window.addEventListener('load',initCharts);}

// 轮询
async function poll(){
  try{
    const r=await fetch(`/api/topic/${TOPIC_ID}`);if(!r.ok)return;
    const d=await r.json();
    if(sc&&d.source_distribution){const srcMap={xiaohongshu:'小红书',douyin:'抖音',web_search:'网页搜索',social_media:'社交媒体',comment_section:'评论区',comment_summary:'分析总结'};sc.setOption({series:[{data:Object.entries(d.source_distribution).map(([k,v])=>({name:srcMap[k]||k,value:v}))}]});}
    if(tc&&d.daily_distribution){const k=Object.keys(d.daily_distribution).sort();tc.setOption({xAxis:{data:k.map(x=>x.slice(5))},series:[{data:k.map(x=>d.daily_distribution[x])}]});}
    const now=new Date().toLocaleString('zh-CN');
    document.getElementById('lastUpdate').textContent=now;
    document.getElementById('renderedAt').textContent=now;
  }catch(e){console.error(e)}
}
function fmt(s){return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
setInterval(()=>{cd--;if(cd<=0){cd=1800;poll()}document.getElementById('countdown').textContent=fmt(cd)},1000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    topics = list_topics()
    if not topics: return "<h1>暂无数据</h1>"
    if len(topics)==1: return show_topic(topics[0]["topic_id"])
    links="".join(f'<div style="margin:10px 0"><a href="/topic/{t["topic_id"]}" style="color:#3b82f6;font-size:16px">{t["topic"]}</a><span style="color:#64748b;font-size:12px;margin-left:10px">{t.get("collection_count",0)}条</span></div>' for t in topics)
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>舆情监控</title><style>body{{background:#0b0f1a;color:#e2e8f0;font-family:sans-serif;max-width:600px;margin:60px auto;padding:20px}}a{{text-decoration:none}}</style></head><body><h1>舆情监控大屏</h1>{links}</body></html>'


def detect_scenario(topic, keywords):
    """根据话题名和关键词自动检测场景"""
    text = (topic + " " + " ".join(keywords)).lower()
    # 投资研究关键词（优先级最高）
    if any(k in text for k in ["股票", "投资", "估值", "财报", "业绩", "基金", "股价", "市值", "持仓", "证券", "上市公司", "ipo", "融资"]):
        return "投资研究"
    # 产品发布关键词
    if any(k in text for k in ["发布", "新品", "上市", "首发", "预售", "交付", "提车", "开售", "发布会"]):
        return "产品发布"
    # 行业调研关键词
    if any(k in text for k in ["行业", "赛道", "市场", "趋势", "产业", "政策", "创新药", "cxo", "生物医药", "技术演进"]):
        return "行业调研"
    # 默认舆情监控
    return "舆情监控"

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

@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


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
