# 数据调研 Skill (Data Research)

全天候数据采集 → 增量存储 → 8维度分析 → 问题发现 → 本地看板自动刷新渲染。

## 核心能力

### 1. 问题发现导向
从社交网络和网络信息中发现问题，不是展示数据。每个发现都回答：发现了什么 → 意味着什么 → 建议怎么做。

### 2. 4种场景自适应
| 场景 | 触发词 | 分析链路 |
|------|--------|----------|
| **投资研究** | 股票/投资/估值/财报 | 上市公司→大单品→评论→意图→市场认知→投资判断 |
| **产品发布** | 发布/新品/上市/交付 | 产品→主内容+评论→意图→市场认知→传播策略 |
| **行业调研** | 行业/赛道/市场/趋势 | 行业→市场数据→竞争格局→趋势判断→机会识别 |
| **舆情监控** | 舆情/口碑/评价/争议 | 品牌→情感追踪→危机预警→叙事分析→应对建议 |

### 3. 时间对比引擎
每次采集自动与上次对比，计算 delta：
- 数据量变化（新增/减少）
- 情感变化（正面率升降）
- 新关键词涌现/消失
- 趋势判断（急转正面/急转负面/改善/恶化/增长/稳定）

### 4. 异常检测
自动识别三类异常：
- **情感急转**：正面→负面突变（阈值 ±0.3）
- **量级异常**：数据量突然翻倍
- **关键词涌现**：新词出现频率 > 阈值

### 5. 多话题总览
首页显示所有调研话题的健康状态（绿/黄/红灯），点击进入单话题详情。

### 6. 深度评论区分析
每个数据源（小红书/抖音/百度新闻）都必须：
- 采集评论区数据
- 生成评论区总结（高频词/情绪分布/代表性评论）
- 全屏弹窗查看完整分析报告

## 安装

```bash
# Codex
cp -r myou-data-research ~/.codex/skills/data-research

# MiMoCode
cp -r myou-data-research ~/.local/share/mimocode/skills/data-research

# Claude Code
cp -r myou-data-research ~/.claude/skills/data-research
```

### 依赖
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

### 看板功能

- 暗色全屏监控大屏，上下自由滚动
- 关键发现卡片（严重/高风险/中等/洞察）
- 态势判断 + Delta 对比（数据变化/信号变化/情感变化/趋势）
- 异常检测告警（情感急转/量级异常/关键词涌现）
- 风险预警（三级计数 + 详情 + 行动建议）
- 各平台评论区洞察（摘要 + 全屏弹窗完整分析）
- 信号与建议
- D3.js 数据驱动图表（时间趋势柱状图）
- 演变时间线
- 数据条目表格（平台发布时间排序）
- 关于弹窗（公众号二维码 + X @iGaves）
- ESC / × 关闭弹窗
- 30分钟自动轮询刷新

## 目录结构

```
myou-data-research/
├── SKILL.md                    # 主指令文件（561行）
├── README.md                   # 本文件
├── agents/
│   └── openai.yaml             # UI 元数据
├── scripts/
│   ├── dashboard_server.py     # Flask 看板服务
│   └── data_store.py           # JSON 数据存储（含 Delta/异常检测/多话题总览）
├── assets/
│   ├── d3.min.js               # D3.js 可视化库
│   └── qrcode.png              # 公众号二维码
└── references/
    └── data_sources.md         # 数据源参考（中文标签映射/评论区模板/信号框架）
```

## 数据目录

数据存储在 `~/.local/share/data-research/` 目录下：

```
~/.local/share/data-research/
└── {topic-id}/
    ├── meta.json       # 话题元数据
    ├── entries.json    # 数据条目
    ├── evolution.json  # 演变节点
    ├── signals.json    # 信号洞察
    └── snapshots.json  # 快照（用于 Delta 对比）
```

## API

| 端点 | 说明 |
|------|------|
| `GET /` | 多话题总览（健康状态） |
| `GET /topic/{id}` | 单话题详情看板 |
| `GET /api/topic/{id}` | JSON API |
| `GET /api/topics` | 所有话题列表 |
| `GET /assets/{file}` | 静态资源 |

## License

MIT
