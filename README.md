# 数据调研 Skill (Data Research)

全天候数据采集 → 增量存储 → 8维度分析 → 问题发现 → 看板自动刷新渲染。

## 特性

- **问题发现导向**：从社交网络和网络信息中发现问题，不是展示数据
- **4种场景预设**：舆情监控、行业调研、产品发布、投资研究，每种场景有独立的分析链路
- **深度分析**：核心发现包含商业模式、增长驱动、估值逻辑、竞争格局等深度分析
- **多平台采集**：支持小红书、抖音、微博、雪球等平台的数据采集
- **自动刷新看板**：暗色全屏监控大屏，30分钟自动轮询刷新
- **中文标签**：所有标签使用中文显示

## 安装

### Codex / MiMoCode / Claude Code

将 `myou-data-research` 目录复制到对应 skill 目录：

```bash
# Codex
cp -r myou-data-research ~/.codex/skills/data-research

# MiMoCode
cp -r myou-data-research ~/.local/share/mimocode/skills/data-research

# Claude Code
cp -r myou-data-research ~/.claude/skills/data-research
```

### 依赖安装

```bash
pip install flask
```

## 使用

### 触发词

- "调研XX"
- "帮我看看XX的舆情"
- "追踪XX事件变化"
- "XX话题发酵过程"
- "数据调研"
- "舆情监控"

### 场景自动匹配

| 场景 | 触发词 | 分析链路 |
|------|--------|----------|
| 投资研究 | 股票/投资/估值/财报 | 上市公司→大单品→评论→意图→市场认知→投资判断 |
| 产品发布 | 发布/新品/上市/交付 | 产品→主内容+评论→意图→市场认知→传播策略 |
| 行业调研 | 行业/赛道/市场/趋势 | 行业→市场数据→竞争格局→趋势判断→机会识别 |
| 舆情监控 | 舆情/口碑/评价/争议 | 品牌→情感追踪→危机预警→叙事分析→应对建议 |

## 看板功能

- 暗色全屏监控大屏，上下自由滚动
- 关键发现卡片（严重/高风险/中等/洞察）
- 态势判断（阶段、情感流向、新关键词、关键变化）
- 风险预警（严重/高风险/中等计数 + 详情 + 行动建议）
- 各平台评论区洞察（摘要 + 全屏弹窗完整分析 + 情绪分析）
- 信号与建议
- D3.js 数据驱动图表（来源分布饼图、时间趋势柱状图）
- 演变时间线
- 数据条目表格（平台发布时间排序）
- 关于弹窗（公众号二维码 + X @iGaves）
- ESC / × 关闭弹窗
- 30分钟自动轮询刷新

## 目录结构

```
myou-data-research/
├── SKILL.md                    # 主指令文件
├── README.md                   # 本文件
├── agents/
│   └── openai.yaml             # UI 元数据
├── scripts/
│   ├── dashboard_server.py     # Flask 看板服务
│   └── data_store.py           # JSON 数据存储
├── assets/
│   ├── d3.min.js               # D3.js 可视化库
│   └── qrcode.png              # 公众号二维码
└── references/
    └── data_sources.md         # 数据源参考
```

## 数据目录

数据存储在 `~/.local/share/data-research/` 目录下：

```
~/.local/share/data-research/
└── {topic-id}/
    ├── meta.json      # 话题元数据
    ├── entries.json   # 数据条目
    ├── evolution.json # 演变节点
    └── signals.json   # 信号洞察
```

## License

MIT
