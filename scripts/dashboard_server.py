#!/usr/bin/env python3
"""Dynamic data-driven monitoring dashboard. Adapts layout/visualization to data shape."""

import json, os, sys
from datetime import datetime
from flask import Flask, render_template_string, jsonify, send_from_directory, redirect

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_store import (
    DATA_DIR, list_topics, get_topic_summary,
    snapshot_topic, get_delta, detect_anomalies, get_all_topics_overview
)
from report_generator import REPORT_CSS, _report_header, _report_footer, get_topic_report

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
app = Flask(__name__)

TOPIC_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ topic }} - 深度调研看板</title>
<script src="/assets/echarts.min.js"></script>
<style>
{{ report_css | safe }}

/* 实时监测层（dash- 前缀，避免与报告样式冲突） */
.dash-topbar{position:sticky;top:0;z-index:100;background:rgba(10,14,23,.9);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--border);padding:9px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.dash-left{display:flex;align-items:center;gap:12px;min-width:0;flex-wrap:wrap}
.dash-brand{display:flex;align-items:baseline;gap:7px;font-family:var(--mono);font-weight:800;font-size:12px;letter-spacing:1.5px;white-space:nowrap}
.dash-brand .brand-mark{color:var(--accent)}
.dash-brand .brand-sub{font-size:9px;font-weight:600;letter-spacing:2px;color:var(--text2)}
.dash-brand::after{content:'';width:1px;height:14px;background:var(--border)}
.dash-live{display:flex;align-items:center;gap:6px;color:var(--pos);font-family:var(--mono);font-weight:700;font-size:10px;letter-spacing:1px;white-space:nowrap}
.dash-live::before{content:'';width:7px;height:7px;background:var(--pos);border-radius:50%;animation:dash-pulse 2.2s infinite}
@keyframes dash-pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(52,211,153,.45)}50%{opacity:.55;box-shadow:0 0 0 6px rgba(52,211,153,0)}}
.dash-scenario{font-size:9px;font-weight:700;padding:3px 9px;border-radius:4px;background:rgba(91,140,255,.15);color:var(--accent);border:1px solid rgba(91,140,255,.35);letter-spacing:.5px;white-space:nowrap}
.dash-topic{font-size:14px;font-weight:800;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.dash-right{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-left:auto}
.dash-clk{font-family:var(--mono);font-size:10.5px;color:var(--text2);white-space:nowrap}
.dash-countdown{color:var(--mid);font-weight:700}
.dash-btn{display:inline-flex;align-items:center;gap:5px;padding:5px 11px;border-radius:6px;background:var(--panel2);border:1px solid var(--border);color:var(--text);font-size:11px;font-weight:600;cursor:pointer;transition:border-color .15s,background .15s;text-decoration:none;white-space:nowrap;font-family:inherit}
.dash-btn:hover{background:#182240;border-color:#2c3c63}
.dash-btn:active{background:#101828}
.dash-strip{display:flex;flex-wrap:wrap;gap:6px 20px;align-items:center;margin:0 0 26px;padding:11px 16px;background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;font-size:12.5px}
.dash-strip .lbl{font-family:var(--mono);font-size:9.5px;color:var(--accent);letter-spacing:1px;font-weight:700}
.dash-strip b{font-family:var(--mono);font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:2px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
@media(max-width:640px){.dash-clk{display:none}.dash-topic{white-space:normal;overflow:visible;text-overflow:clip;flex-basis:100%;font-size:13px}.dash-topbar{padding:8px 12px;gap:8px}.dash-btn{padding:4px 8px;font-size:10px}.dash-scenario{font-size:8px;padding:2px 7px}.dash-right{flex-basis:100%;margin-left:0;justify-content:flex-start}}
@media print{.dash-topbar,.dash-strip{display:none!important}}
body{overflow-x:hidden}
</style>
</head>
<body>
<div class="dash-topbar">
  <div class="dash-left">
    <span class="dash-brand"><span class="brand-mark">MYOU</span><span class="brand-sub">数据调研</span></span>
    <span class="dash-live">LIVE</span>
    <span class="dash-scenario">{{ scenario }}</span>
    <span class="dash-topic">{{ topic }}</span>
  </div>
  <div class="dash-right">
    <span class="dash-clk">更新 <span id="lastUpdate">{{ rendered_at }}</span></span>
    <span class="dash-clk">刷新 <span class="dash-countdown" id="countdown">30:00</span></span>
    <button class="dash-btn" onclick="triggerCollect()" title="立即采集">↻ 采集</button>
    <button class="dash-btn" onclick="exportPDF()" title="导出PDF">⇩ PDF</button>
  </div>
</div>
{{ report_header | safe }}
<div class="container">
  {% if delta_html %}{{ delta_html | safe }}{% endif %}
  {{ report_body | safe }}
  {{ footer_html | safe }}
</div>
<script>
const TOPIC_ID='{{topic_id}}';
let cd=1800;

async function triggerCollect() {
  try {
    const r = await fetch('/api/collect/' + TOPIC_ID);
    const d = await r.json();
    if (d.status === 'success') { alert('采集完成：新增 ' + d.new_entries + ' 条数据'); location.reload(); }
    else { alert('采集失败：' + d.message); }
  } catch(e) { alert('采集失败：' + e.message); }
}

async function exportPDF() {
  try {
    const r = await fetch('/api/export/' + TOPIC_ID);
    const d = await r.json();
    if (d.status === 'success') { alert('PDF已生成：' + d.path); }
    else { alert('导出失败：' + d.message); }
  } catch(e) { alert('导出失败：' + e.message); }
}

function fmt(s){return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}
async function poll(){
  try{
    const r=await fetch(`/api/topic/${TOPIC_ID}`);if(!r.ok)return;
    const now=new Date().toLocaleString('zh-CN');
    document.getElementById('lastUpdate').textContent=now;
  }catch(e){}
}
setInterval(()=>{cd--;if(cd<=0){cd=1800;poll()}document.getElementById('countdown').textContent=fmt(cd)},1000);
</script>
</body>
</html>"""


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MYOU · 数据调研看板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#0a0e17;--panel:#101828;--panel2:#141d33;--line:#1d2943;
  --text:#e6ecf7;--dim:#7c8db5;
  --accent:#5b8cff;--accent2:#22d3ee;
  --pos:#34d399;--neg:#fb7185;--warn:#fbbf24;--purple:#a78bfa;
  --mono:'SF Mono','JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
}
html{scroll-behavior:smooth}
body{font-family:'SF Pro Display','PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.65;min-height:100vh;overflow-x:hidden}
.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

.topbar{position:sticky;top:0;z-index:100;background:rgba(10,14,23,.88);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line);padding:10px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px}
@media(max-width:640px){.topbar .right{display:none}}
.brand{display:flex;align-items:baseline;gap:7px;font-family:var(--mono);font-weight:800;font-size:12px;letter-spacing:1.5px}
.brand .brand-mark{color:var(--accent)}
.brand .brand-sub{font-size:9px;font-weight:600;letter-spacing:2px;color:var(--dim)}
.brand::after{content:'';width:1px;height:14px;background:var(--line)}
.live{display:flex;align-items:center;gap:6px;color:var(--pos);font-family:var(--mono);font-weight:700;font-size:10px;letter-spacing:1px}
.live::before{content:'';width:7px;height:7px;background:var(--pos);border-radius:50%;animation:pulse 2.2s infinite}
@keyframes pulse{0%,100%{opacity:1;box-shadow:0 0 0 0 rgba(52,211,153,.45)}50%{opacity:.55;box-shadow:0 0 0 6px rgba(52,211,153,0)}}
.topbar .right{font-family:var(--mono);font-size:10px;color:var(--dim)}

.page{max-width:1100px;margin:0 auto;padding:32px 20px 60px}
.hero{margin-bottom:26px}
.hero .title{font-size:24px;font-weight:800;letter-spacing:.5px;margin:10px 0 4px}
.hero .sub{font-size:12px;color:var(--dim)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin:22px 0 30px}
@media(max-width:640px){.stats{grid-template-columns:repeat(2,1fr)}}
.stat{background:var(--panel);padding:14px 18px;display:flex;flex-direction:column;gap:3px}
.stat .num{font-family:var(--mono);font-variant-numeric:tabular-nums;font-size:22px;font-weight:800;line-height:1;letter-spacing:-.5px}
.stat .num.ok{color:var(--pos)}
.stat .num.warn{color:var(--warn)}
.stat .num.bad{color:var(--neg)}
.stat .num.accent{color:var(--accent)}
.stat .lbl{font-size:10px;color:var(--dim);letter-spacing:.8px}

.topic-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:12px}
@media(max-width:420px){.topic-grid{grid-template-columns:1fr}}
.topic-card{display:flex;gap:14px;background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:10px;padding:16px 18px;text-decoration:none;color:inherit;transition:border-color .15s,background .15s,transform .15s}
.topic-card:hover{background:#131c30;border-color:#2c3c63;transform:translateY(-1px)}
.topic-card .main{flex:1;min-width:0}
.topic-card .name{font-size:14px;font-weight:800;line-height:1.4;margin-bottom:6px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.topic-card .meta{font-size:10.5px;color:var(--dim);margin-bottom:10px;font-family:var(--mono)}
.topic-card .meta b{color:var(--text)}
.sentbar{display:flex;height:4px;border-radius:2px;overflow:hidden;background:var(--panel2);margin-bottom:12px}
.sentbar .pos{background:var(--pos)}
.sentbar .neg{background:var(--neg)}
.sentbar .neu{background:#3a4a6d}
.topic-card .foot{display:flex;justify-content:space-between;align-items:center;gap:10px}
.topic-card .foot .mono-mini{font-family:var(--mono);font-size:10px;color:var(--dim);display:flex;gap:10px}
.topic-card .report-link{font-size:11px;color:var(--accent);font-weight:600;white-space:nowrap}
.topic-card:hover .report-link{color:#8fb0ff}
.topic-card .side{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;flex-shrink:0}
.health-dot{width:9px;height:9px;border-radius:50%;box-shadow:0 0 8px currentColor}
.topic-card .side .rates{font-family:var(--mono);font-size:9.5px;color:var(--dim);text-align:center;line-height:1.6}
.health-chip{display:inline-block;font-size:9px;font-weight:800;letter-spacing:.5px;padding:2px 8px;border-radius:4px}
.health-chip.green{background:rgba(52,211,153,.14);color:var(--pos)}
.health-chip.yellow{background:rgba(251,191,36,.14);color:var(--warn)}
.health-chip.red{background:rgba(251,113,133,.14);color:var(--neg)}
.health-chip.unknown{background:rgba(124,141,181,.14);color:var(--dim)}

.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;min-height:50vh;text-align:center}
.empty .code{font-family:var(--mono);font-size:32px;color:var(--dim);letter-spacing:2px}
.empty p{font-size:13px;color:var(--dim)}

.footer{position:sticky;top:100vh;border-top:1px solid var(--line);padding:12px 20px;font-size:10px;color:var(--dim);text-align:center;font-family:var(--mono)}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:3px}
</style>
</head>
<body>
<div class="topbar">
  <div style="display:flex;align-items:center;gap:12px">
    <span class="brand"><span class="brand-mark">MYOU</span><span class="brand-sub">数据调研</span></span>
    <span class="live">LIVE</span>
  </div>
  <div class="right">全天候数据采集 · 问题发现导向</div>
</div>
<div class="page">
  <div class="hero">
    <div class="mono" style="font-size:10px;color:var(--accent);letter-spacing:1.5px">DATA RESEARCH CONSOLE</div>
    <h1 class="title">数据调研看板</h1>
    <p class="sub">{{count}} 个调研话题 · 自动持续采集 · 情感 / 信号 / 演变追踪</p>
  </div>
  <div class="stats">
    <div class="stat"><span class="num accent">{{count}}</span><span class="lbl">调研话题</span></div>
    <div class="stat"><span class="num">{{total_entries}}</span><span class="lbl">数据条目</span></div>
    <div class="stat"><span class="num">{{total_signals}}</span><span class="lbl">监测信号</span></div>
    <div class="stat"><span class="num {% if total_critical > 0 %}bad{% else %}ok{% endif %}">{{total_critical}}</span><span class="lbl">严重预警</span></div>
    <div class="stat"><span class="num ok">{{healthy}}</span><span class="lbl">健康话题</span></div>
  </div>
  <div class="topic-grid">
  {% if cards %}
  {{ cards | safe }}
  {% else %}
  <div class="empty" style="grid-column:1/-1"><div class="code">NO DATA</div><p>暂无调研数据 · 从 <span class="mono">data_store.py init</span> 开始创建话题</p></div>
  {% endif %}
  </div>
</div>
<div class="footer">MYOU DATA RESEARCH · {{rendered_at}}</div>
</body>
</html>"""


@app.route("/")
def index():
    overview = get_all_topics_overview()
    if not overview:
        return render_template_string(INDEX_HTML, count=0, total_entries=0, total_signals=0,
                                      total_critical=0, healthy=0, cards="",
                                      rendered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if len(overview) == 1:
        return show_topic(overview[0]["topic_id"])

    cards = ""
    total_entries = total_signals = total_critical = healthy = 0
    for t in overview:
        h = t.get("health", "unknown")
        color = {"green": "#34d399", "yellow": "#fbbf24", "red": "#fb7185"}.get(h, "#7c8db5")
        chip = {"green": "健康", "yellow": "关注", "red": "风险"}.get(h, "未知")
        ec = t.get("entry_count", 0); sc = t.get("signal_count", 0)
        cc = t.get("critical_signals", 0); hc = t.get("high_signals", 0)
        pr = int(t.get("positive_rate", 0) * 100); nr = int(t.get("negative_rate", 0) * 100)
        neu = max(0, 100 - pr - nr)
        total_entries += ec; total_signals += sc; total_critical += cc
        if h == "green": healthy += 1
        act = t.get("latest_activity", "")[:16] or t.get("updated_at", "")[:16]
        cards += f'''<a class="topic-card" href="/topic/{t['topic_id']}" style="border-left-color:{color}">
          <div class="main">
            <div class="name">{t['topic']}</div>
            <div class="meta">条目 <b>{ec}</b> · 信号 <b>{sc}</b> · 更新 {act}</div>
            <div class="sentbar"><span class="pos" style="width:{pr}%"></span><span class="neg" style="width:{nr}%"></span><span class="neu" style="width:{neu}%"></span></div>
            <div class="foot">
              <span class="mono-mini"><span>严重 <b style="color:{'var(--neg)' if cc else 'var(--dim)'}">{cc}</b></span><span>高 <b style="color:{'var(--warn)' if hc else 'var(--dim)'}">{hc}</b></span></span>
              <span class="report-link">查看深度报告 →</span>
            </div>
          </div>
          <div class="side">
            <span class="health-chip {h}">{chip}</span>
            <div class="rates">正面 {pr}%<br>负面 {nr}%</div>
          </div>
        </a>'''

    return render_template_string(INDEX_HTML, count=len(overview), total_entries=total_entries,
                                  total_signals=total_signals, total_critical=total_critical,
                                  healthy=healthy, cards=cards,
                                  rendered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


TREND_LABELS = {
    "rapidly_improving": "🚀 急转正面", "rapidly_declining": "🔻 急转负面",
    "improving": "📈 改善", "declining": "📉 恶化", "growing": "📊 增长",
    "stable": "➡️ 稳定",
}


def build_delta_strip(delta, anomalies):
    """实时监测条：与上次采集的对比 + 异常数。数据不存在时返回空串。"""
    parts = []
    if delta and delta.get("has_previous"):
        ed = delta.get("entry_delta", 0)
        sd = delta.get("signal_delta", 0)
        ss = delta.get("sentiment_shift", 0)
        sign = lambda v: (f"+{v}" if v > 0 else str(v))
        parts.append('<span class="lbl">实时对比</span>')
        parts.append(f'<span>数据 <b style="color:{("var(--pos)" if ed > 0 else "var(--neg)" if ed < 0 else "var(--text2)")}">{sign(ed)}</b></span>')
        parts.append(f'<span>信号 <b style="color:{("var(--neg)" if sd > 0 else "var(--pos)" if sd < 0 else "var(--text2)")}">{sign(sd)}</b></span>')
        parts.append(f'<span>情感 <b style="color:{("var(--pos)" if ss > 0.05 else "var(--neg)" if ss < -0.05 else "var(--text2)")}">{"+" if ss > 0 else ""}{ss * 100:.0f}%</b></span>')
        if delta.get("trend"):
            parts.append(f'<span>趋势 <b>{TREND_LABELS.get(delta["trend"], delta["trend"])}</b></span>')
        if delta.get("new_keywords"):
            parts.append(f'<span>新涌现 <b style="color:var(--accent)">{delta["new_keywords"][:5]|join("、")}</b></span>')
    if anomalies:
        parts.append(f'<span><b style="color:var(--neg)">异常 {len(anomalies)}</b></span>')
    return '<div class="dash-strip">' + "".join(parts) + "</div>" if parts else ""


@app.route("/topic/<topic_id>")
def show_topic(topic_id):
    try:
        a, body = get_topic_report(topic_id)
    except FileNotFoundError:
        return f"<h1>未找到</h1>", 404

    # 实时监测：快照对比 + 异常检测
    snapshot_topic(topic_id)
    delta = get_delta(topic_id)
    anomalies = detect_anomalies(topic_id)
    delta_html = build_delta_strip(delta, anomalies)

    return render_template_string(TOPIC_HTML,
        topic_id=topic_id, topic=a["meta"]["topic"], scenario=a["scenario"],
        report_css=REPORT_CSS, report_header=_report_header(a),
        report_body=body, footer_html=_report_footer(a),
        delta_html=delta_html,
        rendered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@app.route("/api/topic/<topic_id>")
def api_topic(topic_id):
    try: return jsonify(get_topic_summary(topic_id))
    except FileNotFoundError: return jsonify({"error":"not found"}),404

@app.route("/api/topics")
def api_topics(): return jsonify(list_topics())


@app.route("/api/export/<topic_id>")
def export_pdf(topic_id):
    """Generate and return PDF report."""
    try:
        from report_generator import generate_pdf
        path = generate_pdf(topic_id)
        return jsonify({"status": "success", "path": path})
    except ImportError:
        return jsonify({"status": "error", "message": "reportlab not installed. Run: pip install reportlab"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/topic/<topic_id>/report")
def show_report(topic_id):
    """深度报告已整合进 topic 详情页，旧地址跳转。"""
    return redirect(f"/topic/{topic_id}")


@app.route("/api/report/<topic_id>", methods=["GET", "POST"])
def api_generate_report(topic_id):
    """Regenerate the HTML report for a topic."""
    try:
        from report_generator import generate_html_report
        topic_dir = os.path.join(DATA_DIR, topic_id)
        report_path = os.path.join(topic_dir, "report.html")
        path = generate_html_report(topic_id, report_path)
        return jsonify({"status": "success", "path": path,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except FileNotFoundError:
        return jsonify({"error": "topic not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/collect/<topic_id>")
def trigger_collect(topic_id):
    """Trigger data collection for a topic."""
    try:
        from auto_collect import run_collection
        result = run_collection(topic_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/collect")
def trigger_collect_all():
    """Trigger data collection for all active topics."""
    try:
        from auto_collect import run_all_topics
        results = run_all_topics()
        return jsonify({"status": "success", "count": len(results), "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
